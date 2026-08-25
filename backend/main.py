#!/usr/bin/env python3
"""Cookie Vault - 自托管多平台 Cookie 保险库
保存/管理各平台账号登录态，扫码登录/续期，按需导出 cookies。
"""
import json
import os
import sqlite3
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "vault.db"
QR_DIR = DATA_DIR / "qr"
STATIC_DIR = Path(os.environ.get("STATIC_DIR", "/app/static"))
PANEL_PASSWORD = os.environ.get("PANEL_PASSWORD", "")
SCAN_TIMEOUT = int(os.environ.get("SCAN_TIMEOUT", "180"))  # 秒

QR_DIR.mkdir(parents=True, exist_ok=True)

# ---------------- 内置平台预设 ----------------
BUILTIN_PLATFORMS = [
    {
        "name": "哔哩哔哩",
        "domain": "bilibili.com",
        "login_url": "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
        "scan_mode": "bilibili_api",
        "check_cookies": ["SESSDATA", "DedeUserID"],
        "icon": "📺",
    },
    {
        "name": "小红书",
        "domain": "xiaohongshu.com",
        "login_url": "https://www.xiaohongshu.com",
        "scan_mode": "playwright",
        "check_cookies": ["web_session", "customerClientId"],
        "icon": "📕",
    },
    {
        "name": "抖音",
        "domain": "douyin.com",
        "login_url": "https://www.douyin.com",
        "scan_mode": "playwright",
        "check_cookies": ["sessionid", "sessionid_ss"],
        "icon": "🎵",
    },
    {
        "name": "百度",
        "domain": "baidu.com",
        "login_url": "https://passport.baidu.com/v2/?login",
        "scan_mode": "playwright",
        "check_cookies": ["BDUSS", "BDUSS_BFESS"],
        "icon": "🔍",
    },
]

