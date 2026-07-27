# resolve_stale 按影响范围标记：只读设计

日期：2026-07-27

性质：只读设计与源码/生产只读核验；未改代码、未标记订单、未调整 `MAX_STALE_RESOLVE_ORDERS`。

## 一、目标与边界

已确认的产品决策是：下列规则变更不再一律要求 `resolve_all`，而是标记真正可能受影响的
`(ecommerce_order_no, source)`，随后由 `resolve_stale` 重建。

1. 成品—组件关系（`product_finished_packaged`）的新增/移除；
2. 产成品等效件对（`packaged_equivalent`）的新增/移除；
3. 销退仓库排除开关（`return_warehouse_filter.is_excluded`）的变化。

本设计只覆盖上述三类。成品编码、解析算法、候选排序、导入原始数据格式等变化仍应先单独判断，不能自动套用本设计。

## 二、现状与必须修复的语义缺口

当前 `resolve_stale` 的消费端完整：读取 `shipping_order_finished.is_stale=True` 的订单对，写 task 隔离的
staging，再以短事务替换该范围正式结果。但没有任何生产路径把 `is_stale` 写为 `True`；导入和重算反而都
显式写入 `False`。因此现有按钮通常没有工作量。

另有两个不能在实施时忽略的事实：

- `_resolve_orders()` 对每个 source 的订单都读取 `shipping_record` **和**同订单的 `return_record`。规则对
  销退组件的影响，会改变 `return_quantity`/`actual_quantity`，不能只查正向发货记录。
- 成品组合是全订单的贪心过程。某个规则变化即使最终改变的是另一个成品，其订单也必然提供了该变化规则
  可消费的组件。因此先得到“安全超集”再标 stale 是正确优先级；不能为减少数量而冒漏标风险。

## 三、统一的影响范围模型

每次规则保存先构造两个集合：

```text
affected_supply_codes   # 规则变化前后可能作为供给被消费的产成品编码
direct_finished_codes   # 成品—组件关系直接变更的成品编码；等效/仓库变更为空
```

随后在同一数据库事务中产生候选订单号，并最终只对已有派生对执行：

```text
affected_pairs = distinct (
  (order_no, source) from shipping_record 正向行命中 affected_supply_codes
  ∪ (order_no, source) from return_record 命中 affected_supply_codes 后，回查该订单的 shipping_record source
  ∪ (order_no, source) from shipping_order_finished.finished_code 命中 direct_finished_codes
)

UPDATE shipping_order_finished
SET is_stale = TRUE
WHERE (source, ecommerce_order_no) IN affected_pairs
```

`UPDATE` 必须幂等；已经 stale 的行仍属于本次影响范围，但不应重复产生额外任务。标记时应返回：影响订单对数、
影响正式行数、按 source 分布，供 UI 与审计日志展示。

这里刻意不把“零命中”当作错误：规则可能确实只影响未来数据。反查范围只负责不漏掉历史派生结果。

## 四、三类规则的反查细节

### A. 成品—组件关系新增/移除

真实写入口：

- `POST /api/product/finished/<finished_id>/packaged/<packaged_id>`；
- `DELETE /api/product/finished/<finished_id>/packaged/<packaged_id>`。

当前仓储每次关联变更即独立 commit；实施时必须先读取旧组件集合，再把“关系变更 + stale 标记”收敛为一个
service 事务，不能先提交关系、再 best-effort 标记。

范围构造：

1. 读取该成品变更前、变更后的全部 required component codes；
2. 对每个 required code 加入其**解析器当前使用的直接等效集合**及自身。注意现实现不是传递闭包，设计也不得
   擅自按图传递扩张；实施时应复用解析器构造 `equiv_map` 的相同语义；
3. `affected_supply_codes` 为前后两套供给编码的并集；
4. `direct_finished_codes={当前成品 code}`；
5. 按第三节查询正向、销退及已有该 finished_code 的派生行。

这会保守标记“含任意相关供给”的订单，而非仅标记所有组件齐全的订单。原因是新增/移除一个组件会改变候选的
可行性与贪心竞争顺序；仅用 SQL 写一个不完整的 `HAVING 全部组件存在` 判断容易漏掉等效替代和竞争订单。

### B. 等效件新增/移除

真实写入口目前在 shipping blueprint：

- `POST /api/shipping/equivalents`；
- `DELETE /api/shipping/equivalents/<id>`。

尽管 URL 暂在 shipping 域，等效件是产品匹配主数据；保存逻辑应与影响范围服务共用同一事务。

对一条 `(code_a, code_b)` 变更：

1. `affected_supply_codes={code_a, code_b}`；
2. 正向记录中任一端点出现的订单均进入候选；
3. 销退记录中任一端点出现的订单，也映射回所有已有派生 source；
4. 不只标记 `finished_code` 恰为某个特定成品：新增等效件可能使以前未匹配的订单首次匹配，删除则可能使原有
   匹配失效。

