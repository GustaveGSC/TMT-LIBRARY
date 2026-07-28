# 财务端地域/品牌筛选选项：后端交接

分支：`codex/finance-chart-options`  
状态：实现完成，未合并、未部署。

## 改动

- `ShippingRepository.get_chart_options()` 在 `source='finance'` 时：
  - 标签分类“地域”从 `ShippingFinanceCustomerMapping.country` 读取去重非空文本；
  - 标签分类“品牌”从 `ShippingFinanceCustomerMapping.brand` 读取去重非空文本；
  - 两者返回 `value_kind: 'name'`，每项的 `id`/`name` 都是映射文本本身。
- 其他维度以及整个 `source='shipping'` 路径保持原产品标签读取逻辑，并统一显式返回 `value_kind: 'id'`。
- 不改图表数据查询、缓存 key、数据库或接口路径。图表选项缓存本来以 `source + 日期范围` 为 key；客户映射保存路由已有缓存失效调用。
- API 契约已更新 `.claude/modules/api.md`。

## 口径说明

严格按交接文档示例，选项取**所有非空客户映射值**，未额外限制 `status='export'`。这避免在本批未经确认的情况下收窄已有可见映射数据；前端应只根据 `value_kind` 决定传 `tag_names`，不自行将文本当标签 ID。

## 验证

- 新增/扩展 `test_finance_chart_uses_manual_mapping_for_trade_country_brand_and_filters`：
  - 财务端地域/品牌来自映射表、去重且 `value_kind='name'`；
  - 发货端仍从标签库读取且 `value_kind='id'`；
  - 非地域/品牌维度在两来源下保持标签语义。
- `python -m pytest backend/tests -q`：通过。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。

## Claude 后续

1. 审查合并后部署（无迁移）；reload 后清一次 chart-options 内存缓存或等待 TTL。
2. 在 `ShippingDashboard.vue` 按 `tag_dimensions[].value_kind` 组装 `tag_filters`：`name` → `tag_names`，`id` → `tag_ids`。
3. 用真实浏览器在财务端选一个品牌/地域，确认下钻数据筛选正常；再回归发货端标签筛选。
