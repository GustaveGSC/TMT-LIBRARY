# Codex 后端评审：Cookie/Token 联合设计

日期：2026-07-21
评审对象：`handoff/2026-07-21-token-cookie-joint-design.md`
状态：**方案方向可行，但存在 1 个上线阻断项；补齐下列约束后再实施**

## 一、结论

`httpOnly` 会话 Cookie + CSRF 防护的总体方向可行，`Result.to_response()` 也不构成障碍。但当前“仅 Web、Electron 暂不涉及”与“后端直接停止接受 Authorization”不能同时成立：已安装 Electron 与 Web 共用 `src/api/http.js`，并连接同一个生产后端。只改 Web 构建并切断 Bearer 后，现有桌面端会立即失去登录和 API 能力。

在以下二选一被用户明确确认前，不应开始实施或部署：

1. **推荐：把 Electron 纳入本次迁移和验收。** 需实际验证 Electron `file://` 渲染页对 `https://tmt-library.cn` 的 Cookie、SameSite、CORS、CSRF header 和持久化行为，不能仅按普通浏览器推断。
2. 明确停止/下线现有 Electron 客户端，并接受其在后端切换后不可用。

不建议为 Electron 长期保留 Bearer、Web 使用 Cookie 的双轨方案；同一个公开后端难以安全识别“可信 Electron”，双轨会保留 localStorage token 的原风险并扩大测试面。

## 二、后端范围需要补充的内容

### 1. 保持 `verify_token(token)` 为纯校验函数

当前 `verify_token` 接收 token 字符串，本身不读取 Header。建议保持这一职责，新增统一的请求级读取函数，从 `request.cookies['tmt_session']` 取值后调用 `verify_token`。然后替换全部四类调用点：

- `make_blueprint_guard`
- `require_auth`
- `routes/account/__init__.py` 自定义蓝图守卫
- `routes/version/__init__.py` 自定义写接口守卫

原设计遗漏了后两处；只修改 `auth.py` 通用守卫会导致账号管理和版本发布仍读取 Bearer。

### 2. CSRF 应集中覆盖所有受保护的非安全方法

不能只放在 `make_blueprint_guard` 的“编辑权限”分支，否则会遗漏 `require_auth`、账号/版本自定义守卫，以及被归类为只读查询的 POST。建议由一个统一函数或应用级 `before_request` 覆盖 `POST/PUT/PATCH/DELETE`，并明确：

- 登录、游客登录、注册属于无现有会话的公开入口，列入明确豁免清单。
- 登出必须验证 CSRF。
- CORS 预检 `OPTIONS` 必须直接放行，不能要求会话或 CSRF。
- GET/HEAD/OPTIONS 不做 CSRF 校验，同时继续保证这些方法没有状态变更副作用。

比对使用 `hmac.compare_digest`，缺 Cookie、缺 Header或不匹配统一返回 403，不返回 token 内容。

### 3. 建议改为“与会话绑定的 Double Submit”

原文的随机 CSRF Cookie + Header/Cookie 相等属于 naive double-submit。建议登录时生成随机 CSRF 值，同时把该值或其不可逆绑定值写进签名 JWT claim；写请求校验 Header、CSRF Cookie、JWT claim 三者绑定，而不是只比对前两者。这样不会新增服务端会话表，仍保持无状态。

OWASP 对新实现推荐与认证会话显式绑定的 signed double-submit，并指出单纯 Header/Cookie 相等可能受到 Cookie 注入影响。SameSite 应视为纵深防御，而不是替代 CSRF token。

### 4. 401 和账号安全操作的 Cookie 生命周期

原设计写了“401 时后端清 Cookie”，但当前实现的各个 401 返回点不会自动附加清 Cookie头。需要统一实现，例如在 `after_request` 中对 401 删除两个 Cookie，避免逐路由遗漏。

还需覆盖以下行为：

- 用户修改自己的密码后，当前 JWT 的 `token_version` 已失效；成功响应应清 Cookie，前端转登录页，不能等下一次请求才发现 401。
- 管理员修改别人的密码/状态/角色，不清管理员自己的 Cookie。
- 登录/游客登录每次轮换 JWT 与 CSRF；失败登录不得覆盖现有 Cookie。
- 登出幂等清理两个 Cookie，即使会话已失效也应可完成清理。可让登出在仅有 Cookie 时仍返回成功，但有有效会话的请求必须通过 CSRF。

### 5. `Result.to_response()` 无需改动

