# 后端接口（完整）

## 鉴权说明
所有接口（除下方标注「公开」外）均需浏览器携带有效的 `tmt_session` Cookie。
登录/游客接口通过 `Set-Cookie` 下发 `tmt_session`（httpOnly）和 `tmt_csrf`；响应体不包含 token。注册接口不自动登录。
后续请求只接受 Cookie 会话，不再接受 `Authorization: Bearer`。写请求必须携带与 `tmt_csrf` Cookie 一致的 `X-CSRF-Token`，且该值与签名会话绑定。
401 → 后端统一清除认证 Cookie，前端清理本地展示状态并跳转 `/login`。

未预期的服务端异常统一返回 HTTP 500 和通用消息，`data.error_id` 及消息中的错误编号可用于关联服务端完整 traceback；数据库、文件路径、OSS 等原始异常文本不返回客户端。文件大小、类型等受控校验错误仍返回明确的 400/413 信息。

| 蓝图 | 策略 |
|------|------|
| account | login / guest / register 公开；改密需登录（仅限本人或 admin）；其余仅 admin |
| version | GET 公开；POST 仅 admin |
| product / category / lifecycle 等 | `product:view`（读）+ `product:edit`（写） |
| shipping | `shipping:view` + `shipping:edit`；导出需 `shipping:export` |
| aftersale | `aftersale:view` + `aftersale:edit`；导出需 `aftersale:export` |
| rd | `rd:view`（读）+ `rd:edit`（写）；reminders 管理另需 `rd:admin` |

环境变量：
- `JWT_SECRET`：JWT 签名密钥，生产必须设置强随机值
- `APP_ENV`：默认为 `production`；仅 `development` / `dev` / `local` / `test` / `testing` 跳过生产密钥校验
- `JWT_SECRET`、`SHARE_SECRET`：生产环境必须设置为非默认强密钥，否则应用拒绝启动
- `ALLOW_REGISTER`：公开注册默认关闭；仅 `true` / `1` / `yes` 明确开启
- 注册用户 JWT 包含 `ver`；账号被禁用、删除、改密、重置密码或权限变化后，旧 token 立即失效
- 游客 JWT 每次请求使用数据库中的当前 guest 角色权限，不长期信任 token 内嵌权限
- 过期、伪造、旧版本、已禁用或已删除账号的 token 均返回标准 HTTP 401，前端沿用现有统一登出处理

