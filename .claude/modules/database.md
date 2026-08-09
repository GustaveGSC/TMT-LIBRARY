# 数据库表结构

## 迁移管理

- Alembic 配置：`alembic.ini`，迁移目录：`backend/migrations/`
- `20260720_01` 是生产现状的空 baseline，不包含业务 DDL
- `20260720_02` 新增 `shipping_task`
- `20260724_01` 为 `shipping_task` 新增数据库级互斥租约 `lease_key`
- `20260725_01` 新增成品组合安全重算暂存表 `shipping_resolve_target` /
  `shipping_order_finished_staging`
- `20260726_01` 新增与正式表同构的 `shipping_order_finished_next` standby，以及
  `shipping_order_finished_generation` / `_next` 代际标记
- `20260721_01` 清理不受支持的 `product:delete` 权限及既有角色关联
- `20260721_02` 增加财务客户简称字段、人工映射表，并规范财务行内部唯一键
- `20260721_03` 将客户简称带入成品组合结果，并增加 `(source, customer_alias)` 聚合索引
- `20260721_04` 将财务客户映射从布尔值改为四态审核状态
- `20260723_01` 删除已取消的 guest 角色及其关联
- `20260723_02` 准备开发者/管理者/运维权限域、标准角色和兼容映射
- 生产已完成 `stamp 20260720_01`，模型差异检查为 0
- `app.py` 启动时只校验数据库 revision，不执行隐式 DDL 或自动 upgrade
- 后续结构变更必须使用经人工审查的 Alembic revision，部署前单独 `upgrade head`

