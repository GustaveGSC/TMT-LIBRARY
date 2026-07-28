# "全球区域/品牌"从通用标签维度体系彻底解耦为独立财务维度，交接 Codex

状态：待实现（架构改动，涉及迁移，请仔细看契约要点）

## 背景

这几轮陆续修复了财务端"全球区域"（原名"地域"）/"品牌"两个维度的筛选选项、tooltip 等问题，
但这些都是在"这两个维度本质上是借用 `ProductTagCategory`/`is_shipping_dim` 通用标签维度体系"
这个前提下打的补丁。用户这次直接指出了架构层面的问题，我们决定彻底解耦，不再继续打补丁：

1. **命名脆弱性**：世界地图功能（`ShippingDashboard.vue` 前端）靠硬编码字符串
   `REGION_TAG_DIM_NAME = '地域'` 判断"当前选中的维度是不是那个支持世界地图的地域维度"。
   这次分类改名成"全球区域"直接导致世界地图失效——只要分类名再变一次就会再断一次。
2. **配置耦合**：`TagDimensionConfig.vue`（"标签分析维度"配置页）里，"作为发货分析维度"这个
   开关同时控制着"该分类是否出现在图表维度选择里"。但"全球区域/品牌"这两个维度对财务端来说
   根本不是真正的标签数据（值来自 `ShippingFinanceCustomerMapping` 人工映射，不是
   `product_finished_tag` 多对多关联），业务人员如果在这个配置页把开关关掉，会直接导致财务
   图表少了这两个维度，但配置页的措辞（"标签分析维度"）完全没有提示这里还牵扯财务人工映射。
3. **范围过宽**：用户确认这两个维度只有财务端（外贸数据）需要看，发货端（国内数据）不需要，
   现在却在两个 source 下都出现在标签筛选/维度选择里。

## 需要实现

### 1. 数据库：给 `product_tag_category` 加一列，用数据代替硬编码字符串判断

新增字段 `finance_dimension_field`（nullable，`VARCHAR(20)` 即可），取值 `'country'` /
`'brand'` / `NULL`。`NULL` 表示这是普通标签维度（继续走现有 `is_shipping_dim`/
`shipping_dim_enabled` 体系，不受这次改动影响）。

迁移里把当前实际数据（分类名 `'地域'` 或 `'全球区域'` 二选一存在的那一行）回填成
`finance_dimension_field='country'`，分类名 `'品牌'` 的那一行回填成 `'brand'`（复用上一轮
`_finance_mapping_field_for_category()` 里已经验证过的名字判断逻辑做迁移期一次性回填，
迁移跑完之后代码不应该再依赖名字字符串判断）。

### 2. 后端代码：用新字段取代 `_finance_mapping_field_for_category(name)` 的名字匹配

`backend/database/repository/shipping/__init__.py` 里所有原本用分类名判断"是不是财务映射
维度"的地方（`get_chart_options`、`get_chart_data` 的分组与 `tag_filters`、
`get_finance_map_breakdown` 的 `country_category_id`/`breakdown_group_by` 校验），改成直接
读 `ProductTagCategory.finance_dimension_field` 字段：

```python
def _finance_mapping_field_for_category_row(category: 'ProductTagCategory'):
    if category is None or not category.finance_dimension_field:
        return None
    return {
        'country': ShippingFinanceCustomerMapping.country,
        'brand':   ShippingFinanceCustomerMapping.brand,
    }.get(category.finance_dimension_field)
```

原来按 id 查名字再判断字符串的地方，改成直接查 `finance_dimension_field` 列（一次查询即可，
不需要额外 JOIN）。原来的 `_FINANCE_COUNTRY_CATEGORY_NAMES`/别名集合可以删掉了——这就是这次
解耦要解决的根本问题，不应该再保留名字判断作为兜底。

### 3. `get_chart_options`：财务维度按 source 完全分流可见性

- `source == 'finance'`：`finance_dimension_field` 非空的分类，始终纳入 `tag_dimensions`
  （不再受 `is_shipping_dim` 门控——这两个维度对财务端来说不是"要不要启用"的问题，而是固定
  存在的财务口径），`value_kind='name'`，`tags` 来自映射表去重值（沿用上一轮已实现的逻辑）。
- `source == 'shipping'`：`finance_dimension_field` 非空的分类**完全从 `tag_dimensions` 里
  排除**（不是隐藏，是不返回），因为用户确认发货端不需要这两个维度。
