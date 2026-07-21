# 部署记录 · Cookie/CSRF 会话改造上线（直接切换）

日期：2026-07-21

## 背景

Cookie/Token 改造从只读方案评审 → Codex 后端评审补漏 → 联合设计定稿 → Electron 停止支持决策解除阻断项 → 前端实施 → 后端实施，走完整个流程后本次上线。全程记录见 `handoff/2026-07-21-token-cookie-*.md` 系列文档。

## 后端审查结论

`codex/backend-cookie-csrf`（`8f594ee`）质量非常扎实，完整覆盖了联合设计定稿的全部要点：

- CSRF 是与 JWT 会话绑定的 signed double-submit（不是 naive 比较），`hmac.compare_digest` 三方比对（header/cookie/JWT claim）
- 四个鉴权入口全部替换：`make_blueprint_guard`、`require_auth`、account 自定义守卫、version 自定义守卫，都改成从 `tmt_session` Cookie 读取，且都正确处理了 `OPTIONS` 直接放行
- `get_request_user()` 用 `g._verified_session_user` 做单请求内缓存，避免 CSRF 校验和权限校验各查一次数据库
- 401 响应用 `app.after_request` 统一清 Cookie；登出接口清 Cookie；本人改密清 Cookie；管理员改别人密码不清自己的 Cookie——全部按设计文档实现
- CORS 加了 `supports_credentials=True` 且显式拒绝通配符 `*`，顺手把默认开发环境 CORS 白名单从 `5173` 改成正确的 `5173`+`5174`（之前发现的既有小 bug 一并修了）
- 测试覆盖极其全面：93 项全过，包括跨会话 CSRF 不能混用、单请求只查一次数据库（性能）、登录失败不覆盖已有 Cookie、还有一条专门的回归测试确认没有任何代码路径还在读 `Authorization` header

本地复跑 `python -m pytest`：93 passed。审查通过，合并（fast-forward 到 `8f594ee`）。

## 部署前 Claude 侧补充的两项（Codex 要求）

1. `UserSettingsDrawer.vue` 的本人改密成功回调：之前只提示"修改成功"，现在同步清本地 `user`/`login_time` 并跳转登录页，匹配后端"本人改密立即清会话 Cookie"的行为（`97512ff`）
2. `frontend-rdtools.md` 里过期的 `Authorization: Bearer` 描述改成实际的 httpOnly Cookie + `X-CSRF-Token` 机制

## 部署前检查

- 生产 `APP_ENV=production`（确认）
- 生产 `CORS_ORIGINS` 未设置，回落到代码默认值（不含通配符 `*`，且生产环境本身同源不受 CORS 限制，不影响）

## 部署顺序（按直接切换方案）

1. 部署后端 5 个文件（`app.py`/`auth.py`/`security_config.py`/`routes/account/__init__.py`/`routes/version/__init__.py`），md5 核对一致
2. `systemctl reload gunicorn`，等待后复查 `status`+`journal`，确认无崩溃
3. 验证 `/health`（200，`{"status":"ok"}`，nginx 代理已在上一批修复过）、`/ready`（200）、登录接口（错误密码 400，未下发 Cookie，符合"登录失败不覆盖已有 Cookie"设计）
4. **立即**部署 Web 端构建产物（tar+scp 方式），压缩不兼容窗口
5. 部署后验证：首页 200，`/health`/`/ready` 200，线上 JS bundle hash 与本地构建一致

## 已知影响

和之前几次密钥/机制变更一样：**所有当前登录用户的旧会话立即失效**，因为旧前端发的 `Authorization` header 后端已经不认了，新前端发的请求走 Cookie 但用户还没重新登录种下 Cookie。用户下次操作会被引导重新登录，一次性代价，这是"直接切换"方案本身接受的结果。

## 待验证（需要真实账号，我这边没有生产凭据）

建议实际登录一次，用浏览器开发者工具核对：
- 登录响应的 `Set-Cookie` 头：`tmt_session`（HttpOnly, Secure, SameSite=Strict）+ `tmt_csrf`（非 HttpOnly，其余相同）
- 后续请求自动带上 Cookie，写操作（比如编辑一条产品数据）能正常通过（说明 CSRF header 被正确附加和校验）
- 点"退出登录"后 Cookie 被清空，回到登录页
- 改一次自己的密码，确认立即被跳转到登录页（不是等下一次请求才发现）

## 附带上线

本次部署也一并上线了之前提交但等待这批一起走的：
- 产品库"产成品清单"卡片新增"查看所有产成品数据"弹窗（`0149b7a`）

## Cookie/Token 改造周期收尾

至此"周期一"（Cookie/Token 改造）完整走完：只读评审 → 联合设计 → Electron 决策 → 前后端实施 → 联调部署，全部完成并上线。按之前 `2026-07-21-session-close.md` 的规划，接下来是"周期二"（P3 结构重构）和"周期三"（Git 历史清理），继续按小步迁移、专门停工窗口的原则分别排期。
