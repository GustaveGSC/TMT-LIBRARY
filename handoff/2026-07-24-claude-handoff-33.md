# Codex → Claude 交接：财务导入工作流 D 批后端（SSE → 短轮询）

日期：2026-07-24

提交：`c9ef58b refactor(shipping): use persisted task polling`

## 新契约

统一轮询：

```http
GET /api/shipping/tasks/<task_id>
```

- 需要任一 shipping 权限；
- `Cache-Control: no-store`；
- 响应沿用持久化任务完整结构：
  `task_id/task_type/status/progress/result/message/created_at/updated_at/finished_at`。

旧 `/api/shipping/import/status/<task_id>` 保留为完全相同的兼容别名。

旧 `/api/shipping/import/progress/<task_id>` 暂时保留，但已标记废弃；新前端禁止再创建
EventSource。

## 后端行为变化

- 发货导入、财务导入、resolve-all 新任务不再创建 `queue.Queue`；
- 进度和终态只写 `shipping_task`；
- `_task_queues` 不会因无人消费而积累；
- 旧 SSE 端点从数据库状态兼容生成事件，不依赖内存队列；
- reload 恢复、任务租约、取消和 409 接管语义不变。

## 前端轮询映射

建议抽一个共享 `pollShippingTask(taskId, options)`，活动任务每 1 秒轮询：

| 后端 status | 前端事件语义 |
|---|---|
| `pending` / `running` | 使用 `progress`，其 `step/current/total/message` 原样交给现有处理函数 |
| `done` | `{ step: 'done', data: result }`，停止轮询 |
| `cancelled` | `{ step: 'cancelled', message }`，停止轮询 |
| `error` / `interrupted` | `{ step: 'error', message }`，停止轮询 |

要求：

- 组件卸载、用户关闭任务对话框或新任务替代旧任务时清除 timer/AbortController；
- 单次暂时性网络错误可以继续下一轮，401 交给现有统一登录处理；
- 409 响应中的旧 `task_id` 直接进入同一个轮询器；
- 不允许轮询请求重叠：上一次完成后再安排下一次；
- 终态必须立即停止。

需要替换的 shipping 调用点：

1. `DataImport.vue` 发货导入；
2. `FinanceImport.vue` 财务导入；
3. `page-data-mgmt.vue` resolve-all；
4. `OperatorConfig.vue` resolve-stale（旧 `/task-status`）。

`shippingTaskRecovery.js` 可以改造为统一轮询工具，完成后不再需要“SSE error recovery”命名。

## 自动化验证

后端新增/更新测试覆盖：

- `/tasks/:id` 与旧 `/import/status/:id` 响应完全一致；
- 两者返回 `Cache-Control: no-store`；
- 新财务任务启动后 `_task_queues` 仍为空；
- `q=None` 时进度和终态完整持久化；
- 旧 SSE 在无内存队列时仍能读取持久化终态。

全量 pytest、compileall、git diff --check 均通过。

## 部署顺序

前后端可兼容分两步：

1. 先部署后端并 reload；旧前端 SSE 仍可工作；
2. 验证 `/api/shipping/tasks/<真实任务ID>`；
3. 立即部署前端短轮询版本；
4. 启动一个受控任务，在运行期间反复请求 `/health` 和一个普通业务接口，确认不再被 SSE 长连接占住；
5. 检查浏览器 Network：不得再出现 shipping `text/event-stream`，应为间隔约 1 秒、无重叠的短 GET；
6. 验证 done/error/cancelled/interrupted 和 409 接管均停止或继续正确。

## 新发现：产品生命周期仍有独立 SSE

`src/views/productViews/page-product.vue` 仍使用：

```text
/api/product/lifecycle/progress/<task_id>
```

这不是 shipping 任务，也没有纳入本批持久化契约；它在单 sync worker 下同样可能占住 worker。
本批不要把它错误切到 shipping `/tasks`。需要后续单独审查产品生命周期任务状态是否持久化，再迁移。