```
GET    /health
GET    /ready                                         # 公开；数据库可查询时 200 {status:"ready"}，否则 503 {status:"not_ready"}

POST   /api/account/login                             # 公开；登录时自动写入 user_login_log（成功/失败均记录）
GET    /api/account/guest                             # 公开；游客登录并下发 Cookie 会话（仅 product:view 权限）
POST   /api/account/register                          # 公开但默认关闭（通过 ALLOW_REGISTER=true 开启）；注册后默认 guest 角色
POST   /api/account/logout                            # 清除会话/CSRF Cookie；幂等；有效会话请求需通过 CSRF
GET    /api/account/login-logs                        # 登录记录原始列表（author 专用）?page&per_page&username
GET    /api/account/login-stats/dau                   # 日活统计（author 专用）?days=30 → [{date,count}]
GET    /api/account/login-stats/users                 # 账号登录统计（author 专用）→ [{username,display_name,total,success_count,failed_count,last_login_at,identity_type}]
GET    /api/account/users
POST   /api/account/users
PUT    /api/account/users/:id
DELETE /api/account/users/:id
POST   /api/account/users/:id/roles/:id
DELETE /api/account/users/:id/roles/:id
GET    /api/account/roles
POST   /api/account/roles
DELETE /api/account/roles/:id
POST   /api/account/roles/:id/permissions/:code
GET    /api/account/permissions
POST   /api/account/permissions
PUT    /api/account/permissions/:id

本人成功修改密码后，响应为 200，同时清除当前会话与 CSRF Cookie；前端应在显示成功提示后清理本地展示状态并跳转登录页。管理员修改其他用户密码时不清管理员会话。

GET    /api/version/latest
GET    /api/version/list
POST   /api/version/
POST   /api/version/presign   # body: {filename,file_size}；响应 required_headers，PUT 必须原样携带；上限 500MB
POST   /api/version/upload    # 服务器中转上传 OSS（已不推荐，保留兼容）

POST   /api/product/import/preview
POST   /api/product/import
GET    /api/product/stats
GET    /api/product/finished
POST   /api/product/finished
GET    /api/product/packaged/all
GET    /api/product/packaged/candidates
POST   /api/product/packaged
GET    /api/product/finished/:id/packaged
POST   /api/product/finished/:id/packaged/:id
DELETE /api/product/finished/:id/packaged/:id

GET    /api/erp-code-rules/
POST   /api/erp-code-rules/
PUT    /api/erp-code-rules/:id
DELETE /api/erp-code-rules/:id

GET    /api/category/tree
POST   /api/category/categories
PUT    /api/category/categories/:id
DELETE /api/category/categories/:id
POST   /api/category/series
PUT    /api/category/series/:id
DELETE /api/category/series/:id
POST   /api/category/models
PUT    /api/category/models/:id
DELETE /api/category/models/:id

GET    /api/product/tags/categories/                  # 标签分类列表（含旗下 tags[]）
POST   /api/product/tags/categories/                  # 新增分类 {name,color?,sort_order?}
PUT    /api/product/tags/categories/:id                # 更新分类 {name,color?,sort_order?,is_shipping_dim?}
                                                      #   is_shipping_dim 未传则保留原值；传 true/false 控制该分类是否作为发货图表聚合维度
                                                      #   传了 is_shipping_dim 时会顺带清空 shipping chart-options 缓存（否则最多 5 分钟才生效）
DELETE /api/product/tags/categories/:id                # 删除分类（旗下标签移至未分类）
GET    /api/product/tags/
POST   /api/product/tags/
PUT    /api/product/tags/:id                          # {name,category_id?,color?,shipping_dim_enabled?}
                                                      #   shipping_dim_enabled 未传则保留原值；控制该标签在其分类作为发货维度时是否纳入统计
                                                      #   传了 shipping_dim_enabled 时同上会清空 chart-options 缓存
DELETE /api/product/tags/:id
POST   /api/product/tags/finished/:finished_id/:tag_id
DELETE /api/product/tags/finished/:finished_id/:tag_id

GET    /api/resources/types                           # 列出所有资料类型（按 sort_order）；product:view
POST   /api/resources/types                           # 新增类型 {name, sort_order}；admin only
PUT    /api/resources/types/:type_id                  # 编辑类型；admin only
DELETE /api/resources/types/:type_id                  # 删除类型（有资料时 fail）；admin only

GET    /api/resources                                 # 列出资料库 ?type_id&search&page&size；type_id='none' 查未分类
                                                      #   返回 {items, total}，每条含 linked_count（三路 UNION 计算）
POST   /api/resources                                 # 新建资料 {title,type_id,url,source,file_type,storage_key,original_filename,description}
PUT    /api/resources/:id                             # 编辑资料
DELETE /api/resources/:id                             # 删除资料（同时解除所有关联）
PUT    /api/resources/:id/tags                        # 设置关联标签 {tag_ids:[...], tag_condition?:null|{op,items}}（全量替换）
                                                      # tag_condition=null → 旧 OR 逻辑；对象 → AND/OR/NOT 树形条件
PUT    /api/resources/:id/models                      # 设置关联型号 {model_ids:[...]}（全量替换）
GET    /api/resources/:id/signed-url                  # 生成 OSS 签名 GET URL（?disposition=inline|attachment）
POST   /api/resources/presign                         # 预签名直传 {ext,file_size} → {presign_url,oss_url,storage_key,file_type,file_size,required_headers}
                                                      #   OSS key 格式：tmt-library/resources/{YYYYMM}/{ts}_{uuid8}.{ext}
                                                      #   PUT 必须携带响应中的 Content-Type/Content-Length；上限 500MB

GET    /api/resources/finished/:code                  # 获取产品关联资料（直接+标签继承+型号继承，去重，含 link_type）
POST   /api/resources/finished/:code                  # 直接关联资料 {resource_id, sort_order}
DELETE /api/resources/finished/:code/:resource_id     # 解除直接关联
PUT    /api/resources/finished/:code/order            # 更新排序 {ordered_ids:[...]}

GET    /api/product/params/keys                       # 所有键名按分组聚合
POST   /api/product/params/keys                       # 创建键名 {name, group_name, sort_order?}
PUT    /api/product/params/keys/:key_id               # 更新键名
DELETE /api/product/params/keys/:key_id               # 删除键名（返回 usage_count 供前端二次确认）
GET    /api/product/params/finished/:finished_id      # 获取成品参数，按分组聚合
POST   /api/product/params/finished/:finished_id      # 全量 Upsert 保存成品参数

POST   /api/shipping/import/shipping                  # 上传发货清单（发货端），返回 task_id；source='shipping'
POST   /api/shipping/import/finance                   # 上传财务清单（财务端），返回 task_id；正数量→发货(source='finance')，负数量→销退，售后组过滤
                                                      #   独立销退清单接口已废弃，销退数据统一通过财务清单负数量行导入
                                                      #   Excel/CSV 单文件 20MB、解压后 100MB、最多 50 sheet/100000 行
GET    /api/shipping/import/progress/:task_id         # SSE 进度流：parsing→parsed→inserting→inserted→resolving→done/error/cancelled
GET    /api/shipping/import/status/:task_id           # 持久化状态查询（需 shipping 权限），SSE 断开/reload 后用 task_id 回查，不会读取后删除
POST   /api/shipping/import/cancel/:task_id           # 发送中止信号，后台完成当前 chunk 后 rollback
GET    /api/shipping/operators                        # 获取所有最近操作人及其分类
POST   /api/shipping/operators/classify               # 批量保存操作人分类 [{operator, type}]
GET    /api/shipping/stats                            # 统计摘要
GET    /api/shipping/shipped-dates                    # 所有发货记录的 shipped_date（去重升序，不含销退日期）
POST   /api/shipping/resolve                          # 刷新 is_stale 订单的成品组合；旧 /task-status 轮询入口保留，状态已持久化
POST   /api/shipping/resolve-all                      # 全量重新计算所有订单成品组合（SSE 进度，task_id 复用 import/progress 流）；两个 source 分开 resolve
                                                      #   import/shipping、import/finance、resolve-all 均可通过 import/status 回查终态
GET    /api/shipping/warehouses                       # 所有出现过的仓库名及 is_excluded 状态
POST   /api/shipping/warehouses/filter                # 批量保存仓库过滤配置 [{warehouse_name, is_excluded}]
GET    /api/shipping/equivalents                      # 列出所有通用件对（含 name_a/name_b 产成品名称）
POST   /api/shipping/equivalents                      # 新增 {code_a, code_b, note?}；服务端保证 code_a<code_b；校验产成品存在
DELETE /api/shipping/equivalents/<id>                 # 删除通用件对
GET    /api/shipping/chart-options                    # 渠道名和省份去重列表；?source=shipping|finance 过滤来源
                                                      #   返回额外含 tag_dimensions: [{category_id,name,color,tags:[{id,name}]}]
                                                      #   （已配置 is_shipping_dim=1 的标签分类及其 shipping_dim_enabled=1 的标签，见 database.md product_tag_category）
POST   /api/shipping/chart-data                       # 图表聚合数据，body 含 source('shipping'|'finance')、trade_type('all'|'domestic'|'foreign')
                                                      #   trade_type: domestic 排除 %-FTP 系列，foreign 仅保留 %-FTP 系列（后端 SQL LIKE）
                                                      #   group_by 除固定维度外，可传 'tag:<category_id>' 按该标签分类聚合（需先在数据配置中启用该分类为发货维度）
                                                      #   tag_filters?: [{category_id, tag_ids}]，与 group_by 相互独立的标签筛选（不管当前按什么维度聚合都生效），
                                                      #     同一分类内多个 tag_id 为 OR，不同分类之间为 AND

GET    /api/aftersale/pending                         # 待处理订单列表（动态查询，尚未建工单的售后操作人订单）
GET    /api/aftersale/pending/count                   # 待处理订单数量
POST   /api/aftersale/suggest-product                 # 型号/物料等推荐；body 含 product_codes、seller_remark 等
                                                      #   返回 data 中可含 suggestions：
                                                      #   suggested_shipping_alias_id, suggested_return_alias_id,
                                                      #   suggested_return_alias_source('library'|'history'|null),
                                                      #   suggested_return_alias_score（仅 library 匹配时有值）,
                                                      #   suggested_reason_id, suggested_reason_category_id
GET    /api/aftersale/cases                           # 工单列表（分页+服务端排序）
                                                      #   params: page/size/status/date_start/date_end/order_no/
                                                      #           channel_name/province/city/district/
                                                      #           reason_category/reason_name/
                                                      #           shipping_alias/return_alias/model_code/
                                                      #           sort_by/sort_order(asc|desc)
                                                      #   返回：{total, items[]} items 不含 reasons（两阶段加载）
POST   /api/aftersale/cases/export/start              # 启动异步导出（后台线程），立即返回 task_id
                                                      #   body: 与 GET /cases query params 同字段（JSON）
                                                      #   返回：{task_id}；上限 EXPORT_MAX_ROWS=50000 工单；分页+write-only 写临时文件
GET    /api/aftersale/cases/export/status/<task_id>  # 轮询导出进度
                                                      #   返回：{status: pending|running|done|error, message}；内部 interrupted 对旧前端映射为 error
                                                      #   状态和结果文件跨 worker reload 保留；任务 30 分钟 TTL 自动清理
GET    /api/aftersale/cases/export/download/<task_id># 下载已生成的 xlsx，下载后自动清理任务
                                                      #   一行一条原因记录；列：订单号/售后日期/购买日期/间隔天数/
                                                      #   产品型号/产品名称/一级原因/二级原因/发货物料简称/渠道/
                                                      #   省份/城市/县区/商家备注/买家留言
GET    /api/aftersale/cases/reasons                   # 批量获取指定工单的原因详情（selectinload，无N+1）
                                                      #   params: ids（逗号分隔的 case id 列表）
                                                      #   返回：{ "case_id": [reason...] } 字典
GET    /api/aftersale/cases/:id                       # 单条工单详情（含 reasons）
POST   /api/aftersale/cases                           # 确认/创建工单（body: {order_no, products, remarks, reasons[]}）
PUT    /api/aftersale/cases/:id                       # 更新工单 reasons
POST   /api/aftersale/cases/:order_no/ignore          # 标记为忽略
GET    /api/aftersale/filter-options                  # 表格筛选选项（raw SQL DISTINCT，懒加载）
                                                      #   返回：{channels, provinces, cities, districts,
                                                      #          reason_categories, reason_names,
                                                      #          shipping_aliases, return_aliases, model_codes}
POST   /api/aftersale/auto-match                      # body: {text, buyer_remark?, semantic?, model_id?}
                                                      #   model_id 可选：对历史无关联原因软降权 40%（冷启动时不过滤）
                                                      #   返回 Top5：reason_id, name, category_name, confidence,
                                                      #   source('keyword'|'history'|'case'|'semantic'), matched_keywords[],
                                                      #   keyword_score, case_score, history_score, semantic_score, total_score
GET    /api/aftersale/reason-keyword-rules            # 读取词典（仅 enabled 行；stopwords/fault_terms/component_terms/short_keep_terms 为 string[]）
PUT    /api/aftersale/reason-keyword-rules            # 全量覆盖词典表（先 delete 再插入）；body 同 GET 的 data 形状：
                                                      #   { stopwords[], fault_terms[], component_terms[], short_keep_terms[],
                                                      #     synonyms: [{ pattern, replacement, is_regex? }] } （缺省 is_regex 时服务端按 true）
                                                      #   未传 short_keep_terms 时保留库内原短词保留表（兼容旧客户端）
                                                      #   成功后返回最新词典；服务端缓存约 60s，提交后失效
GET    /api/aftersale/product-remark-dict             # 产品留言词典（全量，含 disabled）→ [{id,type,value,display,enabled,sort_order}]
PUT    /api/aftersale/product-remark-dict             # 全量替换；body: { items:[{type,value,display?,enabled?,sort_order?}] }
                                                      #   size 类型必须填 display；成功后返回最新全量列表；服务端缓存约 120s 后失效
GET    /api/aftersale/reasons                         # 原因库（按 category 聚合）
POST   /api/aftersale/reasons                         # 创建原因
PUT    /api/aftersale/reasons/:id                     # 更新原因
DELETE /api/aftersale/reasons/:id                     # 删除原因
GET    /api/aftersale/reasons/:id/usage               # 查询使用次数
POST   /api/aftersale/reasons/:source_id/merge-into/:target_id  # 合并原因（迁移引用+合并关键词+删除 source）
GET    /api/aftersale/reason-categories               # 所有一级分类
GET    /api/aftersale/shipping-ignore-terms           # 发货物料匹配过滤词列表
POST   /api/aftersale/shipping-ignore-terms           # 新增过滤词 {term}
DELETE /api/aftersale/shipping-ignore-terms/:id       # 删除过滤词
GET    /api/aftersale/shipping-aliases                # 发货物料简称列表
POST   /api/aftersale/shipping-aliases                # 新增发货物料简称 {name}
PUT    /api/aftersale/shipping-aliases/:id            # 更新发货物料简称
DELETE /api/aftersale/shipping-aliases/:id            # 删除发货物料简称
GET    /api/aftersale/return-aliases                  # 售后物料简称列表
POST   /api/aftersale/return-aliases                  # 新增售后物料简称 {name}
PUT    /api/aftersale/return-aliases/:id              # 更新售后物料简称
DELETE /api/aftersale/return-aliases/:id              # 删除售后物料简称
GET    /api/aftersale/model/:model_id/series-monthly  # 按月聚合指定 model 所属系列的售后工单数+发货实际量（仅有售后数据的月份）
GET    /api/aftersale/stats                           # 统计摘要（pending/confirmed/ignored 数量 + Top5 原因）
GET    /api/aftersale/chart-options                   # 图表筛选选项（channels/provinces/categories）
POST   /api/aftersale/chart-filter-options            # 联动筛选选项，body: {date_start?, date_end?, channel_names?, provinces?, cities?, model_ids?, reason_ids?, reason_category_ids?, shipping_alias_ids?, return_alias_ids?}
                                                      #   返回：{channels, provinces, cities, model_ids, reason_ids, shipping_alias_ids, return_alias_ids}（跨维度联动过滤）
POST   /api/aftersale/chart-data                      # 图表聚合数据，body: {group_by('product'|'reason_category'|'reason'|'shipping_alias'|'channel'|'province'), date_start?, date_end?, max_days_since_purchase?, channel_names?, provinces?, cities?, model_ids?, category_ids?, series_ids?, reason_ids?, reason_category_ids?, shipping_alias_ids?, return_alias_ids?}
                                                      #   reason_category：按一级分类聚合；reason：按具体原因聚合（通常在 reason_category 下钻后使用）
```