如果未来把等效件改成传递闭包语义，这个反查规则必须与解析器一起重新审计；不能只扩展标记器。

### C. 仓库排除开关

真实写入口：`POST /api/shipping/warehouses/filter`，一次可批量改变多个仓库。

仓库过滤只影响 `get_order_return_products()`：它动态排除 `return_record.warehouse_name` 命中的销退记录，
不影响正向 `quantity`，但会影响同订单已匹配成品的 `return_quantity`/`actual_quantity`。

范围构造比前两类更精确：

1. 将请求的配置与当前配置逐仓库 diff，只处理 `is_excluded` 实际翻转的名称；
2. 查询 `return_record.warehouse_name IN changed_names` 的 distinct order_no；
3. 对这些 order_no，找出已有 `shipping_order_finished` 的 distinct `(source, order_no)` 并标 stale；
4. NULL/空仓库不属于任一显式仓库开关，不能因批量保存被误标。

该规则不应按“当前是否已经 excluded”过滤 `return_record`，因为从排除→纳入与纳入→排除都需要重算。

## 五、并发、原子性与任务边界

仅在单个 config endpoint 中加一条 `UPDATE is_stale` 不够。当前发货写任务持有 `shipping_mutation` 数据库租约，
而产品/仓库/等效件配置保存不会参与该租约；若规则保存和 resolve 同时发生，可能出现 resolver 读取旧规则、
随后配置更新并标 stale、又被 resolver 的正式写入覆盖为 `False` 的竞态。

推荐后续实施采用“规则变更任务”而非无协调的同步保存：

1. 配置保存申请与导入/resolve 共用的短时 mutation lease；存在运行中发货任务则返回 409，不提交规则；
2. 在一个数据库事务内：读取旧规则 → 计算保守 scope → 保存规则 → `UPDATE is_stale` → 写入审计记录；
3. 事务完成后释放短时 lease；不自动启动 `resolve_stale`，由用户查看影响数量后主动执行；
4. 若 scope 超过当前 `MAX_STALE_RESOLVE_ORDERS`，仍允许保存规则和标记，但 UI 必须明确提示“超过增量安全上限，
需走全量重建或等待上限经门禁调整”，不能悄悄只重算前 10,000。

这里的“任务”是锁与审计语义，不等于后台跑完整重算；具体是扩展 `shipping_task` 还是抽出通用 mutation lock，
可在实施批次选择，但必须满足跨进程、reload 后不丢失、与 resolve 使用同一事实来源。

## 六、建议的数据访问与索引前置检查

实施前先在生产只读 `EXPLAIN` 核验每条反查 SQL。查询应按短编码集合走 `shipping_record.product_code` 和
`return_record(product_code/warehouse_name, ecommerce_order_no)` 的索引；若缺少索引，先单独提出 Alembic 迁移，
不得让配置保存退化为扫描大表。

标记后 `resolve_stale` 的 subset cutover 当前计划从 task 私有 target 表驱动，用 `ix_sof_order_no` 定位正式行，
`source` 后过滤。若未来要提高 10,000，上线前应评估 `(source, ecommerce_order_no)` 复合索引；本设计不授权
添加它。

## 七、实施验收测试（后续批次，不在本轮实现）

每类变更都必须至少覆盖：

- 正向命中订单、销退命中订单、无历史命中规则；
- shipping 与 finance 两来源同订单；
- 已匹配、未匹配及竞争成品订单；
- 重复保存不扩大 scope/不产生重复副作用；
- 变更与运行中 resolve 的 409/租约隔离；
- 标记后 `resolve_stale` 成功将目标行全部恢复 `is_stale=False`，范围外 checksum 不变；
- scope 超过上限时规则保存仍一致、任务明确拒绝而非部分重算；
- viewer 无法变更规则，editor 可变更。

新增测试不能只 mock `mark_stale()`：需要 SQLite/真实事务测试证明“规则写入与 stale 标记”同成同败，及路由层
真实权限链路。

## 八、仍需用户确认的产品点

1. 成品—组件关系与等效件变更，是否在影响订单对超过上限时允许保存后等待维护窗口，还是强制阻止保存？
   本设计推荐**允许保存并明确挂起 stale，禁止偷偷局部重算**。
2. 当规则变更范围接近全量时，是否在 UI 直接引导用户走 `resolve_all`？推荐是，避免长期积压大量 stale。
3. 是否把“成品—组件关系、等效件”正式迁至 product 域。它不阻塞本设计，但应在后续结构整理时完成，
   迁移前接口兼容层必须保留。

在这三点确认前，不建议进入写代码阶段。