- 新增一个顶层字段，供前端识别"当前财务视图里哪个维度支持世界地图"，不再靠名字字符串比较：
  ```python
  result['map_dimension_category_id'] = next(
      (cat.id for cat in tag_cats if cat.finance_dimension_field == 'country'),
      None,
  ) if source == 'finance' else None
  ```
  （如果同时存在多个 `finance_dimension_field == 'country'` 的分类——理论上不应该出现，但如果
  出现，取第一个即可，不需要做复杂容错。）

### 4. `/api/product/tags/categories/`（`TagCategoryService.get_all()`/`to_dict()`）

`ProductTagCategory.to_dict()` 加上 `finance_dimension_field` 字段返回给前端，供
`TagDimensionConfig.vue` 过滤掉这两个分类（不在通用标签维度配置页里出现，避免被误关）。

`TagCategoryService.update()`（分类改名/改开关）不需要特殊拦截 `finance_dimension_field`
非空的分类——是否允许改名、改颜色这些不涉及这次解耦的核心问题，除非你评估后觉得有必要额外
保护，否则不用加。

## 契约要点

- `finance_dimension_field` 只影响这次列出的三个查询函数的判断依据，不改变
  `get_chart_data`/`get_finance_map_breakdown` 已有的行为逻辑（人工映射替换、`tag_names`
  兼容、多国 `GROUP_CONCAT` 等都维持不变，只是判断"是不是财务维度"的依据从名字换成字段）。
- 已有的 `product_finished_tag` 多对多关联、这两个分类下现存的 `ProductTag` 行（比如"中国"
  "捷克"这些标签）**不需要删除或清理**，只是发货端（`source='shipping'`）的
  `get_chart_options` 不再把这两个分类作为可选维度返回；如果这些标签行还被产品资料/其他地方
  引用，不受这次改动影响。
- 不需要处理"如果同一时刻数据库里同时存在名为'地域'和'全球区域'两个不同分类"这种边界情况，
  迁移只需按当前生产实际数据（一行地域/全球区域，一行品牌）回填。

## 不需要的改动

- 不需要改前端——`TagDimensionConfig.vue` 和 `ShippingDashboard.vue` 的改动我来做（后者要把
  `REGION_TAG_DIM_NAME` 字符串比较换成用新的 `map_dimension_category_id` 字段判断）。
- 不需要动 `get_finance_customer_aliases`/`save_finance_customer_mapping` 等财务映射管理
  相关接口，那些和"这个分类是不是财务维度"无关。

## 验证要求

- 迁移：跑 `alembic upgrade head` 后，`product_tag_category` 表原"全球区域"行
  `finance_dimension_field='country'`，"品牌"行 `finance_dimension_field='brand'`，其余分类
  该字段为 `NULL`。
- 单测覆盖：
  - `get_chart_options(source='finance')` 返回的 `tag_dimensions` 包含这两个财务维度
    （`value_kind='name'`），且不受 `is_shipping_dim=False` 影响（把 `is_shipping_dim` 显式
    设成 `False` 后依然出现，验证"不再被通用开关门控"）；同时返回
    `map_dimension_category_id` 等于"全球区域"分类的 id。
  - `get_chart_options(source='shipping')` 返回的 `tag_dimensions` 里**不包含**这两个财务
    维度；`map_dimension_category_id` 为 `None`。
  - `get_chart_data`/`get_finance_map_breakdown` 的既有测试（`test_finance_customer_mapping.py`
    里覆盖"地域"和"全球区域"两种命名场景的用例）继续通过，确认迁移到字段判断后行为不变。
  - `/api/product/tags/categories/` 返回的分类里，这两个分类的 `finance_dimension_field`
    正确，其余分类为 `null`。

## Claude 后续动作

收到实现后我会：
1. Review 代码 + 跑测试，重点确认 `is_shipping_dim` 门控确实被绕开、迁移回填数据正确。
2. 备份数据库（涉及 schema 迁移）→ 上传代码 →`alembic upgrade head`→`alembic current`确认→
   reload gunicorn。
3. 前端改动：`TagDimensionConfig.vue` 过滤掉这两个分类；`ShippingDashboard.vue` 把世界地图
   判断从 `REGION_TAG_DIM_NAME` 字符串比较换成 `map_dimension_category_id`；财务视图下确认
   左侧筛选/维度选择器仍能看到这两个维度，发货视图下确认已经看不到。
4. 真实浏览器验证：财务视图切到"全球区域"维度，世界地图正常显示；发货视图确认维度列表和
   标签筛选里都没有"全球区域"/"品牌"这两项；标签分析维度配置页确认这两个分类不再出现、
   也无法通过该页面误关。