## /api/product/stats 返回结构
```json
{
  "total_finished":    <int>,   // 符合 finished 编码规则的 import 记录数（排除 ignored）
  "unprocessed":       <int>,   // total_finished - product_finished 非ignored记录数
  "last_imported_at":  "YYYY-MM-DD" | null,
  "days_since_import": <int> | null,
  "categories": [
    { "description": "xxx", "count": <int>, "unprocessed": <int> }
    // 按 erp_code_rules description 分组，按数量降序，均排除 ignored 产品
  ]
}
```

## 发货后台任务状态

`GET /api/shipping/import/status/:task_id` 需要任一 shipping 权限，无请求参数。成功响应：

```json
{
  "success": true,
  "message": "success",
  "data": {
    "task_id": "UUID",
    "task_type": "import_shipping | import_finance | resolve_all | resolve_stale",
    "status": "pending | running | done | error | cancelled | interrupted",
    "filename": "原上传文件名或 null",
    "progress": { "step": "inserting", "current": 100, "total": 500 },
    "result": null,
    "message": "",
    "created_at": "YYYY-MM-DD HH:mm:ss",
    "updated_at": "YYYY-MM-DD HH:mm:ss",
    "finished_at": null
  }
}
```

- `done` 时 `result` 与 SSE `done.data` 相同。
- `error/cancelled/interrupted` 时查看 `message`；`interrupted` 表示 worker 被重启或 reload，导入事务不会留下部分业务数据。
- 不存在的 task_id 返回 HTTP 404；终态查询不会删除记录。
- 前端 SSE `onerror` 后应调用本接口回查；若仍为 `pending/running` 可短暂轮询，进入终态后停止。

