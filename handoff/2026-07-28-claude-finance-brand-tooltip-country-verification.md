# 财务端"品牌"图表 tooltip 附带国家：生产验证通过并已上线

日期：2026-07-28

## 结论

Codex 的实现（840d0ac）审查通过：只在 `finance_mapping_field is ShippingFinanceCustomerMapping.brand`
时才填 `name_expr`，复用了文件顶部已导入的 `distinct as sql_distinct`，未新增导入、未影响
其他分组路径。已合并部署，真实 HTTP 验证通过，前端无需任何改动（tooltip 的 `nameMap` 机制本来
就是通用的）。

## 部署

无迁移，同步 `database/repository/shipping/__init__.py` 一个文件，MD5 核对一致，
`systemctl reload gunicorn`，master PID 未变，无崩溃重启，`/health`/`/ready` 正常。

## 真实 HTTP 验证

`POST /api/shipping/chart-data`，`{"group_by":"tag:2","source":"finance","trade_type":"all"}`
（category_id=2 是"品牌"）：

| label（品牌） | name（国家） |
|---|---|
| eliNeli | 捷克 |
| Nature Kid | 德国 |
| Astro | 中国、台湾（同一品牌历史映射到多个地区，GROUP_CONCAT 完整保留） |
| costa | 中国、台湾 |
| ergosmart | 白俄罗斯 |
| Claire | 加拿大 |

`eliNeli` → 捷克，与用户举例的"eliNeli-捷克"预期一致。

## 当前状态

用户反馈的"品牌图表 tooltip 需要附带对应国家"需求已完整解决并生产验证，无已知遗留问题。
