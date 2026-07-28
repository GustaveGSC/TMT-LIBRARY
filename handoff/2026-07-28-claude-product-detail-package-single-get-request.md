# 产品详情包：缺一个"查询单个包完整信息"接口（交接 Codex）

## 背景

前端"产品详情包管理"页（`ProductDetailPackages.vue`）点开某个包的详情弹窗时，需要展示该包
已上传的全部图片/视频。现有接口里没有一个能满足这个需求：

- `GET /api/product-detail-packages`（列表）只返回 `media_count`/`cover_thumbnail`，不含完整
  `media` 数组。
- `GET /api/product-detail-packages/finished/:code`（成品匹配）虽然会返回 `media`，但要求传入
  一个真实的成品 code，且只返回"匹配到当前成品"的包，不能用来单独查一个指定的包。

结果是：本次前端提交里，重新打开一个**之前已经上传过图片的包**时，媒体网格是空的（同一次
上传会话里本地维护的 `detailMedia` 状态还在，所以"建包→上传→立刻能看到"是正常的；但关掉
弹窗再打开，或者换一个已有包，就看不到已上传的内容了）。这是一个真实的功能缺口，不是我自己
先解决掉、只是没验证到。

## 需要的后端改动

新增 `GET /api/product-detail-packages/:id`，返回单个包的完整信息（`name`/`tag_ids`/
`tag_condition`/`model_ids`/`media` 数组），复用现有的 `DetailPackageRepository.get()` +
`media_for_packages([id])` 就能拼出来，不需要新查询逻辑，预计是几行代码的量。

```python
def get_one(self, package_id):
    package = DetailPackageRepository.get(package_id)
    if not package:
        return Result.fail('产品详情包不存在')
    media = DetailPackageRepository.media_for_packages([package_id])[package_id]
    return Result.ok(data=package.to_dict(media=media))
```

路由 `product:view` 权限即可（只读）。

## 不需要的改动

- 不需要迁移，不需要改现有其它接口的返回结构。

## 验证要求

- 真实 HTTP：新建包 → 上传两张图 → 用新接口查询该包 id → 确认 `media` 数组含两条记录、字段
  完整（`oss_url`/`file_type`/`original_filename`）。
