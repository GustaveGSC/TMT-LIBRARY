# Cookie/Token 改造 · 联合设计（方案A + 直接切换，仍未实施）

日期：2026-07-21
承接 [2026-07-21-token-cookie-design-review.md](2026-07-21-token-cookie-design-review.md)。已确认：**方案 A（httpOnly Cookie + Double Submit CSRF）+ 直接切换**（不做新旧并存，上线那一刻所有已登录用户掉线重新登录，和之前几次密钥变更的做法一致）。范围仅 Web 端，Electron 暂停不涉及。

本文件把方案细化到可以分别交给 Claude（前端）和 Codex（后端）实施的颗粒度。**这一步仍然只是设计定稿，不写代码**——定稿后再各自建 worktree 开始实施。

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

## 二、后端改动范围（Codex）

### 1. `backend/auth.py`

- `generate_token()` 不变（仍然生成 JWT，只是不再由调用方直接塞进响应体）
- 新增：CSRF token 生成函数，`secrets.token_urlsafe(32)` 级别的随机值即可，不需要签名（它不代表身份，只用来配合 Cookie 做 Double Submit 校验）
- `verify_token()` 的调用方式要变：现在从 `request.headers.get('Authorization')` 取 token，改成从 `request.cookies.get('tmt_session')` 取。**这是核心改动点，`make_blueprint_guard`/`require_auth` 里都要跟着改**
- 新增 CSRF 校验逻辑：在 `make_blueprint_guard` 的写请求分支里，比对 `request.headers.get('X-CSRF-Token')` 和 `request.cookies.get('tmt_csrf')`

### 2. 登录/登出相关路由（`routes/account/__init__.py`）

- `login`/`guest_login`：不再往响应体的 `data.token` 塞值，改成用 `flask.Response.set_cookie()` 下发两个 Cookie。注意 Flask 的 `Result.to_response()` 目前是怎么构造 Response 对象的，需要确认能不能在返回前附加 `set_cookie`（大概率需要小改 `Result.to_response()` 或者在路由里拿到 Response 对象后手动调用 `set_cookie`）
- 新增登出接口（如果现在没有专门的登出接口——目前前端 401 时是本地清 localStorage 直接跳转，没有调后端；改成 Cookie 后，前端主动登出也需要一个后端接口来清 Cookie，纯本地清不掉 httpOnly Cookie）

### 3. CORS 配置确认

`CORS(app, origins=_cors_origins)` 现在没有 `supports_credentials=True`。Cookie 方案下，跨域场景（本地开发 Vite dev server）必须显式加 `supports_credentials=True`，否则浏览器不会携带/接受跨域 Cookie。生产环境因为同源不受影响，但本地开发链路要过一遍。

### 4. `Secure` 属性和本地开发的兼容

`Secure` Cookie 只在 HTTPS 下生效。本地开发用的是 `http://127.0.0.1:8765`（非 HTTPS），如果 Cookie 强制 `Secure=True`，本地开发登录会直接种不上 Cookie。需要按环境区分：生产 `Secure=True`，本地开发环境（`APP_ENV` 非 production）`Secure=False`。这个和现有 `security_config.py` 里已经有的"非生产环境放宽"的模式一致，可以复用类似判断逻辑。

### 5. 需要新增/调整的测试

- `verify_token` 从 Cookie 读取的单测
- CSRF 校验通过/拒绝的单测（header 和 Cookie 一致/不一致/缺失三种场景）
- 登录响应确实带上了两个 `Set-Cookie` 头，且 `tmt_session` 有 `HttpOnly` 标记、`tmt_csrf` 没有
- 登出接口清空 Cookie

## 三、前端改动范围（Claude）

### 1. `src/api/http.js`

- 移除 `localStorage.getItem('tmt_token')` 读取和 `Authorization` header 设置逻辑
- axios 需要配置 `withCredentials: true`，否则浏览器不会自动带上 Cookie（尤其本地开发跨域场景下必须；生产同源下大多数浏览器默认也会带，但显式设置更保险，不依赖隐式行为）
- 写请求前从 `document.cookie` 解析出 `tmt_csrf` 的值，加到请求头 `X-CSRF-Token`（写一个小工具函数读某个 Cookie 的值，原生 `document.cookie` 解析，不需要额外依赖）
- 401 处理：不再需要清 `localStorage.tmt_token`（Cookie 由后端清，前端读不到也管不着），但 `user`/`login_time` 这类本地展示用的非敏感信息还是可以留在 localStorage，跳转登录页的逻辑不变

### 2. 登录/登出流程

- 登录成功后，前端不再需要主动存 token（后端已经通过 Set-Cookie 存好了），只需要存 `user` 展示信息
- 新增调用登出接口的逻辑（用户点"退出登录"按钮时，以及可能的其他登出入口，要改成先调后端登出接口再跳转，不能只本地清 localStorage 了事）

### 3. 需要排查的调用点

- 全局搜一遍 `localStorage.getItem('tmt_token')`、`localStorage.setItem('tmt_token'`、`localStorage.removeItem('tmt_token'` 这几个精确写法，确认改造覆盖所有调用点（目前印象里只有 `http.js` 一处读、登录页一处写、`http.js` 401 处理一处删，但要重新搜索确认，不能凭记忆）
- 检查有没有绕开 `http.js` 拦截器、直接手动构造请求的地方（比如某些下载/预签名场景可能是原生 `fetch`/`XMLHttpRequest`，之前处理预签名上传时见过原生 XHR 用法，这些如果也需要带身份信息，要确认它们是否也需要 `withCredentials`）

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
