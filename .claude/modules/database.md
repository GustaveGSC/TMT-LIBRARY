# 数据库表结构

## 账号
```
users             id, username, password(bcrypt), display_name, is_active, created_at, updated_at
roles             id, name, description
permissions       id, code, name, description
user_roles        user_id, role_id
role_permissions  role_id, permission_id

user_login_log
  id, user_id(FK→users SET NULL nullable), username(输入的用户名),
  display_name(成功时记录), status(ENUM success/failed),
  machine_name(VARCHAR 128，主机名，用于区分游客身份), login_at(CST DateTime)
  # 每次登录尝试（包括密码错误/账号不存在/账号禁用）均写入；游客登录也写入
  # verify_password + guest_login 均记录；user_id 找不到用户时为 NULL
  # 游客以 machine_name 区分不同用户（socket.gethostname() 服务端获取）
```

## 版本
```
app_version       id, version, description, download_url, created_at
```

## 发货数据
```
shipping_batch
  id, type(shipping/return/finance), filename, row_count, imported_at

shipping_record
  id, batch_id(FK), ecommerce_order_no, line_no, shipped_date,
  channel_name, channel_code, channel_org_name, operator(最近操作人),
  product_code, product_name, spec, quantity, country, province, city,
  district, street, address, buyer_remark, seller_remark,
  source ENUM('shipping','finance') DEFAULT 'shipping'
  # UNIQUE(ecommerce_order_no, line_no, product_code, record_type, source)
  # source='shipping'：发货端 ERP 导出；source='finance'：财务端 ERP 导出（line_no=None）
  # 财务端必要列：交易日期/部门名称/品号/品名/规格/数量/平台订单/省/市/区

return_record
  id, batch_id(FK→shipping_batch), ecommerce_order_no, shipped_date,
  product_code, quantity(负值), warehouse_name
  # UNIQUE(ecommerce_order_no, product_code, shipped_date)
  # 发货端/财务端负数量行均写入此表

shipping_order_finished
  id, ecommerce_order_no, finished_code(NULL=未匹配), finished_name,
  quantity(发货数量), return_quantity(销退数量), actual_quantity(实际=发货-销退),
  shipped_date, operator, channel_name, province,
  is_stale, resolved_at,
  source ENUM('shipping','finance') DEFAULT 'shipping'
  # source 与 shipping_record 对应；两个来源独立 resolve，互不干扰
  # INDEX(source)；图表查询必须带 source 过滤

return_warehouse_filter
  id, warehouse_name(UNIQUE), is_excluded(默认False), created_at
  # 配置计算成品组合时需忽略的仓库（UI：仓库配置 Tab）；调整后刷新全局数据即可生效

shipping_operator_type
  id, operator(UNIQUE), type(shipping/aftersale/unknown), created_at, updated_at
  # 「最近操作人」→ 发货/售后/未分类

  # 按订单对发货/销退数据分别贪心匹配成品组合，写入三列数量

packaged_equivalent
  id, code_a(VARCHAR 64), code_b(VARCHAR 64), note(VARCHAR 255 NULL), created_at
  # UNIQUE(code_a, code_b)；始终存 code_a < code_b（字典序）
  # 声明两个产成品在发货匹配时可互换（如 A01 ↔ B01）
  # _resolve_orders() 加载此表构建等效映射，匹配时任意等效码均可满足槽位需求
  # 建表脚本：backend/create_packaged_equivalents.py
  # 管理入口：数据管理页 → 数据配置 → 产成品通用件配置
```

## 售后数据
（与 `backend/database/models/aftersale/__init__.py` 一致；**词典表**首次可用 `backend/create_reason_keyword_rules.py` 建表并写入种子数据。）

