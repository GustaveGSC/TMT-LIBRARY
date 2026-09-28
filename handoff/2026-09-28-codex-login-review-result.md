# 登录单击与跳转性能改动：Codex 审查结果

> 日期：2026-09-28  
> 状态：代码审查、专项测试和生产构建已完成；未部署、未提交、未 push。生产日志因当前执行环境无法完成 SSH 授权而未核实。

## 代码审查

- `page-login.vue` 引用 `markSessionVerified()` 不构成循环初始化问题：router 先完成模块求值，登录页为懒加载组件，调用发生在登录成功之后。
- 登录成功后以登录响应作为本次会话验证、跳过紧接着的 `/api/account/me`，语义成立。
- Web 端先等待 `router.push('/index')` 完成、再延迟 1.5 秒预热发货看板，可避免预热请求抢在首次导航前占用单 sync worker。
- `/me` 只有明确 401 才清会话；网络错误/5xx 放行，后续业务请求仍由统一 401 拦截器兜底。该方案偏可用性，后端接口权限仍是安全边界。
- 动态 import 错误正则覆盖 Chromium（`Failed to fetch dynamically imported module`）、Safari（`Importing a module script failed`）和 Firefox（`error loading dynamically imported module`）常见文案；10 秒 sessionStorage 限流可避免无限刷新。
- `page-login.vue` 相对 HEAD 的 diff 同时包含此前未提交的发货看板预热实现。不能直接整文件提交；应由前端所有者确认这些 hunk 是否属于同一批，或在干净 worktree 中重新组织提交。

## 测试与构建

专项测试：

```text
npx.cmd playwright test tests/e2e/login-flow.spec.js --reporter=list --workers=1
```

两个登录用例均通过：

1. 单击一次登录进入主页、不请求 `/me`、预热晚于主页到达；
2. 深链 `/me` 502 留在主页，401 返回登录页。

组合回归命令共发现 19 个用例并全部执行到末项，但 Playwright 进程在输出完用例后没有自行退出，最终由人工中止，因此不能记为一次正常退出的 `19 passed`。单独运行登录专项同样打印 `2 ok` 后不退出，倾向于 Windows 下 Playwright WebServer/子进程清理问题，需前端环境后续单独收口。

生产构建：

```text
npm.cmd run build:web
```

构建成功（4027 modules，约 40 秒）。另有一个与登录无关的既有 CSS minify 警告：某处源码注释包含 `rad-*/rpd-*`，`*/` 提前结束 CSS 注释；建议另开小任务定位修复。

## 生产日志核实

尝试只读执行 nginx 日志与 gunicorn `ExecStart` 检查。沙箱内首次请求无法解析 SSH 主机；申请受控 SSH 后授权审核超时且命令未执行，故本轮没有取得生产日志证据。

因此当前结论仍是：代码路径强烈支持交接文档中的根因推断，但尚未用生产请求顺序/耗时证实，不能写成“根因已确认”。

## 后续动作

1. 由 Claude Code 在可访问生产 SSH 的环境只读核实 nginx 请求顺序和 Gunicorn 单 sync worker 配置；
2. 在干净前端 worktree 复跑 4 组测试，确认 Playwright 能正常退出；
3. 前端所有者确认 `page-login.vue` 既有预热 hunk 的归属后，按项目规则执行前端部署；
4. 用真实账号确认登录后无 `/api/account/me`，`chart-options` 在主页渲染后约 1.5 秒发出；
5. 只提交确认过的前端 hunk和两份交接文档。未经用户明确授权不要 push。
