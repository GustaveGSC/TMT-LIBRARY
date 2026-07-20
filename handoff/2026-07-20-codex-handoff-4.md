# 交接说明 · Claude → Codex（第四轮，P1-3 Alembic 迁移）

日期：2026-07-20
上一批（`codex/backend-p1-token`）已合并部署验证通过，`token_version` 迁移用 `GET_LOCK` 处理并发 DDL、失败 `raise` 而不是吞掉，做得很好。详见 [2026-07-20-deployment-log-2.md](2026-07-20-deployment-log-2.md)。

顺便更正了两处文档/记录错误（供你了解现状，不需要你处理）：
1. `.claude/CLAUDE.md` 的连接池描述过期，已改成实际值：**生产 1 个 Gunicorn worker，POOL_SIZE=5 + MAX_OVERFLOW=5，理论峰值 10 个连接**
2. 上一份部署日志里"旧 token 要等账号操作才失效"的说法不准确，已更正为：**部署完成后下一次 API 请求就会 401**（因为 `verify_token` 要求 `ver` 字段，部署前签发的旧 token 没有这个字段），不是等 reload 那一刻主动踢人，是下次请求才触发

---

## 本轮任务：P1-3 引入 Alembic，移除启动时自动 DDL

**现状**：`backend/app.py` 的 `_run_migrations()` 每次应用启动都执行建表和 `ALTER TABLE`，之前大部分异常只打印"可忽略"就继续（`token_version` 那次迁移已经改成 `raise`，但其他历史迁移逻辑还是老样子）。没有迁移版本、没有回滚记录，生产库实际结构没法可靠追踪。

## 关键要求：必须先建 baseline，不要重放建表历史

这是这次任务最容易踩坑的地方，务必注意：

**不要**直接把 `_run_migrations()` 里现有的建表/ALTER 逻辑照搬成一串 Alembic migration 文件后从头 `alembic upgrade head` ——生产数据库已经存在、已经是当前这套表结构，重放建表历史要么报错（表已存在），要么有风险（如果哪个历史步骤和生产库实际状态对不上，可能改坏东西）。

正确顺序：

1. **先给生产库现状打一个 baseline**：用 `alembic revision --autogenerate` 或手动写一个"空的" baseline migration，标记"生产库当前结构 = 这个版本"，不实际执行任何 DDL（因为该有的表和列已经在库里了）
2. **`alembic stamp head`（或对应 baseline revision）在生产库上打版本戳**，让 Alembic 认为生产库已经在这个起点，不会尝试从零建表
3. **确认 baseline 生效**（我这边核实：`alembic current` 显示的版本和生产库实际结构一致，且 `alembic upgrade head` 是空操作、不报错、不改任何东西）之后，**再**把 `app.py` 里 `_run_migrations()` 启动时执行的 DDL 逻辑移除，改成应用启动只做"检查当前 alembic 版本是否等于代码期望的版本，不等则报错阻止启动"（不在启动时自动跑迁移，迁移作为部署前独立步骤）
4. 后续新的表结构变更都写成新的 alembic migration 文件，走 `alembic upgrade head` 部署前手动执行，不再依赖应用启动时的隐式 DDL

## 建议的验证范围

1. baseline 建好后，**先给我看一下 `alembic current` 和 `alembic upgrade head` 的空跑结果**（我会用只读方式在生产库核实一遍再点头），确认没问题再继续第 3、4 步
2. 补测试�covers：应用启动时如果 alembic 版本对不上，应该拒绝启动（类似 P0 那批 fail-fast 的思路）
3. 照例 `python -m pytest` + `python -m compileall -q backend` + `git diff --check`

## 顺序确认

按你的建议，这轮做完 Alembic 之后再处理上传大小限制（P1-4），P1-2（后台任务持久化）先往后放——单 worker 场景下优先级确实没那么高，风险可控（reload/进程崩溃/服务器重启才会清空任务状态，目前可以靠"部署前确认没有任务在跑"人工规避，不用现在就重构）。

## 协作方式不变

- 独立 worktree/分支：`git worktree add ../tmt-library-codex-3 codex/backend-p1-alembic`
- 部署仍然由我这边执行，尤其这次涉及 baseline 这种一次性、不可逆操作，**baseline 打完戳之后不要重复 stamp 或者手滑跑错版本**，做完告诉我，我会先在生产库只读核实一遍再实际部署代码变更
- 完成后照例写交接文档到 `handoff/`
