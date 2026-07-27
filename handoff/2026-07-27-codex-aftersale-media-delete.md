# 售后媒体删除接口交接

## 已完成

- 新增 `DELETE /api/aftersale/media/<id>`，由 aftersale Blueprint 默认写权限门禁保护，即 `aftersale:edit`。
- 删除顺序：先删除媒体 DB 行并提交；成功后调用 OSS `delete_object`。
- OSS 删除失败不改变客户端成功结果，也不恢复 DB 行；失败 key、订单号与错误信息写入既有 `aftersale_media_cleanup_failure`，可供后续重试清理。
- 不存在的媒体返回标准 400 `{success:false,message:"媒体不存在"}`。
- 已更新 `.claude/modules/api.md`。

## 验证

- 新增自动化测试：模拟 OSS 删除异常，断言媒体行已删除、接口成功、清理失败表有准确留痕。
- `pytest backend/tests -q`：通过（含 2 个既有 skip）。
- `python -m compileall -q backend`、`git diff --check`：通过。

## 部署/联调

- 本批无 schema 变化。部署只需同步 `backend/routes/aftersale/__init__.py` 与 `backend/services/aftersale/__init__.py` 后 reload。
- 用 editor 真实 DELETE 一个测试媒体：验证 200、查看器刷新后条目消失、media-flags 计数减少。
- 用 viewer 请求同一路径应为 403。
- 前端已有 `DELETE /api/aftersale/media/<id>` 调用，后端上线后即可解除当前 404。
