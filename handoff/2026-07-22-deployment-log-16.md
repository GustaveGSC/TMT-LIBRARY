# 部署记录 · RD 个人笔记拆分（周期二 P3 分批拆分·第一组）

日期：2026-07-22

## 背景

在 `handoff/2026-07-22-codex-rd-behavior-guards-handoff.md` 建立的路由/权限护栏保护下，Codex 开始按 `2026-07-22-codex-rd-structure-audit.md` 的职责地图分批拆分 `routes/rd/__init__.py`。第一组选择风险最低的"个人笔记"（4个端点）。交接文档：`handoff/2026-07-22-codex-rd-notes-split-handoff.md`。

## 审查结论

`codex/rd-notes-split`（`710263c` + `2e2e582`）审查通过，`git merge --ff-only` 合入 master：

- 新增 `database/repository/rd/notes.py`（`RdNoteRepository`：`list_for_user`/`get_for_user`/`create`/`update`/`delete`）、`services/rd/notes.py`（`RdNoteService`：内容校验 + 编排）、`routes/rd/notes.py`（4个端点，只做参数解析和 `Result` 包装）。
- `routes/rd/__init__.py` 删除原有4个端点实现（-70行），文件末尾 `from . import notes as _notes_routes` 在 `rd_bp` 定义之后延迟导入子模块，避免循环导入，路由仍挂在同一个 Blueprint 上。
- 所有权检查从"先 `Query.get(nid)` 取出再比较 `username`"改为 `filter_by(id=note_id, username=username).first()` 直接在数据库层过滤，语义等价，顺带消除了 notes 相关的 `Query.get()` 弃用告警（reminders 部分的告警还在，是下一批的范围）。
- URL、HTTP 方法、权限、成功/失败响应结构、错误消息文案（如"笔记不存在或无权限"、"笔记内容不能为空"）逐条核对与原代码一致。
- `test_rd_route_guards.py` 新增结构断言：`/api/rd/notes` 的4条路由的 `view_functions.__module__` 确实等于 `'routes.rd.notes'`，防止以后"看起来拆了但路由其实还挂在旧模块"这种表面拆分。
- 本地复跑：`pytest` 131 passed（notes 相关的 `Query.get()` 告警消失，reminders 告警仍在，符合预期），`compileall`/`git diff --check` 通过。

## 部署

按 Codex 要求的顺序（先新增模块，最后更新引用它们的 `routes/rd/__init__.py`）：

1. 确认服务器无导入/resolve 任务在跑。
2. 服务器建 `database/repository/rd/`、`services/rd/` 目录（如不存在）。
3. 依次 scp 上传 `database/repository/rd/__init__.py`、`database/repository/rd/notes.py`、`services/rd/notes.py`、`routes/rd/notes.py`，md5 逐一核对一致。
4. 最后 scp 上传 `routes/rd/__init__.py`，md5 核对一致。
5. `systemctl reload gunicorn`；8秒后复查：master pid 2258 未变，新 worker（15306）干净启动，无崩溃记录。
6. `/health`、`/ready` 均 200。
7. 实测 `GET /api/rd/notes`（未登录）返回 401 而非 500，证明新的 `routes.rd.notes` 模块被正确导入并挂载，未触发 import 错误。

## 影响说明

- 无接口契约变更、无数据库结构变更、无前端改动。
- 之后如果要 grep RD 个人笔记相关代码，实现已从 `routes/rd/__init__.py` 移到 `routes/rd/notes.py` + `services/rd/notes.py` + `database/repository/rd/notes.py` 三层。

## 下一批

按 Codex 建议，稳定后单独拆 reminders（提醒事项管理，`rd:admin` 权限边界那部分），拆分方式和验证方式与本批一致。