## 上传安全限制

- Flask `MAX_CONTENT_LENGTH` 默认 500MB，可通过同名环境变量（字节数）覆盖；全局超限统一返回 HTTP 413 和 `{success:false,message}`。
- 产品、发货/财务、ECR/BOM/PDM、成本库 Excel/CSV：单文件 20MB；校验扩展名、MIME 和真实文件头；xlsx 解压后 100MB、最多 2000 个内部文件、50 个工作表、100000 行。
- 产品封面及原始封面：每张 Base64 解码后 10MB，仅 PNG/JPEG/WebP，声明 MIME 必须与真实图片格式一致。
- OSS 预签名接口必须接收 `file_size`，签名绑定 `Content-Length`；前端 PUT 时必须使用响应中的 `required_headers`。

## /api/rd/cost（BOM 成本库）

权限：`rd:view`（读）/ `rd:edit`（写）

```
GET    /api/rd/cost/snapshots              # 成本快照列表，按产成品分组；?page&per_page
                                           #   → items:[{finished_code,finished_name,orders:[{sku_id,snapshot_id,order_no,snapshot_date,created_at,created_by,total_cost}]}]
POST   /api/rd/cost/preview               # 预览 BOM Excel（multipart file）
                                           #   → {order_no,sku_count,skus,warnings,suggested_date}
POST   /api/rd/cost/import                # 导入（JSON模式）：{preview_data,snapshot_date,notes}
                                           #   purchased_semi_codes 在 preview_data 内；外购半成品子件不写 bom_line
DELETE /api/rd/cost/snapshots/:id         # 删除整个快照（含所有 SKU）
DELETE /api/rd/cost/skus/:sku_id          # 删除单个 SKU 及其 BOM 行；若快照无剩余 SKU 则顺带删快照

GET    /api/rd/cost/sku/:sku_id/bom       # BOM 树；含 child_spec/child_code_with_version/material_category/supplier_name
                                           #   半成品 total_price = 子件合计（外购半成品保留自身价格）；按 child_code 排序

GET    /api/rd/cost/nodes                 # 物料节点查询；?q&node_type&page&per_page
                                           #   Python 侧按 erp_code_rules 前缀匹配 material_category，先按分类后按品号排序
GET    /api/rd/cost/nodes/:id             # 节点详情（含 suppliers、material_category）
PATCH  /api/rd/cost/nodes/:id             # 更新节点：is_purchased_semi / notes
GET    /api/rd/cost/nodes/:id/prices      # 价格记录（含 order_no via snapshot join）；按 price_date desc
POST   /api/rd/cost/nodes/:id/prices      # 手动添加价格记录 {unit_price,price_date?,supplier_name?,notes?}
PATCH  /api/rd/cost/prices/:id            # 更新价格记录 {unit_price?,supplier_name?,price_date?,notes?}
DELETE /api/rd/cost/prices/:id            # 删除价格记录
GET    /api/rd/cost/nodes/:id/usages      # 物料使用记录（BOM 出现次数，含 order_no/finished_code）
GET    /api/rd/cost/nodes/:id/price-history  # 物料历史价格（来自 BOM 行，按快照日期）
GET    /api/rd/cost/col-aliases           # 读取 Excel 列名映射
PUT    /api/rd/cost/col-aliases           # 更新 Excel 列名映射
```

### material_category 规则
物料分类通过 `erp_code_rules` 表前缀匹配得出（最长前缀优先），与产品库编码规则完全一致。不存储在 `cost_bom_node`，每次查询时动态计算。
