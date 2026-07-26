# 交接说明 · Claude → Codex（第三十二轮，Codex 额度恢复，解冻任务并给出优先级）

日期：2026-07-25

Codex 额度恢复，解冻"发货任务取消、确定性解析与安全重算"这条任务线。冻结期间生产状态没有变化：
`ALLOW_FULL_RESOLVE` 仍未设置，`POST /api/shipping/resolve-all` 仍立即 503，确定性解析和"完成发货"
元数据口径已经在增量导入路径生效（见 `handoff/2026-07-25-codex-handoff-31.md`）。

## 冻结前的完整状态

见 `handoff/2026-07-25-claude-staging-cutover-gate-test-report.md`（门禁失败详情：692,003 行无
WHERE 条件的全表 DELETE 超过 `read_timeout=30`，生产实测 560 秒后失败；数据安全性验证通过，
但失败清理路径本身也失败，残留了约 94 万行孤儿 staging/target 数据，已手动清理）。

## 恢复后的优先级（按你之前给出的判断，我同意这个顺序）

### 1. 最高优先级：resolve_all 的 rename-table 型 cutover 重新设计

不要重试同一个全表 DELETE 方案，也不要简单分块改正式表（会重新引入"取消/失败时数据处于中间态"的
问题）。按你自己在冻结前给出的方向设计：

- 构建"下一代正式表"（新表或等价机制），最后用 `RENAME TABLE` 做原子切换；
- 旧表/旧代异步清理，不阻塞 cutover 本身；
- 需要同时补：
  1. 失败清理的独立连接与退避重试（对应下面第2条的次生问题）；
  2. 可观测的遗留 staging/临时表清理机制（目前"一小时后下次重算触发"的懒清理不够，孤儿数据可能
     长期无人发现，考虑要不要一个真正的定时任务，或至少让 `/health`、监控能看到"当前有未清理的
     临时表"这种信号）；
  3. 磁盘余量预检（cutover 前检查磁盘空间是否够放下一份完整新表）；
  4. rename 失败、reload 竞态、取消、回滚，四类场景各自的门禁测试。
- 生产数据量此时是 692,003 行（比 B 批设计时的参考值又涨了约 3 万），设计时按"还会继续变大"假设
  留余量，不要刚好卡在当前规模。

这批完成后，"新旧口径混用窗口"（增量导入已用新规则，历史数据还是旧规则）才能真正关闭，是当前最
紧迫的事。

### 2. 顺带修复：`cleanup_resolve_staging()` 失败清理路径的健壮性

门禁测试发现：全表 DELETE 超时断连后，紧跟着的清理调用大概率撞上同一个连接/资源问题，自己也失败，
异常被 `except Exception as cleanup_exc: report_internal_error(...)` 静默吞掉，没有重试、没有告警
升级。同时这次实测还暴露了一个独立的代码 bug：

```
TypeError: report_internal_error() got multiple values for argument 'context'
```

（见 `journalctl` 里 `_run_staged_resolve` 那次异常处理本身抛出的 TypeError，说明清理失败后连
"记录一条清晰的内部错误"这一步都没做成，只留下一个更难排查的二次异常）。这个签名 bug 请顺带修掉，
两个问题都在同一段异常处理代码附近，适合一起改。

### 3. resolve_stale（局部重算）加防护或先验证

冻结前判断：resolve_stale 用的是 subset cutover（`DELETE ... WHERE EXISTS(...)`，不是全表
DELETE），理论上更安全，但从未在有真实 `is_stale` 数据的情况下压测过——生产当前 `is_stale=0`，
这条路径的规模上限完全没有实测依据。目前它没有被 fail-fast 挡住，仍然完全开放。

请评估：是否要在 rename-table 方案落地前，也给 resolve_stale 加一个类似的规模预检或临时开关（比如
如果一次要处理的 stale 订单数超过某个阈值就先拒绝，避免复刻同样的超时问题）；或者如果你判断 subset
DELETE 在可预见的 stale 规模下足够安全，说明理由即可，不强制要求和 resolve_all 一样的重新设计。

### 4. 暂不启动：D 批压测

原方案的生产规模压测矩阵（1千/1万/5万/10万行、并发、资源峰值）等 rename-table 方案完成并通过前三
项门禁后再排期，不需要现在开始设计。

## 给 Claude 的后续

等 rename-table 方案的后端契约稳定后，我这边配合：

- 解除 `ShippingMaintenancePage.vue` 里 `FULL_RESOLVE_TEMPORARILY_DISABLED` 临时禁用；
- 恢复 `tests/e2e/shipping-resolve-cancel.spec.js`、`task-conflict-409.spec.js`、
  `shipping-task-polling.spec.js` 里被 skip 的 resolve-all 相关用例；
- 如果新设计对任务进度事件的字段/阶段有变化（比如多了"清理旧表"阶段），同步更新前端的阶段文案。

契约稳定前不预先动前端代码。
