# 交接说明 · Claude → Codex（第十一轮，把外贸客户人工映射应用到发货图表）

日期：2026-07-21

第十轮（`handoff/2026-07-21-codex-handoff-10.md`）已完成并上线：`customer_alias` 字段落库、`shipping_finance_customer_mapping` 人工映射表、配置页面都已在跑。用户已导入 3 个月财务数据（`shipping_record` 里约 2 万行有 `customer_alias`），并在配置页面人工标注了 7 条映射（4 条确认外贸、3 条确认非外贸）。这一轮要把映射结果实际用到发货图表上。

## 一、核心业务规则（已和用户逐条确认，不要再自行假设）

1. **人工映射完全优先于产品标签，不是"标签优先、映射兜底"**：财务来源（`source='finance'`）订单的"国家"/"品牌"，只要 `customer_alias` 命中 `shipping_finance_customer_mapping` 且 `is_export=1`，就直接用这条映射的 `country`/`brand`，**完全不看产品标签**（哪怕产品本身打了别的地域/品牌标签也不用）。
2. **映射记录支持"确认不是外贸"**（`is_export=0`）：这类订单**既不算内销也不算外贸**，是第三种状态，不能被塞进"内销"桶里凑数。
3. **`customer_alias` 还没有任何人工映射记录的订单**（配置页面里那个简称用户还没处理到）：内销/外贸筛选时**不计入统计**（既不算内销也不算外贸，图表上直接不体现这部分数量）。这个规则可能后续会改（等用户标注得差不多了，可能要求"未映射默认按内销"），但**这一轮先按"不计入"实现，不要自作主张按内销兜底**。
4. **世界地图 / 国家维度展示**：`is_export=0`（确认非外贸）和未映射的订单，**都不在世界地图上画点**（也不出现在国家排行榜里）。只有 `is_export=1` 且 `country` 非空的映射对应的发货量才上图。
5. **财务端的"内销/外贸/全部"筛选（`trade_type`）也要改用这份人工映射来判断**，不能再用现有的 `_get_ftp_finished_codes()`（系列编码 `%-FTP` 后缀）那套启发式。也就是说 `trade_type='foreign'` 时，只筛出 `customer_alias` 命中 `is_export=1` 映射的订单；`trade_type='domestic'` 时同理反过来（具体"内销"桶是否包含未映射订单，按第 3 条——先不包含）。
6. **发货端（`source='shipping'`）的内销/外贸筛选整体取消**：这个筛选器一直是基于 FTP 系列标签的启发式判断，用户现在明确不想再用这套逻辑，且发货端订单没有 `customer_alias` 这种可追溯到真实客户的字段，无法做人工映射。前端会把 `trade_type` 选择器隐藏为仅财务端可见（这部分我这边改，不需要 Codex 处理），但麻烦确认一下后端 `get_chart_data`/`get_chart_options` 在 `source='shipping'` 时如果前端不再传 `trade_type`（或固定传 `'all'`）能不能正常工作，不需要额外改动的话就不用动。

## 二、现有机制（供设计参考，读代码即可确认，不要凭我这段描述直接下手）

- `shipping_order_finished` 当前**没有** `country`/`brand` 列，图表里的国家/品牌来自查询时按 `finished_code` 现关联 `product_tag`（`is_tag_group_by` 分支，`get_chart_data` 里 `group_by='tag:<category_id>'`）。这套机制是**产品级**标签，天然不知道订单实际发往哪里，这正是这次要解决的问题。
- `_resolve_orders()`（`backend/services/shipping/__init__.py`）把 `shipping_record` 里的订单数据贪心匹配成品组合后写入 `shipping_order_finished`，目前 `meta` 里没有带 `customer_alias`（`get_order_products` 目前也不查这个字段），需要补上。
- 前端世界地图（`ShippingDashboard.vue`）消费"地域"标签维度时，要求返回的分组值是**国家中文名**字符串，通过 `COUNTRY_NAME_MAP`（前端常量）转换成 GeoJSON 英文名再匹配地图。`加拿大`/`德国`/`俄罗斯` 已经在这个映射表里；`香港`/`台湾`/`澳门` 不在 `COUNTRY_NAME_MAP` 里，是走单独的特殊逻辑（从中国省级地图里抠出这三个区划叠加到世界地图，见 `.claude/modules/frontend-data-mgmt.md` "标签维度 chip（动态）" 一节最后部分）。**用户已经在映射表里填了"香港"作为国家**，这个值前端现有渲染逻辑已经支持，不需要为此新增前端代码——只要后端吐出来的分组值就是"香港"这个字符串，前端会自动按现有特殊逻辑处理。
- 结论：**只要后端按现有"地域"标签维度同样的响应契约（分组值=国家中文名字符串）把数据吐出来，前端世界地图/排行榜代码完全不用改**。真正要改的是 `get_chart_data` 内部这条数据从哪来。

