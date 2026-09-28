# 登录需点两下 + 登录跳转慢：交接给 Codex

> 日期：2026-09-28
> 来源：用户反馈「有时登录页需要按两下登录才能登录，点击登录到跳转页面耗时过久」
> 状态：Claude 已按代码分析**改好前端代码，但未测试、未部署、未提交**（本机命令执行被权限检查服务持续报错卡住）。
> 请 Codex：核实根因 → 跑测试 → 部署 → 提交推送。

---

## 1. 现象

| # | 现象 | 频率 |
|---|---|---|
| A | 输入账号密码点「登录」，页面停在登录页没反应，也没有错误提示；再点一次就进去了 | 偶发 |
| B | 点「登录」到进入主页要等很久 | 经常 |

## 2. 根因分析（基于代码，**尚未用服务器日志核实**）

### 改动前的登录链路（Web 端）

| 步骤 | 位置 | 说明 |
|---|---|---|
| 1 | `page-login.vue` `handleLogin` | `POST /api/account/login`（bcrypt 校验，双核小机器上本身有几百 ms） |
| 2 | 同上 | 登录成功后**先**调 `prefetchShippingDashboard()`：并发发出分类树 + `GET /api/shipping/chart-options`（后者缓存未命中时要计算数秒） |
| 3 | 同上 | `router.push('/index')` |
| 4 | `src/routers/index.js` `beforeEach` | 应用启动后第一次导航到非登录页，`authChecked=false` → 串行调 `GET /api/account/me` |
| 5 | 后端 | gunicorn **单 sync worker**，请求排队处理：`/me` 排在第 2 步两个预热请求后面 → **现象 B** |
| 6 | `beforeEach` 的 `catch` | `/me` 只要抛错（超时、502/504、断网，不只是 401）就 `clearSession()` 并 `return '/login'`，**静默**回登录页；此时 `authChecked` 已是 true，第二次点登录不再调 `/me`，直接进 → **现象 A** |

另一个会表现为「点了没反应」的可能：部署后旧页面 `import()` 已被整体覆盖删除的旧 hash 分片失败，vue-router 导航被中止、停在原页面（nginx 缓存头已在 2026-07-23 修过，但已打开未刷新的旧页面仍可能遇到）。

补充：`page-index.vue` 本身**不发任何接口请求**，所以主页慢只可能来自上面的 `/me` 排队 + 分片下载。

## 3. 已改代码（未提交）

| 文件 | 改动 |
|---|---|
| `src/routers/index.js` | ① 新增 `export function markSessionVerified()`，把 `authChecked` 置 true；② `/me` 的 catch 改为**只有 `err.response.status === 401` 才** clearSession + 回 `/login`，超时/5xx/断网放行（之后业务请求真 401 时，`http.js` 拦截器照样会跳登录）；③ 新增 `router.onError`：动态分片加载失败时整页 reload 到目标路由，用 `sessionStorage.chunk_reload_at` 限制 10 秒内只刷新一次，防止无限刷新 |
| `src/views/loginViews/page-login.vue` | ① `import { markSessionVerified } from '@/routers'`；② `onMounted` 里预取主页分片 `import('@/views/indexViews/page-index.vue')`；③ 登录成功后先 `markSessionVerified()`；Web 端 `await router.push('/index')` 后再 `setTimeout(prefetchShippingDashboard, 1500)`（Electron 分支保持原顺序）；`loading` 在跳转完成后才复位，防止连点 |
| `tests/e2e/login-flow.spec.js`（新增） | 用例 1：点一次登录就进 `/index`，`/api/account/login` 只调 1 次，**不调** `/api/account/me`，`chart-options` 请求时间晚于进入主页；用例 2：带本地登录态直接打开 `/#/index`，`/me` 返回 502 时停留主页、返回 401 时回登录页 |