当前返回 `(Response, status)`，路由可用 Flask `make_response(result.to_response())` 得到可变 Response，再调用两次 `set_cookie()`。建议封装：

- `set_auth_cookies(response, user)`
- `clear_auth_cookies(response)`

这样登录、游客登录、登出、401、本人改密共享完全相同的名称、Path、SameSite、Secure 和 Max-Age 配置。无需让通用 `Result` 类理解认证 Cookie。

注册接口当前只创建账号，不自动登录，因此无需下发 Cookie；文档应明确保持这一语义。

## 三、Cookie/CORS 参数建议

设计中的命名可以定稿为：

- `tmt_session`
- `tmt_csrf`
- `X-CSRF-Token`
- `Path=/`
- 不设置 `Domain`，使用 host-only Cookie
- `SameSite=Strict`
- `Max-Age=604800`，与 JWT 7 天一致；同时设置一致的 Expires 更利于兼容
- 生产 `Secure=True`；明确的 dev/test/local 环境 `Secure=False`
- `tmt_session`: `HttpOnly=True`
- `tmt_csrf`: `HttpOnly=False`

`CORS(..., supports_credentials=True)` 可行，但 origins 必须是精确白名单，不能使用 `*`。跨域响应只有在客户端启用 credentials 时浏览器才接受 Set-Cookie；同时 Cookie 仍受 SameSite/第三方 Cookie策略约束。因此 `supports_credentials` 不能解决 Electron `file://` 跨站场景，也不能替代实际 Electron 验证。

本地 Web 开发优先继续走 Vite `/api` 代理保持同源，不要把 `localhost:5174` 页面直接请求到 `127.0.0.1:8765`；`localhost` 与 `127.0.0.1` 不是同一站点，Strict Cookie 会造成难以识别的联调失败。

## 四、前端/调用点核对结果

需要 Claude 覆盖的现存 token 调用点不止登录页和 `http.js`：

- `src/api/http.js`：读、附加和删除 `tmt_token`
- `src/views/loginViews/page-login.vue`：保存 token
- `src/routers/index.js`：删除 token
- `src/components/user/UserSettingsDrawer.vue`：删除 token/退出登录

原生调用点判断：

- 资料和安装包的 `XMLHttpRequest` 是向 OSS 预签名地址上传，不应附带本站 Cookie或 CSRF。
- 资料下载的原生 `fetch(url)` 使用签名/公开 URL，不应附带本站 Cookie。
- 现有 SSE 进度接口以不可预测 task_id 作为访问凭证并由后端豁免鉴权，不依赖 Bearer；Web 同源情况下无需额外改造。若 Electron 纳入迁移，仍需逐条实测。

前端 401 处理不应再调用登出接口，否则“401 → 登出请求又 401”可能形成重复处理；401 时清本地展示状态并跳转即可，Cookie 由后端 401 响应统一删除。只有用户主动退出时调用登出接口。

## 五、实施前必须补入联合设计的测试

后端：

- 四类鉴权入口均只接受 Cookie，Bearer 被明确拒绝。
- CSRF 一致、缺 Header、缺 Cookie、错误值、OPTIONS、公开入口豁免。
- CSRF 与当前 JWT 会话绑定，不能混用另一登录会话的 CSRF Cookie。
- 登录/游客登录 Cookie 属性及响应体不含 token；失败登录不覆盖 Cookie。
- 登出、401、本人改密正确清 Cookie。
- `Secure` 仅在明确非生产环境关闭。
- CORS credential 响应只允许配置的 origin。

联合验收：

- Web 生产完整登录、读、写、401、主动登出。
- Vite 代理下的本地 Web 登录和写操作。
- 如果保留 Electron：安装包环境下完整登录、重启后会话保持、读、写、SSE、主动登出；必须以实际 Electron 行为为准。

## 六、是否可以开始实施

后端技术上可实现，预计无需数据库迁移。但当前结论是**有条件通过，暂不开始编码**：先由用户确认 Electron 是纳入迁移还是正式停止支持，并把“会话绑定 CSRF、遗漏守卫、统一 401 清 Cookie、本人改密、OPTIONS”补回联合设计。确认后双方即可各自在独立 worktree 实施。

安全依据：

- OWASP CSRF Prevention Cheat Sheet：推荐与认证会话绑定的 signed double-submit，SameSite 仅作为纵深防御。
- MDN Set-Cookie/CORS 文档：跨域 Set-Cookie 需要 credentials，且 SameSite/第三方 Cookie策略仍独立生效。
