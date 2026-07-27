# 售后工单物料清单：名称缺规格（交接 Codex）

## 问题

用户反馈售后数据表格展开行的"发货物料清单"里，物料名称"只显示了一半"——缺规格信息。

## 根因（已用生产数据核实）

`_get_order_products()` / `_get_batch_order_products()`
（`backend/database/repository/aftersale/__init__.py:412-453`）取的是
`ShippingRecord.product_name`，这是发货/财务清单导入时原始 Excel 里的品名文本，**本身就比较
简短，不含规格**。真正带规格的完整名称在产品库 `product_packaged`/`product_finished` 表的
`name` 字段（拼接了"产成品_桌类_德罗_桌面(V1.1)手摇1.8米榉木白色_A"这种完整描述）。生产数据
实测对照：

```
shipping_record: ('1201QMSJ01-A', '启明星_书架')                      -- 短
product_packaged: ('1201DLZM02-A', '产成品_桌类_德罗_桌面(V1.1)手摇1.8米榉木白色_A')  -- 完整带规格
```

这不是前端截断显示的问题，是这两个函数当初就没有 JOIN 产品库，取的字段本身信息不全。

## 需要的修复

`_get_order_products`/`_get_batch_order_products` 按 `product_code` 关联 `product_packaged`
（找不到再退 `product_finished`，视 `product_code` 实际覆盖哪个表决定关联顺序）取完整
`name` 字段替代/补充 `ShippingRecord.product_name`；找不到匹配产品记录时保留原始
`product_name` 作为兜底，不要因为找不到就整行不显示。

## 性能要求（务必遵守，这是本项目的硬规矩）

- `_get_batch_order_products` 是列表页 Phase1 就会调用的路径（`AftersaleCasesTable.vue`
  loadData() 时机），**不能变成 N+1**——现在是 1 条 `GROUP BY` 查询，加规格信息后必须仍是
  常数条查询（likely：先按 `ecommerce_order_no IN (...)` 查出全部 `(order_no, product_code,
  quantity)`，收集去重后的 `product_code` 集合，再用 `product_code IN (...)` 一次性查
  `product_packaged`/`product_finished` 的 `code→name` 映射字典，Python 层合并，不要在循环里
  查库）。
- `_get_order_products`（单订单版本，供售后处理页 `AftersaleProcess.vue` 用）可以稍微放宽，
  但也应该是 2 条查询（原始聚合 + 一次名称映射查询），不要逐个物料查一次。

## 影响范围确认

搜索这两个函数的调用点，确认是否有依赖当前"简短 product_name"文本做精确字符串匹配的逻辑（比如
简称匹配、自动匹配关键词提取），如果有，需要评估换成完整名称是否会影响那些匹配逻辑的准确率——
不要只改展示字段，忽略了同一份数据还被用作匹配输入源的情况。
