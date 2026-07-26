# resolve_all rename-table cutover 重设计交接

日期：2026-07-26  
分支：`codex/shipping-rename-cutover`  
状态：后端实现完成，本地验证通过；**未部署，`ALLOW_FULL_RESOLVE` 必须继续保持未设置**

## 一、结论

此前 `DELETE 692003 rows + INSERT SELECT` 的 cutover 已完全移除出 full rebuild 路径。
`resolve_all` 现在：

1. 清空并认领与正式表完全同构的 `shipping_order_finished_next`；
2. shipping、finance 两个 source 分块直接写入 standby，每块独立提交；
3. 完整构建和校验后执行取消/CAS 门禁；
4. 用**一条** MySQL `RENAME TABLE` 同时交换正式/standby 数据表和两张代际标记表；
5. 根据正式代标记完成任务状态；旧 worker/reload 恢复也使用同一标记判断是否已经发布。

生产冻结状态没有改变：路由仍默认 503，只有显式设置 `ALLOW_FULL_RESOLVE=true` 才可能执行。

## 二、为什么还需要代际标记

MySQL 8 的 InnoDB `RENAME TABLE` 是原子、crash-safe 的 DDL，但 DDL 会隐式结束事务，不能与
`shipping_task=done` 放进同一个事务。因此同时交换：

- `shipping_order_finished` ↔ `shipping_order_finished_next`
- `shipping_order_finished_generation` ↔
  `shipping_order_finished_generation_next`

标记表固定只有 `id=1` 一行，standby 标记在发布前写入 task_id，并随数据表一起原子交换。

恢复矩阵：

| 故障点 | 正式代标记 | 启动恢复结论 |
|---|---|---|
| CAS 前退出 | 旧 task_id | cancelled/interrupted，正式数据不变 |
| CAS 后、rename 前退出 | 旧 task_id | committing → interrupted |
| rename 后、task done 前退出 | 新 task_id | committing → done |
| task done 后退出 | 新 task_id | 保持 done |

cutover 和启动恢复都持有同一个 MySQL advisory lock，避免 graceful reload 时新旧 worker 竞态。

参考 MySQL 官方说明：InnoDB 的 `RENAME TABLE` 在 MySQL 8 中要么整体提交、要么整体回滚；DDL
不是事务型 DDL，不能和其他 DML 组成同一事务：
https://dev.mysql.com/doc/refman/8.0/en/atomic-ddl.html

## 三、数据库迁移

新增 revision：`20260726_01`，down revision：`20260725_01`。

新增：

- `shipping_order_finished_next`
- `shipping_order_finished_generation`
- `shipping_order_finished_generation_next`

MySQL migration 使用 `CREATE TABLE shipping_order_finished_next LIKE
shipping_order_finished`，确保列类型、排序规则、默认值、行格式和所有性能索引完全一致。代码 metadata
也从正式表克隆 standby，并有自动化测试防止以后只改正式表、忘记同步 standby。

运行时在开始构建和最终切换前双重检查：

- 四张代际表都是 InnoDB；
- 正式表和 standby 的列/索引签名完全一致；
- 正式表没有入向/出向外键；
- 正式表没有 trigger；
- 两个临时 swap 表均不存在。

## 四、构建、回切与退役代

full rebuild 不再写 `shipping_order_finished_staging`，避免同时保留 live + staging + standby
三份大数据。它直接向带完整正式索引的 standby 分块写入。

发布成功后，旧正式代保留在 `shipping_order_finished_next`，不会立即 TRUNCATE：

- 验收失败：执行
  `python backend/scripts/rollback_shipping_generation.py --task-id <UUID> --confirm-task-id <UUID>`
  原子反向交换；
- 验收通过：执行
  `python backend/scripts/cleanup_shipping_retired_generation.py --published-task-id <UUID> --confirm-task-id <UUID>`
  释放旧代磁盘；
- 如不显式清理，下一次 full rebuild 开始时也会先 TRUNCATE standby。

两个维护脚本都要求 task_id 重复确认，并再次核验正式代/standby 状态。

## 五、失败清理与错误上报修复

`cleanup_resolve_staging()` 改为：