```
aftersale_reason_category
  id, name(UNIQUE VARCHAR 100), sort_order, created_at
  # 售后原因一级分类

aftersale_reason
  id, name(UNIQUE VARCHAR 100), category_id(FK→aftersale_reason_category, SET NULL),
  keywords(TEXT逗号分隔), sort_order, use_count, created_at
  # 二级原因；category_id 可为空

aftersale_keyword_candidate
  id, reason_id(FK→aftersale_reason CASCADE), keyword(VARCHAR 20), count(DEFAULT 1)
  # UNIQUE(reason_id, keyword)
  # 确认工单时从备注提取候选词累计 count；晋升需 count ≥ 2（_KW_PROMOTE_THRESHOLD）且质量分 ≥ 0.45，并受跨原因热点词（spread ≥ 3）抑制；晋升后写入 aftersale_reason.keywords 并删除候选行
  # 孤儿清理：手动编辑 reason.keywords 后候选行不自动消失；每次 confirm_case 时顺带清理该工单涉及原因的孤儿候选行
  # 候选池上限 1000 行，超限时按 id 升序删除最旧的 count=1 行；手动清理接口：POST /api/aftersale/admin/cleanup-keyword-candidates

aftersale_shipping_alias
  id, name(UNIQUE VARCHAR 200), keywords(JSON 物料名/代码关键词列表), sort_order, created_at
  # 发货物料简称；匹配与学习逻辑见 frontend-aftersale.md


aftersale_reason_alias_affinity
  id, reason_id(FK→aftersale_reason CASCADE), shipping_alias_id(FK→aftersale_shipping_alias CASCADE),
  count(DEFAULT 1), updated_at
  # UNIQUE(reason_id, shipping_alias_id)
  # 工单确认时，对每条同时有 reason_id + shipping_alias_id 的 reason 行 count+1
  # 用于在候选简称基础分相同时做二次排序（亲和度高的排前）
  # 查询接口：POST /api/aftersale/alias-affinity {reason_id, alias_ids} → {alias_id: count}

aftersale_shipping_ignore_term
  id, term(UNIQUE VARCHAR 100), created_at
  # 发货物料名包含该词时跳过简称匹配与学习

aftersale_product_remark_dict
  id, type(ENUM material/color/drive_type/size), value(VARCHAR 50), display(VARCHAR 50 nullable),
  enabled(TINYINT DEFAULT 1), sort_order(INT DEFAULT 0), created_at
  # UNIQUE(type, value)
  # 供 suggest_product 结构化解析买家留言中的材质/颜色/驱动方式/尺寸关键词
  # size 类型须填写 display（米制表达，如 '1.2米'），供型号名匹配用
  # 初始化：运行 backend/create_product_remark_dict.py；管理入口：词典 Tab → 产品匹配词典

aftersale_dict_suggestion
  id, type(ENUM stopword|ignore_term|promoted_keyword|synonym_candidate),
  value(VARCHAR 100), reason(VARCHAR 500), meta(JSON nullable),
  count(DEFAULT 1), status(ENUM pending|accepted|rejected),
  created_at, updated_at
  # UNIQUE(type, value)
  # 系统在工单确认时自动生成词典优化建议；已拒绝的建议不再重复触发
  # stopword: 跨原因高频候选词建议加入停用词
  # ignore_term: 物料名通用前缀词建议加入发货过滤词
  # promoted_keyword: 自动晋升的关键词，建议用户归类为故障词或部件词
  # synonym_candidate: 疑似同义词对，meta 含 reason_ids（路径一/二均用）
  #   路径一（跨原因中频词）：meta.reason_ids=涉及原因列表，value=候选词本身
  #   路径二（同原因子串重叠）：meta.longer/shorter，value="长词→短词"
  #   接受时需前端传 canonical（归一词），后端写入 aftersale_reason_synonym_rule

aftersale_reason_stopword
  id, term(UNIQUE VARCHAR 100), enabled, sort_order, created_at
  # 原因词典：停用词（enabled 为假不参与加载）

aftersale_reason_fault_term
  id, term(UNIQUE VARCHAR 100), enabled, sort_order, created_at
  # 原因词典：故障核心词

aftersale_reason_component_term
  id, term(UNIQUE VARCHAR 100), enabled, sort_order, created_at
  # 原因词典：部件词

aftersale_reason_short_keep_term
  id, term(UNIQUE VARCHAR 100), enabled, sort_order, created_at
  # 原因词典：短词保留（≤2 字默认视为泛词，在此表中的词除外）

aftersale_reason_synonym_rule
  id, pattern(UNIQUE VARCHAR 200), replacement(VARCHAR 100),
  is_regex(BOOL), enabled, sort_order, created_at
  # 同义词归一；pattern 可为多个别名字面量用 | 拼接（前端「原因词典」如此生成）

aftersale_case
  id, ecommerce_order_no(UNIQUE VARCHAR 100),
  products(JSON 物料行列表，元素含 code/name/quantity 等),
  seller_remark(TEXT), buyer_remark(TEXT),
  shipped_date(DATE), operator, channel_name, province, city, district,
  status(ENUM pending|confirmed|ignored, DEFAULT pending),
  processed_at(DATETIME), created_at, updated_at
  # 索引：ix_aftersale_case_order_no / shipped_date / status

aftersale_case_reason
  id, case_id(FK→aftersale_case CASCADE),
  reason_id(FK→aftersale_reason nullable),
  reason_category_id(FK→aftersale_reason_category SET NULL),
  model_id(FK→product_model SET NULL),
  shipping_alias_id(FK→aftersale_shipping_alias SET NULL),
  purchase_date(DATE), days_since_purchase(INT),
  created_at
  # 一条工单多条原因行；发货简称为 ID 外键，非纯文本冗余列
```

