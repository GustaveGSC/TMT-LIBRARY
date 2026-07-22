# RD 个人笔记分层拆分交接

日期：2026-07-22

## 本批完成内容

按 RD 结构审计的第 2 批计划，只拆分“个人笔记”这一组 4 个端点：

- `backend/routes/rd/notes.py`：仅保留请求读取、当前用户名和 HTTP 响应映射。
- `backend/services/rd/notes.py`：负责内容清理、空内容校验和所有权业务结果。
- `backend/database/repository/rd/notes.py`：负责查询与事务提交。
- `backend/routes/rd/__init__.py`：删除原有 4 个端点实现，在文件末尾导入 notes 子模块；端点仍挂载于原 `rd_bp`，继续受同一个 `rd:view` / `rd:edit` Blueprint guard 保护。
- repository 将旧式 `EcrNote.query.get()` + Python 用户名判断改为按 `id + username` 一次查询，数据库请求数量没有增加。

没有修改 URL、HTTP 方法、权限、响应结构、错误消息、数据库结构或前端代码，因而无需更新 `api.md` / `database.md`，也没有 Alembic migration。

## 提交

- `710263c refactor(rd): split personal notes layers`

分支：`codex/rd-notes-split`

## 自动化验证

- `python -m pytest backend/tests/test_rd_route_guards.py -q`：3 passed
- `python -m pytest backend/tests -q`：131 passed
- `python -m compileall -q backend`：通过
- `python -m alembic -c alembic.ini heads`：`20260721_04 (head)`
- `git diff --check`：通过

测试额外确认：

- 4 个 notes 路由的 view function 均来自 `routes.rd.notes`，防止旧大文件残留重复实现。
- 空白内容仍返回“笔记内容不能为空”。
- Cookie JWT、CSRF、用户数据隔离和越权失败行为继续走真实 Flask + SQLite 链路。

## Claude 审查与部署提示

建议逐层核对旧代码语义后合并。后端部署按以下顺序，避免 worker reload 时导入不到新模块：

1. 新建服务器目录 `backend/database/repository/rd/`。
2. 先上传 `database/repository/rd/__init__.py`、`notes.py`。
3. 上传 `services/rd/notes.py` 和 `routes/rd/notes.py`。
4. 最后上传改动后的 `routes/rd/__init__.py`，再执行 gunicorn reload。
5. 按既有纪律复核延迟日志、`/health` 和 `/ready`；可用两个账号验证笔记隔离。

这批包含运行时代码变化，需要部署；不涉及数据库迁移。

## 后续建议

确认本批上线稳定后，再单独拆 reminders。当前全量测试唯一的 RD SQLAlchemy 弃用告警正来自 reminders 的 `EcrReminder.query.get()`，下一批可随 repository 分层一并消除，不要与 ECR/PDM 文件逻辑搬移混做一批。
