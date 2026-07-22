# RD 路由行为护栏交接

## 本批范围

本批只增加自动化测试，不修改运行时代码、数据库结构或 HTTP 接口契约。

- 为 `routes/rd` 固化 17 个路由的方法与路径快照。
- 为 `routes/rd/cost` 固化 26 个路由的方法与路径快照。
- 通过真实 Flask 请求链路验证提醒事项的权限边界：普通 `rd:view`/`rd:edit` 用户只能读取公开列表，具有 `rd:admin` 的用户才能管理提醒事项。
- 通过真实 Flask 请求链路和 SQLite 数据库验证个人笔记按登录用户名隔离，其他用户不能读取、修改或删除。
- 测试包含 Cookie JWT、CSRF 和 `UserRepository.get_auth_state` 认证状态校验，不是仅对函数做 mock 调用。

## 提交

- `88e3799 test(rd): lock route and permission behavior`

分支：`codex/rd-behavior-guards`

## 验证结果

- `python -m pytest backend/tests/test_rd_route_guards.py -q`：3 passed
- `python -m pytest backend/tests -q`：131 passed
- `python -m compileall -q backend`：通过
- `python -m alembic -c alembic.ini heads`：`20260721_04 (head)`
- `git diff --check`：通过

## 审查提示

- 当前非管理员访问提醒管理接口、越权修改/删除他人笔记时返回 HTTP 400。测试将其作为现有行为基线记录，并不表示 400 是理想的权限状态码；若以后统一改为 403，应作为独立接口契约调整同步前端和 `api.md`，再更新测试。
- 测试运行时暴露出 RD 路由中 3 处旧式 `Query.get()` 的 SQLAlchemy 2.0 弃用告警。本批为避免混入运行时代码变化没有处理，拆分路由时可改为 `db.session.get()`。
- 这是纯测试提交，无需部署或 reload；合并后运行全量测试即可。

## 建议下一步

在这些路由和权限护栏保护下，再按 `2026-07-22-codex-rd-structure-audit.md` 的职责地图拆分 RD 路由。建议一次只移动一个职责组，并保持当前 URL、方法、权限与响应结构不变。
