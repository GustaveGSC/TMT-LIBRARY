# 交接说明 · Claude → Codex（第五轮，P1-2 后台任务 reload 可靠性）

日期：2026-07-20
上一批 Alembic baseline 三轮核验后已经 stamp 成功、`DIFF_COUNT=0`、部署验证通过，详见 [2026-07-20-deployment-log-3.md](2026-07-20-deployment-log-3.md)。

## 触发原因：P1-2 从"理论风险"变成了真实故障

部署 Alembic baseline 那次 `systemctl reload gunicorn` 执行的时候，用户正好在页面上点了"刷新全局发货数据"（`POST /api/shipping/resolve-all`），前端 SSE 长连接（`GET /api/shipping/import/progress/<task_id>`）当场报错：

```
/api/shipping/import/progress/7bb0ca42-ec53-439b-996f-104b673d46b9:1
Failed to load resource: net::ERR_INCOMPLETE_CHUNKED_ENCODING
```

原因很直接：`resolve-all`/`import/shipping`/`import/finance` 这几个接口都是"后台线程 + 模块级 `_task_queues` 字典存 SSE 队列"的模式，状态全在内存里，绑在当前这一个 gunicorn worker 进程上（`priority-correction.md` P1-2 描述的场景）。`reload` 会把 worker 整个换掉，正在跑的后台线程和它对应的 SSE 队列直接消失，前端连接被服务端悍然断开。

**这不是个例**——只要以后任何一次部署（无论前端后端）需要 `reload gunicorn`，只要那个时间点有人在跑导入/刷新/导出，就会复现同样的报错。之前 P1-2 排在"后置"是因为判断单 worker 场景下没有跨 worker 丢状态的问题，风险可控；这次事件说明 reload 本身（不需要多 worker）就足以触发，优先级应该提上来。

好消息是这次任务本身无害：`resolve_all` 是全量幂等重算（不看之前状态，把每个订单重新算一遍），用户直接重新点一次就补完了，没有留下脏数据。但这只是运气好——`import_shipping`/`import_finance` 这类真正写入新数据的导入任务如果被打断，用户不会有任何"重新点一次"的信号（进度条直接消失/报错，不知道数据到底导入了一半还是没导），这个风险更大。

## 本轮任务：P1-2 后台任务持久化

来自 `priority-correction.md` 的建议方向（"短期"部分）：

1. **task 状态/结果落数据库或临时文件**，不要只放模块级字典/Queue——至少要能在 reload 后判断"这个 task_id 之前到底跑没跑完、跑到哪一步、有没有异常"，不能像现在这样直接从内存消失
2. **导入类任务（`import_shipping`/`import_finance`）优先处理**，因为涉及真实数据写入，被打断的后果比 `resolve_all`/`resolve_stale` 这类幂等重算任务更严重——建议要么做成"可恢复/可查询最终状态"，要么至少保证"被打断时不会留下部分写入的脏数据"（比如用事务包住整个导入，失败或中断就整体回滚，不要写一半）
3. **前端体验**：SSE 连接异常断开时，现在前端会怎么处理？（这个我这边可以配合看，如果需要区分"任务真的失败了"和"只是连接断了，任务其实还在后台跑/已经跑完"，前端需要能重新查询任务最终状态，而不是只能死等 SSE 或者直接报错走人）

## 建议的验证范围

1. 实现方案本身（数据库表或文件持久化 task 状态，具体选型你决定）
2. 补自动化测试：模拟"任务开始 → 进程重启/worker替换 → 能否查到任务实际结果"这个场景
3. 如果需要新增或修改接口（比如加一个"查询任务最终状态"的接口，不依赖 SSE），更新 `api.md`，并且告诉我前端需要配合的部分——现在的 SSE 消费逻辑在前端哪些组件里（发货数据管理页的导入/刷新功能），如果接口约定变了我这边要跟着改
4. 照例 `python -m pytest` + `python -m compileall -q backend` + `git diff --check`

## 协作方式不变

- 独立 worktree/分支：`git worktree add ../tmt-library-codex-4 codex/backend-p1-task-persistence`
- 部署仍然由我这边执行，完成后照例写交接文档到 `handoff/`
- **这次改动如果涉及数据库表结构变化，记得配套写 Alembic migration**（不要再用 `app.py` 里那种隐式 DDL 的老方式了——虽然第二阶段"移除 `_run_migrations()`"还没做，但既然 baseline 已经建好了，新的表结构变化建议直接从这次开始就走 alembic migration，不要再往那个隐式 DDL 里加新东西）
