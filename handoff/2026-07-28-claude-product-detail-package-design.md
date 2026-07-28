# "产品详情管理"重新设计：独立文件夹式"包"（交接 Codex）

## 背景与决策过程

上一版方案（复用 `product_resource_type` 加一个"产品详情"类型，过滤展示）已撤销——用户反馈
"实际效果不理想"，原因是：产品详情的图片/视频经常是**大量一次性上传**，而且**内容应该完全
独立于"资料"**，不该依附在资料的类型系统里。

新方案：

1. **UI 层级**：产品详情页折叠区新增"产品详情管理"，与"资料"**同级**（不再是资料内部的子
   类型/子区块），改名为"产品详情管理"。
2. **内容模型**：新建一个完全独立的"包"（package）概念——外观是 Windows 文件夹图标，用户
   自由命名，包内可以拖拽上传任意数量的图片/视频。包与"资料"（`product_resource`）系统**不
   共享数据表**，是并行的新概念。
3. **产品与包的绑定方式**（已与用户确认，见下）：**包设置适用范围**——创建/编辑包时勾选
   哪些系列/型号/标签可以用这个包，产品详情页按当前产品的系列/型号/标签自动匹配展示对应的
   包，不需要每个产品手动选。

## 数据模型（新表，不复用 product_resource）

```
product_detail_package
  id, name(VARCHAR 200 NOT NULL), tag_condition(JSON nullable), created_at, updated_at
  # 参考 product_resource.tag_condition 的语义：NULL=旧OR逻辑（产品有任意关联标签即匹配），
  # {op:'AND'|'OR', items:[{tag_id,not?}|{op,items},...]} 支持任意嵌套 AND/OR/NOT

product_detail_package_media
  id, package_id(FK→product_detail_package CASCADE),
  file_type(VARCHAR 20，image|video), original_filename(VARCHAR 300),
  oss_url(VARCHAR 1000 NOT NULL), storage_key(VARCHAR 500 NOT NULL UNIQUE),
  file_size(BIGINT), sort_order(INT DEFAULT 0), created_at
  # 索引：ix_product_detail_package_media_package_id

product_detail_package_tag        # 包-标签 关联（标签继承匹配，扁平集合供 SQL 候选过滤）
  package_id(FK→product_detail_package CASCADE), tag_id(FK→product_tag CASCADE)
  PRIMARY KEY(package_id, tag_id)

product_detail_package_model      # 包-型号 直接关联（型号继承）
  package_id(FK→product_detail_package CASCADE), model_id(FK→product_model CASCADE)
  PRIMARY KEY(package_id, model_id)
```

**参考 `product_resource` 的既有匹配逻辑**（`ResourceRepository`/`resource_service` 里
"三路关联"和 `tag_condition` 精确匹配的实现），这批可以直接照搬同一套匹配算法应用到新表上，
不需要重新发明：SQL 层用 `product_detail_package_tag`/`product_detail_package_model` 做候选
过滤，Python 层再按 `tag_condition` 精确求值。

**为什么不直接复用 `product_resource` 加字段**：包的语义（自由命名的容器，内部塞若干张图/
视频）和"资料"（单条资料记录本身就是一个文件+标题+描述）不是同一个东西，硬塞会让两套语义
互相污染；新表结构更清晰，后续各自演化互不影响。

## 后端接口设计

新增 Blueprint 或复用现有 `resources` 蓝图下的子路径均可，Codex 自行判断，建议独立前缀
`/api/product-detail-packages`：

- `GET /api/product-detail-packages` — 管理页列表（分页/搜索），返回每个包的 `id/name/
  media_count/cover_thumbnail`（取第一张图片或视频首帧，供 Windows 文件夹图标叠加缩略图，
  没有则用纯文件夹图标）。
- `POST /api/product-detail-packages` — 新建包（仅 `name`，媒体和适用范围单独接口设置）。
- `PUT /api/product-detail-packages/:id` — 改名。
- `DELETE /api/product-detail-packages/:id` — 删除（级联删 media 行 + 对应 OSS 对象；参考
  `aftersale_case_media` 的删除模式：DB 先提交，OSS 逐个尝试删除，失败不回滚只留痕，可以复用
  或新建一张 `product_detail_package_cleanup_failure` 留痕表，参考
  `aftersale_media_cleanup_failure` 的设计）。
- `PUT /api/product-detail-packages/:id/tags` — 设置标签适用范围（`tag_ids` + `tag_condition`，
  参照 `PUT /api/resources/:id/tags` 的现成实现）。
- `PUT /api/product-detail-packages/:id/models` — 设置型号适用范围（参照
  `PUT /api/resources/:id/models`）。
- **上传媒体**（拖拽批量上传，包内文件可能很多）：
  - `POST /api/product-detail-packages/:id/media/presign` — 批量预签名，body 为文件列表
    `[{ext,file_size,original_filename}]`，一次返回该批全部文件的签名（参照
    `product/resource.py::presign_upload` 的单文件签名逻辑扩展成批量，OSS key 规则用
    `product-detail/{package_id}/{uuid}.{ext}`，不需要售后媒体那套"序号预留+session_token"
    的复杂度——包本身在上传前就已经存在（先建包再传文件），不存在"目标还不存在"的并发问题，
    只要 `storage_key` 用 uuid 保证唯一即可，不需要专门的会话预留表）。
  - `POST /api/product-detail-packages/:id/media/confirm` — 确认写入 DB 行（body 为
    presign 返回的 storage_key 列表，服务端按 key 前缀 `product-detail/{package_id}/` 校验
    key 确实属于这个包，防止越权把别的包/别的地方的 OSS 对象误关联进来）。
  - `DELETE /api/product-detail-packages/:id/media/:media_id` — 删除包内单个文件。
- `GET /api/product-detail-packages/finished/:code` — 产品详情页调用，返回按当前产品系列/
  型号/标签匹配到的包列表（含每个包的媒体列表，用于直接渲染画廊，不需要前端再拼两次请求）。

## 性能要求

- `GET /api/product-detail-packages/finished/:code` 必须是常数条查询（当前产品的标签/型号 →
  候选包 → 媒体），不能对每个包再单独查一次媒体列表（一次 JOIN 或一次 `IN` 批量查）。
- 批量上传 presign 一次请求返回整批签名，不要求前端每个文件单独调用一次 presign 接口。
- 管理页列表的 `cover_thumbnail`/`media_count` 需要是批量聚合查询，不能对每个包循环查。

## 前端（交给 Claude，本次不需要 Codex 处理）

- 产品详情页新增顶级折叠区"产品详情管理"，与"资料"同级，展示当前产品匹配到的包（画廊形式，
  复用 `MediaViewer` 查看）。
- 新建一个独立的"产品详情包管理"页面/弹窗（参照 `ProductResources.vue` 的资料库页面结构）：
  Windows 文件夹图标网格 + 新建/改名/删除包 + 点进包内拖拽上传图片视频 + 设置适用范围（复用
  `ProductResources.vue` 里"关联型号"el-cascader + "关联标签"tag_condition 构建器的现成 UI
  模式）。

## 验证要求

- 真实 MySQL 下验证：批量上传 presign 一次请求生成 N 个签名、confirm 校验 storage_key 前缀
  防越权、删除包级联删除媒体行+OSS对象（清理失败留痕）。
- 真实 HTTP 验证 `GET /api/product-detail-packages/finished/:code` 的匹配逻辑：按型号直接
  关联匹配、按标签 tag_condition（AND/OR/NOT）匹配、两者都匹配到同一个包时去重不重复返回。
- 查询数确认符合"性能要求"一节。
