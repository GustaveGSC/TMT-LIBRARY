# 财务国家/品牌维度解耦：后端交接

分支：`codex/finance-dimension-decouple`  
状态：已实现，未合并、未部署。

## 数据迁移

- 新迁移 `20260728_03`：在 `product_tag_category` 增加 nullable
  `finance_dimension_field VARCHAR(20)`。
- 一次性回填：名称为“地域”或“全球区域”的既有分类设为 `country`；“品牌”设为 `brand`；其他分类保持 NULL。
- 迁移对 baseline 测试的空 schema 安全跳过；真实生产表会执行加列与回填。

## 运行时改动

- 运行时代码已移除基于分类名称的财务维度判断，改为只读取 `finance_dimension_field`。
- 财务 source：`country`/`brand` 分类始终返回为 `tag_dimensions`，不受 `is_shipping_dim` 影响，且 `value_kind='name'`。
- 发货 source：完全不返回这两个财务维度；普通标签维度仍按原 `is_shipping_dim` 逻辑返回。
- `chart-options` 新增 `map_dimension_category_id`：财务端为 country 分类 id，发货端为 `null`。
- chart-data 与 map-breakdown 同样按字段判断；地图国家/品牌维度不再受通用标签开关影响。
- 标签分类 API 的 `to_dict()` 新增 `finance_dimension_field`，供前端配置页过滤财务维度。

## 验证

- 迁移测试验证“全球区域”→`country`、“品牌”→`brand`、普通分类→NULL。
- 图表测试覆盖：财务端绕过 `is_shipping_dim=False` 仍显示两个财务维度；发货端不返回它们；地图 id 正确；全球区域筛选、品牌副标题与地图细分仍正常。
- `python -m pytest backend/tests -q`：通过。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。

## 部署验收（Claude 执行）

1. 先备份生产数据库。
2. 上传模型、仓储、迁移与文档，执行 `alembic upgrade head`；确认 revision 为 `20260728_03`。
3. 只读核验：全球区域为 `country`、品牌为 `brand`，其他分类为 NULL。
4. reload 后确认 `/health`、`/ready`；财务 chart-options 包含两个财务维度及正确 `map_dimension_category_id`，发货 chart-options 不含它们。
5. 前端再实现：配置页按 `finance_dimension_field` 过滤，世界地图按 `map_dimension_category_id` 判断，随后做浏览器验收。
