# 发货任务取消 A1 交接

日期：2026-07-24  
分支：`codex/shipping-cancel-a1`  
部署：尚未部署，由 Claude Code 审查和执行

## 本批范围

本批只完成已批准的 A1：

- `shipping_task` 持久化取消字段；
- repository 取消/提交 CAS；
- 统一取消接口；
- 旧取消接口兼容转发；
- 权限、竞态、幂等和迁移测试。

没有把取消检查铺进解析或 `_resolve_orders()`，没有实现重算 staging，也没有修改前端。

## 代码改动

### 数据库

Alembic `20260724_03` 给 `shipping_task` 增加两个可空字段：

- `cancel_requested_at`
- `cancel_requested_by`

模型 `to_dict()` 新增：

- `cancel_requested`
- `cancel_requested_at`
- `cancellable`

`cancellable` 当前只对 `import_shipping/import_finance` 的 pending/running 且尚未请求取消的任务为 true。

### Repository

新增：

- `request_task_cancel(task_id, requested_by)`：原子、幂等登记取消；
- `is_cancel_requested(task_id)`：独立短事务读取，供 A2 长事务检查；
- `try_begin_commit(task_id)`：只有 active 且未取消时才能 CAS 到 `committing`。

取消请求不会释放 `shipping_data_mutation` 租约。只有 worker 写入终态后才释放。

reload 恢复现在覆盖 `pending/running/committing`。原提示中“导入数据已回滚”对分块重算并不总是真实，已收紧成
“任务因服务重启或重载中断”。

### HTTP

新增：

```text
POST /api/shipping/tasks/<task_id>/cancel
权限：shipping:edit
```

结果：

- 首次/重复取消：200，`已发送取消请求`；
- 不存在：404；
- `resolve_all/resolve_stale`：400，`该任务暂不支持取消`；
- 已结束：400；
- committing：409。

旧 `POST /api/shipping/import/cancel/<task_id>` 调用同一处理函数。

A1→A2 过渡期间，路由在持久化成功后仍同步设置原 `_cancel_flags`，避免旧 worker 只读取内存标志时发生功能倒退。
持久化字段已经是对外事实来源；A2 改完 worker 后应删除 `_cancel_flags`。

## CAS 语义

取消与最终提交并发时：

- 取消先写入 `cancel_requested_at`：`try_begin_commit()` 返回 false；
- committing 先成功：取消接口看到 committing 并返回409；
- 两者不会同时成功；
- 两种结果下租约都继续由当前任务持有。

## 自动化验证

- 新增10项测试，覆盖：
  - 持久化和重复取消；
  - 首次操作者审计字段不被重复请求覆盖；
  - 不支持、committing、已结束、不存在；
  - cancel/committing 两线程 CAS 竞态；
  - committing 的 reload 中断和租约释放；
  - HTTP outcome/status/message 映射；
  - 真实 Cookie JWT 下 viewer 403、editor 200；
  - 新旧取消路径使用同一契约。
- Alembic 线性历史和升级建表测试已更新。
- 全量后端：`219 passed`。
- `compileall`、`git diff --check` 通过。
- Alembic：`20260724_03 (head)`。

## 部署顺序

1. 确认没有运行中的 shipping 任务，备份数据库。
2. 上传 migration、模型、repository、route 文件，但不要 reload。
3. `alembic upgrade head`，确认 current=`20260724_03`，核对两个可空字段。
4. 再 reload，连续检查 gunicorn status/journal、`/health`、`/ready`。
5. 用测试导入任务验证：
   - viewer 取消403；
   - editor 新旧路径均200；
   - `cancel_requested_at/by` 已写入；
   - 取消请求后租约仍保留；
   - worker 真正 cancelled 后租约释放。
6. resolve 任务取消必须返回“不支持”，不能返回假成功。

A1 可独立部署，过渡内存标志会维持当前导入取消能力；但前端新交互仍应等待 A2。

## A2 明确入口

A2 需要：

1. 解析、DB比对、bulk写入、增量resolve加入持久化 `cancel_check`；
2. 最终 commit 前调用 `try_begin_commit()`；
3. 取消胜出时 rollback 并进入 cancelled；
4. 删除 `_cancel_flags`；
5. 补 parsing/inserting/resolving 三阶段原子回滚测试。

## 新发现：shipping 旧 SSE 仍能占 worker

`GET /api/shipping/import/progress/<task_id>` 当前仍返回一个循环 `sleep(1)` 的流式 generator。新前端已经不调用，
但旧客户端或直接请求仍会占住唯一 sync worker，因此“代码库已没有任何可占 worker 的 SSE 端点”并不完全准确。

建议 A2 同批把它改成与产品生命周期兼容入口相同的“读取一次持久化快照后立即关闭”，或确认没有兼容需求后删除。
这不改变新前端契约。
