# 财务端"地域/品牌"筛选选项与实际维度数据不一致，交接 Codex

状态：待实现（阻塞中，影响生产可用性，非崩溃级但用户已反馈）

## 背景

`ShippingDashboard.vue` 左侧"标签筛选"面板，对"地域"/"品牌"这两个 `ProductTagCategory`
维度，`source=finance`（外贸财务）时下钻用的其实不是标签关联，而是
`ShippingFinanceCustomerMapping.country`/`.brand` 人工映射字段（`get_chart_data` 里已经这样
特殊处理，见 `backend/database/repository/shipping/__init__.py:2330-2373`，且该函数注释里已
说明"财务端「地域/品牌」既兼容原有 tag_ids，也允许直接传 tag_names，避免人工映射中的新国家/
品牌必须先在产品标签表建档才能下钻"）。

但 `get_chart_options()`（同文件 2253-2269 行）返回的 `tag_dimensions[].tags` **不区分
source**，永远读的是 `ProductTagCategory`/`ProductTag` 标签库。结果：财务视图左侧"品牌"筛选
框里勾的选项，跟财务数据里真实存在的品牌文本完全是两套字符串，选了也筛不出东西。用户已实测
反馈此问题。地域维度是完全一样的代码路径，同样受影响，一起修。

## 需要实现

`get_chart_options(date_start, date_end, source)` 构建 `tag_dimensions` 时，对
`source == 'finance'` 且分类名是"地域"或"品牌"的维度，`tags` 列表改为查
`ShippingFinanceCustomerMapping` 里对应字段（`country`/`brand`）的去重非空值，而不是标签库。

示例方向（不要求逐字照抄，按仓库现有写法风格来）：

```python
FINANCE_MAPPING_FIELDS = {
    '地域': ShippingFinanceCustomerMapping.country,
    '品牌': ShippingFinanceCustomerMapping.brand,
}

tag_dimensions = []
for cat in tag_cats:
    mapping_field = FINANCE_MAPPING_FIELDS.get(cat.name) if source == 'finance' else None
    if mapping_field is not None:
        values = [
            row[0] for row in db.session.query(mapping_field).filter(
                mapping_field.isnot(None), mapping_field != ''
            ).distinct().order_by(mapping_field).all()
        ]
        tags = [{'id': v, 'name': v} for v in values]
        value_kind = 'name'  # 前端据此拼 tag_names 而不是 tag_ids
    else:
        tags = [
            {'id': t.id, 'name': t.name}
            for t in cat.tags.filter_by(shipping_dim_enabled=True).order_by(ProductTag.name).all()
        ]
        value_kind = 'id'
    tag_dimensions.append({
        'category_id': cat.id, 'name': cat.name, 'color': cat.color,
        'tags': tags, 'value_kind': value_kind,
    })
```

## 契约要点

- 新增 `tag_dimensions[].value_kind`：`'id'`（默认，走 `tag_ids`）或 `'name'`（财务映射值，
  走 `tag_names`）。前端 `ShippingDashboard.vue` 组装 `tag_filters` 时要按这个字段判断塞
  `tag_ids` 还是 `tag_names`（我这边收到接口改动后会做前端配合修改，不需要 Codex 改前端）。
- 财务映射值本身没有稳定 id，用值本身当 `id`/`name` 即可（前端 `el-select` 用字符串当 value
  没问题），不需要引入新的 id 概念。
- 这个函数结果有 5 分钟内存缓存（`_chart_options_cache`），key 已包含 `source`，不需要额外改
  缓存逻辑。
- 不影响 `source='shipping'` 路径，那边继续用标签库，`value_kind` 恒为 `'id'`。

## 不需要的改动

- 不需要改 `get_chart_data` 的下钻筛选逻辑，那边已经支持 `tag_names`。
- 不需要新增数据库表或字段。
- 不需要改前端，我这边收到后端改动后自行处理 `ShippingDashboard.vue`。

## 验证要求

- 单测覆盖：`source='finance'` 时 `get_chart_options` 返回的"地域"/"品牌"维度 `tags` 来自
  `ShippingFinanceCustomerMapping` 去重值、`value_kind='name'`；`source='shipping'` 时两个
  维度仍是标签库、`value_kind='id'`；其他维度（非地域/品牌）在两种 source 下都不受影响。
- 跑一遍现有 `test_shipping*` 相关测试，确认没有回归。

## Claude 后续动作

收到实现后我会：
1. Review 代码 + 跑测试。
2. 部署（无迁移，直接 reload gunicorn，注意先清一次 `get_chart_options` 缓存或等 TTL 过期）。
3. 修改 `ShippingDashboard.vue` 的 `tagOptsFor`/筛选参数组装逻辑，按 `value_kind` 分流
   `tag_ids`/`tag_names`。
4. 真实浏览器验证：财务视图下勾选品牌筛选，确认能正确筛出数据。
