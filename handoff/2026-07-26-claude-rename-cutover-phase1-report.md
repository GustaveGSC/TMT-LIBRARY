# resolve_all rename-table cutover：阶段1（安全部署，继续冻结）完成报告

日期：2026-07-26

## 代码审查要点

- `ShippingOrderFinishedNext` 通过 `ShippingOrderFinished.__table__.to_metadata(db.metadata,
  name='shipping_order_finished_next')` 直接从正式表模型派生，结构性防漂移（不是靠测试事后catch，
  未来正式表加列会自动同步到 standby 定义）——比交接文档描述的"有自动化测试防止漂移"更强。
- `publish_full_generation()`：advisory lock 内先校验 standby 归属+任务状态+行数未被并发改变，
  更新 standby 代际标记 `row_count/published_at` 并把任务 `progress/result` 写入（此时状态仍是
  `committing`）、显式 `connection.commit()`，然后执行**一条** `RENAME TABLE`（6 个动作，测试
  `test_mysql_generation_swap_is_one_atomic_rename_statement` 用 mock connection 精确断言
  只发一条语句），最后单独 `_finalize_published_generation()` 把任务改成 `done`。
- 异常处理：任何一步失败都重连查询**正式代**标记的 task_id，如果等于当前 task_id 就说明 rename 已经
  成功（哪怕客户端因 socket 超时以为失败），据此把任务补写为 done 而不是误报失败；否则原样抛出，
  交给下次 worker 启动的 `interrupt_running_tasks()` 走"committing → interrupted"分支。
- 启动恢复逻辑与上面异常处理用的是同一套判定：查正式代标记 task_id，如果该任务在 DB 里还是
  `committing`，先补 done，再把其余 `pending/running/committing` 状态的任务统一标记 interrupted——
  精确复现交接文档里"故障点→正式代标记→恢复结论"的四行矩阵，代码逻辑和文档描述一致。
- `report_internal_error()` 三处误用签名（`report_internal_error(exc, context=...)`）已修正为
  `report_internal_error(context=...)`，与 `error_handling.py` 里的真实签名一致。
- `resolve_stale` 新增 `MAX_STALE_RESOLVE_ORDERS`（默认10000）硬上限，超限直接 error，不建
  staging、不动正式数据。

## 本地验证

- 后端全量 246 项测试通过；`compileall`、`git diff --check` 通过；Alembic 单头 `20260726_01`。

## 生产阶段1 执行记录

1. 确认无运行中 shipping 任务。
2. 全量备份：`/root/backups/tmt_db_20260726_093216_pre_rename_cutover.sql.gz`（确认
   `Dump completed`）。当前磁盘可用 22GB（`/dev/vda3` 40G，已用19G，47%）。
3. 上传 migration/model/repository/route/service/两个维护脚本共 7 个文件，MD5 校验全部一致。
4. `alembic upgrade head` → `20260726_01`，无报错。
5. `SHOW CREATE TABLE` 对比正式表与 standby：除 `AUTO_INCREMENT`（正式表有数据、standby 为空，
   预期差异）外，列定义、字符集、排序规则、索引、引擎完全一致。
6. 四张代际表（正式表+standby+两个marker）均为 InnoDB；正式表确认 0 条入向外键、0 条出向外键、
   0 个触发器；两个 marker 表初始行均为 `id=1, task_id=NULL`（符合迁移预期，未发布任何代）。
7. 确认数据库账号（`root@%`，`WITH GRANT OPTION`）具备 `ALTER/CREATE/DROP` 等 RENAME TABLE 所需
   权限，不是假设，是直接 `SHOW GRANTS` 核实的。
8. 确认生产 `.env` 仍未设置 `ALLOW_FULL_RESOLVE`，`systemctl reload gunicorn`。Master PID 未变，
   journalctl 无异常（新的代际感知 `interrupt_running_tasks()` 在正常场景——无任何已发布代——下
   启动执行无报错）。`/health`、`/ready` 正常。
9. 真实 HTTP 请求（真实用户会话，非 mock）验证 `POST /api/shipping/resolve-all` 仍立即返回 503
   `全量重建正在维护优化，当前暂不可用`；确认这次探测**没有**产生任何新的 `shipping_task`/
   staging/target/standby 记录（`shipping_order_finished_next` 仍 0 行，正式表行数
   692,003 保持不变，与门禁前完全一致）。

## 结论

阶段1（安全部署，继续冻结）全部门禁通过，代码质量审查没有发现问题。生产现在运行的是新的
rename-table cutover 实现，但功能仍完全冻结（`ALLOW_FULL_RESOLVE` 未设置，接口立即 503），
与阶段1的目标"先把代码和表结构安全落地，行为不变"完全一致。

## 下一步：阶段2（低峰门禁）需要用户决定时机

阶段2 会临时设置 `ALLOW_FULL_RESOLVE=true` 并真实触发一次全量重算（预计包含 standby 构建 + 一次
真实 `RENAME TABLE`），全程监控磁盘增长、`/health`/`/ready`/图表查询延迟、MDL 锁等待、rename 实际
耗时、切换前后数据一致性。这是本次冻结解除后第一次真正让新机制跑一次完整全量重算，建议：

- 选择业务低峰时段（比如非工作时间或周末，视你对"低峰"的判断，我这边没有生产流量数据能替你做
  这个判断）；
- 我会在测试前再做一次即时门禁前重新备份；
- 全程前端保持禁用、不对外暴露，只通过我这边的脚本触发和监控。

你希望现在就进行阶段2，还是先约定一个具体时间窗口？
