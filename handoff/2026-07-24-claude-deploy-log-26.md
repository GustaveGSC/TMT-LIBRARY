# Claude 部署记录：安全修复、任务租约与图表性能批次（对应 handoff-26）

日期：2026-07-24

## 部署结果

严格按 `handoff/2026-07-24-claude-handoff-26.md` 的顺序执行，全部成功：

1. 确认无运行中导入/重算任务（`shipping_task` 表 running/pending 记录为空）。
2. 数据库全量备份：`/root/backups/tmt_db_20260724_114743_pre_20260724_01.sql.gz`（38.6MB，dump 尾部确认 `Dump completed`）。
3. 上传 `20260724_01_add_shipping_task_lease.py`，MD5 校验一致，`alembic -c alembic.ini upgrade head` 成功：`20260723_02 -> 20260724_01`。生产库 `DESCRIBE shipping_task` 确认 `lease_key varchar(64) UNI` 列及唯一索引 `uq_shipping_task_lease_key` 已生效。
4. 同步 10 个非测试/非迁移文件（models/repository/routes/services/templates/static），逐一 MD5 校验一致。
5. `systemctl reload gunicorn`：master PID 未变（2091，运行 8+ 小时），旧 worker（2112）正常退出，新 worker（10832）正常启动，无崩溃循环（reload 后 8 秒延迟检查 `systemctl status` + `journalctl` 均正常）。
6. `/health` → `{"status":"ok"}`，`/ready` → `{"status":"ready"}`。

## 生产性能验证（响应 handoff 要求）

对修复后的售后发货分母 SQL（`source='shipping'` + 排除售后操作人 + `USE INDEX`）做 `EXPLAIN ANALYZE`：

- **全历史范围**（2024-01-01 ~ 2026-07-23，覆盖表内绝大多数行）：`Table scan on shipping_order_finished`，实际耗时约 5.26s。MySQL 优化器在此范围下判定全表扫描比索引区间扫描更省，`USE INDEX` 只限定候选索引集合、不强制使用，这与 Codex 报告"跨越两年半、覆盖绝大多数行的范围不能指望降到几十毫秒"的预判一致，不是回归。相比修复前生产慢查询日志记录的 7–10s，已有实质改善（主要来自剔除 finance 来源和售后操作人的行，扫描行数减少）。
- **典型近90天范围**（2026-04-25 ~ 2026-07-23，仪表盘默认/常见查询窗口）：命中 `Index range scan using ix_sof_source_date`，实际耗时约 **324ms**，相比修复前的 7–10s 有数量级改善。这是绝大多数用户实际会触发的路径。

结论：修复对常见使用场景效果显著，全历史无界范围仍受限于低选择性，属已知权衡，建议按原计划观察一周慢查询日志/buffer pool miss 后再评估是否需要更激进的索引策略。

## 待续

- 前端协作项（下一步）：viewer 隐藏仓库筛选保存/编辑入口；`/api/category/tree` 改为挂载时共享 Promise 拉取一次；409 响应展示后端文案 + `data.task_id` 回查。
- 一周后对比 `_get_shipping_agg` 慢查询频率/耗时趋势。
- 按 `handoff/2026-07-24-codex-handoff-25.md` 顺序，下一批进入售后正确性治理（重复确认幂等、`_active_log_ctx` 状态隔离、分页上限、型号删除引用保护）。
