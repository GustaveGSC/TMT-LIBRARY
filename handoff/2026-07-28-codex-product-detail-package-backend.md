# 产品详情包：后端实施交接

分支：`codex/product-detail-packages`  
状态：后端实现完成，尚未合并、部署。

## 实现内容

- 新增独立数据模型，不复用 `product_resource`：
  - `product_detail_package`
  - `product_detail_package_media`
  - `product_detail_package_tag`
  - `product_detail_package_model`
  - `product_detail_package_cleanup_failure`
- 新增 Alembic 迁移 `20260728_02`，基于 `20260728_01`；迁移链保持单 head。
- 新增 `/api/product-detail-packages` Blueprint，所有读取要求 `product:view`，写入要求 `product:edit`。
- 包支持名称、型号范围、标签条件范围；成品读取以“型号命中 OR 复用既有 AND/OR/NOT 标签条件命中”返回匹配包和媒体。
- 媒体上传采用 OSS 预签名 `presign → 直传 → confirm`。key 固定在当前包前缀下、禁止子路径、全局唯一；只接受图片/视频扩展名，默认单文件 500MB。
- 删除采用 DB 先提交、再删除 OSS；OSS 删除失败不回滚已经成功的 DB 删除，而是写入 cleanup failure 留痕。

## 前端契约重点

- 列表：`GET /api/product-detail-packages?search&page&size`，包条目含 `tag_ids`、`tag_condition`、`model_ids`、`media_count`、`cover_thumbnail`。
- 包内媒体：先 `POST /:id/media/presign` 获取每项 `presign_url`、`storage_key`、`required_headers`，PUT OSS 成功后调用 `POST /:id/media/confirm`。
- 产品详情展示：`GET /api/product-detail-packages/finished/:code`，响应是匹配包数组，每包包含 `media` 数组。
- 所有路径、字段和错误边界已写入 `.claude/modules/api.md`；表结构已写入 `database.md`。

## 验证

- `python -m pytest backend/tests -q`：通过（含新增产品详情包预签名/confirm、key 越权拒绝、OSS 清理失败留痕测试）。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。
- Alembic baseline 测试覆盖新 migration head 和建表集合。

## 部署与验收建议（Claude 执行）

1. 按既有纪律先备份生产数据库。
2. 上传新后端文件与 migration，执行 `alembic upgrade head`，核对当前 revision 为 `20260728_02`。
3. reload 后验证 `/health`、`/ready`，再用 editor 身份完成：建包 → 设置范围 → 预签名/确认一张图片 → 成品匹配读取 → 删除媒体。
4. 用 viewer 身份确认写接口为 403；确认 `GET` 可读取。
5. 前端尚未实施。请在前端做独立的包管理页及成品详情匹配展示，不要再把该功能并回资料类型或 `product_resource`。