## 账号
```
users             id, username, password(bcrypt), display_name, is_active, token_version(default 0), created_at, updated_at
roles             id, name, description
permissions       id, code, name, description
user_roles        user_id, role_id
role_permissions  role_id, permission_id

标准权限域（20260723_02 起）
  developer:analytics:view
  account:users:view / account:users:edit
  account:roles:view / account:roles:edit
  ops:login-config:edit

标准角色权限包
  developer -> developer:analytics:view
  manager   -> 四个 account:* 权限
  ops       -> ops:login-config:edit

兼容映射
  # legacy admin 显式绑定迁移当时的全部标准权限，为后续移除代码级绕过做准备
  # author 追加 developer 角色，不撤销任何既有角色；生产现状核实后再决定是否撤销其他角色
  # admin 角色用户和 author 的 token_version 递增一次，重新登录后取得最新显式权限
  # 本 revision 不切换鉴权规则；普通业务账号不受影响

token_version
  # JWT 主动失效版本；禁用/启用账号、改密、重置密码、用户角色或角色权限变化时递增
  # JWT 中的 ver 必须与当前值一致，否则鉴权按 401 处理

user_login_log
  id, user_id(FK→users SET NULL nullable), username(输入的用户名),
  display_name(成功时记录), status(ENUM success/failed),
  machine_name(VARCHAR 128，主机名，用于区分游客身份), login_at(CST DateTime)
  # 每次登录尝试（包括密码错误/账号不存在/账号禁用）均写入
  # verify_password 记录；user_id 找不到用户时为 NULL；历史游客记录保留
  # 游客以 machine_name 区分不同用户（socket.gethostname() 服务端获取）

site_config       key(VARCHAR 64 PK), value(TEXT)
  # 生产 baseline 已有的站点级 key-value 配置；当前 login_mottos 以 JSON 字符串数组存储
  # 不允许应用启动时自动建表，后续结构变更统一走 Alembic
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
  customer_alias(客户简称，可空),
  source ENUM('shipping','finance') DEFAULT 'shipping'
  # UNIQUE(ecommerce_order_no, line_no, product_code, record_type, source)
  # source='shipping'：发货端 ERP 导出；source='finance'：财务端 ERP 导出（line_no='F:YYYYMMDD' 内部键）
  # 财务端「客户简称」为可选列；重导时按唯一键 UPSERT，非空 customer_alias 覆盖历史值

return_record
  id, batch_id(FK→shipping_batch), ecommerce_order_no, shipped_date,
  product_code, quantity(负值), warehouse_name, customer_alias(客户简称，可空)
  # ix_return_record_warehouse_order(warehouse_name, ecommerce_order_no)：仓库规则变更的影响范围反查
  # UNIQUE(ecommerce_order_no, product_code, shipped_date)
  # 发货端/财务端负数量行均写入此表

shipping_order_finished
  id, ecommerce_order_no, finished_code(NULL=未匹配), finished_name,
  quantity(发货数量), return_quantity(销退数量), actual_quantity(实际=发货-销退),
  shipped_date, operator, channel_name, province, customer_alias(客户简称，可空),
  is_stale, resolved_at,
  source ENUM('shipping','finance') DEFAULT 'shipping'
  # source 与 shipping_record 对应；两个来源独立 resolve，互不干扰
  # resolve 元数据采用“完成发货”代表行：shipped_date DESC, id DESC 的首行；
  # customer_alias 若代表行为空，再按同一确定性顺序回退首个非空值；全量重算可修正历史结果
  # INDEX(source)；INDEX(source, customer_alias)；INDEX(source, ecommerce_order_no) 用于 scoped stale 标记；图表查询必须带 source 过滤
  # 成品-组件、通用件、仓库排除规则变更时，仅受影响的既有 (source, order_no) 对置 is_stale=True；配置写入和标记同事务提交

return_warehouse_filter
  id, warehouse_name(UNIQUE), is_excluded(默认False), created_at
  # 配置计算成品组合时需忽略的仓库（UI：仓库配置 Tab）；调整后刷新全局数据即可生效

shipping_operator_type
  id, operator(UNIQUE), type(shipping/aftersale/unknown), created_at, updated_at
  # 「最近操作人」→ 发货/售后/未分类

shipping_finance_customer_mapping
  id, customer_alias(UNIQUE), status, country, brand, note, updated_at
  # 人工维护财务客户简称的外贸/国家/品牌属性；财务图表完全以此表为准
  # status: pending(未审核，默认) / export(外贸客户) / domestic(内销客户) / non_sales(非销售客户)
  # non_sales、pending 与未映射订单均不进入 domestic/foreign；国家/品牌维度只包含 export

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
  id, code(UNIQUE), name, raw_name(NULL), spec(NULL), status(NULL), group_code, group_name, imported_at
  # Excel 按表头名称映射列，缺少品号/品名/分组编码/分组名称时整单拒绝
  # name = 品名（去除「（已停用）」）+ 规格
  # raw_name = ERP 原始品名，仅供停用关键词等原始语义判定；不替代既有 name
  # 重导按 code 做差异更新；内容完全相同的行不写库

erp_code_rules
  id, prefix, type(finished/packaged/semi/material/useless), description, is_disabled(TINYINT 0/1 DEFAULT 0), created_at
  # UNIQUE(prefix, type)，同一前缀可对应多个类型，无优先级
  # type含义：finished=成品，packaged=产成品，semi=半成品，material=原材料，useless=无用物料
  # is_disabled=1 时，成品表/图片/图表视图过滤掉该前缀的成品（全局生效）

erp_group_category
  id, group_code(UNIQUE), is_finished, is_packaged, is_semi, is_material, is_useless,
  remark, updated_by, created_at, updated_at
  # ERP 分组默认大类；不存在记录或五项全 false 均表示未分类
  # 前缀例外规则命中时不再使用分组默认；大类允许多选
  # group_code 在 MySQL 显式使用 utf8mb4_0900_ai_ci，与 import_product_raw 对齐

product_material
  id, code(UNIQUE), short_name, category, spec, cover_image, cover_image_original,
  img_updated_at, remark, is_disabled(INDEX), created_at, updated_at
  # 只存人工属性，按首次保存/传图创建；ERP name/group_code/group_name 不复制
  # is_disabled 为保留列，当前运行时不读写；停用只读状态由 ERP status/关键词实时判定
  # code 在 MySQL 显式使用 utf8mb4_0900_ai_ci，与 import_product_raw 对齐

material_disable_keyword
  id, keyword(VARCHAR 64 UNIQUE), is_disabled, remark, created_at
  # 名称停用规则由界面维护；迁移预置“停用”“作废”，可增删改/停用

material_combo
  id, name(VARCHAR 200 UNIQUE), category(VARCHAR 100 nullable), remark(TEXT nullable),
  is_disabled(BOOLEAN DEFAULT false), sort_order(INT DEFAULT 0), created_by,
  created_at, updated_at
  # 人工维护的售后备件组合；不与产品/型号关联，不支持组合嵌套

material_combo_item
  id, combo_id(FK→material_combo CASCADE), material_code(VARCHAR 255),
  quantity(INT), sort_order(INT), created_at
  # UNIQUE(combo_id, material_code)；明细保存采用整体替换
  # material_code 不设 ERP 外键，MySQL 排序规则显式为 utf8mb4_0900_ai_ci
  # 查询时 JOIN import_product_raw/product_material；ERP 编码消失时保留并标记 is_missing

material_supplier
  id, name(VARCHAR 64 UNIQUE), contact(VARCHAR 64 nullable), remark(TEXT nullable),
  created_by, created_at, updated_at
  # 供应商主数据；关联物料/分组由 cost_material_price 反向实时汇总，不设人工关联表

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
  listed_yymm, delisted_yymm, market(domestic/foreign/both), remark(TEXT NULL),
  cover_image, created_at, updated_at
  # status: unrecorded=未录入, recorded=已录入, ignored=无需录入
  # market: domestic=内销, foreign=外贸, both=内外销

product_packaged
  id, code(UNIQUE), name, length, width, height,
  volume, gross_weight, net_weight, created_at, updated_at

product_finished_packaged
  finished_id(FK), packaged_id(FK), PRIMARY KEY(finished_id, packaged_id)

product_tag_category
  id, name(UNIQUE VARCHAR 32), color(default:#c4883a), sort_order,
  is_shipping_dim(BOOLEAN DEFAULT False), finance_dimension_field(VARCHAR 20 nullable), created_at
  # is_shipping_dim=True 时该分类作为发货图表可选聚合维度（数据管理→数据配置→标签分析维度 配置）
  # finance_dimension_field='country'|'brand' 时是财务客户映射维度：财务端固定显示、发货端不返回，
  # 不受 is_shipping_dim/shipping_dim_enabled 配置影响；NULL 为普通产品标签维度

product_tag
  id, name(UNIQUE), color(default:#c4883a), category_id(FK→product_tag_category nullable),
  shipping_dim_enabled(BOOLEAN DEFAULT True), created_at
  # shipping_dim_enabled=False 的标签在其分类作为发货维度时不参与聚合（也不落入任何兜底分组，直接不出现）
  # 同一产品在同一分类下若被打了多个标签，按标签维度聚合时该产品的发货记录会在多个标签分组中重复计入（多对多设计的已知边界情况，不做去重）

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

product_detail_package             # 独立的产品详情包，不复用 product_resource
  id, name(VARCHAR 200), tag_condition(JSON nullable), created_at, updated_at
  # 成品详情按“型号命中 OR 标签条件命中”展示；tag_condition 语义与 product_resource 相同

product_detail_package_media
  id, package_id(FK→product_detail_package CASCADE), file_type(image|video),
  original_filename(VARCHAR 300), oss_url(VARCHAR 1000), storage_key(VARCHAR 500 UNIQUE),
  file_size(BIGINT), sort_order, created_at

product_detail_package_tag / product_detail_package_model
  package_id(FK→product_detail_package CASCADE), tag_id/model_id(FK CASCADE), PRIMARY KEY(package_id, tag_id/model_id)

product_detail_package_series / product_detail_package_category
  package_id(FK→product_detail_package CASCADE), series_id/category_id(FK CASCADE), PRIMARY KEY(package_id, series_id/category_id)
  # 与型号/标签范围为 OR；关联系列或品类会动态覆盖其未来新增的型号与成品，不保存型号快照

product_detail_package_cleanup_failure
  id, package_id(nullable), storage_key, error_message, created_at
  # 数据库删除成功但 OSS 对象删除失败时留痕；不将已完成的删除操作伪装成失败
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
  supplier_id(FK→material_supplier SET NULL nullable, INDEX),
  source(VARCHAR 20 DEFAULT 'manual'),  # 'manual' | 'bom_import' | 'bom_calc'
  notes(TEXT nullable), created_at
  # 物料库通过 cost_bom_node.code_with_version 对应 import_product_raw.code，展示并维护同一份价格
  # 无成本节点的物料在首次手动加价时惰性创建节点；基础 code 冲突时复用既有节点

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

# 后台任务状态

`shipping_task` 保存发货导入、财务导入和全量重算任务状态：

- 主键 `id` 为接口返回的 UUID task_id。
- `task_type`: `import_shipping | import_finance | resolve_all | resolve_stale`。
- `status`: `pending | running | committing | done | error | cancelled | interrupted`。
- `progress`、`result` 为 JSON；不保存上传文件内容。
- 终态保留 7 天，由创建新任务时顺带清理。
- 新 worker 启动时先用正式代标记恢复 rename 已完成的 committing 全量任务为 done，再把其余
  pending/running/committing 标记为 interrupted。
- 导入业务数据使用单一事务；任务状态通过独立连接提交，不能提交业务 session。
- `lease_key` 为空或固定为 `shipping_data_mutation`；唯一约束保证发货导入、财务导入、
  全量重算和旧数据重算任一时刻只能运行一个。任务进入终态或启动恢复将其清空。
- `cancel_requested_at`/`cancel_requested_by` 持久化记录取消请求；取消请求本身不释放租约。
- 四类任务均支持取消。导入任务在原业务事务中回滚；局部重算只分块提交 task_id 隔离的
  staging；全量重算只分块提交 standby。取消/失败不会修改 `shipping_order_finished`。
- worker 最终提交前用 CAS 从 running 切到 committing，且要求 `cancel_requested_at IS NULL`；
  取消和提交只有一个能成功，committing 后接口返回409。
- 局部重算的正式表 cutover 与 `shipping_task=done` 在同一事务提交。全量重算必须先完成
  shipping、finance 两个 source 的完整 standby，再以单条 MySQL `RENAME TABLE` 同时交换数据表
  和代际标记；任务终态由标记提供 crash/reload 恢复依据。

`shipping_resolve_target` 保存某个重算 task 的订单范围，复合主键为
`(task_id, source, ecommerce_order_no)`。`shipping_order_finished_staging` 保存该 task 的完整
派生结果，业务列与 `shipping_order_finished` 对齐，并以 task_id 隔离。暂存表不与任务表建立
外键，避免 cutover/清理引入级联锁；终态超过一小时的遗留暂存数据会在下一次重算开始时清理。

`shipping_order_finished_next` 的列、默认值、排序规则和索引名必须与
`shipping_order_finished` 完全一致；生产迁移用 `CREATE TABLE ... LIKE` 保证物理结构相同。
两张 generation 表各固定一行 `id=1`，随数据表在同一条 rename 中交换。运行时切换前还会核验
四张代际表均为 InnoDB、正式/standby 结构一致、正式表没有外键引用、临时 swap 表不存在。
standby 中的退役旧代不会在发布后立即 TRUNCATE，以保留验收窗口内的快速回切能力；验收后可
显式清理，下一次全量重建开始时也会先清空。失败清理由分块 DELETE、独立新连接和最多三次退避
重试完成，遗留数据仍由延迟清理兜底。维护窗口如需回切，使用
`backend/scripts/rollback_shipping_generation.py --task-id <UUID> --confirm-task-id <UUID>`；
脚本会再次核验正式代标记，并使用同一条原子 rename 反向交换。验收通过后使用
`cleanup_shipping_retired_generation.py` 并重复传入同一个 task_id，显式释放退役代空间。

`product_lifecycle_task` 独立保存产品生命周期更新任务，不与发货任务表混用：

- 主键 `id` 为 UUID task_id，状态、进度、结果及时间字段与 `shipping_task` 的通用部分一致。
- `task_type` 不落库，接口固定返回 `product_lifecycle`。
- 固定 `lease_key=product_lifecycle_update`，唯一约束保证同一时刻只有一个生命周期更新。
- 重复启动返回 409 和当前持有租约的 task_id；终态释放租约。
- 新 worker 启动时把遗留 pending/running 标记为 interrupted；终态保留 7 天。
- 生命周期业务更新使用单一事务，任务进度通过独立连接提交。
