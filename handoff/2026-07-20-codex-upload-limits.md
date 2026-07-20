# Codex · P1-4 上传与导入限制

日期：2026-07-20  
分支：`codex/backend-p1-upload-limits`

## 已完成

- Flask `MAX_CONTENT_LENGTH` 默认 500MB，可通过同名环境变量（字节）覆盖；超限统一返回标准 JSON 和 HTTP 413。
- 发货/财务、产品原始数据、ECR/BOM/PDM、BOM 成本文件统一执行读取前限制：单文件 20MB。
- Excel 联合检查扩展名、MIME、真实 OLE/ZIP 文件头和 OOXML 工作簿结构。
- xlsx 限制解压后 100MB、内部文件 2000 个、工作表 50 个；解析阶段限制 100000 行。
- CSV 检查文本编码及二进制 NUL，限制 20MB/100000 行。
- 产品封面和原始封面分别限制为 Base64 解码后 10MB，只允许 PNG/JPEG/WebP；声明 MIME 与真实解码格式不一致时拒绝。
- 产品资料和版本安装包预签名接口新增必填 `file_size`，签名绑定 `Content-Length`，响应返回 `required_headers`。
- 没有数据库结构变化，不需要新增 Alembic revision。

## 限制选择

- 全局 500MB 对齐现有 nginx `/api/version/upload` 上限；普通 `/api/` 仍由 nginx 20MB 和业务层 20MB 双重限制。
- 产品资料走浏览器直传 OSS，不经过 nginx，因此单独限制 500MB，并用签名绑定声明大小。
- `application/octet-stream` 作为浏览器无法识别 Office/CSV MIME 时的兼容值，但文件扩展名和真实内容检查仍必须通过。

## 自动化验证

```text
python -m pytest backend/tests -q
60 passed
python -m compileall -q backend
通过
git diff --check
通过
```

覆盖：全局 413、正常 xlsx、伪造 xlsx、MIME/扩展名不一致、zip bomb 形态、图片 MIME 伪造、预签名缺少/超限大小、签名 Content-Length。

本轮在 `create_app()` 新增的只有配置赋值和 413 error handler，没有新增需要 app context 的数据库/扩展调用。测试会真实执行 `create_app()`，并断言 `interrupt_running_tasks()` 调用期间存在 app context，防止上次事故回归。

## Claude 前端配合

以下两个接口契约有变化，部署后端前必须先改前端或同批发布：

1. `POST /api/resources/presign` 请求增加 `file_size: file.size`；OSS PUT 使用响应 `required_headers`，尤其是精确的 `Content-Length`。
2. `POST /api/version/presign` 同样增加 `file_size` 并使用 `required_headers`。

此外，前端可在发请求前按同一限制给出即时提示：Excel/CSV 20MB、单张封面 10MB、资料/安装包 500MB。服务端校验仍为最终门禁。

## 部署核验

- 本批没有迁移；确认生产 Alembic 仍为 `20260720_02 (head)`。
- 前端预签名适配完成后再部署后端，使用 reload，不 restart。
- 验证 `/health`、正常小文件、超限文件 413、伪造扩展名 400、资料直传成功。

未部署、未 push。
