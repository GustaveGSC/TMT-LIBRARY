# 售后媒体导入后端：生产验证通过并已上线

日期：2026-07-27

## 结论

Codex 的后端实现（25663ca，`aftersale_media_upload_session` 预留会话 + 零信任 confirm +
replace 时序修正）审查代码后确认与设计基线一致，本地测试全绿，已部署上线并通过完整真实
MySQL/HTTP 验证。

## 代码审查要点

- `presign_media`：在数据库写入 `AftersaleMediaUploadSession` 后才生成签名；用
  `UniqueConstraint('order_no','reserved_start')` 而非应用层锁解决并发同订单争抢序号
  （唯一约束冲突时重试最多 3 次），比原设计建议的 `SELECT ... FOR UPDATE` 更轻量，效果等价。
- `confirm_media`：只接受 `session_token`，`manifest` 全部来自 presign 阶段落库的服务端记录，
  客户端无法传入任意 storage_key/大小；`uploaded_by` 与 session 创建者一致才允许确认。
- `replace` 时序：先在一个事务里删旧行+插新行+标记 session confirmed 并提交，提交成功后才
  逐个尝试删旧 OSS 对象，失败写入 `aftersale_media_cleanup_failure` 不回滚新数据——与设计要求的
  时序完全一致。
- `order_no` 正则 `^[A-Za-z0-9_-]{1,100}$`、文件名拒绝 `/\\\x00`、扩展名白名单，均已落实。
- `media-flags`/`precheck` 均为单条 `GROUP BY`/`IN (...)` 批量查询，不随订单数增长。

## 本地验证

`pytest backend/tests -q` 全绿（2 项既有 MySQL 集成测试按预期 skip）、`compileall` 通过。新增
`test_aftersale_media.py` 直接验证：零信任 manifest（构造恶意 `uploaded` 参数不影响落库结果）、
replace 提交后才清理旧对象、并发序号预留、清理失败留痕、路径穿越拒绝。

## 部署

无残留活跃 `shipping_task`；`mysqldump` 备份（`/tmp/tmt_db_20260727_backup_pre_aftersale_media.sql.gz`，
已核对 "Dump completed" 结尾）；5 个文件（migration/model/repository/service/route）MD5 核对后
`alembic upgrade head`（`20260727_01 -> 20260727_02`，`alembic current` 确认到 head，三张新表
`SHOW CREATE TABLE` 核实存在）；`systemctl reload gunicorn`，master PID 未变，无崩溃重启，
`/health`/`/ready` 正常。

## 真实 HTTP / OSS 验证（测试订单 `CLAUDEVERIFY-20260727-001`，完成后已清理）

| 验证项 | 结果 |
|---|---|
| viewer 调 precheck/media-flags/详情 | 均 200 |
| viewer 调 presign/confirm | 均 403（editor 反向验证均 200/成功） |
| 新订单 append 3 个文件 | presign 分配 seq `[1,2,3]`，真实 OSS PUT 200，confirm 200，详情查询三条记录序号正确 |
| 再次 append 1 个文件 | 新 seq 为 `4`（接续既有最大值），confirm 成功 |
| replace 1 个文件 | 新 seq 从 `1` 重新开始，confirm 后旧 4 个 OSS 对象访问全部 **404**（真实删除，不是只删 DB 行） |
| 模拟 OSS 删除失败（monkeypatch `delete_object` 抛异常） | confirm 仍返回成功，`aftersale_media_cleanup_failure` 写入 1 条留痕记录 |
| 重复调用已确认的 `session_token` | 返回 `idempotent: true`，未重复插入 |

全部测试数据（DB 行 + OSS 对象）已在验证结束后清理干净，生产库无残留。

## 当前状态

后端五个接口（precheck/presign/confirm/media-flags/详情）已上线，可供前端接入。前端衔接要点
（沿用 Codex 交接文档）：presign 拿到 `session_token` 后，所有文件 OSS PUT 全部成功才调用
`confirm({session_token})`；不要回传或自拼 storage_key。

## 后续

前端交互（文件夹选择、冲突确认弹窗、批量上传执行、表格展开行媒体展示）尚未实现，按原设计文档
建议顺序推进，不阻塞后端已上线的部分。
