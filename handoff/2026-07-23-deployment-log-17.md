# 部署记录 · RD 变更提醒拆分（周期二 P3 分批拆分·第二组）

日期：2026-07-23

## 背景

延续 RD 路由分批拆分（第一组"个人笔记"已完成，见 `2026-07-22-deployment-log-16.md`），第二组拆分"变更提醒管理"（5个端点，`rd:admin` 权限边界）。交接文档：`handoff/2026-07-22-codex-rd-reminders-split-handoff.md`。

## 审查结论

`codex/rd-reminders-split`（`94fcef2` + `6ba99f9`）审查通过，`git merge --ff-only` 合入 master：

- 新增 `database/repository/rd/reminders.py`（`RdReminderRepository`）、`services/rd/reminders.py`（`RdReminderService`：内容校验 + 编排）、`routes/rd/reminders.py`（5个端点）。
- 权限校验顺序逐条核对与原代码一致：`@require_auth` 装饰器验证 JWT 在先，`is_rd_admin()` 检查在函数体内在后，`list_reminders`（GET /reminders，全体 rd 用户可读）本身不加 `@require_auth`，与原实现一致，未被拆分过程改变权限边界。
- `EcrReminder.query.get(rid)` 全部替换为 `db.session.get(EcrReminder, reminder_id)`，消除了这部分的 SQLAlchemy 弃用告警（至此 notes+reminders 两批告警全部清除，全量测试 0 warning）。
- 错误文案逐条比对一致："权限不足：需要研发部管理员权限"、"提醒不存在"、"提醒内容不能为空"。
- `test_rd_route_guards.py` 新增结构断言（reminders 端点确实来自 `routes.rd.reminders`）+ 更完整的行为测试（管理员创建/编辑/下架/重新上架全流程 + 普通用户越权创建被拒）。
- 本地复跑：`pytest` 131 passed，0 warning；`compileall`/`git diff --check` 通过。

## 部署

按顺序（先新增模块，最后更新 `routes/rd/__init__.py`）：

1. 确认服务器无导入/resolve 任务在跑。
2. scp 上传 `database/repository/rd/reminders.py`、`services/rd/reminders.py`、`routes/rd/reminders.py`，md5 逐一核对一致。
3. scp 上传 `routes/rd/__init__.py`，md5 核对一致。
4. `systemctl reload gunicorn`；8秒后复查：master pid 2151（当日已重启过一次，与本次部署无关）未变，新 worker（7238）干净启动。
5. `/health`、`/ready` 均 200。
6. 实测 `GET /api/rd/reminders`、`GET /api/rd/reminders/all`（均未登录）均返回 401（认证网关拦截），非 500，证明 `routes.rd.reminders` 模块正确导入挂载。

## 顺带发现（未处理，仅记录）

reload 前的日志中看到一条与本次改动无关的历史报错：`09:08:21` `database/repository/aftersale/__init__.py:3451 match_shipping_alias` 抛出 `IndexError: list index out of range`（`top_candidates[0][0]`，候选列表为空时越界）。发生在本次部署之前，与 RD 拆分无关，未去动它，仅记录供后续关注（如果售后自动匹配功能出现异常，这是一个已知线索）。

## 影响说明

- 无接口契约变更、无数据库结构变更、无前端改动。
- RD 提醒相关代码位置：`routes/rd/reminders.py` + `services/rd/reminders.py` + `database/repository/rd/reminders.py`。

## 下一批

Codex 建议先补 `_compare_bom`、ECR/ECN round-trip、PDM 两个构建函数（`_ptb_build_erp_data`/`_ptb_build_bom_data`）的 fixture 护栏测试，再动 Excel 纯逻辑部分的拆分。
