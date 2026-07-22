# RD 变更提醒分层拆分交接

日期：2026-07-22

## 本批完成内容

按 RD 结构审计计划，只拆分“变更提醒”职责组：

- `backend/routes/rd/reminders.py`：承载公开列表、管理员全量列表、创建、编辑、下架和重新上架端点。
- `backend/services/rd/reminders.py`：承载内容必填、可选文本清理和提醒状态业务规则。
- `backend/database/repository/rd/reminders.py`：承载列表、主键读取、写入与事务提交。
- `backend/routes/rd/__init__.py`：删除旧实现，在文件末尾导入 reminders 子模块；所有端点仍挂在原 `rd_bp`，继续受父 Blueprint 的 `rd:view` / `rd:edit` guard 保护。

管理接口仍先执行 `@require_auth`，再执行 `is_rd_admin()`；权限失败仍返回“权限不足：需要研发部管理员权限”。公开列表行为不变。旧式 `EcrReminder.query.get()` 已改成 `db.session.get()`。

没有修改 URL、HTTP 方法、权限、响应结构、错误文案或数据库结构，因此无需更新 `api.md` / `database.md`，没有 Alembic migration。

## 提交

- `94fcef2 refactor(rd): split reminder management layers`

分支：`codex/rd-reminders-split`

## 自动化验证

- `python -m pytest backend/tests/test_rd_route_guards.py -q`：3 passed
- `python -m pytest backend/tests -q`：131 passed，无 warnings
- `python -m compileall -q backend`：通过
- `python -m alembic -c alembic.ini heads`：`20260721_04 (head)`
- `git diff --check`：通过

行为护栏现在额外覆盖：

- reminders 的全部路由实现均来自 `routes.rd.reminders`。
- 普通 RD 用户可读公开列表，但全量读取和创建均被 `rd:admin` 拒绝。
- 管理员完整执行创建、编辑、下架和重新上架，并核验公开列表随状态变化。

## Claude 审查与部署提示

建议逐条对照旧实现，重点核对装饰器顺序和失败文案。部署顺序：

1. 先上传新增的 `database/repository/rd/reminders.py`。
2. 再上传 `services/rd/reminders.py`、`routes/rd/reminders.py`。
3. 最后上传修改后的 `routes/rd/__init__.py`，再 reload gunicorn。
4. 按既有纪律复核延迟日志、master PID、`/health`、`/ready`。
5. 用普通 RD 用户验证公开列表，用 `rd:admin` 用户验证管理列表；避免为验证创建无法清理的生产数据，如需写验证应使用已有提醒做可逆上下架并恢复原状态。

这批有运行时代码变化，需要部署；不涉及数据库迁移。

## 后续建议

notes/reminders 两个数据库 CRUD 域已完成拆分。下一阶段进入审计第 3 批“抽纯文件服务”前，应先补齐审计中尚未完成的纯函数 fixture 护栏：`_compare_bom`、ECR/ECN round-trip、`_ptb_build_erp_data`、`_ptb_build_bom_data`。不要在缺少这些测试时直接搬移大段 Excel 逻辑。
