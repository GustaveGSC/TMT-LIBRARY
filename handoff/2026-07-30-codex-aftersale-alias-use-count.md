# 售后物料简称引用次数接口

`GET /api/aftersale/shipping-aliases` 的每个简称项新增 `use_count`，值为
`aftersale_case_reason.shipping_alias_id` 的实时引用次数。

- 使用单条 `LEFT OUTER JOIN + GROUP BY` 聚合，包含零引用简称；
- 不新增持久化计数字段，不需要回填或维护；
- 前端原有的缺失值兼容逻辑可直接接收该字段；
- 本地 `compileall` 与 `git diff --check` 通过；未部署。