**请先 review 这三处 diff**（`git diff src/routers/index.js src/views/loginViews/page-login.vue`），重点确认：
- `page-login.vue` 反向 import `@/routers` 没有循环依赖问题（router 模块在登录页懒加载前已求值完毕，理论上安全）；
- `onError` 的错误信息正则能覆盖 Chrome / Safari / Firefox 三种写法。

## 4. 待办（按顺序）

### 第 1 批：核实根因（只读）

1. 看服务器 nginx 访问日志，找近期登录前后的请求顺序与耗时：
   ```bash
   ssh tmt "tail -n 20000 /var/log/nginx/access.log | grep -E 'account/(login|me)|chart-options|categor' | tail -60"
   ```
   期望看到：`login` 之后紧跟 `chart-options`/分类树，`/me` 在它们之后返回，且 `/me` 有非 200（502/504）或明显延迟的记录。如 nginx `log_format` 未记录 `$request_time`，可看 `journalctl -u gunicorn` 或临时只读评估，**不要为此改线上 nginx 配置**，先回报。
2. 确认 `gunicorn.service` 仍是 `-w 1` sync worker：`ssh tmt "grep ExecStart /etc/systemd/system/gunicorn.service"`。
3. 若日志显示根因不同（例如 login 接口本身就慢、bcrypt rounds 过高、LoginLog 写库慢），请在本文档末尾追加结论后再决定是否调整方案。

### 第 2 批：测试

```bash
npx playwright test tests/e2e/login-flow.spec.js tests/e2e/no-horizontal-overflow.spec.js tests/e2e/purchase-tools.spec.js tests/e2e/material-bom.spec.js --reporter=line
npm run build:web   # 必须实际 build 一次（历史上有 dev 不复现、生产构建才报的 TDZ 问题）
```

测试要求：
| 用例 | 断言 |
|---|---|
| 单次点击登录 | URL 变为 `#/index`；`/api/account/me` 调用次数 = 0；`/api/account/login` = 1 |
| 预热延后 | 首个 `chart-options` 请求时间 > 进入 `/index` 的时间 |
| 深链 + `/me` 502 | 停留 `#/index` |
| 深链 + `/me` 401 | 跳 `#/login` |
| 回归 | 登录页布局用例、采购工具、物料 BOM 用例全部通过 |

### 第 3 批：部署（仅前端，无后端/迁移改动）

按 `CLAUDE.md`「构建与部署 → 前端部署」执行（tar + scp + 服务器端备份 `.old` 后覆盖），然后：
- 核对线上 `index.html` 中 `assets/index-*.js` 与本地 `dist-web/index.html` 一致后再删 `/var/www/tmt-library.old`；
- 用真实账号在浏览器里登录一次，DevTools Network 确认：登录后没有 `/api/account/me`，`chart-options` 在主页渲染后约 1.5 秒才发出。

### 第 4 批：提交推送

只提交本任务的 3 个文件（工作区还有其他人未提交的改动，**不要** `git add -A`）：
```bash
git add src/routers/index.js src/views/loginViews/page-login.vue tests/e2e/login-flow.spec.js handoff/2026-09-28-codex-login-double-click-slow.md
git commit -m "fix(login): single click login, skip redundant /me, defer dashboard prefetch"
git push origin master
```
注意：`src/views/loginViews/page-login.vue` 在本任务之前**可能已有别人未提交的改动**（git status 显示它早已是 M 状态）。提交前用 `git diff` 确认，如混有无关改动，只暂存本任务相关的 hunk 或先与用户确认。

## 5. 不在本次范围

- 不改 gunicorn worker 数/类型（服务器 1.7GB 内存，已知约束，见 CLAUDE.md「性能与负载规范」）。
- 不改后端 `/api/account/login`、`/api/account/me` 逻辑。
- 预热本身保留（2026-09-14 为发货看板首次进入慢加的），只调整发送时机。

## 6. 回报格式

请回报：日志核实结论（根因是否成立）、测试结果（通过数/失败详情）、部署后线上 hash、提交号。