# ---------------- 数据库 ----------------
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db():
    with db() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS platforms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                domain TEXT NOT NULL,
                login_url TEXT DEFAULT '',
                scan_mode TEXT DEFAULT 'playwright',
                check_cookies TEXT DEFAULT '[]',
                icon TEXT DEFAULT '🌐',
                created_at REAL
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform_id INTEGER NOT NULL,
                name TEXT DEFAULT '',
                cookies TEXT DEFAULT '[]',
                status TEXT DEFAULT 'active',
                expires_at REAL DEFAULT 0,
                added_at REAL,
                last_refresh_at REAL
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS scan_sessions (
                id TEXT PRIMARY KEY,
                platform_id INTEGER,
                account_id INTEGER,
                mode TEXT,
                status TEXT DEFAULT 'starting',
                message TEXT DEFAULT '',
                qr_path TEXT DEFAULT '',
                created_at REAL,
                updated_at REAL
            )"""
        )
        # 内置平台（不存在才插入）
        n = con.execute("SELECT COUNT(*) c FROM platforms").fetchone()["c"]
        if n == 0:
            for p in BUILTIN_PLATFORMS:
                con.execute(
                    "INSERT INTO platforms (name,domain,login_url,scan_mode,check_cookies,icon,created_at) VALUES (?,?,?,?,?,?,?)",
                    (p["name"], p["domain"], p["login_url"], p["scan_mode"],
                     json.dumps(p["check_cookies"]), p["icon"], time.time()),
                )


def now():
    return time.time()


def cookie_expires(cookies: list) -> float:
    """取所有 cookie 中最早的过期时间；无过期时间的（session cookie）视为永不过期"""
    exps = [c.get("expires", 0) for c in cookies if c.get("expires")]
    return min(exps) if exps else 0


def account_status(expires_at: float) -> str:
    if expires_at <= 0:
        return "active"  # 永不过期
    if expires_at < now():
        return "expired"
    if expires_at - now() < 7 * 86400:
        return "expiring"
    return "active"


# ---------------- 认证 ----------------
def auth_ok(authorization: str = "") -> bool:
    if not PANEL_PASSWORD:
        return False  # 未配置 PANEL_PASSWORD 时拒绝一切访问，防止裸奔
    token = authorization.replace("Bearer ", "").strip()
    # 简单 token：密码的 sha1（登录接口发放）
    import hashlib
    return token == hashlib.sha1(PANEL_PASSWORD.encode()).hexdigest()


def require_auth(authorization: str = Header("")):
    if not auth_ok(authorization):
        raise HTTPException(status_code=401, detail="未授权，请先登录")


# ---------------- FastAPI ----------------
app = FastAPI(title="Cookie Vault", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/health")
def health():
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}


# ---------- 认证 ----------
class LoginReq(BaseModel):
    password: str


@app.post("/api/login")
def login(req: LoginReq):
    import hashlib
    if not PANEL_PASSWORD:
        raise HTTPException(status_code=503, detail="服务未配置登录密码，请设置 PANEL_PASSWORD 环境变量后重启")
    if req.password == PANEL_PASSWORD:
        return {"token": hashlib.sha1(PANEL_PASSWORD.encode()).hexdigest()}
    raise HTTPException(status_code=401, detail="密码错误")


# ---------- 平台 ----------
class PlatformIn(BaseModel):
    name: str
    domain: str
    login_url: str = ""
    scan_mode: str = "playwright"
    check_cookies: list = []
    icon: str = "🌐"


@app.get("/api/platforms")
def list_platforms(authorization: str = Header("")):
    require_auth(authorization)
    out = []
    with db() as con:
        rows = con.execute("SELECT * FROM platforms ORDER BY id").fetchall()
        for r in rows:
            accts = con.execute(
                "SELECT id,name,status,expires_at,last_refresh_at FROM accounts WHERE platform_id=?",
                (r["id"],),
            ).fetchall()
            acct_list = []
            for a in accts:
                st = account_status(a["expires_at"])
                acct_list.append({
                    "id": a["id"], "name": a["name"], "status": st,
                    "expires_at": a["expires_at"],
                    "last_refresh_at": a["last_refresh_at"],
                    "platform_id": r["id"],
                })
            out.append({
                "id": r["id"], "name": r["name"], "domain": r["domain"],
                "icon": r["icon"], "scan_mode": r["scan_mode"],
                "accounts": acct_list,
            })
    return {"platforms": out}


@app.post("/api/platforms")
def add_platform(p: PlatformIn, authorization: str = Header("")):
    require_auth(authorization)
    with db() as con:
        cur = con.execute(
            "INSERT INTO platforms (name,domain,login_url,scan_mode,check_cookies,icon,created_at) VALUES (?,?,?,?,?,?,?)",
            (p.name, p.domain, p.login_url, p.scan_mode,
             json.dumps(p.check_cookies), p.icon, now()),
        )
        return {"id": cur.lastrowid}


@app.delete("/api/platforms/{pid}")
def del_platform(pid: int, authorization: str = Header("")):
    require_auth(authorization)
    with db() as con:
        con.execute("DELETE FROM accounts WHERE platform_id=?", (pid,))
        con.execute("DELETE FROM platforms WHERE id=?", (pid,))
    return {"ok": True}


# ---------- 账号 ----------
@app.get("/api/accounts/{aid}/cookies")
def get_cookies(aid: int, fmt: str = "txt", authorization: str = Header("")):
    """导出 cookies：fmt=txt(Netscape, yt-dlp 用) | json | header"""
    require_auth(authorization)
    with db() as con:
        row = con.execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="账号不存在")
    cookies = json.loads(row["cookies"] or "[]")

    if fmt == "json":
        return JSONResponse(cookies)
    if fmt == "header":
        header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("value"))
        return JSONResponse({"cookies": header})
    # txt (Netscape)
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        dom = c.get("domain", "")
        if dom.startswith("."):
            dom = dom[1:]
        include_sub = "TRUE" if dom.startswith(".") else "FALSE"
        if c.get("domain", "").startswith("."):
            include_sub = "TRUE"
        exp = int(c.get("expires", 0)) or 0
        secure = "TRUE" if c.get("secure") else "FALSE"
        lines.append(f"{dom}\t{include_sub}\t{c.get('path','/')}\t{secure}\t{exp}\t{c.get('name','')}\t{c.get('value','')}")
    return JSONResponse({"cookies": "\n".join(lines)})


@app.delete("/api/accounts/{aid}")
def del_account(aid: int, authorization: str = Header("")):
    require_auth(authorization)
    with db() as con:
        con.execute("DELETE FROM accounts WHERE id=?", (aid,))
    return {"ok": True}


@app.post("/api/accounts/{aid}/rename")
def rename_account(aid: int, body: dict, authorization: str = Header("")):
    require_auth(authorization)
    name = (body.get("name") or "").strip()
    with db() as con:
        con.execute("UPDATE accounts SET name=? WHERE id=?", (name, aid))
    return {"ok": True}


# ---------- 扫码会话 ----------
class ScanStart(BaseModel):
    platform_id: int
    account_id: int | None = None  # None=添加新账号；有值=续期


@app.post("/api/scan/start")
def scan_start(req: ScanStart, authorization: str = Header("")):
    require_auth(authorization)
    sid = uuid.uuid4().hex[:12]
    with db() as con:
        p = con.execute("SELECT * FROM platforms WHERE id=?", (req.platform_id,)).fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="平台不存在")
    with db() as con:
        con.execute(
            "INSERT INTO scan_sessions (id,platform_id,account_id,mode,status,message,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (sid, req.platform_id, req.account_id, p["scan_mode"], "starting", "", now(), now()),
        )
    # 后台线程执行扫码
    t = threading.Thread(target=run_scan, args=(sid, dict(p), req.account_id), daemon=True)
    t.start()
    return {"session_id": sid}


@app.get("/api/scan/{sid}/status")
def scan_status(sid: str, authorization: str = Header("")):
    require_auth(authorization)
    with db() as con:
        row = con.execute("SELECT * FROM scan_sessions WHERE id=?", (sid,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "status": row["status"],
        "message": row["message"],
        "qr_url": f"/api/scan/{sid}/qr.png" if row["qr_path"] else None,
        "account_id": row["account_id"],
    }


@app.get("/api/scan/{sid}/qr.png")
def scan_qr(sid: str):
    with db() as con:
        row = con.execute("SELECT qr_path FROM scan_sessions WHERE id=?", (sid,)).fetchone()
    if not row or not row["qr_path"] or not Path(row["qr_path"]).exists():
        raise HTTPException(status_code=404, detail="二维码不存在")
    return FileResponse(row["qr_path"], media_type="image/png")


@app.post("/api/scan/{sid}/cancel")
def scan_cancel(sid: str, authorization: str = Header("")):
    require_auth(authorization)
    with db() as con:
        con.execute("UPDATE scan_sessions SET status='cancelled', message='已取消' WHERE id=?", (sid,))
    return {"ok": True}


# ---------- 扫码执行 ----------
def set_session(sid: str, status: str, message: str = "", qr_path: str = ""):
    with db() as con:
        con.execute(
            "UPDATE scan_sessions SET status=?, message=?, qr_path=?, updated_at=? WHERE id=?",
            (status, message, qr_path, now(), sid),
        )


def save_account_cookies(platform: dict, account_id, cookies: list, name: str = ""):
    """入库：cookies + 过期时间 + 状态；返回账号 id"""
    expires_at = cookie_expires(cookies)
    st = account_status(expires_at)
    with db() as con:
        if account_id:
            con.execute(
                "UPDATE accounts SET cookies=?, status=?, expires_at=?, last_refresh_at=?, name=COALESCE(NULLIF(?,''),name) WHERE id=?",
                (json.dumps(cookies), st, expires_at, now(), name, account_id),
            )
            return account_id
        cur = con.execute(
            "INSERT INTO accounts (platform_id,name,cookies,status,expires_at,added_at,last_refresh_at) VALUES (?,?,?,?,?,?,?)",
            (platform["id"], name, json.dumps(cookies), st, expires_at, now(), now()),
        )
        return cur.lastrowid


def run_scan(sid: str, platform: dict, account_id):
    mode = platform["scan_mode"]
    try:
        if mode == "bilibili_api":
            do_bilibili_scan(sid, platform, account_id)
        elif mode == "playwright":
            do_playwright_scan(sid, platform, account_id)
        else:
            set_session(sid, "failed", f"不支持的扫码模式: {mode}")
    except Exception as e:
        traceback.print_exc()
        set_session(sid, "failed", f"扫码异常: {e}")


# ---- B站官方 API 扫码 ----
def do_bilibili_scan(sid: str, platform: dict, account_id):
    import requests
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
    })
    # 1. 生成二维码
    r = s.get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate", timeout=15)
    data = r.json()["data"]
    qr_url, qrcode_key = data["url"], data["qrcode_key"]
    # 2. 生成二维码图片
    import qrcode as qrlib
    img = qrlib.make(qr_url)
    qr_path = QR_DIR / f"{sid}.png"
    img.save(qr_path)
    set_session(sid, "waiting", "请使用 B站 App 扫码", str(qr_path))
    # 3. 轮询
    deadline = time.time() + SCAN_TIMEOUT
    while time.time() < deadline:
        time.sleep(2)
        r = s.get(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
            params={"qrcode_key": qrcode_key}, timeout=15,
        )
        j = r.json()
        inner = j.get("data") or {}
        code = inner.get("code", j.get("code"))  # 新版接口真实状态在 data.code
        if code == 0:
            # 登录成功！访问跳转 URL 拿全量 cookie
            jump = inner.get("url") or ""
            if jump:
                s.get(jump, timeout=15)
            cookies = [
                {"name": c.name, "value": c.value, "domain": c.domain,
                 "path": c.path, "expires": c.expires or 0, "secure": c.secure}
                for c in s.cookies
            ]
            # 取昵称
            name = ""
            try:
                nav = s.get("https://api.bilibili.com/x/web-interface/nav", timeout=15).json()
                name = nav.get("data", {}).get("uname", "")
            except Exception:
                pass
            aid = save_account_cookies(platform, account_id, cookies, name)
            set_session(sid, "success", f"登录成功：{name or '已入库'}", str(qr_path))
            return
        elif code == 86038:
            set_session(sid, "expired", "二维码已过期，请重新获取")
            return
        elif code == 86090:
            set_session(sid, "scanned", "已扫码，请在手机上确认", str(qr_path))
        # 86101 = 未扫码，继续等
    set_session(sid, "expired", "等待超时，请重新获取二维码")


# ---- Playwright 通用扫码 ----
def do_playwright_scan(sid: str, platform: dict, account_id):
    from playwright.sync_api import sync_playwright

    check_cookies = json.loads(platform.get("check_cookies") or "[]")
    login_url = platform.get("login_url") or f"https://{platform['domain']}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            locale="zh-CN",
        )
        page = ctx.new_page()
        page.set_default_timeout(30000)
        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass
        time.sleep(3)
        # 截图：优先截二维码元素；失败则全页
        qr_path = QR_DIR / f"{sid}.png"
        shot_ok = False
        for sel in ["img[class*='qrcode']", ".qrcode img", "canvas", ".login-qrcode", "img[src*='qr']"]:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible():
                    el.screenshot(path=str(qr_path))
                    shot_ok = True
                    break
            except Exception:
                continue
        if not shot_ok:
            page.screenshot(path=str(qr_path), full_page=False)
        set_session(sid, "waiting", "请使用 App 扫码", str(qr_path))

        # 轮询登录态
        deadline = time.time() + SCAN_TIMEOUT
        while time.time() < deadline:
            time.sleep(3)
            try:
                cookies = ctx.cookies()
                names = {c["name"] for c in cookies}
                # 关键 cookie 出现即视为登录成功
                hit = [ck for ck in check_cookies if ck in names]
                if hit or any(c["name"] in ("sessionid", "web_session", "BDUSS", "SESSDATA") for c in cookies):
                    # 再等等页面稳定，多取一次
                    time.sleep(2)
                    cookies = ctx.cookies()
                    out = [
                        {"name": c["name"], "value": c["value"], "domain": c["domain"],
                         "path": c["path"], "expires": c.get("expires", -1) or 0,
                         "secure": c.get("secure", False)}
                        for c in cookies
                    ]
                    aid = save_account_cookies(platform, account_id, out)
                    set_session(sid, "success", f"登录成功 (命中 {','.join(hit)})", str(qr_path))
                    return
                # 页面跳转到主页也算（兜底）
                if "passport" not in page.url and page.url != login_url and page.url.strip():
                    time.sleep(2)
                    cookies = ctx.cookies()
                    out = [
                        {"name": c["name"], "value": c["value"], "domain": c["domain"],
                         "path": c["path"], "expires": c.get("expires", -1) or 0,
                         "secure": c.get("secure", False)}
                        for c in cookies
                    ]
                    aid = save_account_cookies(platform, account_id, out)
                    set_session(sid, "success", "登录成功（页面跳转）", str(qr_path))
                    return
            except Exception:
                continue
        set_session(sid, "expired", "等待超时，请重新获取二维码", str(qr_path))
        ctx.close()
        browser.close()


# ---------- 静态前端 ----------
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
