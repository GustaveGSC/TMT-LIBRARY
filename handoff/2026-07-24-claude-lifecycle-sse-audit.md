# 产品生命周期 SSE · 只读审计报告

日期：2026-07-24
性质：只读代码走查 + 生产环境只读查询实测，无代码变更、无数据写入。

## 结论先行

产品生命周期更新（`POST /api/product/lifecycle/update` + `GET /api/product/lifecycle/progress/<task_id>`）
和 D 批之前的发货任务是**同一种风险模式**：纯内存 `queue.Queue`、无持久化、SSE 长连接占住唯一 sync
worker。实测生产数据下，仅只读聚合查询部分就要 ~6.9 秒，加上循环内每个型号一次 `db.session.commit()`
（233~403 次），预估全流程在十几到三十秒量级——量级上小于 resolve-all（分钟级），但**同样会在运行期间
让整个后端对其他所有请求失去响应**，因为问题根源是"SSE 连接持有 worker"，不是"计算本身有多慢"。

建议：**不需要插队到"数据管理入口迁移"之前单独立项**，但应该在近期批次里顺带迁移（可以和其他现有 SSE
清理工作合并，采用 D 批已验证过的持久化任务表模式），因为它是当前代码库里唯一还没有迁移完的
SSE-占用-worker 风险点。

## 一、是否持久化：否

`backend/routes/product/lifecycle.py`：

```python
_task_queues: dict = {}   # 纯内存，进程重启/reload 即丢失

@lifecycle_bp.post('/update')
def start_update():
    task_id = str(uuid.uuid4())
    q = queue.Queue()
    _task_queues[task_id] = q
    ...
    threading.Thread(target=run, daemon=True).start()
    return Result.ok(data={'task_id': task_id}).to_response()

@lifecycle_bp.get('/progress/<task_id>')
def get_progress(task_id):
    q = _task_queues.get(task_id)
    if not q:
        return Result.fail('任务不存在').to_response()
    def generate():
        while True:
            event = q.get(timeout=300)   # 阻塞等待，最长300秒
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get('step') in ('done', 'error'):
                _task_queues.pop(task_id, None)
                break
    return Response(stream_with_context(generate()), mimetype='text/event-stream', ...)
```

这和 D 批之前的 `backend/routes/shipping/__init__.py` 里 `import_progress()` 的旧实现几乎一模一样：
没有数据库表兜底，没有 reload 恢复机制，`generate()` 里的 `q.get(timeout=300)` 会让这条 HTTP 连接
（也就是唯一的 sync worker）整整阻塞到任务结束或 300 秒超时为止。

对比：D 批之后的 `shipping_task` 表模式——持久化状态、reload 后可从数据库恢复、前端改短轮询不再占用
worker——生命周期任务完全没有对应机制。

## 二、实际运行时长：只读部分实测 ~6.9 秒，全流程预估十几到三十秒

`update_lifecycle()`（`backend/services/product/lifecycle.py:124-300`）分两段：

**第一段（只读聚合，已在生产实测）**：

```
query1（每型号发货首尾月份，JOIN shipping_order_finished）：2.933s（233 个型号有发货数据）
query2（每型号所有出现月份，用于孤立尾部检测）：            1.811s（2425 行）
query3（每型号每月发货数量，用于重新上市判断）：            1.975s（2425 行）
query4（全部 status=recorded 的成品）：                    0.206s（403 行）
──────────────────────────────────────────────────────────
只读部分合计：6.925s
```

三条聚合查询都是对 `shipping_order_finished`（生产 66 万+行）做 `JOIN product_finished` 后
`GROUP BY model_id`，**没有任何 `USE INDEX` hint**，也没有按 `source` 过滤——和这批之前修复的
`_get_shipping_agg()` 是同一类"缺索引 hint 的全表 JOIN 聚合"问题，只是这里的过滤条件
（`status='recorded'` + `operator NOT IN (...)`）选择性可能不同，需要 Codex 用 `EXPLAIN ANALYZE`
进一步确认，我这里没有对这几条 SQL 做执行计划分析（只测了端到端耗时，避免在生产环境做更深的诊断性
查询）。

