# 后端接口（完整）

## 鉴权说明
所有接口（除下方标注「公开」外）均需 `Authorization: Bearer <token>` 请求头。  
token 由登录/游客/注册接口返回，前端存于 `localStorage.tmt_token`，由 axios 拦截器自动附加。  
401 → 前端清 localStorage 并跳转 `/login`。

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
- `ALLOW_REGISTER`：`false` / `0` / `no` 可关闭公开注册（默认 `true`）

```
GET    /health

POST   /api/account/login                             # 公开；登录时自动写入 user_login_log（成功/失败均记录）
GET    /api/account/guest                             # 公开；游客登录，返回 token（仅 product:view 权限）
POST   /api/account/register                          # 公开（可通过 ALLOW_REGISTER=false 关闭）；注册后默认 guest 角色
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

GET    /api/version/latest
GET    /api/version/list
POST   /api/version/
POST   /api/version/presign   # 生成 OSS 预签名 PUT URL，body: {filename} → {presign_url, oss_url}；前端直传 OSS 用
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

GET    /api/product/tags/
POST   /api/product/tags/
PUT    /api/product/tags/:id
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
PUT    /api/resources/:id/tags                        # 设置关联标签 {tag_ids:[...]}（全量替换）
PUT    /api/resources/:id/models                      # 设置关联型号 {model_ids:[...]}（全量替换）
GET    /api/resources/:id/signed-url                  # 生成 OSS 签名 GET URL（?disposition=inline|attachment）
POST   /api/resources/presign                         # 预签名直传 {ext} → {presign_url, oss_url, storage_key, file_type}
                                                      #   OSS key 格式：tmt-library/resources/{YYYYMM}/{ts}_{uuid8}.{ext}

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

POST   /api/shipping/import/shipping                  # 上传发货清单，返回 task_id
POST   /api/shipping/import/return                    # 上传销退清单，返回 task_id（仅处理负数量行，按订单号匹配）
GET    /api/shipping/import/progress/:task_id         # SSE 进度流：parsing→parsed→inserting→inserted→resolving→done/error/cancelled
POST   /api/shipping/import/cancel/:task_id           # 发送中止信号，后台完成当前 chunk 后 rollback
GET    /api/shipping/operators                        # 获取所有最近操作人及其分类
POST   /api/shipping/operators/classify               # 批量保存操作人分类 [{operator, type}]
GET    /api/shipping/stats                            # 统计摘要
GET    /api/shipping/shipped-dates                    # 所有发货记录的 shipped_date（去重升序，不含销退日期）
POST   /api/shipping/resolve                          # 刷新 is_stale 订单的成品组合
POST   /api/shipping/resolve-all                      # 全量重新计算所有订单成品组合（SSE 进度，task_id 复用 import/progress 流）
GET    /api/shipping/warehouses                       # 所有出现过的仓库名及 is_excluded 状态
POST   /api/shipping/warehouses/filter                # 批量保存仓库过滤配置 [{warehouse_name, is_excluded}]
GET    /api/shipping/chart-options                    # 渠道名和省份去重列表 {channels, provinces}
POST   /api/shipping/chart-data                       # 图表聚合数据，body: {group_by, date_start?, date_end?, channel_names?, provinces?, category_id?, series_id?, model_id?} → {summary, items}

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
                                                      #   返回：{task_id}；上限 EXPORT_MAX_ROWS=50000 行
GET    /api/aftersale/cases/export/status/<task_id>  # 轮询导出进度
                                                      #   返回：{status: 'pending'|'done'|'error', message}
                                                      #   error 状态会自动 pop 任务；任务 30 分钟 TTL 自动清理
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
