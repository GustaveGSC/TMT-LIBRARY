# Claude 部署记录：发货任务取消 A1（持久化取消协议）

日期：2026-07-24

## 审查要点

- `request_task_cancel()`/`try_begin_commit()` 都是单条原子 UPDATE，WHERE 条件本身就是判定条件——
  决策完全在 UPDATE 语句内完成，后续 SELECT 只用于给调用方分类返回文案，不构成 TOCTOU 竞态窗口。
- CAS 竞态测试用真实 `threading.Barrier(2)` 对真实 SQLite 跑两个线程，断言
  `(task.status == 'committing') != (task.cancel_requested_at is not None)`——精确的互斥不变量，
  不是只看"没崩溃"。
- 取消请求不释放 `shipping_data_mutation` 租约，只有 worker 真正进入终态才释放——审查确认与既有
  shipping_task 租约模型一致，没有引入新的竞态模式。
- `interrupt_running_tasks()` 现在同时覆盖 `committing` 状态，且不再声称"业务数据已回滚"（分块重算
  中途中断不一定真的是回滚状态）——文案收紧是对的，避免误导用户。
- 209→219 项测试全部真实断言（权限用真实 Cookie+JWT+CSRF，竞态用真实多线程），非 mock 空转。

## 新发现（Codex 报告，已复核确认）

`GET /api/shipping/import/progress/<task_id>` 兼容端点仍是 `while True: ... time.sleep(1)` 的循环
generator，直到任务终态才退出——直接访问这个端点仍会占住唯一 sync worker。之前 D 批验证时我只确认了
"新前端不再创建 EventSource"和"新端点响应快"，没有重新审查这个被保留为"deprecated 但循环体未改"的
兼容端点本身，属于我自己验证盲区。已读源码确认 Codex 的描述准确（`backend/routes/shipping/__init__.py`
第196-226行）。同意 Codex 建议放在 A2 一并处理（改成读一次持久化快照立即返回，和产品生命周期的兼容
入口做法一致），不在本批单独处理，避免和 A2 的其他 worker 改动重复触碰同一批文件。

## 部署（按交接文档顺序）

1. 确认无运行中 shipping 任务，备份数据库
   （`/root/backups/tmt_db_20260724_172302_pre_shipping_cancel_a1.sql.gz`，确认 `Dump completed`）。
2. 上传 migration/模型/repository/route 共 4 个文件，MD5 校验一致，reload 前确认。
3. `alembic upgrade head` → `20260724_03`，`DESCRIBE` 确认 `cancel_requested_at`/`cancel_requested_by`
   两个可空列已添加。
4. `systemctl reload gunicorn`：master PID 未变，journalctl 无异常，`/health`/`/ready` 正常。
5. 真实 HTTP 端到端验证（签发 author 账号的真实会话，viewer 场景用同一账号 id 但裁剪 JWT 里的
   permissions 模拟，不需要额外测试账号）：用两条合成的 `shipping_task` 行（不接触任何业务表，
   测试后删除）验证：
   - viewer 取消 → 403；
   - editor 新路径 `/tasks/<id>/cancel` → 200，`cancel_requested=true`；
   - 数据库确认 `cancel_requested_at`/`cancel_requested_by` 已写入，`lease_key` 仍保留；
   - 旧路径 `/import/cancel/<id>` 对同一任务重复取消 → 200，幂等；
   - `resolve_all` 类任务取消 → 400 `该任务暂不支持取消`，不是假成功。
   全部与交接文档描述的契约一致。

## 结论

A1 门禁全部通过，无需回滚。A1 只登记取消请求，没有把检查铺进解析/`_resolve_orders()`，因此现有导入
任务的实际取消能力仍由过渡期保留的 `_cancel_flags` 内存标志承载（路由层持久化成功后仍同步写入），
不会倒退。下一步等 Codex A2（检查点铺开 + 原子回滚 + 顺带修复旧 SSE 循环端点），前端导入取消适配在
A2 契约稳定后再开始。
