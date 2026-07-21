# Cookie/Token 改造 · 只读方案评审（不实施）

日期：2026-07-21
本文件只做方案评审和建议，不改代码。按收尾计划，这是"周期一"的起点，评审通过/达成一致后才进入联合设计→实施阶段。

**范围更新（2026-07-21 追加）**：桌面端（Electron）已决定暂停——代码保留，但不再投入新功能开发或验证，等以后有需求再恢复。因此这次 token 改造**只针对 Web 端设计和实施**，不需要验证 Electron 的 BrowserWindow session/Cookie 共享行为（下面第三节的分析作为历史记录保留，供以后 Electron 恢复时参考，但不阻塞本次改造）。

---

## 一、现状梳理

### 前端
- `src/api/http.js`：token 存 `localStorage.getItem('tmt_token')`，请求拦截器手动加 `Authorization: Bearer <token>`；响应拦截器在 401 时清 `localStorage` 并跳转登录页
- Electron 和 Web 共用这一套代码，无差异化处理

### 后端
- `backend/auth.py`：JWT，`HS256` 签名，有效期 7 天，payload 含 `id/username/roles/permissions/ver`
- `verify_token()` 会额外查一次数据库确认账号状态（`is_active`）和 `token_version`，实现"改密/禁用/撤权后旧 token 立即失效"（P1-1 已上线）
- `make_blueprint_guard`/`require_auth` 从 `Authorization` 请求头取 token，没有任何 Cookie 相关代码
- CORS：`CORS(app, origins=_cors_origins)`，生产环境靠 `CORS_ORIGINS` 环境变量配置，默认开发环境是 `["http://localhost:5173", "file://"]`（**发现一个小的既有不一致**：Vite dev server 实际端口是 `5174`（`vite.config.web.ts`），默认值写的是 `5173`，本地 `npm run dev:web` 联调时如果没显式设置 `CORS_ORIGINS` 会被 CORS 拦。这个不影响本次评审结论，顺手记一笔，修的话是一行代码，可以在真正实施这批改造时顺带修，不需要现在单独起任务）

### 关键的架构事实：生产环境全链路是同源

这是这次评审里最重要的发现，直接决定了方案的可行性和复杂度：

1. **Web 端**：`dist-web` 部署在 `https://tmt-library.cn`（nginx 静态文件服务），API 也在同一个域名下（`/api/` 反代到后端）。前端 JS 发起的请求和页面本身**同源**。
2. **Electron 桌面端**：`electron/main/window.ts` 的 `WEB_BASE = 'https://tmt-library.cn'`，主窗口/登录窗口是 `loadURL(WEB_BASE + '/#/login')`——**桌面端不是加载本地打包资源再跨域调 API，而是 Electron 的 BrowserWindow 直接导航到 `https://tmt-library.cn` 这个真实网页**，行为上和一个装了这个网站的浏览器窗口没有本质区别。Electron 的 `session`（默认 partition）会像真实浏览器一样持久化该域名下的 Cookie。

**结论：Web 和 Electron 两端在生产环境下，请求 API 时都是同源请求，不存在真正的"跨域"场景**（只有本地开发时 Vite dev server :5174 → 后端 :8765 这一段是跨域，走的是 Vite 代理，Cookie 会随代理请求转发，一般不需要额外处理）。

这个事实大幅降低了 httpOnly Cookie 方案的复杂度——不需要处理"三方 Cookie 被浏览器拦截"“跨站 Cookie SameSite 限制"这类通常最棘手的问题。

---

## 二、候选方案对比

### 方案 A：httpOnly Cookie + CSRF Token

**做法**：登录成功后，后端用 `Set-Cookie: tmt_session=<jwt>; HttpOnly; Secure; SameSite=Strict` 下发 token，前端 JS 不再手动读写 token；改用 CSRF token（比如登录响应里额外返回一个非 HttpOnly 的 CSRF token，写请求时前端从一个可读的地方取出加到请求头，后端校验）。