- staging 和 target 按 5000 行分块 DELETE、每块提交；
- 失败后使用新连接，0.25s / 0.5s 退避，最多三次；
- full rebuild 未发布 standby 使用 advisory lock + owner task_id 核验后 TRUNCATE；
- 延迟清理同时识别“task 行已被 7 天保留策略删除”的孤儿 task_id。

三处错误调用已从错误的：

```python
report_internal_error(exc, context='...')
```

改为真实签名：

```python
report_internal_error(context='...')
```

新增测试直接触发清理失败分支，确认不会再被 `TypeError` 覆盖；另有测试模拟前两次连接失败、第三次
新连接成功并完成清理。

## 六、resolve_stale 规模保护结论

当前生产 stale=0，无法证明大范围 subset DELETE 在 30 秒 read_timeout 内安全，因此不能把
“subset 通常较小”当成保证。

已增加默认上限：

- `MAX_STALE_RESOLVE_ORDERS=10000`
- 统计单位为不同的 `(ecommerce_order_no, source)`；
- 超限时任务直接进入 error，公开说明实际数量与上限，不创建 staging、不修改正式数据；
- 环境变量必须为正整数。

10000 是临时防护值，不是压测结论。门禁应分别测试 1000 / 5000 / 10000 个订单范围，再决定是否
降低或提高。

## 七、本地验证

- 后端全量测试通过（最终数量以合并审查时输出为准）。
- 新增/强化覆盖：
  - standby 与 live metadata 列、索引完全一致；
  - migration 单头和三张新表/marker 初始行；
  - full generation 原子交换；
  - rename 后、task done 前的启动恢复；
  - 保留旧代并原子回切；
  - MySQL 路径只有一条包含六个 rename 动作的语句；
  - task 状态变化时拒绝发布；
  - cleanup 新连接重试及错误上报签名；
  - stale 上限边界。
- `python -m compileall -q backend` 通过。
- `git diff --check` 通过。
- `alembic heads`：`20260726_01 (head)`。

本机没有 MySQL client / Docker，因此 MySQL 物理 DDL、权限、MDL 等待和磁盘门禁必须由部署方在
生产同版本环境完成，不能用 SQLite 自动化测试替代。

## 八、部署与门禁顺序

### 阶段 1：安全部署，继续冻结

1. 全量备份数据库和当前后端文件。
2. 上传 migration、model、repository、service、route 和两个维护脚本，尚不 reload。
3. `alembic upgrade head` 到 `20260726_01`。
4. 核验 `SHOW CREATE TABLE shipping_order_finished` 与 `_next`，索引/排序规则一致。
5. 核验四张代际表都是 InnoDB，正式表无 FK、无 trigger。
6. 核验运行账号具备单条 rename 所需权限；不要假定 database-wide grant。
7. 保持生产 `.env` **没有** `ALLOW_FULL_RESOLVE=true`，reload。
8. 验证 `/health`、`/ready`、gunicorn 日志；直接 POST `/resolve-all` 仍应立即 503。

### 阶段 2：低峰门禁

门禁前重新备份，并确认可用磁盘至少容纳：

- 当前 live 全部 data + indexes；
- 新 standby 全部 data + indexes；
- target 表、binlog/undo/临时空间；
- 至少 30% 额外安全余量。

临时设置 `ALLOW_FULL_RESOLVE=true` 并 reload，只通过直接 API 触发，前端继续禁用。全程记录：

- standby 构建耗时与磁盘增长；
- `/health`、`/ready`、普通 chart 查询 p50/p95/max；
- `performance_schema.metadata_locks` / processlist 中的 MDL 等待；
- rename 实际耗时；
- live marker task_id、任务 result、source 分组行数和业务 checksum；
- standby 是否完整保留旧代。

### 阶段 3：判定

- 任一结构、权限、磁盘、结果或延迟门禁失败：立即保持前端禁用和 503；如 rename 已完成，用 task_id
  执行回切脚本。
- 全部门禁通过：再由用户决定长期设置 `ALLOW_FULL_RESOLVE=true`，Claude 恢复前端按钮与 6 个
  skipped Playwright；观察窗口结束后运行清理脚本释放旧代。

## 九、明确未包含

- 未部署、未修改生产环境变量。
- 未解除前端禁用。
- 未开始 D 批压测。
- 未把 stale 上限视为最终容量结论。

