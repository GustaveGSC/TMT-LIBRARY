# Cookie/Token 改造 · 联合设计（方案A + 直接切换，仍未实施）

日期：2026-07-21
承接 [2026-07-21-token-cookie-design-review.md](2026-07-21-token-cookie-design-review.md)。已确认：**方案 A（httpOnly Cookie + Double Submit CSRF）+ 直接切换**（不做新旧并存，上线那一刻所有已登录用户掉线重新登录，和之前几次密钥变更的做法一致）。范围仅 Web 端，Electron 暂停不涉及。

本文件把方案细化到可以分别交给 Claude（前端）和 Codex（后端）实施的颗粒度。

**定稿更新（2026-07-21）**：Codex 后端评审（[2026-07-21-codex-token-cookie-design-review.md](2026-07-21-codex-token-cookie-design-review.md)）指出了本文件初版的几个遗漏，用户已确认停止支持现有 Electron 客户端（[2026-07-21-electron-support-end-decision.md](2026-07-21-electron-support-end-decision.md)），解除了唯一的上线阻断项。下面第二、三节已按评审意见更新为定稿版本，**现在可以开始实施**（各自独立 worktree）。

---

## 一、总体流程

```
登录成功
  → 后端 Set-Cookie: tmt_session=<jwt>; HttpOnly; Secure; SameSite=Strict; Path=/
  → 后端 Set-Cookie: tmt_csrf=<random>; Secure; SameSite=Strict; Path=/  （非 HttpOnly，前端 JS 可读）
  → 响应体仍返回 user（展示信息，不含 token）

后续请求
  → 浏览器自动带 tmt_session Cookie（GET/POST 都会带）
  → 写请求（POST/PUT/DELETE/PATCH）前端从 tmt_csrf Cookie 读值，加到请求头 X-CSRF-Token
  → 后端 before_request：先验证 tmt_session（同现有 verify_token 逻辑），
     写请求再额外比对 X-CSRF-Token 头 == tmt_csrf Cookie 值，不一致拒绝

登出 / 401
  → 后端 Set-Cookie 清空两个 Cookie（Max-Age=0）
  → 前端跳转登录页
```

## 二、后端改动范围（Codex）· 定稿版

### 1. `backend/auth.py`

- `generate_token()` 不变
- CSRF token **不是**普通随机值，而是**和当前会话（JWT）绑定**的 signed double-submit：登录时生成随机值，同时把它（或其不可逆绑定值）写进 JWT 的一个 claim；写请求校验时要求 `X-CSRF-Token` 头、`tmt_csrf` Cookie、JWT claim 三者一致，而不是只比较 Header 和 Cookie 两者（naive double-submit 对 Cookie 注入没有防护）
- `verify_token(token)` 保持"纯校验函数"职责不变（接收 token 字符串，不读 Header/Cookie）；新增一个统一的请求级读取函数，从 `request.cookies.get('tmt_session')` 取值后调用 `verify_token`
- **必须替换全部四类调用点**，不能只改 `auth.py` 通用守卫：
  1. `make_blueprint_guard`
  2. `require_auth`
  3. `routes/account/__init__.py` 里的自定义蓝图守卫
  4. `routes/version/__init__.py` 里的自定义写接口守卫
- CSRF 校验用统一函数或应用级 `before_request` 覆盖 `POST/PUT/PATCH/DELETE`，不能只放在某一个守卫的"编辑权限"分支：
  - 登录、游客登录、注册是无现有会话的公开入口，明确豁免
  - 登出必须验证 CSRF
  - `OPTIONS`（CORS 预检）直接放行，不要求会话或 CSRF
  - GET/HEAD/OPTIONS 不做 CSRF 校验，同时保证这些方法本身没有状态变更副作用
  - 比对用 `hmac.compare_digest`；缺 Cookie/Header/不匹配统一返回 403，不回显 token 内容

### 2. Cookie 生命周期：登录/登出/401/改密要统一清干净