**优点**：
- 前端 JS（包括任何 XSS 注入的脚本）读不到 token 本身，即使页面被注入恶意脚本也偷不走 token——这是这次改造要解决的核心风险
- 浏览器自动带上 Cookie，前端拦截器逻辑简化（不用手动管理 token 生命周期）
- 结合上面"全链路同源"的事实，`SameSite=Strict` 或 `Lax` 都能直接用，不需要 `SameSite=None`（那个通常需要额外的第三方 Cookie 豁免逻辑，很麻烦）

**缺点/复杂度**：
- **必须配套 CSRF 防护**，否则 Cookie 自动携带反而让 CSRF 攻击更容易（相比 Bearer token 现在这种"必须显式代码读 token 加 header"的方式，天然就防 CSRF）
- 后端要新增 CSRF token 的签发和校验逻辑（可以用 Double Submit Cookie 模式：CSRF token 既放一个可读 Cookie，又要求写请求把它带在自定义 header 里，后端比对两者一致；这个模式和现有的 `Authorization` header 校验模式改动幅度接近，不算特别陌生）
- 登出/401 场景，前端不能再"读 localStorage 判断有没有登录"来做本地状态展示（比如用户名展示在导航栏），需要额外一次接口请求或者返回时带上非敏感的用户信息到一个前端可读的地方（比如登录响应里的 `user` 字段本来就有，可以继续用 localStorage 存"非敏感展示信息"，只是不再存 token 本身）
- Electron 侧：需要确认 Electron 的 `session.cookies` 在应用重启后是否持久化（默认 persist session 是会持久化的，除非明确配置成 `session: 'inMemory'` 之类，需要在 `electron/main/window.ts` 创建 `BrowserWindow` 时检查有没有覆盖默认 session 行为——目前代码看没有特殊配置，应该是默认持久化的，但需要在联合设计阶段实际验证一遍，不能只凭代码推断）

### 方案 B：维持 localStorage，但加固现有机制

**做法**：不改存储位置，把 P1-1 已经做的 `token_version` 机制进一步加固——比如缩短 token 有效期（现在 7 天偏长）、更激进地检查账号状态（现在已经是每次请求都查一次，这块已经比较到位了）、加内容安全策略（CSP，`src/index.html` 已经有 CSP 头，但需要确认 `script-src` 之类的策略够不够严格来防 XSS 注入）。

**优点**：改动量最小，不涉及 CSRF、不涉及 Electron Cookie 行为验证这些新增复杂度

**缺点**：治标不治本——XSS 风险的根本原因（token 存在 JS 可读的地方）没有解决，只是缩小了被盗用后的时间窗口和账号状态检测的及时性。如果这次评审的目标就是"彻底解决 XSS 窃取 token 的风险"，方案 B 达不到

### 方案 C：短时 access token + 可撤销 refresh token

**做法**：access token 有效期缩短到几分钟到几十分钟，存内存（比如 Pinia store，不落盘），refresh token 走 httpOnly Cookie，定期用 refresh token 换新的 access token。

**优点**：安全性理论上最高（access token 泄露的时间窗口最小），是目前主流单页应用的标准做法

**缺点**：改动量最大——前端要实现 access token 过期后的静默刷新逻辑（axios 拦截器里加刷新队列，避免并发请求时刷多次），后端要新增 refresh token 的签发、轮换、撤销逻辑（存储介质选择：数据库表还是 Redis，这个项目目前没有 Redis，可能要落数据库表），Electron 桌面端如果长时间挂后台（比如常驻托盘），refresh 逻辑要考虑应用休眠恢复后 token 是否已经过期需要重新登录的边界情况。相对这个项目当前的体量（内部工具，用户量不大），这个方案的复杂度收益比可能不划算

---

## 三、Electron 具体可行性分析（暂停，仅存档供以后参考）

**桌面端已暂停，本节分析不影响本次改造范围，不需要现在验证。** 以后如果 Electron 恢复开发，重新实施 Cookie 方案时再回来看这节。

之前 P1-1 报告里担心的"Electron 环境下 Cookie 机制是否可靠"，结合这次梳理 `window.ts` 的实现，结论是：**可行性较高，但需要在联合设计阶段做一次实测验证，不能只凭代码推断就直接实施**。原因：

