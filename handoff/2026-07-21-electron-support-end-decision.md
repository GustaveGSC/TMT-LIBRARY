# Electron 停止支持决策

日期：2026-07-21
决策人：用户
状态：已确认

## 决策

正式停止支持现有 Electron 客户端。

Cookie/Token 改造只需保证 Web 端和本地 Web 开发链路可用。后端切换后不再接受 `Authorization: Bearer`，不为现有 Electron 保留双轨兼容逻辑；已安装的 Electron 客户端届时无法继续登录或调用生产 API，这是本次决策明确接受的结果。

## 对实施范围的影响

- 解除 `2026-07-21-codex-token-cookie-design-review.md` 中的唯一上线阻断项。
- 后端仅实现 httpOnly Cookie 会话，不增加 User-Agent、Origin 或其他“Electron 特例”。
- CORS 精确白名单不再为 `file://` / `null` Electron 来源保留兼容项；是否立即从默认配置删除旧来源，由后端实施时结合现有生产 `.env` 一并核对。
- 前端 Cookie 改造只验收 Web 生产环境和 Vite 同源代理开发环境，不制作或发布新 Electron 安装包。
- 项目文档、下载入口和发布流程中仍存在的 Electron 支持说明，应由 Claude Code 在前端实施批次统一清理或标记为历史内容。

## 实施前仍需纳入设计的后端要求

- CSRF token 与签名 JWT 会话绑定，而非只比较 Cookie/Header。
- 覆盖 `make_blueprint_guard`、`require_auth`、account 自定义守卫和 version 自定义守卫。
- 对写请求统一校验 CSRF，明确豁免公开认证入口并放行 `OPTIONS`。
- 登录/游客登录设置 Cookie；主动登出、401、本人改密成功后统一清 Cookie。
- Cookie 参数采用已评审命名：`tmt_session`、`tmt_csrf`、`X-CSRF-Token`、host-only、`Path=/`、`SameSite=Strict`、7 天；生产 Secure，明确的开发/测试环境非 Secure。

## 下一步

联合设计现在可以进入实施阶段。Codex 和 Claude Code 必须使用各自独立 worktree/分支；后端先完成并通过自动化测试，双方核对接口契约后再按直接切换方案连续部署后端和完整 Web 构建。
