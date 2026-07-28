# 产品详情包单项读取接口交接

分支：`codex/product-detail-package-get`  
状态：已实现，尚未合并或部署。

## 改动

- 新增 `GET /api/product-detail-packages/:id`，沿用 Blueprint 的 `product:view` 读取权限。
- 返回指定包的完整信息：包名称、`tag_ids`、`tag_condition`、`model_ids` 以及排序后的完整 `media` 数组。
- 不新增迁移、不修改已有列表或成品匹配接口。
- API 契约已补到 `.claude/modules/api.md`。

## 验证

- 新增服务测试：已有包读取会返回两条完整媒体且遵守 `sort_order`；不存在的 id 返回失败。
- 将运行 `pytest backend/tests`、`compileall`、`git diff --check` 后提交。

## 给 Claude 的验收

合并部署后，以 `product:view` 用户请求已有包 id，确认 `data.media` 返回 `oss_url`、`file_type`、`original_filename` 等字段；再请求不存在 id，确认返回现有失败响应。
