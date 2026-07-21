# 前端实施状态 · Cookie/CSRF 改造已完成，等待后端联调

日期：2026-07-21
按 [2026-07-21-token-cookie-joint-design.md](2026-07-21-token-cookie-joint-design.md) 定稿版实施完成，**已提交但未部署**。

## 已完成

- `src/api/http.js`：`withCredentials: true`，移除 Authorization header 读写，写请求（POST/PUT/DELETE/PATCH）从 `tmt_csrf` Cookie 读值加到 `X-CSRF-Token` 请求头，401 处理只清本地展示状态不再主动调登出接口
- `src/views/loginViews/page-login.vue`：登录成功不再存 token
- `src/components/user/UserSettingsDrawer.vue`：主动登出先调 `POST /api/account/logout`（**这个接口名是我按设计文档假设的，需要和 Codex 实际实现的登出接口路径核对一致**）
- `src/routers/index.js`：本地 8 小时不活跃超时的 `clearSession()` 移除 tmt_token 引用
- `.claude/claude.md`：标记 Electron 暂停，修正 `getBaseURL()` 注释里的过期 IP 地址

## 未做（不在这批范围内，按决策文档）

- 没有改动 `electron/` 目录本身的代码
- 没有制作/测试新的 Electron 安装包

## ⚠️ 部署阻塞：等 Codex 后端就绪

这批改动**不能单独部署**——部署后所有请求都不带 Authorization header，如果后端还没切到 Cookie 校验，会导致所有用户完全无法通过身份校验（比现在更彻底地"全部掉线"，且掉线后新登录也过不了，因为后端仍期待 header）。

按直接切换方案：**后端先部署，验证 `/health`+`/ready`+登录接口正常后，立刻紧跟着部署这批前端**，把不兼容窗口压缩到几分钟内。

## 需要 Codex 确认/对齐的接口细节

1. **登出接口的确切路径**：我在前端假设是 `POST /api/account/logout`，请核对实际实现是否一致，如果不一致告诉我改
2. **登录响应体结构**：确认改造后 `POST /api/account/login` 的响应体里确实不再包含 `token` 字段（前端现在直接 `JSON.stringify(res.data)` 存进 `localStorage.user`，如果后端还在 `data` 里塞 token，会连带把 token 明文存进 localStorage 的 `user` 字段，等于白改）
3. **CSRF Cookie 是否对所有子路径可读**：`tmt_csrf` 的 `Path=/` 设计文档里定了，确认实现和这个一致，否则前端 `document.cookie` 可能读不到

## 联调计划

后端实现完成、本地测试通过后，建议先在**只读方式核实一遍**（我这边可以配合，比如用浏览器开发者工具核对 `Set-Cookie` 头的具体属性），确认没问题再按上面的部署顺序上线。
