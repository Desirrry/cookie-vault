# 🛡️ Cookie Vault

> 自托管 · 多平台账号 Cookie 保险库 —— 扫码登录、自动续期、按需导出

Cookie Vault 是一个轻量级自托管工具,用来统一管理你在各平台的账号登录态(Cookie)。支持**扫码登录/续期**,到期前自动提醒,需要时一键导出 Cookie 给脚本或下载工具使用。

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-1.49+-45ba4b?logo=playwright&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)

---

## ✨ 功能特性

- 🔐 **自托管部署** — 数据完全掌握在自己手里,仅需 Docker 一条命令
- 📱 **扫码登录 / 续期** — 内置 B 站官方扫码 API 与 Playwright 通用扫码,过期账号随时刷新
- 🗂️ **多平台管理** — 内置哔哩哔哩 / 小红书 / 抖音 / 百度预设,也支持自定义平台
- ⏰ **到期状态跟踪** — 自动计算 Cookie 过期时间,标记 `active / expiring / expired` 状态
- 📤 **多格式导出** — Netscape 格式(yt-dlp 等直接用)、JSON、请求头格式
- 🌐 **Web 管理面板** — 无需安装客户端,浏览器打开即用
- 🔌 **REST API** — 所有能力均通过 API 暴露,方便二次开发与脚本调用

## 📸 界面预览

*(欢迎提交截图 PR)*

## 🚀 快速开始

### Docker Compose(推荐)

```bash
git clone https://github.com/<your-name>/cookie-vault.git
cd cookie-vault

# 设置登录密码
export PANEL_PASSWORD=your-strong-password

docker compose up -d --build
```

打开 `http://<服务器IP>:8101`,输入密码即可使用。

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PANEL_PASSWORD` | 无(必填) | 面板登录密码,未设置时服务拒绝所有访问 |
| `DATA_DIR` | `/data` | 数据目录(vault.db + 二维码缓存) |
| `SCAN_TIMEOUT` | `180` | 扫码等待超时时间(秒) |
| `STATIC_DIR` | `/app/static` | 前端静态文件目录 |

> ⚠️ **安全提示**:`PANEL_PASSWORD` 为必填项。未设置密码时,服务会拒绝登录(HTTP 503),防止无认证裸奔。

### 手动运行

```bash
pip install -r requirements.txt
playwright install chromium

export PANEL_PASSWORD=your-strong-password
uvicorn main:app --host 0.0.0.0 --port 8101
```

## 🎯 内置平台

| 平台 | 扫码方式 | 校验 Cookie |
|------|----------|-------------|
| 哔哩哔哩 | 官方扫码 API(`bilibili_api`) | `SESSDATA` / `DedeUserID` |
| 小红书 | Playwright | `web_session` / `customerClientId` |
| 抖音 | Playwright | `sessionid` / `sessionid_ss` |
| 百度 | Playwright | `BDUSS` / `BDUSS_BFESS` |

可在面板中添加自定义平台(域名、登录页、扫码模式、校验 Cookie 均可配置)。

## 📡 API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/login` | 登录,获取 Bearer Token |
| `GET/POST` | `/api/platforms` | 平台列表 / 新增平台 |
| `DELETE` | `/api/platforms/{pid}` | 删除平台 |
| `GET` | `/api/accounts/{aid}/cookies?fmt=txt\|json\|header` | 导出 Cookie |
| `DELETE` | `/api/accounts/{aid}` | 删除账号 |
| `POST` | `/api/accounts/{aid}/rename` | 重命名账号 |
| `POST` | `/api/scan/start` | 发起扫码登录/续期 |
| `GET` | `/api/scan/{sid}/status` | 扫码状态轮询 |
| `GET` | `/api/scan/{sid}/qr.png` | 获取二维码图片 |
| `POST` | `/api/scan/{sid}/cancel` | 取消扫码会话 |

认证方式:`Authorization: Bearer <token>`(token 由 `/api/login` 发放)

## 🛠️ 开发

```bash
# 后端
cd backend
pip install -r ../requirements.txt
uvicorn main:app --reload --port 8101

# 前端为纯静态页面,直接编辑 frontend/ 下文件
```

代码结构:

```
├── backend/main.py       # FastAPI 后端(单文件,约 500 行)
├── frontend/             # 纯 HTML/JS/CSS 前端,零依赖
├── Dockerfile            # 基于 Playwright 官方镜像
└── docker-compose.yml    # 一键部署
```

## 🤝 贡献

欢迎任何形式的贡献!无论是新平台预设、新扫码方式、UI 改进还是文档补充,请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

**值得关注的方向(Roadmap):**

- [ ] 更多平台预设(微博、知乎、Twitter/X 等)
- [ ] Cookie 到期推送通知(Webhook / Telegram / 邮件)
- [ ] 认证增强:随机 Session Token 替代静态 SHA1、登录限流
- [ ] 账号分组与标签
- [ ] 多用户支持
- [ ] 移动端适配

## 📄 许可证

[MIT](LICENSE)

---

*本项目仅供个人学习与合法用途使用,请遵守各平台服务条款。*