**第二段（内存循环 + 逐型号 commit，未在生产执行，只读代码分析）**：

```python
for idx, model_id in enumerate(all_model_ids):   # 生产实测 403 个型号
    ...                                            # 纯 Python 日期字符串运算，无 DB 查询
    db.session.commit()                            # 每个型号一次 commit
```

循环体本身是纯 Python 字符串/日期运算，不含额外 SQL 查询（`shipping_by_model`/`months_by_model`/
`qty_by_model` 都已在第一段一次性加载进内存字典），单次迭代耗时可忽略；但 403 次独立
`db.session.commit()` 各自都有 MySQL 端的事务提交开销，保守估计每次几到几十毫秒，累计可能有数秒到
十几秒。**这部分我没有在生产实际执行**（会产生真实写入，超出"只读审计"范围，需要用户/Codex 明确
授权后再测），以上是基于代码结构的合理预估，不是实测数字。

**全流程预估**：只读部分 ~7s（实测）+ 循环提交部分数秒到十几秒（预估）= 十几到三十秒量级。

## 三、和 resolve-all 的对比

| | resolve-all（D 批前） | 生命周期更新 |
|---|---|---|
| 持久化 | 无（D 批已修复为 `shipping_task` 表） | 无 |
| 规模 | ~25 万订单 | ~403 个型号 |
| 预估/实测耗时 | 分钟级（已用真实数据验证提速） | 十几到三十秒量级（本次只读实测） |
| SSE 占用 worker | 已修复（短轮询） | **仍然存在** |

生命周期任务规模小得多，不会像旧 resolve-all 那样造成长达数分钟的整站无响应，但只要触发一次，唯一的
sync worker 在这十几到三十秒内**同样会拒绝所有其他请求**（包括 `/health`），对用户体感是"点了一下
产品生命周期更新，整个系统卡住半分钟"。这个问题的性质和 resolve-all 完全一样，只是发生频率可能更低
（这是一个不常用的管理操作，不在日常导入流程里）。

## 四、建议

1. **不需要插队到"数据管理入口迁移"之前**：规模判断上它不是当前最紧迫的问题（比 resolve-all 影响小，
   触发频率低），可以按原计划顺序处理数据管理入口迁移、任务取消/并发边界/压测、后端结构拆分。
2. **建议在近期某一批里顺带处理**，复用 D 批已验证的模式：给 `product_lifecycle_task`（或复用/扩展
   `shipping_task` 表结构，如果业务上认为合适放在同一张表）加持久化状态，前端从 SSE 改短轮询。工作量
   预计远小于当初 shipping 那一整套（D 批），因为不涉及任务租约/取消/409 接管这些复杂语义——生命周期
   更新目前看不是并发敏感操作。
3. **顺手排查项**：三条聚合查询是否需要加 `USE INDEX` hint，或者是否可以合并成更少的查询（比如
   query1 的 min/max 和 query3 的按月汇总有重叠的 JOIN 条件，理论上能合并成一次查询用窗口函数或者
   在 Python 里从 query3 的结果推导出 first/last month，省掉 query1）。这个不影响是否要做持久化迁移，
   是否要做建议 Codex 判断优先级。

## 五、给 Codex 的问题

1. 是否同意"不插队，按原计划顺序处理，只在后续某一批顺带迁移生命周期 SSE"这个优先级判断？
2. 持久化状态是新建一张 `product_lifecycle_task` 表，还是扩展现有 `shipping_task` 表（加
   `domain`/`task_type` 区分）？两种方案哪个更符合现有代码组织习惯？
3. 三条聚合查询是否值得在这次迁移里顺带加索引 hint 或合并，还是单独排期？
