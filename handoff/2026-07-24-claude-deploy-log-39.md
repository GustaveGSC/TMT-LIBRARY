# Claude 部署记录：发货任务取消 A2（完整导入取消链路）

日期：2026-07-24 ~ 2026-07-25

## 审查要点

- 取消检查点铺开到解析（每500行）、DB快照比对、UPSERT、增量 resolve（每100单/每chunk）、最终提交前，
  全部统一走 `InterruptedError` → `except Exception: db.session.rollback(); raise` 路径，导入始终保持
  单事务、`commit_chunks=False`，取消不会留下半写数据。
- 最终提交前 `begin_commit()`（即 A1 的 `try_begin_commit()` CAS）与取消竞争：
  `test_shipping_import_winning_final_commit_cas_commits_once` 显式断言调用顺序
  `['cas', 'commit']`，不是只看两者都发生——真的验证了"CAS先于commit"这个关键不变量。
- 旧 `/import/progress/<task_id>` SSE 兼容入口改成读一次持久化快照立即返回，`_cancel_flags` 内存字典
  已完全删除，取消状态只有 `shipping_task.cancel_requested_at` 一个事实来源。
- 225 项测试全部真实断言（CSV 解析取消断点精确到第4次检查触发、CAS 顺序、回滚计数）。

## 部署

1. 确认无运行中任务，备份数据库（`tmt_db_20260725_090252_pre_shipping_cancel_a2.sql.gz`，确认
   `Dump completed`）。本批无 Alembic 迁移，A1 的 `20260724_03` 已足够。
2. 上传 3 个文件（repository/routes/services），MD5 校验一致。
3. `systemctl reload gunicorn`：master 稳定，journalctl 无异常，`/health`/`/ready` 正常。

## 生产验证（真实数据，非 mock）

1. **SSE 循环端点已修复确认**：`curl` 直接请求 `/import/progress/<不存在的task_id>`，6ms 内返回 404，
   不再有循环等待——之前 A1 审查时发现的"仍会占住 worker"的问题已解决。
2. **真实取消端到端**（最强验证）：用真实 HTTP 会话构造一个2000行合成发货清单（订单号带唯一测试
   标记，测试前确认库里不存在同标记数据），通过 `/api/shipping/import/shipping` 触发真实导入任务，
   立即发送真实 `/api/shipping/tasks/<id>/cancel` 请求，轮询到终态：
   - 任务终态为 `cancelled`，文案"导入已中止，业务数据已回滚"；
   - 查询 `shipping_record` 表确认该测试批次标记对应的行数为 **0**——取消命中并完整回滚，不是
     mock 断言，是对生产数据库的真实读验证。

## 结论

A1+A2 门禁全部通过，无需回滚。发货/财务导入现在有完整、持久化、可跨进程恢复的取消能力。
`resolve_all`/`resolve_stale` 仍明确返回"不支持取消"，范围未扩大。

## 下一步

- 前端：导入取消按钮 + 轮询状态适配（`cancellable`/`cancel_requested` 字段驱动 UI），Claude 待安排。
- 后续按既定顺序：B批生产只读歧义审计 → C批 staging/cutover 安全取消重算 → D批同规格压测。
