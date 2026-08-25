/* Cookie Vault 前端逻辑 */
const $ = (s) => document.querySelector(s);
const API = "";

let token = localStorage.getItem("cv_token") || "";
let platforms = [];
let currentPlatformId = null;
let scanTimer = null;

const STATUS_MAP = {
  ok: ["正常", "ok"],
  expiring: ["即将过期", "warn"],
  expired: ["已过期", "bad"],
};

/* ---------- 工具 ---------- */
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add("hidden"), 2200);
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers["Authorization"] = "Bearer " + token;
  if (opts.body && typeof opts.body !== "string") {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(API + path, { ...opts, headers });
  if (res.status === 401) {
    showLogin();
    throw new Error("未授权");
  }
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (e) {}
    throw new Error(msg);
  }
  return res.json();
}

function fmtTime(ts) {
  if (!ts) return "永不过期";
  const d = new Date(ts * 1000);
  const now = Date.now();
  const diff = ts * 1000 - now;
  const days = Math.floor(diff / 86400000);
  const hm = `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  if (diff < 0) return `${hm} 已过期`;
  if (days > 0) return `${hm}（剩 ${days} 天）`;
  const hours = Math.floor(diff / 3600000);
  if (hours > 0) return `${hm}（剩 ${hours} 小时）`;
  return `${hm}（不足 1 小时）`;
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/* ---------- 登录 ---------- */
function showLogin() {
  $("#main-view").classList.add("hidden");
  $("#login-view").classList.remove("hidden");
}
function showMain() {
  $("#login-view").classList.add("hidden");
  $("#main-view").classList.remove("hidden");
}
$("#login-btn").addEventListener("click", async () => {
  const pw = $("#login-password").value;
  try {
    const r = await api("/api/login", { method: "POST", body: { password: pw } });
    token = r.token;
    localStorage.setItem("cv_token", token);
    $("#login-err").classList.add("hidden");
    showMain();
    await loadPlatforms();
  } catch (e) {
    $("#login-err").textContent = e.message;
    $("#login-err").classList.remove("hidden");
  }
});
$("#login-password").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("#login-btn").click();
});
$("#logout-btn").addEventListener("click", () => {
  token = "";
  localStorage.removeItem("cv_token");
  showLogin();
});

/* ---------- 平台 ---------- */
async function loadPlatforms() {
  const r = await api("/api/platforms");
  platforms = r.platforms;
  renderTabs();
  if (!currentPlatformId || !platforms.find((p) => p.id === currentPlatformId)) {
    currentPlatformId = platforms.length ? platforms[0].id : null;
  }
  renderAccounts();
}

function renderTabs() {
  const nav = $("#platform-tabs");
  nav.innerHTML = "";
  for (const p of platforms) {
    let worst = "ok";
    for (const a of p.accounts) {
      if (a.status === "expired") worst = "red";
      else if (a.status === "expiring" && worst === "ok") worst = "yellow";
    }
    const el = document.createElement("div");
    el.className = "tab" + (p.id === currentPlatformId ? " active" : "");
    el.innerHTML = `<span>${escapeHtml(p.icon)}</span><span>${escapeHtml(p.name)}</span>
      <span class="dot ${worst}"></span><span class="count">${p.accounts.length}</span>`;
    el.addEventListener("click", () => {
      currentPlatformId = p.id;
      renderTabs();
      renderAccounts();
    });
    nav.appendChild(el);
  }
}

/* ---------- 账号卡片 ---------- */
function renderAccounts() {
  const p = platforms.find((x) => x.id === currentPlatformId);
  const grid = $("#account-grid");
  const empty = $("#empty-hint");
  if (!p) {
    grid.innerHTML = "";
    $("#current-platform-name").textContent = "平台";
    empty.classList.remove("hidden");
    return;
  }
  $("#current-platform-name").textContent = `${p.icon} ${p.name}`;
  if (!p.accounts.length) {
    grid.innerHTML = "";
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");
  grid.innerHTML = "";
  for (const a of p.accounts) {
    const [label, cls] = STATUS_MAP[a.status] || ["未知", "ok"];
    const card = document.createElement("div");
    card.className = `acct-card ${a.status === "expired" ? "expired" : a.status === "expiring" ? "expiring" : ""}`;
    card.innerHTML = `
      <div class="acct-head">
        <div class="acct-avatar">${escapeHtml(p.icon)}</div>
        <div>
          <div class="acct-name">${escapeHtml(a.name || "未命名账号")}</div>
          <div class="acct-meta">${escapeHtml(p.name)} · 更新于 ${fmtTime(a.last_refresh_at)}</div>
        </div>
        <span class="badge ${cls}"><span class="dot"></span>${label}</span>
      </div>
      <div class="acct-actions">
        <button class="btn copy-btn" data-act="copy-txt">📄 txt</button>
        <button class="btn copy-btn" data-act="copy-json">{} json</button>
        <button class="btn copy-btn" data-act="copy-header">⇥ header</button>
        <button class="btn refresh-btn" data-act="refresh">🔄 续期</button>
        <button class="btn del-btn" data-act="del" title="删除账号">✕</button>
      </div>
      <div class="copy-hint">过期时间：${fmtTime(a.expires_at)}</div>`;
    card.querySelectorAll(".copy-btn").forEach((b) =>
      b.addEventListener("click", () => copyCookies(a.id, b.dataset.act.replace("copy-", ""))));
    card.querySelector('[data-act="refresh"]').addEventListener("click", () => startScan(p.id, a.id, `续期：${a.name || p.name}`));
    card.querySelector('[data-act="del"]').addEventListener("click", async () => {
      if (!confirm(`删除账号「${a.name || "未命名"}」？此操作不可恢复。`)) return;
      await api(`/api/accounts/${a.id}`, { method: "DELETE" });
      toast("已删除");
      await loadPlatforms();
    });
    grid.appendChild(card);
  }
}

/* ---------- 复制 ---------- */
async function copyCookies(aid, fmt) {
  try {
    const r = await api(`/api/accounts/${aid}/cookies?fmt=${fmt}`);
    const text = fmt === "json" ? JSON.stringify(r, null, 2) : r.cookies;
    await navigator.clipboard.writeText(text);
    toast(`已复制 ${fmt.toUpperCase()} 格式 cookies`);
  } catch (e) {
    toast("复制失败：" + e.message);
  }
}

/* ---------- 扫码 ---------- */
function startScan(platformId, accountId, title) {
  $("#scan-title").textContent = title || "扫码登录";
  $("#scan-qr").style.display = "none";
  $("#scan-status").textContent = "正在生成二维码…";
  $("#scan-status").className = "scan-status";
  $("#scan-modal").classList.remove("hidden");
  clearInterval(scanTimer);
  api("/api/scan/start", { method: "POST", body: { platform_id: platformId, account_id: accountId } })
    .then(({ session_id }) => {
      pollScan(session_id);
      scanTimer = setInterval(() => pollScan(session_id), 3000);
    })
    .catch((e) => {
      $("#scan-status").textContent = "启动失败：" + e.message;
      $("#scan-status").className = "scan-status failed";
    });
}

async function pollScan(sid) {
  try {
    const r = await api(`/api/scan/${sid}/status`);
    const st = $("#scan-status");
    const img = $("#scan-qr");
    if (r.qr_url) {
      img.src = `${API}${r.qr_url}?t=${Date.now()}`;
      img.style.display = "block";
    }
    const map = {
      starting: ["正在准备…", ""],
      waiting: ["等待扫码…", ""],
      scanned: ["✅ 已扫码，请在手机上确认", "scanned"],
      success: ["🎉 登录成功！cookies 已入库", "success"],
      expired: ["⏰ 二维码已过期，请关闭后重试", "expired"],
      failed: ["❌ " + (r.message || "扫码失败"), "failed"],
      cancelled: ["已取消", ""],
    };
    const [text, cls] = map[r.status] || [r.message || r.status, ""];
    st.textContent = text;
    st.className = "scan-status " + cls;
    if (r.status === "success") {
      clearInterval(scanTimer);
      $("#scan-hint").textContent = "可以关闭此窗口了";
      setTimeout(() => {
        $("#scan-modal").classList.add("hidden");
        $("#scan-hint").textContent = "请使用 App 扫描二维码";
      }, 1500);
      await loadPlatforms();
    } else if (["expired", "failed", "cancelled"].includes(r.status)) {
      clearInterval(scanTimer);
    }
  } catch (e) {
    clearInterval(scanTimer);
  }
}

$("#scan-close-btn").addEventListener("click", () => {
  clearInterval(scanTimer);
  $("#scan-modal").classList.add("hidden");
  $("#scan-hint").textContent = "请使用 App 扫描二维码";
});
$("#add-account-btn").addEventListener("click", () => {
  const p = platforms.find((x) => x.id === currentPlatformId);
  if (!p) return toast("请先添加平台");
  startScan(p.id, null, `添加账号：${p.name}`);
});

/* ---------- 添加平台 ---------- */
$("#add-platform-btn").addEventListener("click", () => {
  $("#platform-modal").classList.remove("hidden");
});
$("#pf-cancel").addEventListener("click", () => $("#platform-modal").classList.add("hidden"));
$("#pf-save").addEventListener("click", async () => {
  const body = {
    name: $("#pf-name").value.trim(),
    domain: $("#pf-domain").value.trim().replace(/^https?:\/\//, ""),
    login_url: $("#pf-domain").value.trim().startsWith("http")
      ? $("#pf-domain").value.trim()
      : "https://" + $("#pf-domain").value.trim(),
    scan_mode: $("#pf-mode").value,
    check_cookies: $("#pf-check").value.split(/[,，\s]+/).filter(Boolean),
    icon: $("#pf-icon").value.trim() || "🌐",
  };
  if (!body.name || !body.domain) return toast("名称和域名必填");
  try {
    await api("/api/platforms", { method: "POST", body });
    $("#platform-modal").classList.add("hidden");
    toast("平台已添加");
    await loadPlatforms();
  } catch (e) {
    toast("添加失败：" + e.message);
  }
});

/* ---------- 初始化 ---------- */
(async function init() {
  if (token) {
    try {
      await loadPlatforms();
      showMain();
      return;
    } catch (e) {}
  }
  showLogin();
})();
