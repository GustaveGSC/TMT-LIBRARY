# 财务品牌图表 tooltip 国家副标题：后端交接

分支：`codex/finance-brand-tooltip-country`  
状态：已实现，未合并、未部署。

## 改动

- 仅在 `get_chart_data()` 的财务“品牌”映射分组中，新增 item 的 `name` 字段。
- `name` 使用 `GROUP_CONCAT(DISTINCT ShippingFinanceCustomerMapping.country)`：一个品牌对应多个历史国家时返回逗号分隔文本，不会静默丢失任一国家。
- 财务“地域/全球区域”分组不返回 `name`（label 已是国家）；发货端、系列、型号等既有路径不变。
- 前端无需修改，现有 tooltip 的 `nameMap` 会直接显示该副标题。

## 验证

- 单一国家品牌返回正确 `name`。
- 同一品牌对应“加拿大、波兰”时，响应保留两个国家。
- 地域分组明确不含 `name`。
- `python -m pytest backend/tests/test_finance_customer_mapping.py -q`：通过。
- `python -m pytest backend/tests -q`、`python -m compileall -q backend`、`git diff --check`：通过。

## 部署验收

无需迁移。Claude 合并部署后，在财务视图按品牌分组，确认 tooltip 显示“品牌名 + 灰色国家副标题”；再确认按全球区域分组未多出重复副标题。
