# 后端接口（完整）

```
GET    /health

POST   /api/account/login
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
POST   /api/version/upload

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
POST   /api/aftersale/auto-match                      # body: {text}
                                                      #   返回 Top5：reason_id, name, category_name, confidence,
                                                      #   source('keyword'|'history'), matched_keywords[], keyword_score,
                                                      #   history_score, total_score（历史阶段仅关键词候选不足时启用）
GET    /api/aftersale/reason-keyword-rules            # 读取词典（仅 enabled 行；stopwords/fault_terms/component_terms/short_keep_terms 为 string[]）
PUT    /api/aftersale/reason-keyword-rules            # 全量覆盖词典表（先 delete 再插入）；body 同 GET 的 data 形状：
                                                      #   { stopwords[], fault_terms[], component_terms[], short_keep_terms[],
                                                      #     synonyms: [{ pattern, replacement, is_regex? }] } （缺省 is_regex 时服务端按 true）
                                                      #   未传 short_keep_terms 时保留库内原短词保留表（兼容旧客户端）
                                                      #   成功后返回最新词典；服务端缓存约 60s，提交后失效
GET    /api/aftersale/reasons                         # 原因库（按 category 聚合）
POST   /api/aftersale/reasons                         # 创建原因
PUT    /api/aftersale/reasons/:id                     # 更新原因
DELETE /api/aftersale/reasons/:id                     # 删除原因
GET    /api/aftersale/reasons/:id/usage               # 查询使用次数
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
GET    /api/aftersale/stats                           # 统计摘要（pending/confirmed/ignored 数量 + Top5 原因）
GET    /api/aftersale/chart-options                   # 图表筛选选项（channels/provinces/categories）
POST   /api/aftersale/chart-filter-options            # 联动筛选选项，body: {date_start?, date_end?, channel_names?, provinces?, cities?, model_ids?, reason_ids?, reason_category_ids?, shipping_alias_ids?, return_alias_ids?}
                                                      #   返回：{channels, provinces, cities, model_ids, reason_ids, shipping_alias_ids, return_alias_ids}（跨维度联动过滤）
POST   /api/aftersale/chart-data                      # 图表聚合数据，body: {group_by('product'|'reason'|'shipping_alias'|'channel'|'province'), date_start?, date_end?, max_days_since_purchase?, channel_names?, provinces?, cities?, model_ids?, category_ids?, series_ids?, reason_ids?, reason_category_ids?, shipping_alias_ids?, return_alias_ids?}
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
