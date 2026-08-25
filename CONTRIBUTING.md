# 贡献指南

感谢你愿意参与 Cookie Vault 的完善!🎉 无论是修 bug、加平台、写文档还是提建议,都非常欢迎。

## 🐛 报告问题

- 使用 [GitHub Issues](https://github.com/<your-name>/cookie-vault/issues) 提交
- 请包含:复现步骤、期望行为、实际行为、环境信息(OS / Docker 版本 / 日志片段)
- 涉及具体平台扫码失败时,请附上 `docker logs cookie-vault` 中的相关日志

## 🔧 提交代码

1. **Fork** 本仓库并创建新分支:`git checkout -b feature/xxx`
2. 遵循现有代码风格(保持简洁,后端单文件结构优先)
3. 提交前自测:
   ```bash
   # 后端语法与启动检查
   python -m py_compile backend/main.py
   ```
4. 提交 PR,描述清楚改动目的与验证方式

## 🎯 欢迎的贡献方向

- **新平台预设**:在 `backend/main.py` 的 `BUILTIN_PLATFORMS` 中追加(需给出扫码方式与校验 Cookie 名)
- **新扫码方式**:目前有 B 站官方 API(`bilibili_api`)与 Playwright 通用两种,欢迎补充其他平台的官方扫码接口
- **UI 改进**:前端是零依赖纯静态页面,直接改 `frontend/` 即可
- **文档与国际化**:README 英文版、使用教程等

## ⚠️ 注意事项

- 不要提交任何真实 Cookie 数据、密码、Token 或截图
- `data/` 目录(运行时数据库)已被 `.gitignore` 排除,请勿强制添加
- 涉及平台反爬策略的改动请谨慎,本项目仅用于个人合法用途
