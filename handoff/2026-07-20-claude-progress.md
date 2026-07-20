# Claude 处理进度 · P0-1 (HTTPS) 前端部分

日期：2026-07-20
按 [2026-07-20-priority-correction.md](2026-07-20-priority-correction.md) 的顺序开始处理，我负责的第一项是 P0-1（客户端改用 HTTPS 域名）。这里记录处理过程和一个意外发现。

## 意外发现：桌面端当前在生产环境应该是完全打不开的

处理 P0-1 前先核实了服务器现状：`nginx -T` 显示 `tmt-library.cn` 已经用 Certbot 配好了 443 证书，`/api/` 反代和静态资源（`root /var/www/tmt-library`）**只挂在 443 这个 vhost 下**；plain HTTP（80端口）访问 IP 或域名，除了 `tmt-library.cn` 会 301 跳转到 https 外，其余一律 404（实测验证：`http://47.99.100.138/` → 404，`http://47.99.100.138/api/...` → 404）。gunicorn 也只绑定 `127.0.0.1:8765`，不对外。

而 `electron/main/window.ts` 里桌面端的登录窗口/主窗口是直接 `loadURL(WEB_BASE + '/#/login')` 从服务器加载整个页面（不是加载本地打包资源），`WEB_BASE` 之前硬编码是 `http://47.99.100.138`。这意味着**当前发布的桌面端安装包在生产环境应该是完全打不开的**（会一直卡白屏或走离线降级页），不只是"密码明文传输"的安全问题，是功能性的连接失败。

## 已修复（4 处，均改成 `https://tmt-library.cn`）

- [src/api/http.js](../src/api/http.js) — Electron 分支的 API baseURL
- [electron/main/window.ts](../electron/main/window.ts) — `WEB_BASE`，桌面端加载整个 UI 的地址
- [electron/main/index.ts](../electron/main/index.ts) — `get-api-base` IPC handler 返回值（目前 `getBaseURL()` 没实际调用它，但保持一致，避免以后有人接上这条路径又踩坑）
- [src/index.html](../src/index.html) — CSP `connect-src` 白名单，否则改完 URL 浏览器/Electron 会因为 CSP 拦截请求
- [vite.config.web.ts](../vite.config.web.ts) — 本地 web 开发模式的 `/api` 代理 target，顺手一起改了，不改的话本地 `npm run dev:web` 联调生产库也会 404

`npm run build:web` 和 `npm run build`（electron-vite）都跑通了，没有编译错误。**还没有部署，也没有打新的桌面端安装包**——这只是代码层面的改动，等你确认要不要现在部署/发新版。

## 需要 Codex 确认的一点：连接池实际配置比 P1-5 报告写的更夸张

顺手看了一眼 `backend/.env.web`（服务器部署用的环境变量模板，未提交 git），里面写的是：
```
POOL_SIZE=10
MAX_OVERFLOW=10
```
注释是"4 个 gunicorn worker × 每个最多 5 并发 = 约 20 连接"，但配置的数值本身是 10+10，不是 5+5——如果这个 `.env.web` 就是服务器上实际生效的配置（还是说服务器上有另一份手工改过的 `.env`？需要 Codex 核实），那按注释的算法，4 worker × (10+10) 理论峰值会到 80 个连接，比 P1-5 报告里"每 worker 10 个连接"的估计还要严重。这条我没有改动服务器配置，只是核实后发现和文档描述（`QueuePool(size=2)`）差距更大，报给 Codex 处理。

## 已处理：桌面端下载入口隐藏

`src/views/indexViews/page-index.vue` 里"下载桌面版"按钮改成 `v-if="false"`（保留路由 `/download` 和 `DownloadPage.vue` 不删，只是不再展示入口），因为桌面端当前不可用且暂不处理。

## 已处理：前端路由权限补齐（对应"其他一致性问题"里的"路由没有统一权限声明"）

`src/routers/index.js` 之前只有 `/aftersale/cases` 和 `/rd-tools` 两个路由有 `meta.permission`，其余业务页/管理页完全没有路由级权限声明——未授权用户能直接进入页面看到空白/报错，而不是被拦截跳转。这次补齐：

- `/product` → `product:view`
- `/shipping` → `shipping:view`
- `/data-mgmt` → `shipping:view`（沿用 `usePermission.js` 注释里"发货数据 / 数据管理"共用同一组权限码的约定）
- `/aftersale` → `aftersale:view`
- `/admin/version-release`、`/admin/users`、`/admin/permissions` → 新增 `meta: { adminOnly: true }`，路由守卫改为角色判断而不是权限码判断
- `/admin/login-logs` → 新增 `meta: { authorOnly: true }`，因为 `api.md` 里这个接口标注"author 专用"，比 admin 更严格，之前完全没有路由层拦截
- `/general-tools` 保持不设权限（工具页，登录即可用，判断是刻意设计）

路由守卫函数相应扩展了 `adminOnly`/`authorOnly` 分支。`npm run build:web` 验证通过。

## 已处理：财务/销退导入入口命名整理

业务决策已确认：**只保留财务表导入（同时包含正负数量），不需要独立销退清单入口**。核实发现：

- 实际在用的组件是 `ReturnImport.vue`（401行，`page-data-mgmt.vue` 里唯一被 import 的），标题是"导入财务清单"、调 `/import/finance`，说明"正数量行写入发货记录，负数量行写入销退记录"——命名和内容对不上
- `FinanceImport.vue`（300行）是另一个更旧、更简陋的版本，**完全没有被任何地方引用**，是死代码

处理：删除未使用的旧 `FinanceImport.vue`，把在用的 `ReturnImport.vue` 改名为 `FinanceImport.vue`（同步改了 `page-data-mgmt.vue` 里的 import/组件标签，以及文件内部 `.return-import` CSS class 名），`npm run build:web` 验证通过。

**需要 Codex 配合**：后端 `/import/return` 接口现在确认前端完全不用，按业务决策应该删除或归档，麻烦 Codex 确认后端有没有其他调用方（定时任务/脚本），没有的话可以清掉，并同步更新 `api.md`。

## 前端后续计划

暂时没有更多前端待办了，等 Codex 那边处理完第一、二阶段后端问题，或者你指派新的检查方向。
