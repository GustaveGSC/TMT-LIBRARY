# 产品详情文件夹：缺一个"查询单个文件夹完整信息"接口，交接 Codex

状态：待实现（阻塞中——前端功能已部署，双击进入文件夹目前必现 405，见下方"现状"）。

## 背景

前端"产品详情管理"页（`ProductDetailPackages.vue`）双击进入某个文件夹时，需要展示该文件夹
已上传的全部图片/视频。现有接口没有一个能满足这个需求：

- `GET /api/product-detail-packages`（列表）只返回 `media_count`/`cover_thumbnail`，不含完整
  `media` 数组。
- `GET /api/product-detail-packages/finished/:code`（成品匹配）虽然会返回 `media`，但要求传入
  一个真实的成品 code，且只返回"匹配到当前成品"的文件夹，不能用来单独查一个指定的文件夹。

## 现状（真实报错，已由用户在生产复现）

前端 `openFolder()` 调用 `GET /api/product-detail-packages/:id`，该路径当前只注册了
`PUT`/`DELETE`，没有 `GET`，浏览器控制台报：

```
GET https://tmt-library.cn/api/product-detail-packages/3 405 (METHOD NOT ALLOWED)
```

**任何文件夹（不管有没有图片）双击进入都会报这个错，媒体网格显示为空**——不是"只有已有内容
的文件夹才受影响"，是这条交互路径完全不可用。这是当前唯一阻塞"产品详情文件夹"功能可用的问题。

## 需要实现

新增 `GET /api/product-detail-packages/:id`，返回单个文件夹的完整信息（`name`/`tag_ids`/
`tag_condition`/`model_ids`/`media` 数组）。可以直接复用现有的 `DetailPackageRepository.get()`
+ `media_for_packages([id])` 拼装，不需要新查询逻辑：

```python
def get_one(self, package_id):
    package = DetailPackageRepository.get(package_id)
    if not package:
        return Result.fail('产品详情包不存在')
    media = DetailPackageRepository.media_for_packages([package_id])[package_id]
    return Result.ok(data=package.to_dict(media=media))
```

路由权限 `product:view` 即可（只读）。

## 契约要点（前端已经在按这个假设调用）

`GET /api/product-detail-packages/:id` → `{ success, data: { id, name, tag_ids, tag_condition,
model_ids, media: [{id, file_type, original_filename, oss_url, storage_key, file_size,
sort_order, created_at}, ...] } }`

## 不需要的改动

- 不需要迁移，不需要改现有其它接口（列表/成品匹配）的返回结构。

## 验证要求（提交前请确认）

- `pytest backend/tests -q`、`python -m compileall -q backend`、`git diff --check` 照例通过。
- 真实 HTTP：新建文件夹 → 上传两张图 → 用新接口查询该文件夹 id → 确认 `media` 数组含两条
  记录、字段完整（`oss_url`/`file_type`/`original_filename`）；对一个不存在的 id 请求应返回
  `success:false`，不是 500。

## Claude 后续动作（提交后我会执行）

按既有纪律本地测试 → 审查代码 → 部署（本批预计无迁移，只需同步改动的路由/服务文件后
reload）→ 真实 HTTP 验证 → 用真实浏览器确认"双击进入文件夹不再 405，已有内容的文件夹能正确
显示图片"。