## 产品库
```
import_product_raw
  id, code(UNIQUE), name, group_code, group_name, imported_at
  # Excel列：品号(0)/品名(1)/规格(2)/品号群组(7)/群组名称(8)
  # name = 品名（去除「（已停用）」）+ 规格

erp_code_rules
  id, prefix, type(finished/packaged/semi/material), description, is_disabled(TINYINT 0/1 DEFAULT 0), created_at
  # UNIQUE(prefix, type)，同一前缀可对应多个类型，无优先级
  # type含义：finished=成品，packaged=产成品，semi=半成品，material=物料
  # is_disabled=1 时，成品表/图片/图表视图过滤掉该前缀的成品（全局生效）

product_category
  id, name(UNIQUE), sort_order, created_at

product_series
  id, category_id(FK), code, name, sort_order, created_at
  # UNIQUE(category_id, code)  ← code 在同一品类内唯一（跨品类可重复）

product_model
  id, series_id(FK), code, name, name_en, model_code(UNIQUE), sort_order, created_at
  # UNIQUE(series_id, code)    ← code 在同一系列内唯一（跨系列可重复）
  # model_code 全局唯一

product_finished
  id, code(UNIQUE), status, model_id(FK→product_model),
  listed_yymm, delisted_yymm, market(domestic/foreign/both),
  cover_image, created_at, updated_at
  # status: unrecorded=未录入, recorded=已录入, ignored=无需录入
  # market: domestic=内销, foreign=外贸, both=内外销

product_packaged
  id, code(UNIQUE), name, length, width, height,
  volume, gross_weight, net_weight, created_at, updated_at

product_finished_packaged
  finished_id(FK), packaged_id(FK), PRIMARY KEY(finished_id, packaged_id)

product_tag
  id, name(UNIQUE), color(default:#c4883a), created_at

product_finished_tag
  finished_id(FK), tag_id(FK), PRIMARY KEY(finished_id, tag_id)

product_param_key
  id, name(VARCHAR 64), group_name(VARCHAR 20), sort_order, created_at
  # group_name: dimension=尺寸, config=配置, brand=品牌, other=其他
  # UNIQUE(name, group_name)

product_finished_param
  id, finished_id(FK→product_finished CASCADE), key_id(FK→product_param_key CASCADE),
  value(VARCHAR 255), sort_order, created_at, updated_at
  # UNIQUE(finished_id, key_id)
  # 保存使用 Upsert（按 key_id 对比已有记录，更新/插入/删除）

product_resource_type
  id, name(VARCHAR 100 UNIQUE NOT NULL), sort_order(INT DEFAULT 0), created_at
  # 资料类型；预置种子数据：说明书/安装视频/售后视频/专利/认证
  # 有资料时禁止删除（Service 层校验，返回 fail）

product_resource
  id, title(VARCHAR 200 NOT NULL), type_id(FK→product_resource_type RESTRICT nullable),
  url(VARCHAR 1000 NOT NULL), storage_key(VARCHAR 500 nullable),
  source(VARCHAR 20 DEFAULT 'external'),   # 'oss' | 'external'
  file_type(VARCHAR 20 DEFAULT 'link'),    # 'pdf' | 'image' | 'video' | 'link' | 'other'
  original_filename(VARCHAR 300 nullable),
  description(TEXT), tag_condition(JSON nullable), created_at, updated_at
  # type_id=NULL 为未分类（侧边栏"未分类"入口可筛选）
  # storage_key 仅 source='oss' 时有值，用于生成签名 URL
  # tag_condition=NULL → 旧 OR 逻辑（产品有任意关联标签即匹配）
  # tag_condition={op:'AND'|'OR', items:[{tag_id,not?}|{op,items},...]} → 支持 AND/OR/NOT 任意嵌套
  #   例：{"op":"AND","items":[{"tag_id":1},{"op":"OR","items":[{"tag_id":2},{"tag_id":3}]}]}
  # product_resource_tag 中间表保留，存扁平 tag 集合（SQL 候选过滤用），Python 层再按 tag_condition 精确匹配
  # 删除标签时自动从所有资料的 tag_condition 中清除（tag.py _clean_tag_id_from_condition）

product_finished_resource          # 成品-资料 直接关联（多对多）
  finished_id(FK→product_finished CASCADE),
  resource_id(FK→product_resource CASCADE),
  sort_order(INT DEFAULT 0),
  PRIMARY KEY(finished_id, resource_id)

product_resource_tag               # 资料-标签 关联（标签继承）
  resource_id(FK→product_resource CASCADE),
  tag_id(FK→product_tag CASCADE),
  PRIMARY KEY(resource_id, tag_id)
  # 产品若带有该标签，则自动继承此资料（link_type='tag'）

product_resource_model             # 资料-型号 关联（型号继承）
  resource_id(FK→product_resource CASCADE),
  model_id(FK→product_model CASCADE),
  PRIMARY KEY(resource_id, model_id)
  # 产品若属于该型号，则自动继承此资料（link_type='model'）
```

