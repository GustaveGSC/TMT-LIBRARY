# 产品生命周期任务持久化与查询优化交接

日期：2026-07-24  
分支：`codex/product-lifecycle-task`  
部署：尚未部署；由 Claude Code 审查并执行

## 本批完成内容

### 1. 持久化任务与互斥

- 新增 Alembic revision `20260724_02` 和 `product_lifecycle_task`。
- 固定唯一租约 `product_lifecycle_update`，同一时间只能运行一个生命周期更新。
- 重复启动 `POST /api/product/lifecycle/update` 返回标准 409：

```json
{
  "success": false,
  "message": "已有产品生命周期更新任务正在运行，请等待其结束后重试",
  "data": {"task_id": "<当前任务>"}
}
```

- 新 worker 启动时将遗留 `pending/running` 任务标记为 `interrupted` 并释放租约。
- 任务状态写入使用独立数据库连接，不会提交生命周期业务 session。
- 生命周期数据改为一次事务提交；异常时显式 rollback，避免半更新。

### 2. 短轮询契约

- 新增 `GET /api/product/lifecycle/tasks/<task_id>`，需要 `product:view`。
- 响应字段与任务通用结构一致，`Cache-Control: no-store`。
- 旧 `/progress/<task_id>` 暂时保留为无阻塞兼容入口：只读取一次数据库快照并立即关闭连接，不再等待
  `queue.Queue`，因此不会占住唯一 sync worker。新前端仍必须切到 `/tasks/<task_id>` 短轮询。
- 删除模块级内存队列和阻塞式 SSE generator。

### 3. 生命周期计算优化

- 原来的首尾月、月份集合、月度数量三条重复 JOIN 聚合，合并为一条“型号 + 月份 + 数量”查询。
- 首月、末月和有数据月份在 Python 中从同一份月度结果推导。
- 保留原有业务口径：未增加 `source` 过滤；仍排除售后操作人；数量为 NULL 的月份仍会进入月份集合。
- 使用现有 `ix_sof_finished_code_date` MySQL hint。
- 原来每个型号一次 `commit()` 改成全部计算完成后一次提交。
- 进度持久化由每型号一次降为首项、末项及每10个型号一次，避免用任务表写入重新制造大量小事务。

## 自动化验证

- 新增5项生命周期测试：
  - 两线程并发租约竞争；
  - reload 中断恢复及租约释放；
  - 409 响应和当前 task_id；
  - 持久化短轮询及旧入口非阻塞快照；
  - 单次月度聚合、索引 hint、一次业务提交。
- 更新 Alembic 线性历史和建表验证。
- 更新 `create_app()` app-context 回归测试，确保两个启动恢复调用都位于应用上下文。
- 全量后端测试通过。
- `compileall`、`git diff --check` 通过。
- Alembic 单头：`20260724_02 (head)`。

## Claude 审查重点

1. 确认 `product_lifecycle_task` 独立于 `shipping_task` 的边界可接受。
2. 核对旧 EventSource 兼容入口是“一次响应立即关闭”，不存在 `q.get()`、生成器等待或内存队列。
3. 核对异常路径先 rollback 业务事务，再将任务写为 error。
4. 核对原查询中 `quantity IS NULL` 的月份没有因三查合一丢失。
5. 前端 409 时接管 `data.task_id`，不要重新启动第二个任务。

## 生产部署门禁

这批同时涉及表结构、启动时查询和真实生命周期数据写入，部署顺序不能调整：

1. 确认当前没有人在运行生命周期更新，并完整备份生产数据库。
2. 上传 migration、模型、repository、service、route、app 文件，但先不要 reload。
3. 执行 `alembic upgrade head`，确认 current 为 `20260724_02`，检查新表唯一约束和索引。
4. 在隔离进程中对生产数据执行只读对比：
   - 旧三查询生成的 `shipping_by_model/months_by_model/qty_by_model`；
   - 新单查询生成的三个字典；
   - 逐型号精确比较，必须 0 不一致。
5. 对新聚合 SQL 做 `EXPLAIN ANALYZE`，确认使用
   `ix_sof_finished_code_date`，记录扫描行数和实际耗时。若 hint 计划反而更差，停止部署并退回 Codex。
6. 对生命周期写入路径开启事务执行一次，记录拟更新结果后 rollback，再查询确认数据库没有变化。
7. 门禁全部通过后 reload；连续检查 status/journal、`/health`、`/ready`。
8. 实测启动任务、短轮询到终态、第二次并发启动返回409；确认任务期间 `/health` 仍能快速响应。
9. 后端稳定后立即部署 Claude 的前端短轮询改动。

特别注意：新 `app.py` 启动时会查询 `product_lifecycle_task`，所以必须先迁移建表、后 reload。顺序反过来会导致
worker 启动失败。

## 给 Claude 的前端契约

- 启动：`POST /api/product/lifecycle/update`
- 查询：`GET /api/product/lifecycle/tasks/<task_id>`，建议每秒一次、不重叠
- 活动态：`pending | running`
- 终态：`done | error | interrupted`（当前没有取消入口）
- 进度读取 `data.progress`：
  - 准备：`{step:"preparing",current:0,total:0}`
  - 处理：`{step:"processing",current,total}`
  - 完成：`data.result={updated,total_models}`
- 409：显示后端文案并接管返回的 task_id。
- 组件卸载或启动新轮询前清理 timer。

前端提交应保持独立，补 Playwright 覆盖正常轮询、409接管、终态停止和卸载清理。
