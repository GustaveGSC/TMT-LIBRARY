# 后端接口（完整）

## 鉴权说明
所有接口（除下方标注「公开」外）均需浏览器携带有效的 `tmt_session` Cookie。
登录接口通过 `Set-Cookie` 下发 `tmt_session`（httpOnly）和 `tmt_csrf`；响应体不包含 token。注册接口不自动登录。
后续请求只接受 Cookie 会话，不再接受 `Authorization: Bearer`。写请求必须携带与 `tmt_csrf` Cookie 一致的 `X-CSRF-Token`，且该值与签名会话绑定。
401 → 后端统一清除认证 Cookie，前端清理本地展示状态并跳转 `/login`。

未预期的服务端异常统一返回 HTTP 500 和通用消息，`data.error_id` 及消息中的错误编号可用于关联服务端完整 traceback；数据库、文件路径、OSS 等原始异常文本不返回客户端。文件大小、类型等受控校验错误仍返回明确的 400/413 信息。

| 蓝图 | 策略 |
|------|------|
| account | login / register 公开；本人改密需登录；用户、角色和分析端点按下方显式权限矩阵 |
| version | GET 公开；POST 仅 admin |
| product / category / lifecycle 等 | `product:view`（读）+ `product:edit`（写） |
| shipping | `shipping:view` + `shipping:edit`；导出需 `shipping:export` |
| aftersale | `aftersale:view` + `aftersale:edit`；导出需 `aftersale:export` |
| rd | `rd:view`（读）+ `rd:edit`（写）；reminders 管理另需 `rd:admin` |

权限体系已切换为显式权限码授权：

| 权限域 | 权限码 | 目标接口范围 |
|---|---|---|
| 开发者 | `developer:analytics:view` | 登录日志、DAU、用户登录统计 |
| 管理者 | `account:users:view/edit` | 用户查看与管理 |
| 管理者 | `account:roles:view/edit` | 角色、权限查看与管理 |
| 运维 | `ops:login-config:edit` | 登录页轮播文案修改 |

`developer`、`manager`、`ops` 是标准权限包。功能授权只检查 JWT 中的显式权限码，不因 `admin` 角色名或 `author` 用户名直接放行；admin 已通过数据库角色权限关联获得全部标准权限，author 已显式获得 developer 角色。`admin`/`author` 不可删除禁用仍是账号保护规则，不是功能授权。Electron 版本发布功能已冻结，本轮不修改 version 蓝图，version 写接口暂时保留 legacy admin 角色检查，等待死功能清理。

环境变量：
- `JWT_SECRET`：JWT 签名密钥，生产必须设置强随机值
- `APP_ENV`：默认为 `production`；仅 `development` / `dev` / `local` / `test` / `testing` 跳过生产密钥校验
- `JWT_SECRET`、`SHARE_SECRET`：生产环境必须设置为非默认强密钥，否则应用拒绝启动
- `ALLOW_REGISTER`：公开注册默认关闭；仅 `true` / `1` / `yes` 明确开启
- 密码统一要求至少 6 个字符且 UTF-8 编码不超过 72 字节；注册、管理员创建/更新、本人改密和管理员重置均执行相同服务层校验
- 登录失败限流：同一账号 5 分钟 5 次、同一客户端 IP 5 分钟 20 次；登录成功清除该账号失败计数
- 注册限流：公开注册开启时，同一客户端 IP 每小时最多 5 次；超限统一返回 HTTP 429 `{success:false,message:"尝试次数过多，请稍后重试"}`
- 客户端 IP 读取 nginx 设置的 `X-Real-IP`，本地未经过代理时回退到 `request.remote_addr`
- 注册用户 JWT 包含 `ver`；账号被禁用、删除、改密、重置密码或权限变化后，旧 token 立即失效
- 过期、伪造、旧版本、已禁用或已删除账号的 token 均返回标准 HTTP 401，前端沿用现有统一登出处理

