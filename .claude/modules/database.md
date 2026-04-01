# 数据库表结构

## 账号
```
users             id, username, password(bcrypt), display_name, is_active, created_at, updated_at
roles             id, name, description
permissions       id, code, name, description
user_roles        user_id, role_id
role_permissions  role_id, permission_id
```

## 版本
```
app_version       id, version, description, download_url, created_at
```

## 发货数据
```
shipping_batch
  id, type(shipping/return), filename, row_count, imported_at

shipping_record
  id, batch_id(FK), ecommerce_order_no, line_no, shipped_date,
  channel_name, channel_code, channel_org_name, operator(最近操作人),
  product_code, product_name, spec, quantity, country, province, city,
  district, street, address, buyer_remark, seller_remark
  # UNIQUE(ecommerce_order_no, line_no, product_code)
  # 仅存发货数据；record_type 列存在但固定='shipping'（旧迁移残留，不再使用）
  # 文件内同 key 行先合并（quantity 累加）再与 DB 去重
  # 按列名匹配（_build_col_map），与列顺序无关，缺失必要列抛 ValueError
  # 必要列：电商主订单号/单据日期/渠道名称/渠道商/渠道商名称/最近操作人
  #         项次/商品型号/商品名称/数量/省份
  # 可选列（有则读取）：国家/市区/县区/街道/详细地址/规格/买家留言/商家备注

return_record
  id, batch_id(FK→shipping_batch), ecommerce_order_no, shipped_date,
  product_code, quantity(负值), warehouse_name
  # UNIQUE(ecommerce_order_no, product_code, shipped_date)
  # 独立存储销退清单原始数据（全量保存，不在导入时过滤仓库）
  # 必要列：平台订单/交易日期/品号/数量/仓库名称
  # 导入时：仅保留数量<0 的行；仅保留 ecommerce_order_no 在 shipping_record 已存在的行
  # 计算 shipping_order_finished 时动态过滤 is_excluded=True 的仓库，不影响原始数据

return_warehouse_filter
  id, warehouse_name(UNIQUE), is_excluded(默认False), created_at
  # 配置计算成品组合时需忽略的仓库（UI：仓库配置 Tab）；调整后刷新全局数据即可生效

shipping_operator_type
  id, operator(UNIQUE), type(shipping/aftersale/unknown), created_at, updated_at
  # 「最近操作人」→ 发货/售后/未分类

shipping_order_finished
  id, ecommerce_order_no, finished_code(NULL=未匹配), finished_name,
  quantity(发货数量), return_quantity(销退数量), actual_quantity(实际=发货-销退),
  shipped_date, operator, channel_name, province,
  is_stale(产品库变更后标记), resolved_at
  # 按订单对发货/销退数据分别贪心匹配成品组合，写入三列数量
```

## 售后数据
```
aftersale_reason
  id, name(UNIQUE), category(VARCHAR 50), keywords(TEXT, 逗号分隔),
  sort_order(INT), use_count(INT 引用次数), created_at

aftersale_case
  id, ecommerce_order_no(UNIQUE), products(JSON [{code,name,quantity}]),
  seller_remark(TEXT), buyer_remark(TEXT),
  shipped_date, operator, channel_name, province,
  status(ENUM: pending/confirmed/ignored, DEFAULT pending),
  processed_at(DATETIME nullable), created_at, updated_at
  # 来源：shipping_record 中 operator 属于 aftersale 类型的记录，按 ecommerce_order_no 聚合

aftersale_case_reason
  id, case_id(FK→aftersale_case CASCADE), reason_id(FK→aftersale_reason nullable),
  custom_reason(VARCHAR 200), involved_products(JSON nullable), notes(TEXT), created_at
  # 一个工单可拆分为多条原因记录（对应 seller_remark 中的多类问题）
```

## 产品库
```
import_product_raw
  id, code(UNIQUE), name, group_code, group_name, imported_at
  # Excel列：品号(0)/品名(1)/规格(2)/品号群组(7)/群组名称(8)
  # name = 品名（去除「（已停用）」）+ 规格

erp_code_rules
  id, prefix, type(finished/packaged/semi/material), description, created_at
  # UNIQUE(prefix, type)，同一前缀可对应多个类型，无优先级
  # type含义：finished=成品，packaged=产成品，semi=半成品，material=物料

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
```
