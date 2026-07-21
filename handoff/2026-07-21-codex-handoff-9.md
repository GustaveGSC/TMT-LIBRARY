# Codex → Claude Code 第九轮交接

日期：2026-07-21
分支：`codex/backend-p1-error-readiness-sql`

## 完成内容

### P1 原始异常信息泄露

- 新增统一异常处理模块 `backend/error_handling.py`。
- 未预期异常在服务端通过 Flask logger 记录完整 traceback，并附 12 位随机错误编号。
- 客户端统一收到 HTTP 500、通用错误消息和 `data.error_id`，不再收到数据库、文件路径、OSS 等原始异常文本。
- 已覆盖产品导入/图片/资料、发货查询与后台任务、售后导出、研发 Excel/BOM、安装包上传等现存泄露点。
- `UploadValidationError` 属于受控输入校验，继续返回明确的 400/413 信息。

### P1 数据库 readiness

- 保留 `GET /health` 作为不访问数据库的 liveness，语义不变。
- 新增公开 `GET /ready`，执行一次 `SELECT 1`：成功返回 `200 {"status":"ready"}`，失败记录 traceback 并返回 `503 {"status":"not_ready"}`。
- 已同步 `.claude/modules/api.md`。

### P2 售后 SQL 拼接

- `q_distinct` 改为只接受 `AftersaleCase` ORM 列对象，通过 SQLAlchemy 构造 DISTINCT 查询。
- 已移除动态 SQL 标识符的 f-string 拼接，查询次数仍为原来的 4 次，不引入 N+1。

### product:delete 后端清理

- 从 `backend/seed_permissions.py` 删除废弃种子。
- 新增 Alembic 数据迁移 `20260721_01`：先删除所有 `role_permissions` 关联，再删除 `permissions` 中的 `product:delete`。
- 更新数据库迁移文档；新代码唯一 head 为 `20260721_01`。

## 自动化验证

- `python -m pytest backend/tests -q`：通过（73 tests）。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。
- 新增测试覆盖：异常文本隐藏及日志追踪、readiness 最小查询及故障传播、售后查询不再拼接列名、权限种子与迁移清理。

## 部署顺序（重要）

应用启动会校验数据库 revision，必须按以下顺序：

1. 先把本批后端文件（包括 migration）同步到服务器，暂不 reload。
2. 在 `/opt/tmt-library` 执行 `python -m alembic -c alembic.ini upgrade head`。
3. 核对 `alembic current` 为 `20260721_01 (head)`，并可只读确认 `product:delete` 及其角色关联已不存在。
4. 再执行 `systemctl reload gunicorn`，按既定纪律延迟复查 status 和 journal。
5. 验证 `/health` 为 200、`/ready` 为 200；不要为了测试 503 人为断开生产数据库。

本批未部署、未 push。
