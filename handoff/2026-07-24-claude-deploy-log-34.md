# Claude 部署记录：财务导入工作流 D 批（SSE → 短轮询）

日期：2026-07-24

## 后端（对应 handoff-33）

- 提交：`c9ef58b refactor(shipping): use persisted task polling`
- 无数据库迁移。同步 `routes/shipping/__init__.py`，MD5 校验一致，`systemctl reload gunicorn`，
  master PID 未变，`/health`/`/ready` 正常。
- 部署后直接调用 `get_persisted_task_status()` 验证了一个真实生产任务（`resolve_all`，
  `resolved: 250565`）：`status=200`、`Cache-Control: no-store`、`result` 字段完整——与
  `test_shipping_task_reliability.py` 的断言一致。

## 前端

- 提交：`e021301 refactor(frontend): shipping后台任务进度从SSE改为短轮询`
- 新增 `src/utils/shippingTaskPoll.js`（`pollShippingTask`），删除 `shippingTaskRecovery.js`。
- 四处调用点全部替换：`DataImport.vue`（发货导入）、`FinanceImport.vue`（财务导入）、
  `page-data-mgmt.vue`（resolve-all）、`OperatorConfig.vue`（resolve-stale，原本是手写
  800ms×1125次轮询循环，现在统一用共享 poller）。
- 组件卸载（`onUnmounted`）、新任务发起前都会 `stop()` 清理上一个 poller，避免残留 timer。
- `src/views/productViews/page-product.vue` 的产品生命周期 SSE 按交接文档要求原样保留，未纳入
  本次迁移。

## 验证

- `npm run build:web` 通过。
- Playwright 48 用例全绿，含 2 个新增用例：
  1. 验证 resolve-all 全流程不再产生任何 `/import/progress/` SSE 请求，轮询请求间隔
     700ms~2000ms 之间（目标 1s，容忍事件循环抖动），不重叠，`done` 状态后立即停止；
  2. 验证任务进行中离开页面（路由切换、组件卸载）后轮询立即停止，不残留 timer。
- 生产响应时间抽样（`/health` 与 `/api/shipping/tasks/<真实任务ID>` 各 5 次交替请求）：
  均在 14-18ms 内返回，证明这两个端点都不会占住 worker——与旧 SSE 端点会持有连接直到任务
  终态形成对比。
- 部署顺序按交接文档：先部署后端 reload → 验证 `/tasks/<id>` → 部署前端 → 生产响应时间抽样。
- 部署后线上 `index.html` 引用的 JS hash 与本地构建比对一致（`index-DDL0mwDo.js`）。

## 遗留

产品生命周期任务仍用独立 SSE（`/api/product/lifecycle/progress/<task_id>`），未持久化、未纳入
本次迁移，后续需要单独评估是否要复用 `shipping_task` 一样的持久化任务模型。

至此财务导入工作流 A/B/C/D 四批全部完成部署。