```
GET    /health
GET    /ready                                         # 公开；数据库可查询时 200 {status:"ready"}，否则 503 {status:"not_ready"}

GET    /api/config/login-mottos                       # 公开；返回登录页轮播语句字符串数组，配置缺失/损坏时返回内置默认值
PUT    /api/config/login-mottos                       # ops:login-config:edit；body {mottos:string[]}，去除空白项后至少保留一条；成功返回保存后的数组

POST   /api/account/login                             # 公开；登录时自动写入 user_login_log（成功/失败均记录）；失败受账号+IP双维度限流
POST   /api/account/register                          # 公开但默认关闭（通过 ALLOW_REGISTER=true 开启）；注册后无角色/业务权限，仅可使用无需权限码的通用工具；同IP每小时最多5次
POST   /api/account/logout                            # 清除会话/CSRF Cookie；幂等；有效会话请求需通过 CSRF
GET    /api/account/login-logs                        # developer:analytics:view；?page&per_page&username
GET    /api/account/login-stats/dau                   # developer:analytics:view；?days=30 → [{date,count}]
GET    /api/account/login-stats/users                 # developer:analytics:view → [{username,display_name,total,success_count,failed_count,last_login_at,identity_type}]
GET    /api/account/users                             # account:users:view
POST   /api/account/users                             # account:users:edit
PUT    /api/account/users/:id                         # account:users:edit；仅允许 display_name，禁止 roles/token_version/status/password 等 mass assignment
DELETE /api/account/users/:id                         # account:users:edit
PUT    /api/account/users/:id/password                # 本人，或 account:users:edit
PUT    /api/account/users/:id/status                  # account:users:edit
POST   /api/account/users/:id/reset-password          # account:users:edit；admin/author 受保护账号仅 admin 角色操作者可重置
POST   /api/account/users/:id/roles/:id               # account:users:edit；admin 为冻结存量角色，任何操作者均不可再分配
DELETE /api/account/users/:id/roles/:id               # account:users:edit；撤销 admin 角色额外要求操作者已是 admin
GET    /api/account/roles                             # account:roles:view
POST   /api/account/roles                             # account:roles:edit
DELETE /api/account/roles/:id                         # account:roles:edit；内置 admin 角色不可删除
POST   /api/account/roles/:id/permissions/:code       # account:roles:edit
GET    /api/account/permissions                       # account:roles:view
POST   /api/account/permissions                       # account:roles:edit
PUT    /api/account/permissions/:id                   # account:roles:edit

本人成功修改密码后，响应为 200，同时清除当前会话与 CSRF Cookie；前端应在显示成功提示后清理本地展示状态并跳转登录页。具备 `account:users:edit` 的管理者操作其他用户时不清管理者会话。

GET    /api/version/latest
GET    /api/version/list
POST   /api/version/
POST   /api/version/presign   # body: {filename,file_size}；响应 required_headers，PUT 必须原样携带；上限 500MB
POST   /api/version/upload    # 服务器中转上传 OSS（已不推荐，保留兼容）

POST   /api/product/import/preview
POST   /api/product/import
GET    /api/product/stats
GET    /api/product/finished
POST   /api/product/finished       # body 可含 remark（TEXT，可为空）；列表项同步返回 remark
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
DELETE /api/category/models/:id                       # 被成品或售后工单引用时返回 400，需先迁移关联数据

GET    /api/product/tags/categories/                  # 标签分类列表（含旗下 tags[]、finance_dimension_field: country|brand|null）
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

GET    /api/product-detail-packages                    # product:view；?search&page&size，返回 {items,total,page,size}
POST   /api/product-detail-packages                    # product:edit；新建 {name}
GET    /api/product-detail-packages/:id                # product:view；返回单个包完整信息（含 tag_ids/tag_condition/model_ids/series_ids/category_ids/media[]）
PUT    /api/product-detail-packages/:id                # product:edit；重命名 {name}
DELETE /api/product-detail-packages/:id                # product:edit；删除包及 DB 媒体记录；OSS 清理失败留痕、不回滚成功删除
PUT    /api/product-detail-packages/:id/tags           # product:edit；全量设置 {tag_ids:[int],tag_condition?:null|object|array}
PUT    /api/product-detail-packages/:id/models         # product:edit；全量设置 {model_ids:[int]}
PUT    /api/product-detail-packages/:id/series         # product:edit；全量设置 {series_ids:[int]}
PUT    /api/product-detail-packages/:id/categories     # product:edit；全量设置 {category_ids:[int]}
POST   /api/product-detail-packages/:id/media/presign  # product:edit；批量 {files:[{ext,original_filename,file_size}]}
                                                      #   返回每项 presign_url/storage_key/oss_url/file_type/file_size/required_headers；仅 image/video，单项上限500MB
POST   /api/product-detail-packages/:id/media/confirm  # product:edit；{files:[{storage_key,original_filename,file_size}]}
                                                      #   key 必须属于当前包且不得有子路径；storage_key 全局唯一
DELETE /api/product-detail-packages/:id/media/:media_id # product:edit；DB 先删除，OSS 失败留痕
GET    /api/product-detail-packages/finished/:code     # product:view；返回当前成品匹配的包及媒体，匹配为型号 OR 标签条件

GET    /api/product/params/keys                       # 所有键名按分组聚合
POST   /api/product/params/keys                       # 创建键名 {name, group_name, sort_order?}
PUT    /api/product/params/keys/:key_id               # 更新键名
DELETE /api/product/params/keys/:key_id               # 删除键名（返回 usage_count 供前端二次确认）
GET    /api/product/params/finished/:finished_id      # 获取成品参数，按分组聚合
POST   /api/product/params/finished/:finished_id      # 全量 Upsert 保存成品参数

POST   /api/product/lifecycle/update                  # 启动产品生命周期更新；product:edit
                                                      # 成功 200: data={task_id}
                                                      # 已有任务时 409: data={task_id}，前端接管该任务
GET    /api/product/lifecycle/tasks/:task_id          # 查询持久化任务；product:view；建议每秒短轮询
                                                      # 200: data={task_id,task_type,status,progress,result,message,
                                                      #            created_at,updated_at,finished_at}
                                                      # 不存在时 404；响应 Cache-Control:no-store
GET    /api/product/lifecycle/progress/:task_id       # 旧前端兼容；立即返回单次 SSE 快照后关闭，
                                                      # 不再等待队列/占用 sync worker；新前端禁止使用

POST   /api/shipping/import/shipping                  # 上传发货清单（发货端），返回 task_id；source='shipping'
POST   /api/shipping/import/finance                   # 上传财务清单（财务端），返回 task_id；正数量→发货(source='finance')，负数量→销退，售后组过滤
                                                      #   仅 UPSERT 新增或字段实际变化的行；完全相同行计入 skipped
                                                      #   新增/变化的发货或销退订单在同一事务内自动增量重算派生组合
                                                      #   结果 inserted/updated/skipped 与 returns 对应字段分别表示新增/变化/未变化行数
                                                      #   done.result 另含：
                                                      #   customer_alias_conflicts_count: 本文件订单中存在多个非空客户简称的订单总数
                                                      #   customer_alias_conflicts_order_nos: string[]，按订单号升序、最多100项
                                                      #   customer_alias_conflicts_truncated: boolean，总数超过返回清单长度时为true
                                                      #   客户简称冲突只提示、不阻断导入
                                                      #   独立销退清单接口已废弃，销退数据统一通过财务清单负数量行导入
                                                      #   Excel/CSV 单文件 20MB、解压后 100MB、最多 50 sheet/100000 行
GET    /api/shipping/tasks/:task_id                   # 后台任务统一短轮询入口（需 shipping 权限，建议 1-2 秒间隔，Cache-Control:no-store）
POST   /api/shipping/tasks/:task_id/cancel            # shipping:edit；持久化、幂等地请求取消
                                                      # 四类数据写任务均支持；成功 data 含
                                                      # task_id/task_type/status/cancel_requested/cancellable
                                                      # 不存在404；不支持/已结束400；committing阶段409
GET    /api/shipping/import/status/:task_id           # 兼容旧客户端，响应同 /tasks/:task_id
GET    /api/shipping/import/progress/:task_id         # 已废弃 SSE 兼容入口；立即返回单次持久化快照后关闭，
                                                      # 不再等待终态/占用 sync worker；新客户端禁止使用
POST   /api/shipping/import/cancel/:task_id           # 旧取消入口，转发到 /tasks/:task_id/cancel
GET    /api/shipping/operators                        # 获取所有最近操作人及其分类
POST   /api/shipping/operators/classify               # 批量保存操作人分类 [{operator, type}]
GET    /api/shipping/stats                            # 统计摘要
GET    /api/shipping/shipped-dates                    # 所有发货记录的 shipped_date（去重升序，不含销退日期）
POST   /api/shipping/resolve                          # 刷新 is_stale 订单的成品组合；旧 /task-status 轮询入口保留，状态已持久化
                                                      # 默认最多10000个(order_no,source)，可用
                                                      # MAX_STALE_RESOLVE_ORDERS调整；超限任务直接error且不建staging
POST   /api/shipping/resolve-all                      # 全量重新计算所有订单成品组合；返回 task_id
                                                      # 当前默认维护关闭：未显式配置 ALLOW_FULL_RESOLVE=true 时
                                                      # 立即返回 HTTP 503，不创建任务/租约/暂存数据
                                                      #   import/shipping、import/finance、resolve-all、resolve 均通过 tasks/:task_id 轮询
                                                      #   四类数据写任务（另含 POST /resolve）数据库级互斥；
                                                      #   已有任务运行时返回 409，data.task_id 为当前任务
                                                      #   resolve 写 task 隔离 staging 后做小范围事务替换；
                                                      #   resolve-all 直接构建同构 standby，shipping+finance
                                                      #   全部完成后用单条 MySQL RENAME TABLE 原子交换
GET    /api/shipping/warehouses                       # 所有出现过的仓库名及 is_excluded 状态
POST   /api/shipping/warehouses/filter                # 批量保存仓库过滤配置 [{warehouse_name, is_excluded}]；同事务标记受影响订单 stale
GET    /api/shipping/finance-customer-aliases         # shipping:view；客户简称计数+人工映射，?keyword=&page=1&per_page=100（上限500）
POST   /api/shipping/finance-customer-aliases/mapping # shipping:edit；新增或更新人工映射

`GET /api/shipping/finance-customer-aliases` 查询参数：`keyword` 可选字符串，按客户简称包含匹配；`page` 默认 1；`per_page` 默认 100、最大 500。成功响应：

```json
{"success":true,"message":"success","data":{"items":[{"customer_alias":"外贸-印尼-PT","occurrences":120,"mapping":{"id":1,"customer_alias":"外贸-印尼-PT","status":"export","country":"印尼","brand":"Brand A","note":null,"updated_at":"2026-07-21 18:00:00"}}],"page":1,"per_page":100,"total":1,"status":null}}
```

未维护的简称其 `mapping` 为 `null`。GET 可传 `status=pending|export|domestic|non_sales`；其中 `pending` 同时包含 `mapping=null` 和显式 pending，非法值返回 400。`POST /api/shipping/finance-customer-aliases/mapping` 请求体：`customer_alias`（必填字符串，最长255）、`status`（必填，四选一：`pending` 未审核、`export` 外贸客户、`domestic` 内销客户、`non_sales` 非销售客户）、`country`（可选，最长100）、`brand`（可选，最长100）、`note`（可选，最长1000）。成功返回 `{success,message,data}`，其中 `data` 是保存后的完整 mapping；参数错误返回 400，无编辑权限返回 403。该接口已移除 `is_export`，旧前端请求不兼容。
GET    /api/shipping/equivalents                      # 列出所有通用件对（含 name_a/name_b 产成品名称）
POST   /api/shipping/equivalents                      # 新增 {code_a, code_b, note?}；服务端保证 code_a<code_b；校验产成品存在，并标记受影响订单 stale
DELETE /api/shipping/equivalents/<id>                 # 删除通用件对，并标记受影响订单 stale

上述仓库过滤、通用件对、以及成品-产成品关联写接口均复用发货数据变更租约：若导入或重算正在运行，返回 `409 { success:false, data:{task_id} }`。成功响应的 `data` 保留原字段，并新增 `stale_pairs`、`stale_limit`、`requires_full_resolve`。规则保存与 `is_stale` 标记在同一事务提交；当 `requires_full_resolve=true` 时，配置已保存且不会部分重算，调用方应引导用户执行完整重建。
GET    /api/shipping/chart-options                    # 渠道名和省份去重列表；?source=shipping|finance 过滤来源
                                                      #   返回额外含 tag_dimensions: [{category_id,name,color,tags:[{id,name}],value_kind:'id'|'name'}]
                                                      #   source=finance 的 finance_dimension_field=country/brand 分类取客户映射 country/brand 去重值，value_kind='name'（前端须传 tag_names）；其余维度为产品标签，value_kind='id'
                                                      #   source=finance 另含 map_dimension_category_id（country 财务维度 id）；source=shipping 为 null，且不返回任一财务维度
                                                      #   （已配置 is_shipping_dim=1 的标签分类及其 shipping_dim_enabled=1 的标签，见 database.md product_tag_category）
POST   /api/shipping/chart-data                       # 图表聚合数据，body 含 source('shipping'|'finance')、trade_type('all'|'domestic'|'foreign')
                                                      #   source=shipping：trade_type 保留历史 FTP 产品判断（前端固定传 all）
                                                      #   source=finance：domestic/foreign 仅按人工映射 status=domestic/export；pending、non_sales、未映射均不进入两者，all 仍包含全部
                                                      #   group_by 除固定维度外，可传 'tag:<category_id>' 按该标签分类聚合（需先在数据配置中启用该分类为发货维度）
                                                      #   source=finance 且标签分类 finance_dimension_field=country/brand 时，按人工映射的 country/brand 聚合；仅 status=export 且值非空的数据参与
                                                      #   按“品牌”聚合的 item 额外含 name（该品牌对应的一个或多个国家，以逗号分隔），供 tooltip 副标题显示；地域聚合不含 name
                                                      #   tag_filters?: [{category_id, tag_ids?, tag_names?}]，与 group_by 相互独立
                                                      #   source=finance 且分类 finance_dimension_field=country/brand 时可直接传 tag_names（字符串数组，单项最长100，最多100项），按人工映射文本筛选
                                                      #     tag_names 不要求 product_tag 中存在同名标签；与 tag_ids 同时传时取名称并集，同一分类内为 OR、不同分类之间为 AND
                                                      #   其他来源/分类忽略 tag_names，仍只支持 tag_ids，以保持产品标签筛选语义
POST   /api/shipping/map-breakdown                    # shipping:view；财务端世界地图的批量悬浮细分
                                                      #   body: source 固定 finance、country_category_id（finance_dimension_field='country'）、
                                                      #         countries（去重后 1..100 个国家）、breakdown_group_by（series 或 tag:<品牌分类ID>）
                                                      #   可附带与 chart-data 相同的 date_start/date_end/category_ids/series_ids/model_ids/
                                                      #         tag_filters/channel_names/channel_codes/provinces/cities/districts 筛选项；不接受 trade_type
                                                      #   单条 grouped 查询返回 data.items:[{country,label,name?,quantity,return_quantity,actual_quantity}]，
                                                      #         按 country、actual_quantity desc、label 排序；仅人工映射 status=export 且 country 非空的财务数据
                                                      #   source 非 finance、地域/品牌维度无效或必填字段非法返回 400；无 shipping:view 返回 403
                                                      #   不适用于 source=shipping 的产品标签多对多地图，后者继续使用原 chart-data 路径

GET    /api/aftersale/pending                         # 待处理订单列表（动态查询，尚未建工单的售后操作人订单）
                                                      #   page>=1，page_size 1..200；非法值返回 400
GET    /api/aftersale/pending/count                   # 待处理订单数量
POST   /api/aftersale/media/precheck                  # aftersale:view；{order_nos: string[1..200]} 批量返回每单已有媒体摘要
POST   /api/aftersale/media/presign                   # aftersale:edit；{order_no,mode:append|replace,files:[{ext,file_size,original_filename}]}
                                                      # 返回不可伪造 session_token 和批量 OSS PUT 签名；服务端预留 seq，1小时过期
POST   /api/aftersale/media/confirm                   # aftersale:edit；{session_token}；只以 session 服务端 manifest 落库
                                                      # replace 先提交新记录再补偿删除旧 OSS；清理失败写入留痕表
POST   /api/aftersale/cases/media-flags               # aftersale:view；{order_nos:string[1..200]} → {order_no: media_count}，单次 GROUP BY
GET    /api/aftersale/cases/:order_no/media           # aftersale:view；按需返回该订单全部图片/视频
DELETE /api/aftersale/media/:id                       # aftersale:edit；先删 DB 记录，后补偿删除 OSS；OSS 失败留痕但仍返回成功
POST   /api/aftersale/suggest-product                 # 型号/物料等推荐；body 含 product_codes、seller_remark 等
                                                      #   返回 data 中可含 suggestions：
                                                      #   suggested_shipping_alias_id, suggested_return_alias_id,
                                                      #   suggested_return_alias_source('library'|'history'|null),
                                                      #   suggested_return_alias_score（仅 library 匹配时有值）,
                                                      #   suggested_reason_id, suggested_reason_category_id
GET    /api/aftersale/cases                           # 工单列表（分页+服务端排序）；?has_media=true|1 时仅返回存在媒体的订单
                                                      #   params: page/page_size/status/date_start/date_end/order_no/
                                                      #           channel_name/province/city/district/
                                                      #           reason_category/reason_name/
                                                      #           shipping_alias/return_alias/model_code/
                                                      #           sort_by/sort_order(asc|desc)
                                                      #   page>=1，page_size 1..200；各批量 ID 筛选最多 200 个正整数
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
                                                      #   params: ids（逗号分隔，最多 200 个正整数）
                                                      #   返回：{ "case_id": [reason...] } 字典
GET    /api/aftersale/cases/:id                       # 单条工单详情（含 reasons）
POST   /api/aftersale/cases                           # 确认/创建工单（body: {order_no, products, remarks, reasons[]}）
                                                      #   同一订单已 confirmed 时幂等返回原工单且不重复学习；
                                                      #   修改已确认工单必须使用 PUT /cases/:id
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
GET    /api/aftersale/shipping-aliases                # 发货物料简称列表；每项含实时 use_count（工单原因引用次数）
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

`GET /api/shipping/tasks/:task_id` 需要任一 shipping 权限，无请求参数；建议活动任务每
1–2 秒轮询，终态立即停止。`/import/status/:task_id` 是相同响应的兼容别名。成功响应：

```json
{
  "success": true,
  "message": "success",
  "data": {
    "task_id": "UUID",
    "task_type": "import_shipping | import_finance | resolve_all | resolve_stale",
    "status": "pending | running | committing | done | error | cancelled | interrupted",
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
- `committing` 表示任务已通过最终提交 CAS，不能再取消；该状态通常很短暂。
- `error/cancelled/interrupted` 时查看 `message`；`interrupted` 表示 worker 被重启或 reload，导入事务不会留下部分业务数据。
- 不存在的 task_id 返回 HTTP 404；终态查询不会删除记录。
- 新前端只使用本接口短轮询；旧 SSE 入口仅返回调用时的一次快照，不等待状态变化。

`POST /api/shipping/tasks/:task_id/cancel` 对四类任务均生效。导入任务在文件解析、数据库
分块比对/写入、增量成品组合解析及最终提交前检查；命中取消会回滚整个导入事务。
`resolve_stale` 分块提交的仅是 task_id 隔离的 staging，不会改变正式结果；默认安全上限为
10000 个 `(order_no, source)`，未完成更大范围门禁前拒绝执行。`resolve_all` 分块构建与正式表
同构的 standby；取消或失败不会修改正式表。成功通过 `running → committing` CAS 后，数据表和
代际标记由一条 MySQL `RENAME TABLE` 原子交换。DDL 与任务状态不能共用事务，因此新 worker 会先
读取随表交换的代际标记：rename 已完成则把 committing 任务恢复为 done，未完成才标 interrupted。
所有任务的最终提交均用 CAS 与取消请求竞争，committing 后取消返回 409。

全量重算成功 result 在原字段外增加 `"cutover":"rename"` 和
`"retired_generation_retained":true`；旧正式代保留在 standby，验收后才能显式清理，下一次
全量重建开始时也会先清空。生产在新门禁通过前仍不得设置 `ALLOW_FULL_RESOLVE=true`。

## 上传安全限制

- Flask `MAX_CONTENT_LENGTH` 默认 500MB，可通过同名环境变量（字节数）覆盖；全局超限统一返回 HTTP 413 和 `{success:false,message}`。
- 产品、发货/财务、ECR/BOM/PDM、成本库 Excel/CSV：单文件 20MB；校验扩展名、MIME 和真实文件头；xlsx 解压后 100MB、最多 2000 个内部文件、50 个工作表、100000 行。
- 产品封面及原始封面：每张 Base64 解码后 10MB，仅 PNG/JPEG/WebP，声明 MIME 必须与真实图片格式一致。
- OSS 预签名接口必须接收 `file_size`，签名绑定 `Content-Length`；前端 PUT 时必须使用响应中的 `required_headers`。

## /api/rd（研发工具）

权限：`rd:view`（读/处理）与 `rd:edit`（POST 写请求，沿用 Blueprint 守卫）。以下文件解析接口仅接受经过上传校验的 `multipart/form-data`：

```
POST   /api/rd/ecr/parse-ecr             # ecr_file：ECR xlsx/xls；返回表单字段与 changes
POST   /api/rd/ecr/compare-bom           # bom_before + bom_after：两个 BOM xlsx；返回 changes/stats
POST   /api/rd/pdm2bom/process            # pdm_file：PDM xlsx；返回 columns/table_data/error_map/total_level
```

- 缺文件、非法类型/文件头返回 400，文件超限返回 413。
- `ecr_path`、`bom_before_path`、`bom_after_path`、`file_path` 旧 Electron JSON 协议已下线；非 multipart 请求返回 400，服务端不会检查或读取请求中指定的路径。

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