## 三、这一轮要做的事

1. **`_resolve_orders()` / `shipping_order_finished` 加 `customer_alias` 列**（新迁移），`_resolve_orders()` 从 `meta` 里带过去写入（financeside 订单才有值，shipping 端全 NULL 无所谓）。`get_order_products` 需要能查出 `customer_alias`（订单内多行 `customer_alias` 理论上应该一致，取任意一行/第一行即可，如果实际数据有一单多个简称的脏数据情况，按你的判断处理，可以打日志但不要中断整个 resolve）。
2. **新增一个查国家/品牌用人工映射的维度**，供 `get_chart_data` 在 `source='finance'` 时使用：具体是新增一个独立的 `group_by` 值（比如 `'finance_country'`/`'finance_brand'`），还是复用现有 `tag:<id>` 机制外挂一个特判分支，由你决定，怎么改动小、和现有 `get_chart_data` 里 `needs_trade_filter`/`needs_model_join` 这套条件分支结构最协调就怎么来。**硬性要求是响应契约不变**：`items` 里的分组值字段还是国家中文名字符串（品牌同理，直接用映射表里的 `brand` 文本）。
3. **国家/品牌维度的过滤规则**：`JOIN shipping_finance_customer_mapping ON customer_alias = mapping.customer_alias AND mapping.is_export = 1 AND mapping.country IS NOT NULL`（品牌维度同理用 `mapping.brand IS NOT NULL`），未命中的订单不出现在这个维度的分组结果里（自然实现"未映射/确认非外贸不上图"，因为是 INNER JOIN 不是 LEFT JOIN）。
4. **`trade_type` 判断改用映射**：`source='finance'` 时，`trade_type='foreign'` 改成"`customer_alias` 命中 `is_export=1` 的映射"，`trade_type='domestic'` 改成"`customer_alias` 为空，或命中的映射 `is_export=0`，或...."——这里唯一还有点含糊的是"未映射"要不要算进 domestic，**按本文档第一节第 3 条，未映射的这一轮不计入 domestic**，所以 `domestic` 的准确定义应该是"`customer_alias` 命中了一条 `is_export=0` 的映射"（不是"没有 customer_alias 或没映射就算内销"）。`source='shipping'` 的 `trade_type` 判断逻辑不用动（前端不会再传，但后端保留现有实现即可，除非你觉得应该同步下线，你决定）。
5. **性能**：`shipping_finance_customer_mapping` 目前只有个位数记录，`JOIN`/子查询开销可以忽略，不用像 `_get_ftp_finished_codes()` 那样加缓存层，除非你预计这张表以后会变得很大。
6. **`resolve_orders`/`resolve-all` 跑完之后要清 `get_chart_options` 缓存**（`_invalidate_chart_options_cache()`），这个现有机制已经在别处调用了，加了新字段/新查询路径记得确认这条链路没漏。
7. **更新 `.claude/modules/api.md`/`database.md`**：`shipping_order_finished` 新增列、`get_chart_data` 新 `group_by` 取值（如果新增的话）的契约说明。

## 四、这一轮不用管的部分

- `shipping_finance_customer_mapping` 表结构本身不用改（`is_export`/`country`/`brand` 字段已经够用）。
- 配置页面（前端已上线）不用改，用户已经在用它标注数据。
- `source='shipping'` 的内外销选择器移除是前端改动，我这边处理，不需要 Codex 动后端逻辑（除非上面第一节第 6 条你发现后端需要配合调整）。

## 五、验证要求

- 至少要能验证：财务端切到"外贸数据"，世界地图只画出"香港/加拿大/德国/俄罗斯"这几个国家（对应你已确认的 4 条映射），且数量看起来和实际发货记录对得上（可以直接查库核对某一国家的汇总数量）。
- 用户已经在真实生产库里标注了数据，建议直接用生产库只读核对（不需要造测试数据），或者用测试库套一份类似结构的种子数据也可以，你决定。
- 照例 `python -m pytest` + `python -m compileall -q backend` + `git diff --check`；新增的 `_resolve_orders` customer_alias 传递、`get_chart_data` 新分支、trade_type 判断改动都建议补测试覆盖。

## 协作方式

独立 worktree/分支，完成后照例写交接文档。这次不涉及大批量历史数据变更（迁移只是加一列 + 一次性把 `shipping_order_finished` 里 finance 来源记录的 `customer_alias` 回填，回填可以在 `_resolve_orders` 下次跑 `resolve-all` 时自然完成，不强制要求迁移本身做数据回填——如果你选择在迁移里直接回填也可以，风险自行评估），部署前不需要像上一轮那样做全库备份，但麻烦还是明确写一下部署顺序（迁移 → reload → 验证）。
