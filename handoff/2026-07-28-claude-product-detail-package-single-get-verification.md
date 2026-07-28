# 产品详情文件夹单项读取接口：生产验证通过并已上线

日期：2026-07-28

## 结论

Codex 的实现（0bbb78e）审查通过，精确匹配请求（`GET /:id`，`product:view` 权限，复用现成
repository 方法拼装，无冗余）。本地测试全绿（含新增的 sort_order 排序断言 + 不存在 id 断言），
已合并部署，真实 HTTP 验证通过。此前用户报告的 405 报错已解决。

## 部署

无迁移，同步 `routes/product/detail_package.py` + `services/product/detail_package.py` 两个
文件，MD5 核对一致，`systemctl reload gunicorn`，master PID 未变，无崩溃重启，`/health` 正常。

## 真实 HTTP 验证（测试数据，完成后已清理）

| 验证项 | 结果 |
|---|---|
| 建文件夹 → 上传一张图 → viewer 身份 `GET /:id` | 200，`media` 数组含完整字段（`oss_url`/`file_type`/`original_filename`/`storage_key`/`sort_order`） |
| 请求不存在的 id | 400，`{"success":false,"message":"产品详情包不存在"}`，不是 500 |
| 清理删除测试文件夹 | 200 |

## 当前状态

产品详情文件夹功能此前唯一的阻塞项（双击进入报 405）已解决，前端 `openFolder()` 现在可以
正常加载已有文件夹的媒体列表。建议用户实际在浏览器里走一遍"新建文件夹→上传图片→退出→重新
双击进入→图片还在"这条链路做最终确认。