- 封装 `set_auth_cookies(response, user)` / `clear_auth_cookies(response)` 两个函数，登录、游客登录、登出、401、本人改密共享完全相同的名称/Path/SameSite/Secure/Max-Age 配置，不要在各个路由里各写一遍
- **401**：不能指望每个 401 返回点手动加清 Cookie 逻辑，容易漏；用应用级 `after_request` 统一处理，对 401 响应删除两个 Cookie
- **本人改密**：改完自己的密码后，当前 JWT 的 `token_version` 已经失效，成功响应也要清 Cookie，前端直接跳登录页，不要等下一次请求才发现 401
- **管理员改别人的密码/状态/角色**：不清管理员自己的 Cookie
- **登录/游客登录**：每次轮换 JWT 和 CSRF；登录失败不能覆盖已有的有效 Cookie
- **登出**：幂等，即使当前会话已经失效也要能正常清 Cookie（登出本身不因为 session already invalid 而报错），但如果登出请求带着一个仍然有效的会话，必须照样过 CSRF 校验
- **注册接口**：不自动登录，不下发 Cookie，保持现有语义不变

### 3. `Result.to_response()` 不需要改动

当前返回 `(Response, status)`，路由里用 `flask.make_response(result.to_response())` 拿到可变 Response 对象后调用 `set_auth_cookies`/`clear_auth_cookies` 即可，不需要让通用的 `Result` 类理解认证 Cookie 这件事。

### 4. CORS 配置确认

- `CORS(app, origins=_cors_origins, supports_credentials=True)`——**origins 必须是精确白名单，不能用 `*`**（浏览器规则：`supports_credentials=True` 时 `Access-Control-Allow-Origin` 不能是通配符）
- `supports_credentials` 只解决"浏览器要不要在跨域请求里带/接受 Cookie"，不代表 Electron `file://` 场景能用——但这次不涉及 Electron，不用管这条
- **本地 Web 开发优先继续走 Vite `/api` 代理保持同源**，不要把 `localhost:5174` 页面直接请求 `127.0.0.1:8765`；`localhost` 和 `127.0.0.1` 不是同一站点，`SameSite=Strict` 会导致 Cookie 种不上、联调莫名其妙地全部 401，且很难排查。这条对 Claude 前端联调也很重要，一并记在这里

### 5. `Secure` 属性和本地开发的兼容

生产 `Secure=True`；明确的非生产环境（`APP_ENV` 非 production）`Secure=False`，复用 `security_config.py` 已有的环境判断模式。

### 6. Cookie 参数（已定稿）

| 参数 | 值 |
|---|---|
| 名称 | `tmt_session`（会话）、`tmt_csrf`（CSRF） |
| CSRF header 名 | `X-CSRF-Token` |
| `Path` | `/` |
| `Domain` | 不设置，host-only Cookie |
| `SameSite` | `Strict` |
| `Max-Age` | `604800`（7 天，和 JWT 有效期一致），同时设置一致的 `Expires` |
| `Secure` | 生产 `True`，明确非生产环境 `False` |
| `HttpOnly` | `tmt_session`=`True`，`tmt_csrf`=`False` |

### 7. 需要新增/调整的测试

- 四类鉴权入口均只接受 Cookie，Bearer 被明确拒绝
- CSRF：一致、缺 Header、缺 Cookie、错误值、`OPTIONS`、公开入口豁免，各自独立场景
- CSRF 与当前 JWT 会话绑定，不能混用另一个登录会话的 CSRF Cookie
- 登录/游客登录 Cookie 属性正确，响应体不含 token；登录失败不覆盖已有 Cookie
- 登出、401、本人改密正确清 Cookie；管理员改别人的密码不清自己的 Cookie
- `Secure` 仅在明确非生产环境关闭
- CORS credential 响应只允许配置的 origin，不允许 `*`

## 三、前端改动范围（Claude）· 定稿版

### 1. `src/api/http.js`

- 移除 `localStorage.getItem('tmt_token')` 读取和 `Authorization` header 设置逻辑
- axios 配置 `withCredentials: true`
- 写请求前从 `document.cookie` 解析出 `tmt_csrf` 的值，加到请求头 `X-CSRF-Token`
- **401 处理修正（Codex 指出的点）**：401 时只清本地展示状态（`user`/`login_time`）并跳转登录页，**不要额外调用登出接口**——Cookie 已经由后端 401 响应统一删除（见后端 `after_request` 那条），前端如果在 401 处理里又调一次登出接口，会出现"401 → 登出请求又 401"的重复处理链路。只有用户**主动点退出登录**时才调登出接口。

### 2. 登录/登出流程

- 登录成功后，前端不再存 token，只存 `user` 展示信息
- 主动登出（用户点按钮）：调用后端新登出接口，清 Cookie，再清本地展示状态并跳转

