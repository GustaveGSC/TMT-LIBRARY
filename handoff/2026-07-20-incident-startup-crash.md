# 事故记录 · P1-2 部署导致约1分45秒服务中断

日期：2026-07-20

## 时间线

- 16:38 完成生产库备份（`/opt/backups/tmt_db_pre_shipping_task_20260720_163803.sql`）
- 16:39 部署 `20260720_02` 迁移 + `ShippingTask` 模型，`alembic upgrade head` 成功，`alembic check` 确认 `No new upgrade operations detected.`
- 16:39 部署剩余后端代码（`app.py`、`shipping` 路由/服务/仓储），`systemctl reload gunicorn`，`systemctl is-active` 一度返回 `active`
- **16:40:20 worker 实际崩溃**：`journalctl` 显示 `RuntimeError: Working outside of application context`，worker exit code 3，systemd 记录 `Shutting down: Master` / `Failed with result 'exit-code'`，进入 `Restart=on-failure` 自动重启循环（每 5 秒重试一次）
- 16:40:40 左右我复查日志发现服务处于 `activating (auto-restart)` 崩溃循环状态——**这段时间站点不可访问**
- 16:41 定位问题：`app.py` 里 `interrupted_tasks = shipping_repository.interrupt_running_tasks()` 直接写在 `create_app()` 顶层、没有包 `with app.app_context():`（同文件里的 `_validate_database_revision` 有正确包裹），导致这行代码在没有 Flask 应用上下文的情况下访问 `current_app`，直接抛异常
- 16:41 本地修复（补 `app.app_context()`），跑 `python -m py_compile` + `pytest` 确认无回归
- 16:42:05 部署热修复、`systemctl restart gunicorn`（这里不是 reload——因为进程已经在崩溃循环里，reload 对着一个不断重启的 master 意义不大，直接 restart 是当时唯一能停止循环的方式）
- 16:42:08 确认 `active (running)`，`/health` 200，登录接口正常响应，日志无报错

**总中断时长：约 1 分 45 秒**（16:40:20 首次崩溃 → 16:42:05 服务重新稳定运行）。

## 根因

`d736599` 引入的 `interrupt_running_tasks()` 调用漏了 `app.app_context()` 包裹。这是一个纯粹的疏漏——同一个 diff 里紧邻的 `_validate_database_revision` 调用是正确写法，两者对比一看就能看出差异，但我在之前的代码审查阶段没有捕捉到这个问题（审查时重点看了迁移文件、外键、索引、事务原子性设计，没有逐行核对 `app.py` 里两处新增调用的 context 包裹是否一致）。

## 责任归属和后续动作

- **我（Claude）在部署前的代码审查没有发现这个 bug**，这是审查疏漏，不是 Codex 的问题被我没查出来就直接部署——以后涉及 `app.py` 启动流程的改动，需要专门核对每一处新增的"直接在 create_app() 顶层调用仓储/服务方法"是否都包了 app context，不能只看业务逻辑对不对
- 已提交热修复 `32fce51`，本地测试通过，已部署验证
- 建议 Codex 后续在 `test_database_revision_guard.py` 或类似测试里，补一个"实际调用 `create_app()` 并确认不抛异常"的冒烟测试，而不是只测 `_validate_database_revision` 这个函数本身——这次的 bug 正是因为没有端到端跑一遍 `create_app()` 才漏掉的（本地 `pytest` 全绿是因为测试没有真正调用 `create_app()`）

## 当前状态

- 服务正常运行，`20260720_02` 迁移已生效，`shipping_task` 表已创建
- 前端 SSE 断线回查逻辑（Codex 建议的 `GET /api/shipping/import/status/<task_id>`）我这边还没开始改，接下来处理
