# 财务端"地域"人工映射替换从未生效：硬编码分类名与实际数据库分类名不一致，交接 Codex

状态：待实现（阻塞中）

## 背景

上一轮修复（2b5af72，`fix(shipping): align finance chart filter options`）已经让"品牌"维度在
`source=finance` 时正确改用 `ShippingFinanceCustomerMapping.brand` 的去重值（`value_kind:'name'`），
生产验证通过。

但真实 HTTP 验证 `GET /api/shipping/chart-options?source=finance` 时发现：地域维度并没有触发
同样的替换逻辑，`value_kind` 仍是 `'id'`，返回的还是产品标签库。排查后确认根因——生产数据库里
这个分类真实名字叫 **"全球区域"**，不是代码里硬编码判断用的字符串 `'地域'`。

这个硬编码字符串匹配同时出现在三处，全部只判断 `'地域'`，从未匹配过"全球区域"，所以财务端地域
筛选的人工映射对齐**从这个特殊处理逻辑最初写下起就没生效过**（不是这次改动引入的新问题，是
一直存在但没被发现的既有 bug）：

- `backend/database/repository/shipping/__init__.py:2330-2333`（`get_chart_data` 分组判断）
- 同文件 2359-2360（`tag_filters` 财务映射筛选判断）
- 同文件 2662-2663、2689-2690（`country_category_id`/`breakdown_group_by` 校验，报错信息也写的是
  "必须是地域标签分类"/"必须是品牌标签维度"）
- 我这轮改的 `get_chart_options`（2255-2269 行区域）里的 `finance_mapping_fields` 字典 key 也是
  `'地域'`

## 需要实现

把所有硬编码判断 `cat.name == '地域'` 的地方，改成同时兼容 `'地域'` 和 `'全球区域'`（或者更彻底
一点：改成读取分类名是否在一个允许列表 `{'地域', '全球区域'}` 里，避免以后分类改名或多环境命名
不一致又踩同样的坑）。

不建议直接把生产库里的分类名从"全球区域"改回"地域"去迁就代码——分类名本身是业务侧配置内容，
可能有其他地方引用了这个显示名称（前端展示、导出文件等），风险不可控，改代码兼容更安全。

涉及位置（本仓库 master 分支，非 Codex 独立分支时的最新行号，实现时以实际代码为准）：
1. `get_chart_options` 里的 `finance_mapping_fields = {'地域': ..., '品牌': ...}` → key 也要
   覆盖 `'全球区域'`
2. `get_chart_data` 里 `if tag_category_name == '地域':` 判断（约 2330 行附近）
3. `get_chart_data` 里 `filter_category_name` 对应的 `mapping_field = {...}.get(filter_category_name)`
   字典（约 2359 行附近）
4. `country_category_id`/`breakdown_group_by` 相关的名字校验（约 2662、2689 行附近），及对应的
   报错文案（如果文案里提"地域"，可以保留原文案或改成"地域（全球区域）"，不强制）

## 契约要点

- 前端不需要改动，`value_kind` 字段的语义和上一轮一致。
- 不要把两个名字都当成独立分类硬塞进结果——同一个分类只应该按它实际的 `cat.name` 判断一次，
  匹配到任意一个别名就按财务映射处理。
- 如果生产库里"地域"和"全球区域"未来可能同时存在（两个不同分类），按分类名精确匹配，不要用
  `in`/模糊包含判断，避免误伤同名子串的其他分类。

## 不需要的改动

- 不需要改数据库、不需要新增字段、不需要改前端。
- 不需要改缓存逻辑。

## 验证要求

- 新增/修改单测：用分类名为"全球区域"的 `ProductTagCategory`（而不是"地域"）验证
  `get_chart_options(source='finance')` 对该维度返回 `value_kind='name'` 且 tags 来自
  `ShippingFinanceCustomerMapping.country` 去重值；`source='shipping'` 时仍是标签库、
  `value_kind='id'`。
- 跑一遍现有 `test_finance_customer_mapping.py` 等相关测试确认无回归（注意：现有测试用的分类名
  可能是 `'地域'`，如果要覆盖"全球区域"场景，建议新增用例而不是改掉验证"地域"命名本身仍兼容的
  旧用例）。

## Claude 后续动作

收到实现后我会：
1. Review 代码 + 跑测试。
2. 部署（无迁移，直接同步改动文件 + reload gunicorn）。
3. 真实浏览器/HTTP 验证：财务视图下地域筛选下拉框显示的是
   `ShippingFinanceCustomerMapping.country` 里的真实文本，且能正确筛出数据。
