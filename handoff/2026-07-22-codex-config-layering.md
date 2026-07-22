# 交接说明 · Codex → Claude（周期二 P3：站点配置分层）

日期：2026-07-22

## 审查结论

`routes/config` 只有 2 个登录轮播语句接口，不存在路由文件过大问题，也不值得继续按功能拆 Blueprint。实际结构问题是路由层同时承担 JSON 解析、默认值、ORM 查询和事务提交，且此前没有任何自动化测试。

本批只做三层职责对齐，HTTP 路径、权限、请求和响应保持不变。

## 完成内容

- 提交：`47c3655 refactor(config): separate route service repository`
- 分支/worktree：`codex/config-layering` / `E:/Project/tmt-library/.worktrees/codex-config-layer`
- `backend/routes/config/__init__.py`：只保留 HTTP 参数、author/admin 权限和 Result 响应。
- 新增 `backend/services/config.py`：负责 login_mottos 默认值、JSON 解码、输入清理和业务校验。
- 新增 `backend/database/repository/config.py`：负责 SiteConfig key-value 查询、写入和 commit；使用 SQLAlchemy 2 的 `db.session.get()`。
- 新增 `backend/tests/test_site_config.py`：覆盖配置缺失/损坏回退、保存规范化、公开 GET、普通用户 403、admin PUT 成功。
- 修正 SiteConfig 模型注释及 database.md：该表属于生产 baseline，禁止再描述成“自动建表”。
- 补齐 api.md 中两个此前遗漏的 config 接口契约。

## 不变项

- `GET /api/config/login-mottos` 仍公开访问，配置无效时返回内置默认语句。
- `PUT /api/config/login-mottos` 仍只允许 author/admin，请求仍为 `{mottos: string[]}`，成功响应仍返回清理后的字符串数组。
- Blueprint、URL prefix、数据库表结构和既有数据均未改变。

## 验证

- `python -m pytest backend/tests -q`：115 passed。
- `python -m compileall -q backend`：通过。
- `python -m alembic -c alembic.ini heads`：`20260721_04 (head)`。
- `git diff --check`：通过。

## 部署顺序

无迁移、无前端构建，但运行时代码有新模块，需要 reload：

1. 先上传 `backend/database/repository/config.py` 和 `backend/services/config.py`。
2. 再上传 `backend/routes/config/__init__.py`（模型注释和文档无需影响生产运行）。
3. `systemctl reload gunicorn`，延迟复查 status/journal，并验证 `/health`、`/ready`。
4. 实测公开 GET 返回语句数组；用 author/admin 保存后再次 GET，确认数据一致。

必须先传新模块再传引用方，避免部署窗口里 worker reload 后 import 失败。

## 下一批建议

`routes/config` 到此已收口，不要继续拆。下一项可以只读梳理 `routes/rd/__init__.py` 与 `routes/rd/cost.py` 的职责和命名不对称，但建议先输出模块地图与拆分边界，不要直接对 1700 行路由做整文件搬移。

本批未部署、未 push，未修改 `src/` 或 Electron。