### 3. 需要排查/修改的调用点（Codex 核对出的完整清单，比初版遗漏更多）

- `src/api/http.js`：读、附加、清除 `tmt_token`
- `src/views/loginViews/page-login.vue`：登录成功保存 token 的逻辑
- `src/routers/index.js`：路由守卫里清 token 的逻辑
- `src/components/user/UserSettingsDrawer.vue`：退出登录按钮，改成调后端登出接口

### 4. 原生请求调用点（已核对，不需要改）

- 资料库/安装包上传用的原生 `XMLHttpRequest` 是直传 OSS 预签名地址，不应该带本站 Cookie/CSRF，维持原样
- 资料下载用的原生 `fetch(url)` 走的是签名/公开 URL，不应该带本站 Cookie，维持原样
- SSE 进度接口（`/api/shipping/import/progress/:id`）用不可预测的 `task_id` 作为访问凭证，后端本身豁免鉴权，不依赖 Bearer，Web 同源下不需要额外改造

### 5. Electron 相关清理（决策要求，本批一并做）

- `src/views/indexViews/page-index.vue` 的下载按钮已经隐藏（之前的改动），保持不变
- 检查 `.claude/claude.md`、`.claude/modules/*.md`、`README` 等文档里残留的 Electron 支持描述，标记为历史/暂停状态，不需要删除 `electron/` 目录代码本身（只是暂停，不是取消）
- 不需要处理 `electron/main/index.ts`/`window.ts` 里的 `getBaseURL`/`WEB_BASE` 之类的 Electron 专属代码——Electron 暂停后不会有新构建，这些代码保持原样即可，不用为了 Cookie 改造去改它们

## 四、直接切换的具体步骤（部署顺序）

1. 后端先部署（新代码同时支持从 Cookie 读 token；**不建议**做"两种方式都支持"的过渡逻辑，因为已经决定直接切换，同时支持反而增加复杂度和攻击面，后端一次性切断 Authorization header 的读取路径）
2. 前端部署（新代码不再发 Authorization header，改用 Cookie + CSRF header）
3. 因为前后端不是原子部署（分别部署总有先后），**这中间会有一个不可避免的短暂不兼容窗口**：
   - 如果后端先上、前端还没上：旧前端发 `Authorization` header，新后端只认 Cookie，所有请求都会 401——**等于提前触发了"直接切换"的掉线效果**，可以接受（反正就是要让大家掉线重新登录），但要确认这个窗口尽量短（后端部署完立刻部署前端，不要间隔太久）
   - 如果前端先上、后端还没上：新前端不发 Authorization header 了，旧后端只认 header，同样会全部 401——效果一样，不影响
4. 部署顺序建议：**后端先部署，验证 `/health`+`/ready`+登录接口正常后，立刻部署前端**，把不兼容窗口压缩到几分钟内
5. 部署后验证：至少验证一次完整登录流程（浏览器开发者工具确认 Set-Cookie 头正确、后续请求正确带上 Cookie 和 CSRF header）、验证写操作（比如编辑一条数据）能正常通过 CSRF 校验、验证登出能正确清 Cookie

## 五、待确认的命名/细节（设计收尾前最后拍板）

- Cookie 名：`tmt_session` / `tmt_csrf`（可以照用，也可以改名，不影响架构，现在定下来避免实施时前后端对不上）
- CSRF header 名：`X-CSRF-Token`
- Cookie 的 `Max-Age`：是否继续保持和 JWT 有效期一致（7 天）
- `SameSite=Strict` 还是 `SameSite=Lax`：`Strict` 更安全但如果以后有"从外部链接直接跳进已登录页面"这类场景会失效（比如分享链接点开直接免登录，目前售后模块的资料分享是走独立的 SHARE_SECRET 机制，不受这个影响，但如果以后有类似需求要注意）。**建议先用 `Strict`**，这个内部工具场景不太需要"外链直接带身份跳转"的需求

---

## 六、下一步

这份设计文档需要 Codex 从后端实现角度过一遍，确认第二节列的改动范围和技术细节没有遗漏或不可行的地方，尤其是 `Result.to_response()` 能不能方便地附加 `set_cookie`、以及现有 `make_blueprint_guard` 改造成本。Codex 确认后，双方各自建 worktree 开始实施，不再需要来回对齐设计。
