# C 批生产容量/锁时长门禁实测报告：resolve_all 全量重建失败

日期：2026-07-25
性质：真实生产维护窗口测试（已获用户明确授权直接在生产做低峰测试，非 staging 环境）
结论：**门禁未通过，`resolve_all` 全量重建当前在生产不可用，需要重新设计 cutover**

## 一、部署过程（已完成，保留在生产）

按标准流程部署：全量备份 → 上传 migration/repository/routes/services → `alembic upgrade head`
到 `20260725_01` → 校验新表结构 → `systemctl reload gunicorn` → 部署已适配取消按钮的前端。全部
验证通过，`/health`/`/ready` 正常，master PID 未变。

## 二、resolve_all 全量重建实测

用真实 HTTP 会话触发 `POST /api/shipping/resolve-all`（当时生产 `shipping_order_finished`
692,003 行：shipping 358,460 + finance 333,543），全程后台线程每 0.3 秒探测 `/health`。

### 阶段耗时

```
t=2.3s    pending
t=32.9s   resolving（current=2000/total=250565，即 staging 分块写入阶段开始）
t=560.2s  error（任务执行失败，错误编号 a0fe975aaabd）
```

staging 分块构建阶段（2.3s ~ 约527s之间）本身运作正常；失败发生在最终 cutover 事务。

### 根因：无 WHERE 条件的全表 DELETE 超过 read_timeout

服务器日志（`journalctl -u gunicorn`）显示：

```
pymysql.err.OperationalError: (2013, 'Lost connection to MySQL server during query (timed out)')
  File ".../database/repository/shipping/__init__.py", line 1136, in cutover_resolve_staging
    deleted = connection.execute(db.delete(live)).rowcount
```

`backend/app.py` 里 SQLAlchemy 引擎配置 `read_timeout=30`（秒）。`cutover_resolve_staging()` 对
`full_rebuild=True`（即 resolve_all）执行的是**不带 WHERE 条件的全表 `DELETE FROM
shipping_order_finished`**（692,003 行），这条语句在这台 2 核/1.7GB、InnoDB buffer pool 仅 128MB
的服务器上耗时超过 30 秒，触发 socket read timeout，连接断开，事务失败。

这正是 C 批交接文档第五节预先警示的场景："如果 staging 证明全表 DELETE + INSERT SELECT 的锁时长
不可接受，不得退回旧的分块覆盖方案；应继续设计表代际/rename 型 cutover 后再上线"——门禁按预期拦下
了这个问题，没有让它变成生产"正常功能"。

### 数据安全验证：完全达标

- **health 探测**：1756 次探测，成功 1756/失败 0，p50=6ms，p95=97ms，max=3229ms（单次抖动，非
  持续阻塞）。全程 `/health` 保持响应，说明 staging 构建阶段（占了失败前绝大部分耗时）没有占住
  唯一 sync worker——真正的风险窗口只在最后那次几十秒的 DELETE 里，且期间 `/health` 探测仍然全部
  成功（因为 DELETE 卡在等待 MySQL 响应的那个后台线程连接上，不是 Flask 请求处理线程本身）。
- **重算前后 `shipping_order_finished` 行数完全一致**：`692003 / shipping=358460 / finance=333543`
  ——DELETE 未提交（客户端连接中断，事务未 COMMIT，InnoDB 自动回滚），INSERT SELECT 未执行，正式
  数据完全没有被触碰。原子性保证在这次真实故障里成立。

### 新发现的次生问题：失败清理路径未生效

任务正确进入 `error` 终态、租约正确释放（`lease_key=None`），但 `shipping_order_finished_staging`
和 `shipping_resolve_target` 两张 staging 表分别残留 **691,998** 行和 **250,565** 行，没有被
`_run_staged_resolve()` 异常处理里的 `cleanup_resolve_staging(task_id)` 立即清理掉。

推测原因：DELETE 超时断连后，紧接着尝试用同一个（可能仍处于不一致状态的）连接池/引擎做清理，大概率
撞上同样的资源紧张或连接异常，`cleanup_resolve_staging` 自身失败但被 `except Exception as
cleanup_exc: report_internal_error(...)` 静默吞掉，没有重试、没有告警升级。系统设计的"一小时延迟
兜底清理"（`cleanup_abandoned_resolve_staging()`，下次重算开始时触发）本可以在一小时后自愈，但
"取消或失败只清理私有代"这个承诺在这次真实失败里没有立即兑现。

