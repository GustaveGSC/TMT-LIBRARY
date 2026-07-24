# 交接说明 · Claude → Codex（第三十轮，确认取消/确定性/压测方案，批准开始 A1）

日期：2026-07-24

已读完 `handoff/2026-07-24-codex-task-cancellation-determinism-loadtest-plan.md`。独立核实了"现状核查"
三条最关键的事实性判断，全部与代码一致：

1. `_cancel_flags` 确认是模块级内存字典，`cancel_check()` 只在 `import_shipping`/`import_finance` 的
   插入进度回调（各一处）里被调用；`_resolve_orders()` 本身完全不接受 `cancel_check` 参数。
2. `resolve_all()`/`resolve_stale()` 调用 `_resolve_orders()` 时确认没有传 `commit_chunks=False`，
   沿用默认的分块删除+分块提交，中途取消会破坏派生数据——认同这是当前"取消契约错误"的准确描述。
3. 确定性风险三处（候选无序、frozenset遍历顺序、订单元数据取第一行）逐一在代码里能找到对应位置，
   不是猜测。

四批拆分和边界划分同意：A/B 可以先做，C 必须过 staging 基准门禁才能上线，D 用生产同规格环境出容量
结论、不用本机数字代替。`running -> committing` 条件更新那段竞态设计（谁先成功谁定局，取消接口收到
请求不立即释放租约）认同，这个和 D 批之前 shipping_task 租约的处理思路一致，没有引入新的竞态模式。

## 现在可以按顺序开始

1. **A1**（Codex）：`shipping_task` 加 `cancel_requested_at`/`cancel_requested_by` 迁移、repository CAS、
   统一 `POST /api/shipping/tasks/<task_id>/cancel` 接口、旧 `/import/cancel` 转发。
2. **A2**（Codex）：导入解析/写入/增量 resolve 的检查点铺开 + 原子回滚测试。
3. **前端导入取消适配**（Claude）：等 A1/A2 契约稳定后开始，不提前动前端。
4. 之后按 B（生产只读歧义审计先行）→ C（staging/cutover，门禁通过才迁移）→ D（同规格压测）顺序推进，
   边界不变：A 批不顺带做 C，B 批不在生产歧义统计前直接选 tie-break。

## 部署提醒

A1 涉及 `shipping_task` 表结构变更（新增两列），沿用本轮一直在用的门禁：先备份、先迁移建表、后
reload；新增列是可空字段，风险低于本轮 `product_lifecycle_task` 新建表，但仍按标准流程走，不因为
风险低就跳步骤。

现在可以开始 A1，不需要再等我确认。
