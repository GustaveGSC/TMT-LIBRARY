# Codex → Claude Code：Cookie/CSRF 后端实施交接

日期：2026-07-21
分支：`codex/backend-cookie-csrf`

## 完成内容

- 会话读取从 `Authorization: Bearer` 直接切换为 httpOnly `tmt_session` Cookie，不保留 Electron/Bearer 兼容路径。
- 登录和游客登录下发：
  - `tmt_session`：HttpOnly、Path=/、SameSite=Strict
  - `tmt_csrf`：可由前端读取、Path=/、SameSite=Strict
  - 两者生产环境均为 Secure，Max-Age/Expires 与 JWT 的 7 天有效期一致。
- CSRF 使用与 JWT claim 绑定的 signed double-submit；写请求必须满足 Header、Cookie、签名 claim 三者一致，并使用常量时间比较。
- CSRF 统一覆盖 POST/PUT/PATCH/DELETE；登录、游客、注册公开入口明确豁免，OPTIONS 放行。
- `make_blueprint_guard`、`require_auth`、account 自定义守卫、version 自定义守卫全部切换到 Cookie。
- 同一请求缓存已验证用户，CSRF 和权限守卫共享结果；普通用户写请求仍只查询一次账号状态，没有增加重复数据库查询。
- 新增 `POST /api/account/logout`，幂等清理两个 Cookie；有效会话调用时必须通过 CSRF。
- 所有 401 响应统一清理两个 Cookie。
- 本人改密成功后立即清理当前 Cookie；管理员修改别人密码不清管理员会话。
- CORS 启用 credentials，拒绝 `CORS_ORIGINS=*`；默认开发来源为 localhost:5173/5174，不再包含 Electron file 来源。
- 修复实现过程中识别出的导入顺序风险：`auth.py` 必须在 `load_dotenv()` 后导入，确保生产 JWT_SECRET 不会读取默认值，并增加回归测试锁定顺序。
- 更新 `.claude/modules/api.md`。

## 与前端约定的三项确认

1. 登出路径：`POST /api/account/logout`，与前端一致。
2. 登录成功响应体：只含用户数据，不含 `token`。
3. `tmt_csrf`：`Path=/`，所有前端子路径均可读取。

## 自动化验证

- `python -m pytest backend/tests -q`：通过（93 tests）。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。

覆盖场景包括 Cookie-only/Bearer 拒绝、四类守卫无 Header 读取、CSRF 缺失/错误/跨会话混用/OPTIONS/公开入口、一次请求仅一次账号状态查询、Cookie 属性、登录失败不覆盖 Cookie、幂等登出、401 清 Cookie、本人/他人改密差异、生产与测试 Secure 差异、CORS 禁止通配符、dotenv 导入顺序。

## Claude 部署前需要补的前端小项

`src/components/user/UserSettingsDrawer.vue` 当前本人改密成功后只显示提示并留在当前页。后端现在会在该 200 响应中立即清 Cookie；前端应在成功提示后清理 `localStorage.user` / `login_time` 并跳转 `/login`，否则用户会停留到下一次请求触发 401 才跳转。

另：`.claude/modules/frontend-rdtools.md` 仍写着 Authorization Bearer，由 Claude 按目录所有权更新为 Cookie 会话说明。

## 部署与联调要求

- 无数据库迁移。
- 部署前只读核对生产：`APP_ENV=production`；`CORS_ORIGINS` 是精确来源列表且不含 `*`。不要输出任何密钥值。
- 按已确认的直接切换：后端文件同步并 reload，严格复查 worker 日志；确认 `/health`、`/ready` 后，立即部署完整 `dist-web/`，缩短不兼容窗口。
- 后端刚切换、旧前端尚未更新期间请求 401 属于预期，不应因此回滚为 Bearer 双轨。
- 联调必须通过 HTTPS 浏览器检查两条 Set-Cookie 属性、登录响应体无 token、读请求、至少一个写请求、本人改密重登录、主动登出和 401 清 Cookie。

本批未部署、未 push，未修改前端源码。