我已手动清理这两张表（按 task_id 精确删除，不影响任何其他数据），验证清理后 staging/target 两表均
为 0 行，`shipping_order_finished` 行数不变，`/health`/`/ready` 正常。

## 三、当前生产状态

- C 批代码（migration + 后端 + 前端取消按钮）**已部署且保留在生产**，因为：
  - 数据安全性验证通过（这是最高优先级的门禁项）；
  - 增量路径（导入触发的 `_resolve_orders`）、`resolve_stale` 在合理规模下大概率不受影响（见下）；
  - 取消能力、`committing` CAS 竞态等 A/B 批能力已经过独立门禁，不受本次失败影响。
- **`resolve_all`（全量重建）当前不可用**：任何用户点击"重建全部成品组合"，在数据量接近现在这个
  规模时，预计约 9 分钟后会看到失败提示。不会损坏数据，但功能本身不可用。
- `resolve_stale`（旧数据重算）理论上受影响更小，因为它是 subset cutover（`DELETE ... WHERE
  EXISTS(...)`，非全表 DELETE），但当前生产 `is_stale` 记录数为 0，本次没有真实数据可供验证，
  这条路径的规模上限还没有实测过。

## 四、建议下一步（交给 Codex 评估设计）

1. **不要重试同一个全表 DELETE 方案。** 按交接文档自己的预案，评估表代际/rename 型 cutover：
   构建一张新表（或用 `RENAME TABLE` 做原子切换），避免在一个语句里处理 60万+行的 DELETE。
   或者分块 DELETE（如每次 5000~10000 行，配合更长的语句级超时或分批提交），但分块提交会重新
   引入"取消/失败时数据处于中间态"的老问题，需要重新设计如何在这种模式下仍保证原子可见性
   （例如：分块只操作 staging 表内部，只有最后的 `RENAME`/指针切换才是真正的原子发布点）。
2. **修复清理路径的健壮性。** `cleanup_resolve_staging()` 在失败后紧跟着重试应该更谨慎：如果
   紧接着大概率会撞同一个连接/资源问题，考虑重试前短暂退避、使用新的独立连接、或者失败后不阻塞
   `raise`，把清理完全交给"一小时延迟兜底清理"并保证这个兜底路径本身有独立监控（当前它只在"下次
   有人发起重算"时触发，没有定时任务，如果长期没人点重算，孤儿 staging 数据会一直留着——这次是
   140MB+ 级别，需要考虑是否需要一个真正的定时清理任务而不是"lazy on next call"）。
3. 生产此时数据量为 shipping=358,460 / finance=333,543（合计692,003），比 B/C 批设计时参考的
   660,720 又增长了约 3 万行，说明数据还在持续增长，redesign 时应按"未来还会更大"的假设留出余量，
   不能刚好卡在当前规模。
4. `resolve_stale` 的 subset cutover 语义看起来更安全（有 WHERE 条件限定范围），但仍建议补一次
   针对"较大数量 stale 订单"（比如人为标记几千到几万条 `is_stale=1`，在只读演练环境或获得授权的
   生产维护窗口）的实测，不能假设"subset 一定小到不会超时"——如果某次通用件配置变更导致大量订单
   同时变 stale，这条路径可能面临类似风险。

## 五、给 Claude 前端的后续

- 保持"重建全部成品组合"按钮可见（不隐藏），但用户点击后失败是预期的已知问题，不是新 bug——已有的
  错误提示机制（`error` 终态展示后端消息）会正常显示失败，不会误导成"数据已损坏"，因为消息本身
  不包含这类措辞。是否需要在按钮旁加一条"当前全量重建可能失败，正在优化"的提示，等 Codex 给出
  修复时间预期后再决定，不在没有明确后端计划前抢先在前端加提示文案。
- `resolve_stale`（"刷新成品组合"按钮）保持现状，暂无已知问题。

## 附：清理记录

```
手动清理（task_id=ccbbf063-97d2-4d0b-91a5-977d37c93f66）：
DELETE FROM shipping_order_finished_staging WHERE task_id=... → 691998 行
DELETE FROM shipping_resolve_target WHERE task_id=...          → 250565 行
清理后确认：两表均 0 行，shipping_order_finished 行数不变，/health、/ready 正常。
```
