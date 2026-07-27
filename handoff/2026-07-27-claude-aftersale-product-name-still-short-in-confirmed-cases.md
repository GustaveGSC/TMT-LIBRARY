# 物料名称修复未覆盖到用户实际反馈的界面（交接 Codex）

日期：2026-07-27

## 结论

8b311e0 的修复本身是对的（`_get_order_products`/`_get_batch_order_products` 优先取
`import_product_raw.name`，查询数不变），已合并部署，本地测试通过。**但真实 HTTP 验证发现它
没有覆盖到用户最初反馈的界面**：售后数据表格（"数据" Tab，`AftersaleTable.vue` →
`AftersaleCasesTable.vue`，固定 `status=confirmed`）展开行的物料名称**依然是短名**，问题
没有解决。

## 根因

`_get_order_products`/`_get_batch_order_products` 只在 `get_pending()`（待处理队列，
`backend/database/repository/aftersale/__init__.py:374`）里被调用——这个路径服务
`AftersaleProcess.vue` 的待处理队列，物料是**实时从 `shipping_record` 聚合**的，因为待处理
订单还没有 `AftersaleCase` 记录。

用户实际反馈、也是这次真正要修的界面是**"数据"Tab 的已确认工单表格**，走的是完全不同的代码
路径：`get_cases()`（同文件 492 行起）查 `AftersaleCase` 表，`AftersaleCase.to_dict()`
（`backend/database/models/aftersale/__init__.py`，`products` 字段附近）**直接返回
`self.products`**——这是确认工单时（`confirm_case`）写入的**静态 JSON 快照**，快照里的
`name` 字段就是当时从 `shipping_record.product_name` 抄录的短名，从来没有走过这次新加的
`_apply_import_product_names` 逻辑。

## 真实验证证据（生产数据，只读）

- 样本：订单 `20260127006`，物料 `1208YJZM01-A`。
  - `shipping_record.product_name`（短名）：`悦己_桌面`
  - `import_product_raw.name`（ERP 全名）：`悦己_桌面 (V1.1)电动1.4米橡木本色_A（1208YJZM01-A）`
  - 真实调用 `GET /api/aftersale/cases?search=20260127006` 返回的 `products[].name`：
    **`悦己_桌面`**（短名，未修复）。
- 批量查询数验证通过（`shipping_record`/`import_product_raw` 各 1 次），证明 8b311e0 本身没有
  引入 N+1，只是这条路径不是用户在用的那条。

## 需要的修复

`get_cases()` 返回的每个 `AftersaleCase.products`（存量 JSON 快照）在**读取时**也要走一遍
`_apply_import_product_names()` 风格的名称覆盖，而不是原样透传快照里的 `name`。具体做法建议：

1. `get_cases()` 拿到分页后的 `items`（`AftersaleCase` 对象列表）后，收集这批订单
   `products` 快照里出现的全部 `code`，一次 `IN (...)` 查 `import_product_raw`，得到
   `code → name` 映射；
2. 在返回前（可以在 repository 层重写快照的 dict，也可以在 service 层
   `[c.to_dict(...) for c in items]` 之后再做一次覆盖，两种都行，选择改动面小的一种）用映射
   覆盖每个物料行的 `name`，找不到映射的保留快照原名兜底；
3. **同样的逻辑也要检查 `get_case_by_order_no`/单订单详情、`AftersaleCasesDrawer.vue` 走的
   `GET /api/aftersale/cases`（同一个接口，图表页"查看数据"抽屉复用的也是这个查询路径）**——
   这些应该会自动受益于同一处修复，不需要重复改，但请在验证清单里覆盖一下确认没有遗漏的分支。
4. 保持查询数不变：这批的核心约束依然是"批量场景一次 `IN` 查询搞定所有订单的编码映射，不逐订单
   查"，和 8b311e0 里已经建立的约束完全一致，只是要接到 `get_cases()` 这条路径上而不是只接在
   `get_pending()` 上。

## 不需要改的部分

- `get_pending()`/`_get_order_products`/`_get_batch_order_products` 本身不需要动，这次的实现
  没有 bug，只是覆盖范围不够。
- 是否需要在 `confirm_case()` 写快照时就换成 ERP 全名（这样未来新确认的工单从源头就是全名，
  历史工单靠读取时覆盖弥补），由 Codex 判断要不要顺手做；如果做，要注意"历史已确认工单的快照
  不会被这个改动自动更新"，读取时覆盖这一层无论如何都不能省略。

## 验证要求（务必用真实 HTTP，不能只看单测）

- 用上面这个真实样本（订单 `20260127006`，物料 `1208YJZM01-A`）复测：`GET
  /api/aftersale/cases?search=20260127006` 返回的 `products[].name` 必须是 ERP 全名
  `悦己_桌面 (V1.1)电动1.4米橡木本色_A（1208YJZM01-A）`。
- 批量场景（不带 `search`，正常分页）确认查询数仍是常数条，不随本页订单数增长。
