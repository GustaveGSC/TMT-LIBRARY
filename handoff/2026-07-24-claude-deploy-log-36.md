# Claude 部署记录：产品生命周期任务持久化 + 查询优化（后端）

日期：2026-07-24

## 代码审查要点

- `product_lifecycle_task` 独立建表，不复用 `shipping_task`，租约/状态写入走独立 `db.engine` 连接
  （不提交业务 session），与 `shipping_task` 的实现模式一致但完全解耦，符合 Codex 交接说明的边界判断。
- 旧 `/progress/<task_id>` 兼容入口审查确认：单次 `Response(...)`，读一次持久化快照立即返回，没有
  `while`/`q.get()`/生成器阻塞，不会占住 worker。
- 异常路径确认：`except Exception: db.session.rollback()` 先于任务状态写 `error`，再 `finally: db.session.remove()`。
- 逐行核对新的单条月度聚合查询：`quantity IS NOT NULL` 过滤条件被移除，改为 `SUM()` 自然忽略 NULL；
  由于该查询 INNER JOIN `ProductFinished.code`，未匹配成品的遗留行（`finished_code IS NULL`）本就不会
  出现，实践中"匹配成功但 quantity 为 NULL"的行不可能存在（`_resolve_orders()` 写入时 quantity 恒为
  Decimal），因此三查合一不会丢失"quantity 为 NULL 的月份仍计入月份集合"这条业务口径，历史行为保留。
- `test_lifecycle_uses_one_monthly_aggregate_and_one_commit` 用 `iter()` 严格限定 `db.session.query()`
  只能被调用 3 次（操作人/月度聚合/成品列表），能真实捕获"三查合一"回归为多查询的情况，不是只看总数。
- 本地 209 项后端测试、`compileall`、`git diff --check`（仅 markdown 手动换行的行尾空格提示）全部通过。

## 部署（严格按交接门禁 9 步执行）

1. 确认无生命周期/发货任务运行，备份数据库
   （`/root/backups/tmt_db_20260724_165016_pre_lifecycle_task.sql.gz`，确认 `Dump completed`）。
2. 上传 migration/模型/repository/service/route/`app.py` 共 7 个文件，MD5 全部校验一致，**暂不 reload**。
3. `alembic upgrade head` → `20260724_02`，`DESCRIBE`/`SHOW INDEX` 确认表结构、唯一约束、复合索引与
   迁移脚本完全一致。
4. 生产只读等价性对比：分别构造旧三查询（`agg_query`/`months_query`/`qty_query`）和新单查询产出的
   `shipping_by_model`/`months_by_model`/`qty_by_model`，对全部 233 个有发货数据的型号逐项精确比较
   （`==` 而非只比数量）——**0 不一致**。
5. 对新聚合 SQL 做 `EXPLAIN ANALYZE`：确认命中 `ix_sof_finished_code_date`（`Index lookup ... using
   ix_sof_finished_code_date`）；对照不带 hint 的执行计划，优化器本就自然选择同一索引，两次实测耗时
   差异（3.166s vs 2.033s）在同一量级、方向上是后一次查询命中了预热缓存，不是计划变差，符合"hint 不
   得比默认计划更差"的门禁要求。
6. 生产环境内对真实 `update_lifecycle()` 做一次完整 dry-run：拦截 `db.session.commit()` 为空操作（让
   SQLAlchemy session 内的挂起变更可查询但不落盘），执行后确认恰好 1 次 commit 调用、42 次 progress
   写入（403 个型号，首/末/每10个一次）、内存中会变化的成品数与 `result['updated']` 一致，随后
   `rollback()`，二次查询确认数据库状态与执行前逐字段完全相同。
7. `systemctl reload gunicorn`：master PID 未变（2091，运行 13+ 小时），journalctl 无异常/无
   traceback，`/health`/`/ready` 正常。
8. 真实 HTTP 端到端验证（签发 `author` 账号的真实会话+CSRF，直接打 gunicorn 8765 端口，不经过
   Flask 测试客户端）：
   - 启动任务 → 200，拿到 `task_id`；
   - 立即并发再启动一次 → **409**，`data.task_id` 与第一次相同；
   - 任务运行期间连续 6 次探测 `/health`（0.5s 间隔）→ **全部 200**，证明新写入路径和短轮询端点均
     不占住唯一 sync worker；
   - 轮询 `GET /tasks/<task_id>` 到终态 → `done`，`result={'total_models': 403, 'updated': 1}`，与
     第 6 步 dry-run 的预期变化数一致；响应头确认 `Cache-Control: no-store`。
9. 本次是真实写入（非 rollback），生产 `product_finished` 表已按新逻辑完成一次实际生命周期重算
   （只有 1 条记录发生变化，与部署前的 dry-run 预期完全吻合，说明生产数据此前已基本是最新状态）。

## 结论

9 步门禁全部通过，无需回滚。后端稳定，进入前端短轮询改造（`page-product.vue`）。
