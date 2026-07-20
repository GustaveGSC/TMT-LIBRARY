# Codex · P1-2 发货后台任务持久化与导入原子性

日期：2026-07-20  
分支：`codex/backend-p1-task-persistence`

## 已完成

- 新增 Alembic revision `20260720_02`，创建 `shipping_task` 持久化任务表；没有向 `app.py` 添加隐式 DDL。
- 持久化 `import_shipping`、`import_finance`、`resolve_all`、`resolve_stale` 的 pending/running/终态、最新进度、结果和错误信息，终态保留 7 天。
- 新增 `GET /api/shipping/import/status/<task_id>`，需要 shipping 权限，终态读取后不删除。
- 原 SSE 进度接口保留；内存 Queue 因 reload 丢失时，会改从数据库读取进度/终态。
- 兼容原 `GET /api/shipping/task-status/<task_id>`，但底层状态已由内存字典改为数据库。
- 新 worker 启动时将上一进程遗留的 pending/running 任务标记为 `interrupted`；状态信息明确提示导入事务已回滚。
- 发货/财务导入不再每 100 行 commit，批次、原始发货/销退记录及本批派生成品结果改为单一业务事务。异常、取消或进程退出均整体 rollback。
- 任务状态使用独立数据库连接提交，不会提前提交导入业务 session。

## 事务与性能判断

- 这是从“短分块事务”改为“整批原子事务”的明确取舍：会延长单次导入事务时间，但消除了 reload/SIGTERM 后半批数据不确定性。
- 进度更新每个导入 chunk 增加一次针对 `shipping_task` 的单行 UPDATE，走主键，不进入业务查询链路。
- 生产当前单 worker；启动时标记旧任务的策略依赖这一现状。未来扩到多 worker 前需增加 worker owner/lease，不能直接沿用当前启动回收策略。
- 上传文件内容不入库，避免大文件占用 MySQL；进程中断后任务可确认失败，但不能自动续跑，需要用户重新上传。

## 自动化验证

```text
python -m pytest backend/tests -q
50 passed
python -m compileall -q backend
通过
git diff --check
通过
python -m alembic -c alembic.ini heads
20260720_02 (head)
python -m alembic -c alembic.ini history
20260720_01 -> 20260720_02 (head)
```

离线生成 MySQL upgrade SQL 已核对：仅创建 `shipping_task`、复合索引并更新 `alembic_version`。

## Claude 部署顺序

本分支包含尚未部署的 Alembic 第二阶段启动 revision 门禁，因此必须整体按以下顺序部署：

1. 备份数据库，并确认没有导入/resolve 任务正在运行。
2. 先部署 `backend/migrations/`、`alembic.ini`（若线上已存在则核对）和包含 `ShippingTask` 的模型文件，不 reload。
3. 执行 `python -m alembic -c alembic.ini upgrade head`。
4. 确认 `alembic current` 为 `20260720_02 (head)`，执行 `alembic check`。
5. 再部署其余 backend 代码，使用 `systemctl reload gunicorn`。
6. 验证 `/health`、登录、两类导入任务创建和 `GET /api/shipping/import/status/<task_id>`。
7. 查看 journal，确认没有 revision mismatch，也没有旧 `[migration]` 隐式 DDL 日志。

## 前端需要配合

- SSE `onerror` 不应直接把任务判为失败；调用 `GET /api/shipping/import/status/<task_id>` 回查。
- 若返回 pending/running，可短暂轮询；done 使用 `result`，error/cancelled/interrupted 展示 `message`。
- 这部分后端已就绪，Claude 可以更新前端消费逻辑。

未部署、未 push。
