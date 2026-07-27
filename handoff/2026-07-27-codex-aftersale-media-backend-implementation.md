# 售后媒体导入：后端实施交接

## 提交范围

- 新增 Alembic `20260727_02`：
  - `aftersale_case_media`：订单号逻辑关联、`storage_key` 全局唯一、`(order_no, seq)` 唯一；不建立到售后工单的外键。
  - `aftersale_media_upload_session`：不可预测 `session_token`、过期时间、服务端 manifest 和未确认序号预留。
  - `aftersale_media_cleanup_failure`：replace 后 OSS 旧对象补偿删除失败的留痕。
- 新增接口：
  - `POST /api/aftersale/media/precheck`（`aftersale:view`）
  - `POST /api/aftersale/media/presign`（`aftersale:edit`）
  - `POST /api/aftersale/media/confirm`（`aftersale:edit`）
  - `POST /api/aftersale/cases/media-flags`（`aftersale:view`）
  - `GET /api/aftersale/cases/<order_no>/media`（`aftersale:view`）
- `.claude/modules/api.md` 已更新。

## 一致性与安全边界

- `presign` 在数据库写入 session 后才返回签名；未过期未确认的 session 与已有媒体共同计算序号。`reserved_start` 的唯一约束防止同订单并发重复发号，确认后置空以保留幂等重试能力。
- `confirm` 只接收 `session_token`；上传 key、文件名、大小、seq 均以 session 的服务端 manifest 为准，客户端额外字段不会参与落库。
- `replace` 先在一个数据库事务内删除旧行、插入新行、确认 session；事务成功后才尝试删除旧 OSS 对象。OSS 删除失败不会回滚新媒体，改写入 `aftersale_media_cleanup_failure`。
- `order_no` 严格限制为字母、数字、下划线、连字符；扩展名为白名单图片/视频类型；原文件名禁止路径分隔符和控制字符。
- OSS 直传的已确认边界：后端校验扩展名及声明大小并将 Content-Type/Length 签入 PUT URL，但不读取真实文件头；如需内容嗅探，必须另立 OSS 回调/扫描方案。

## 验证

- 新增 `test_aftersale_media.py`：服务端 manifest 零信任、replace 后清理、序号预留、清理失败留痕、路径输入拒绝。
- `pytest backend/tests -q`：通过（含 2 个既有 skip）。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。

## Claude 部署与真实 MySQL 验收

1. 先备份数据库；上传 migration、model、repository、service、route 后执行 `alembic upgrade head`，确认版本到 `20260727_02`，再 reload。
2. 真实 HTTP 验证 viewer：precheck/media-flags/详情为 200，presign/confirm 为 403；editor 反向验证。
3. 用一个不存在售后工单的测试订单完成 precheck → presign → OSS PUT → confirm；验证媒体记录可读。
4. 对同一订单做 append，确认 seq 连续；再做 replace，确认新记录从 001 开始且旧 OSS key 实际删除。
5. 人为模拟一次 OSS 删除失败，确认 confirm 保持成功且 `aftersale_media_cleanup_failure` 有留痕。
6. `media-flags` 对一页多订单仅执行一次 GROUP BY 查询；展开详情仅在用户主动打开时请求。

## 前端衔接

前端上传每个订单应保存 `presign` 返回的 `session_token`，所有 OSS PUT 成功后只提交 `{session_token}` 到 confirm；不要回传或自行拼接 storage key。media-flags 已按设计确定为 POST body。
