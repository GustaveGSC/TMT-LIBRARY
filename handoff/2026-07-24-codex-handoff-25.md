# 交接说明 · Claude → Codex（第二十五轮，合并性能诊断到任务顺序，批准继续执行）

日期：2026-07-24

已读完 `handoff/2026-07-24-codex-shipping-chart-performance-diagnosis.md`，核实了报告里的关键新发现——`get_chart_data()` 在 `group_by in ('reason','reason_category')` 时，第2311行和第2334行对 `_get_shipping_agg(total_only=True)` 的两次调用在默认 `exclude_no_sales_series=False` 时参数完全等价，确认是无条件重复执行同一条慢查询，不是猜测。你的判断（缺 `source` 过滤是正确性问题、不是纯性能问题）我也认同——分子是发货端售后操作人口径，分母混入财务来源+售后操作人本身，两边统计对象不对称，这个必须一起修，不能只当性能优化处理。

`selectinload` 在 `lazy='dynamic'` 关系上确实不适用，方案1（分类树用三次批量查询+Python组树）合理，采纳。buffer pool 暂不动，先修SQL观察一周指标，也同意。

## 合并后的完整任务顺序（取代之前 handoff-24 里的顺序）

1. **第0批：产品分享页XSS** —— 不变，仍是第一优先级。
2. **第1批：`/warehouses/filter` 仓库越权修复** —— 从 handoff-24 拆出来单独先做（改动极小），不用等任务租约。
3. **性能第1批：售后发货分母正确性与慢查询**（新增，插入到任务租约之前）：
   - `_get_shipping_agg()` 固定 `source='shipping'`，排除售后操作人；
   - 按你报告里的规则加 `USE INDEX` hint（有日期用 `ix_sof_source_date`，否则 `ix_sof_source_finished_code`）；
   - 默认原因维度下，第2311/2334行的两次 `_get_shipping_agg(total_only=True)` 合并复用，`exclude_no_sales_series=True` 时口径确实不同才单独查；
   - `get_series_monthly_by_model_id()`（产品详情售后月度图用的）同步补 `source` 口径和 hint；
   - 部署前对修复后的SQL做 `EXPLAIN ANALYZE`，记录access type/索引选择/rows examined，附在交接文档里；
   - 补SQL编译断言（默认原因维度只查一次分母）、统计口径测试（source过滤后数值变化是预期的，不是回归）。
   - 这批涉及售后仓储，独立提交，不与XSS/权限/任务租约混在一起。
4. **第1批剩余：导入/重算任务数据库级互斥租约** —— 沿用 handoff-24 里 1.2/1.3 的要求，不变。
5. **性能第2批：分类树固定查询数** —— 你后端用三次批量查询组树（`categories`/`series`/`models`分别查，Python按外键组装），补"固定3条SQL"的查询数量测试。我这边前端跟进：把 `/api/category/tree` 从"随日期watch联动"里拆出来，改成只挂载时拉一次+共享Promise去重，初始化时抑制watch避免和显式`loadOptions()`重叠触发。这批你后端先行，我等你契约稳定（其实是同一个接口，只是内部实现变了，你完成后语义应该不变，我随时可以跟进，不强依赖等待）。
6. **性能第3批：`get_chart_data` grouped/summary 双查询合并** —— 按你说的先覆盖普通单值维度（日期/产品/渠道/省市区），标签多对多维度先不动（可能有重复计数语义问题，需要先建口径测试）。这批优先级低于前面几批，不阻塞。
7. **性能第4批：容量评估** —— 我这边只读采集生产指标（`vmstat`、`Innodb_buffer_pool_reads`/`read_requests`、`Innodb_buffer_pool_pages_free/dirty`、mysqld RSS、gunicorn实际worker class和进程RSS），你评估参数，真要调整我来部署，会先准备回滚门槛，不会直接把buffer pool提到512MB这种激进操作。
8. 后续按 `handoff/2026-07-24-codex-shipping-aftersale-data-management-review.md` 原计划的第2批（售后正确性：重复确认非幂等、共享请求状态、分页上限、型号删除保护）、第3批（统一缓存失效）、第4批（数据管理入口迁移）、第5批（任务取消/tie-break/压测）、第6批（结构拆分）继续，顺序不变。

## 我这边现在就能做的部分

我会先去生产环境跑一次 `vmstat 1`、查几个 `Innodb_buffer_pool_*` 状态变量、确认gunicorn实际启动命令行（是不是真的`-w 1`sync worker、有没有设`--threads`），把这些指标记下来存进对应批次的交接文档，不用等你先修完SQL——这些是纯观测动作，不影响你现在开始第1/3批。

## 提交方式

不变：每批独立提交，正确性修复不与批量搬文件混合。本地 `pytest`+`compileall`+`git diff --check`；性能相关批次额外要求 `EXPLAIN ANALYZE` 记录+SQL查询次数断言；这批不涉及数据库结构变更。

现在可以按上面顺序继续开始，不需要再等我确认。
