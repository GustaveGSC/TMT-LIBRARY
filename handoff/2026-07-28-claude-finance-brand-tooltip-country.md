# 财务端"品牌"图表 tooltip 需要附带对应国家，交接 Codex

状态：待实现

## 背景

发货看板财务视图按"品牌"维度看图表时（`group_by=tag:<品牌category_id>`，走
`is_finance_mapping_group` 分支，`finance_mapping_field` 是
`ShippingFinanceCustomerMapping.brand`），用户希望 tooltip 里品牌名旁边带上对应国家，
类似"eliNeli 捷克"。

好消息是前端 tooltip 已经有现成机制不用改：`buildBarOption`/`buildPieOption`
（`src/views/shippingViews/ShippingDashboard.vue`）里已经有 `nameMap`，只要 chart-data
返回的 item 带 `name` 字段（目前系列/型号维度会填 `ProductSeries.name`/`ProductModel.name`），
tooltip 就会自动在主标题旁显示灰色副标题。只需要后端在按"品牌"分组时，也把 `name` 填成该
品牌对应的国家文本即可，前端不需要任何改动。

## 需要实现

`backend/database/repository/shipping/__init__.py` 的 `get_chart_data()`，
`elif is_finance_mapping_group:` 分支（当前约 2591-2594 行）：

```python
elif is_finance_mapping_group:
    label_expr = finance_mapping_field
    if finance_mapping_field is ShippingFinanceCustomerMapping.brand:
        # 财务人工映射里同一品牌理论上应对应同一国家，但历史数据不保证严格一致，
        # 用 GROUP_CONCAT DISTINCT 兜底多国场景，避免显示时静默丢数据。
        name_expr = func.group_concat(distinct(ShippingFinanceCustomerMapping.country))
    else:
        name_expr = None
    order_expr = func.sum(sof.actual_quantity).desc()
```

注意 `ShippingFinanceCustomerMapping` 在 `needs_finance_mapping` 为真时已经 JOIN 进
主查询（约 2446-2450 行 `if needs_finance_mapping: q = q.join(ShippingFinanceCustomerMapping, ...)`），
`is_finance_mapping_group` 时 `needs_finance_mapping` 恒为真，所以不需要额外 JOIN。

`distinct` 需要从 `sqlalchemy` 导入（若文件顶部尚未导入，加一行 `from sqlalchemy import distinct`）。
MySQL `GROUP_CONCAT` 默认用逗号分隔、自动忽略 NULL，不需要额外处理空值。

`items` 组装那段（约 2619-2629 行）已经是 `has_name = name_expr is not None` 通用逻辑，
不需要改。

## 契约要点

- 只在按"品牌"（`finance_mapping_field is ShippingFinanceCustomerMapping.brand`）分组时填
  `name`；按"全球区域/地域"分组时该字段本身就是国家，不需要（也不应该）再填 `name`。
- 如果一个品牌历史数据里对应了多个国家（人工映射填写不一致），`name` 会是逗号分隔的多个国家，
  前端原样展示即可，不需要做"取第一个"这种丢数据的处理。
- 不影响 `source='shipping'` 路径（`is_finance_mapping_group` 恒为 False）。
- 不影响 `get_chart_options`、`get_finance_map_breakdown`，只改 `get_chart_data` 这一处。

## 不需要的改动

- 不需要改前端，`nameMap` 机制已经是通用的。
- 不需要改数据库、缓存。

## 验证要求

- 单测：财务端按品牌分组时，item 里 `name` 是该品牌对应的国家（单一国家场景）；品牌对应
  多个国家的场景下 `name` 是逗号分隔的多个国家（不丢数据）；按"全球区域"分组时不带 `name`
  字段；发货端不受影响。
- 跑一遍 `test_finance_customer_mapping.py` 确认无回归。

## Claude 后续动作

收到实现后我会 review、部署（无迁移，同步一个文件 + reload gunicorn），并在浏览器里实际看一眼
财务视图按品牌切图，确认 tooltip 里品牌名旁边正确显示了国家。
