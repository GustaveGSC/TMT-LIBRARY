# 财务端“全球区域”分类名兼容：后端交接

分支：`codex/finance-region-category-alias`  
状态：已实现，尚未合并或部署。

## 根因与修复

生产标签分类的显示名是“全球区域”，而财务映射特殊处理此前只硬编码了“地域”，导致：

- chart-options 未返回 country 映射值和 `value_kind='name'`；
- chart-data 的分组、`tag_names` 筛选未识别该分类；
- 财务世界地图批量细分入口拒绝该分类。

新增单一 `_finance_mapping_field_for_category()`，将“地域”和“全球区域”共同映射到
`ShippingFinanceCustomerMapping.country`，“品牌”映射到 `.brand`。所有上述路径都改为复用它，避免再次分叉。

## 验证

- 在既有财务映射测试中保留“地域”兼容测试，并追加将同一分类改名为“全球区域”的验证：
  - 财务 options 返回 country 文本与 `value_kind='name'`；
  - 发货 source 仍返回产品标签与 `value_kind='id'`；
  - 财务 `tag_names` 筛选和批量地图细分均正确命中。
- `python -m pytest backend/tests/test_finance_customer_mapping.py -q`：通过。
- 全量后端回归、`compileall`、`git diff --check` 待提交前执行。

## 部署验收

无需迁移。Claude 部署 reload 后，清 chart-options 缓存或等待 TTL；真实请求
`GET /api/shipping/chart-options?source=finance`，确认“全球区域”维度返回 `value_kind='name'` 和映射国家文本，再在浏览器确认筛选命中。