- 桌面端本质是 Chromium 内嵌浏览器导航到真实 HTTPS 网站，不是自定义协议或 `file://` 加载，Cookie 机制和普通浏览器一致
- 需要验证的具体点：
  1. `BrowserWindow` 有没有设置非默认的 `session`/`partition`（目前代码没看到，需要确认默认行为下 Cookie 是否跨应用重启持久化）
  2. 登录窗口和主窗口是两个不同的 `BrowserWindow`（`createLoginWindow`/`createMainWindow`），需要确认它们是否共享同一个 session（如果不共享，登录窗口种下的 Cookie 主窗口可能读不到）——这个是目前发现的**唯一一个需要重点验证的技术风险点**
  3. 应用更新/重装后 Cookie 是否保留（用户体验层面：会不会导致更新后所有人被登出，这个和目前 JWT 方案下"换 JWT_SECRET 导致全员登出"是类似的可接受的一次性代价，不算新增风险）

---

## 四、CSRF 防护方案（如果选方案 A）

考虑到全链路同源这个前提，`SameSite=Strict` 已经能防住绝大多数跨站 CSRF 场景（浏览器不会在跨站请求里带上 `SameSite=Strict` 的 Cookie）。但为了防御深度，建议还是加一层 Double Submit Cookie：

1. 登录成功时，除了 httpOnly 的 `tmt_session` Cookie，再下发一个**非** httpOnly 的 `tmt_csrf` Cookie（前端 JS 能读到）
2. 前端在写请求（POST/PUT/DELETE/PATCH）时，从这个 Cookie 读值，加到自定义请求头（比如 `X-CSRF-Token`）
3. 后端在处理写请求时，比对请求头里的值和 Cookie 里的值是否一致，不一致就拒绝

这个模式下 `tmt_csrf` 本身不是敏感信息（即使 XSS 能读到它，没有配套的 httpOnly session Cookie 也没法单独构造有效请求），所以不需要额外加密。

---

## 五、迁移路径的关键问题（留给联合设计阶段决定，这里只列问题）

- 新旧机制并存期怎么处理？（比如灰度：某个时间点之后登录的用户走新机制，之前签发的旧 token 继续用旧的验证方式直到自然过期，7 天后完全切换）还是直接切换（会导致所有已登录用户当场掉线，类似之前几次密钥变更的做法）？
- 前端本地"显示用户名"这类非敏感状态展示，要不要继续保留一份在 localStorage？（不影响安全性，只是信息不再包含 token 本身）
- 后端要不要顺便把这次的 CSRF token 签发也纳入 `token_version` 机制的联动（比如撤权时 CSRF token 是否也需要跟着失效——理论上不需要，CSRF token 本身不代表身份，但要在设计阶段明确写清楚，避免实现时有歧义）

---

## 六、推荐结论

**推荐方案 A（httpOnly Cookie + Double Submit CSRF），理由**：
1. 直接解决这次改造要解决的核心问题（XSS 窃取 token）
2. 相比方案 C，复杂度可控，不需要引入新的存储介质（Redis）或复杂的静默刷新队列逻辑
3. 生产环境全链路同源这个既有架构事实，让 Cookie 方案的最大痛点（跨站/第三方 Cookie 限制）基本不存在

**不建议方案 B**：治标不治本，没有真正解决 XSS 场景下 token 被窃取的风险，如果这次改造的目标就是解决这个问题，方案 B 等于没做。

**在正式进入联合设计前，需要你确认的两件事**：
1. 是否认可方案 A 的方向（httpOnly Cookie + CSRF），还是你倾向方案 C（如果对这个内部工具而言，token 泄露风险的实际影响可以接受方案 A 的安全水位，方案 A 性价比更高；如果这个系统未来会对外暴露给更广泛/更不受信任的用户群体，可能需要方案 C 那种更高的安全水位）
2. 迁移策略：新旧并存过渡 还是 直接切换（当场让所有用户掉线，重新登录）

确定方向后再进入真正的联合设计（只针对 Web 端，细化 CSRF header 命名、后端具体改动范围等；Electron session 验证已移出本次范围，见第三节），设计定稿后才开始写代码。