## BOM 成本库（`backend/database/models/rd/cost.py`）

建表脚本：`backend/create_cost_tables.py`

```
cost_snapshot
  id, order_no(VARCHAR 100), snapshot_date(DATE nullable),
  notes(TEXT), created_by(VARCHAR 50), created_at

cost_snapshot_sku                          # 每个快照的产成品（可多个）
  id, snapshot_id(FK→cost_snapshot CASCADE),
  finished_code(VARCHAR 50), finished_name(VARCHAR 200),
  total_cost(DECIMAL 12,4 nullable), created_at

cost_bom_node                              # 物料/半成品/成品节点（跨快照去重，按 code 不含版本）
  id, code(VARCHAR 50 UNIQUE), code_with_version(VARCHAR 50),
  name(VARCHAR 200), spec(TEXT nullable), category(VARCHAR 100 nullable),
  node_type(ENUM material/semi/finished DEFAULT material),
  is_purchased_semi(BOOLEAN DEFAULT False),  # 外购半成品：整体采购，子件不计价
  purchase_type(VARCHAR 50 nullable), material_type(VARCHAR 50 nullable),
  weight_kg(DECIMAL 10,4 nullable), area_m2(DECIMAL 10,4 nullable),
  notes(TEXT nullable), created_at, updated_at
  # material_category 不存储，由 erp_code_rules 前缀匹配动态计算

cost_bom_line                              # BOM 父子关系行（属于某个 sku）
  id, sku_id(FK→cost_snapshot_sku CASCADE),
  parent_node_id(FK→cost_bom_node), child_node_id(FK→cost_bom_node),
  seq(INT nullable), quantity(DECIMAL 12,4), unit_price(DECIMAL 12,4 nullable),
  total_price(DECIMAL 12,4 nullable)

cost_material_price                        # 物料价格记录（手动 + BOM导入自动写入）
  id, node_id(FK→cost_bom_node CASCADE),
  snapshot_id(FK→cost_snapshot SET NULL nullable),  # BOM导入时关联快照
  unit_price(DECIMAL 12,4), price_date(DATE nullable),
  supplier_name(VARCHAR 100 nullable),
  source(VARCHAR 20 DEFAULT 'manual'),  # 'manual' | 'bom_import'
  notes(TEXT nullable), created_at

cost_material_supplier                     # 物料供应商报价（可标记首选）
  id, node_id(FK→cost_bom_node CASCADE),
  supplier_name(VARCHAR 100), unit_price(DECIMAL 12,4 nullable),
  price_date(DATE nullable), is_preferred(BOOLEAN DEFAULT False),
  notes(TEXT nullable), created_at

cost_material_rule                         # 物料匹配规则（保留，暂未使用）
  id, pattern(VARCHAR 200), rule_type(VARCHAR 50), action(VARCHAR 200),
  priority(INT DEFAULT 0), is_active(BOOLEAN DEFAULT True), created_at

cost_column_alias                          # Excel 列名映射（key → aliases[]）
  id, field_key(VARCHAR 50 UNIQUE), aliases(JSON)
```

### 关键设计
- `cost_bom_node.code` 去版本后缀存储（`-A01` 等通过 `_strip_version` 剥离），跨快照复用同一节点
- `code_with_version` 存原始品号用于显示
- 外购半成品（`is_purchased_semi=True`）：BOM 导入时跳过其子件行，`total_price` 取自身价格
- 自制半成品：API 返回时 `total_price = 子件合计`，不存储计算值
