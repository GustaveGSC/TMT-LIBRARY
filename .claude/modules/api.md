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
GET    /api/aftersale/cases                           # 已处理工单列表（分页+筛选：status/date/reason/channel/province）
GET    /api/aftersale/cases/:id                       # 单条工单详情（含 reasons）
POST   /api/aftersale/cases                           # 确认/创建工单（body: {order_no, products, remarks, reasons[]}）
PUT    /api/aftersale/cases/:id                       # 更新工单 reasons
POST   /api/aftersale/cases/:order_no/ignore          # 标记为忽略
POST   /api/aftersale/auto-match                      # body: {text} → 两阶段匹配（关键词库+历史相似度），返回 Top5 建议
GET    /api/aftersale/reasons                         # 原因库（按 category 聚合）
POST   /api/aftersale/reasons                         # 创建原因
PUT    /api/aftersale/reasons/:id                     # 更新原因
DELETE /api/aftersale/reasons/:id                     # 删除原因
GET    /api/aftersale/reasons/:id/usage               # 查询使用次数
GET    /api/aftersale/stats                           # 统计摘要（pending/confirmed/ignored 数量 + Top5 原因）
GET    /api/aftersale/chart-options                   # 筛选选项（channels/provinces/categories）
POST   /api/aftersale/chart-data                      # 图表聚合数据，body: {group_by('reason'|'channel'|'province'|'month'), date_start?, ...}
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
