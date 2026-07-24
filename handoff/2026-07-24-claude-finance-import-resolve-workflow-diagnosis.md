# 财务数据导入/刷新全局数据 耗时与工作流耦合 · 诊断报告

日期：2026-07-24
性质：只读诊断（代码走查 + 生产日志/数据库实测），无代码变更。请 Codex 审核后决定方案与实施顺序。

## 结论先行

用户反馈的工作流是："导入财务数据 → 配置客户匹配（当前叫'外贸客户匹配'）→ 必须再跑一次'刷新全局数据'
（resolve-all），否则外贸数据不准确，但两步都很慢"。诊断后确认：

1. **"必须 resolve-all 客户匹配才准确"这个前提，目前代码层面不成立**——内外销/国家/品牌筛选对财务数据
   是查询时实时 JOIN 客户匹配表，不依赖 resolve 产出的任何快照字段。配置客户匹配后下一次图表请求就是
   准确的，不需要跑全量重算。这是本次诊断最核心的发现，需要 Codex 确认是否有我遗漏的耦合路径；如果确认
   没有，应该在产品/操作层面澄清，减少用户被迫触发慢速 resolve-all 的频率。
2. **两处"慢"是真实的、且原因不同**：
   - resolve-all／大批量导入的成品组合匹配是 O(订单数 × 成品数) 的纯 Python 贪心循环，单线程跑在唯一
     的 gunicorn sync worker 上——这是耗时的根本原因，不是 I/O 问题。
   - 财务导入是一整个不分段提交的大事务，生产已经真实撞到过 MySQL 连接超时导致整单失败
     （`Lost connection to MySQL server during query (timed out)`），这不只是"慢"，是有真实失败/需要
     重新导入的可靠性问题。
3. 唯一确认存在、但影响很小的耦合：客户匹配保存后没有清空 5 分钟 TTL 的 `chart-options` 缓存，筛选面板
   的国家/品牌下拉选项最多可能滞后 5 分钟——**不影响图表数据本身的准确性**，只影响筛选下拉列表的新选项
   出现时机。

## 一、"客户匹配必须 resolve 才生效"是否成立：代码走查

### 财务数据的内外销/国家/品牌筛选是实时 JOIN，不是快照

`backend/database/repository/shipping/__init__.py:1072-1073`：

```python
q = q.outerjoin(
    ShippingFinanceCustomerMapping,
    sof.customer_alias == ShippingFinanceCustomerMapping.customer_alias,
)
...
if needs_trade_filter:
    if source == 'finance':
        expected_status = 'export' if trade_type == 'foreign' else 'domestic'
        q = q.filter(ShippingFinanceCustomerMapping.status == expected_status)
```

这是 `get_chart_data()` 每次请求都会执行的查询路径，按 `customer_alias`（字符串）实时关联客户匹配表的
`status`/`country`/`brand`。`get_chart_data()` 本身没有缓存（之前批次已确认，见
`handoff/2026-07-24-codex-shipping-chart-performance-diagnosis.md` 第3.3节），意味着改完客户匹配、
下一次图表请求立刻反映新状态。

### resolve 阶段完全不碰客户匹配表

`_resolve_orders()`（`backend/services/shipping/__init__.py:349-529`）只做"贪心匹配成品组合"这一件事：
读取 `shipping_record` 的产成品明细，匹配 `product_finished`/`product_packaged`/`packaged_equivalent`，
写入 `shipping_order_finished`。整个函数没有一处读取或写入 `ShippingFinanceCustomerMapping`。
`shipping_order_finished.customer_alias` 只是从 `shipping_record.customer_alias` 原样复制过去的字符串
（`backend/services/shipping/__init__.py:500` 附近的 `meta.get('customer_alias')`），跟客户匹配表的
映射状态完全没有绑定关系——不管这个别名是在导入前还是导入后被配置成"外贸/内销/非销售"，只要字符串对得
上，JOIN 都能查到最新状态。

### 新导入订单已经在导入时自动 resolve 过一次

`import_finance()`（`backend/services/shipping/__init__.py:606-687`）在插入完 `shipping_record` 之后，
对本批次新增订单立刻调用了 `_resolve_orders(new_order_nos, source='finance', ...)`。也就是说，新导入
的财务订单在导入完成的那一刻，`shipping_order_finished` 就已经生成好了，不需要额外再跑一次全量
resolve-all 才能"看到"这批订单。

### 结论

按现有代码，日常"导入财务数据 → 配置客户匹配"这个组合操作后，**不需要**跑 resolve-all 就能让图表的
内外销/国家/品牌统计准确。resolve-all 存在的意义是重算成品组合（比如产品库分类/编码规则变更后需要
重新匹配，或者怀疑历史数据因为产品库变更而匹配错了），跟客户匹配的准确性是两件不相关的事。

**这个结论需要 Codex 确认**：请检查是否存在我未覆盖到的路径——比如 `get_finance_customer_aliases()`
（客户匹配配置页读取可选别名列表的接口）是否某个分支读的是 `shipping_order_finished` 而非
`shipping_record`，导致新导入但未 resolve 的别名不出现在配置列表里。我看到的实现（
`backend/database/repository/shipping/__init__.py:60-118`）是从 `shipping_record`/`return_record`
两表 UNION 聚合别名出现次数，不依赖 `shipping_order_finished`，但这部分逻辑较绕，建议 Codex 复核一遍。

## 二、resolve-all／大批量导入为什么慢：算法复杂度实测

### 生产数据规模

```
product_finished 总数：              488
有产成品组合的成品数（sorted_finished）：404
shipping 来源历史订单数（去重）：      133,701
finance 来源历史订单数（去重）：       116,864
shipping_record 总行数：              768,973
```

### `_resolve_orders()` 的复杂度

`backend/services/shipping/__init__.py:461-479`，对**每一个订单**都要遍历一次 `sorted_finished`
（按产成品数量降序排好的全部 404 个成品）做贪心匹配：

```python
for idx, (order_no, data) in enumerate(order_data.items()):
    ...
    for f_code, f_name, required_codes in sorted_finished:
        if not all(_avail(code, remaining) > 0 for code in required_codes):
            continue
        ...
```

resolve-all 对**全量历史订单**（约 133,701 + 116,864 ≈ 250,565 个）执行这个双重循环，内层
`sorted_finished` 404 项，外加 `_avail()` 内部再遍历 `required_codes`（每个成品的产成品明细，通常
几到十几项）——保守估计这是 **上亿次** 纯 Python 级别的字典查找和条件判断，全程跑在单个 sync worker
里，不释放 GIL 给其他请求。这直接对应 `.claude/CLAUDE.md` 里已经记录的"单 worker + CPU 密集后台任务的
看门狗超时风险"那条规范——resolve-all 和大批量 `import_finance`/`import_shipping` 是目前最典型的会长期
占用 CPU、不主动让出控制权的操作。

大批量导入（比如一次导入几万行的财务 Excel）触发的 `_resolve_orders` 只针对本批新增订单，规模远小于
resolve-all，但如果新增订单量本身达到万级，同样的 O(N×404) 复杂度依然会造成分钟级耗时。

### 尚未验证但值得排查的方向（留给 Codex 评估）

- `sorted_finished` 是否可以按订单内实际出现的 `product_code` 集合先做一次索引/过滤，避免对明显不可能
  匹配的成品也执行一次完整的 `all(_avail(...) > 0 ...)` 检查；
- 是否可以把"产成品→成品"的映射关系预处理成倒排索引（`product_code → 可能用到这个码的成品列表`），
  只遍历订单里出现过的产成品对应的候选成品子集，而不是每次都过一遍全部 404 个成品；
- 分批提交对进度可见性和"CPU 密集型任务定期让出控制权"的价值（下面第三节展开）。

本报告不建议直接改算法实现——现有贪心匹配的语义（精确码优先、等效码兜底、按产成品数量降序贪心）之前
已经踩过坑（见 `feedback_equiv_greedy` 记忆），改动需要跟业务口径一起验证，应该是独立的一批任务。

## 三、财务导入的真实失败案例：长事务撞连接超时

生产 `journalctl -u gunicorn` 日志里有一次真实的导入失败（非推测）：

```
Jul 22 07:38:57 ... sqlalchemy.exc.OperationalError: (pymysql.err.OperationalError)
  (2013, 'Lost connection to MySQL server during query (timed out)')
[SQL: INSERT INTO shipping_record (...) VALUES (...) ON DUPLICATE KEY UPDATE ...]
```

`import_finance()` 调用 `bulk_insert_shipping(..., commit_chunks=False)` 和
`bulk_insert_return(..., commit_chunks=False)`，即整个"插入 shipping_record + 插入 return_record +
resolve 新订单"是**一个未分段提交的大事务**，直到最后才 `db.session.commit()`。当文件较大、加上
resolve 阶段的 CPU 密集计算耗时较长时，同一个数据库连接长时间没有新的活跃查询，触发了 MySQL 侧的连接
超时，导致整个事务失败回滚——用户体验是"导入失败，需要重新上传"，这比"单纯慢"更严重，属于可靠性问题
而不只是性能问题。

这与之前排查过的 `--timeout 1800`（gunicorn 看门狗超时，防止 worker 被误杀）是两个不同层面的超时。
核对 `backend/app.py` 里 SQLAlchemy 连接池配置（第48-60行左右）：

```python
"pool_size":     int(os.getenv("POOL_SIZE", 5)),
"pool_pre_ping": True,
"pool_recycle":  1800,
"connect_args": {
    "connect_timeout": 10,
    "read_timeout":    30,
    "write_timeout":   30,
},
```

`read_timeout=30` 是 pymysql 单条查询等待服务端响应的超时。日志里出错的是一条 `executemany` 批量
`INSERT ... ON DUPLICATE KEY UPDATE`（chunk 内多行合并成一条语句发送），如果这条语句本身在服务端执行
超过 30 秒（大 chunk、有锁等待、或服务器当时正在跑其他慢查询导致行锁/表锁争用），就会直接命中这个
30 秒读超时并整段失败——这是比"连接空闲太久被回收"更直接的解释（`pool_recycle=1800` 针对的是连接池里
闲置连接，不是单条语句执行中的超时）。核对 `bulk_insert_shipping()` 源码（`backend/database/repository/shipping/__init__.py:327`），
`CHUNK = 100`，即失败的那条语句只是 100 行的 upsert，正常情况下不该接近 30 秒——这提示当时更可能是
**锁等待或磁盘 I/O 争用**导致单条本该很快的语句被拖到超时，而不是"chunk 本身太大"。发生时间
（2026-07-22 07:37-07:38）与本轮已修复的 `_get_shipping_agg` 慢查询、以及 128MB buffer pool 明显小于
数据量这两个已确认的容量问题是同一批根因的延伸——值得和"发货图表慢"那次诊断的产能结论一起看，而不是
孤立地调大 `read_timeout` 掩盖问题。建议 Codex 评估：①是否需要把大事务拆分成多段提交（需要评估拆分后
"导入失败部分回滚"这个原子性语义是否还能保持，还是要改成"允许部分成功+明确告知哪些行失败"）；②是否
应该等本轮 SQL 修复+一周慢日志观察窗口结束后，再一并判断是否要提高 buffer pool。

## 四、已确认但影响较小的缓存问题

`backend/routes/shipping/__init__.py:409` 的 `save_finance_customer_mapping()` 路由没有调用
`_invalidate_chart_options_cache()`。`chart-options` 有 5 分钟内存缓存（`.claude/CLAUDE.md` 已记录），
配置客户匹配后，筛选面板的国家/品牌下拉选项列表最多可能要等 5 分钟缓存过期才会出现新值——但这不影响
`chart-data`（实际图表数据）的准确性，因为 `chart-data` 每次都是实时查询（见第一节）。建议顺手补上
这处缓存失效调用，成本很低。

## 五、命名建议（用户原话，转达）

用户建议把"外贸客户匹配"改名为"客户匹配"（页面/tab 文案）。这是纯前端文案改动，风险低，可以随手做，
不影响本报告其他结论。

## 六、给 Codex 的具体问题

1. 第一节的结论（客户匹配不依赖 resolve）是否有我遗漏的耦合路径？如果确认没有，是否需要在前端加一句
   提示（比如客户匹配配置页说明"保存后立即生效，无需刷新全局数据"），减少用户的操作负担和不必要的
   resolve-all 触发频率？
2. `_resolve_orders` 的 O(订单数×成品数) 复杂度是否有优化空间（倒排索引/预过滤），值得单独立项，还是
   现阶段数据量下可以接受，先只解决第三节的连接超时可靠性问题？
3. 生产那次 100 行 chunk 的 upsert 撞到 30 秒 `read_timeout`，是偶发的锁等待/IO 争用，还是有更系统性
   的原因（比如与 resolve 阶段共享同一个长事务、同一连接）？大事务拆分成多段提交在"导入失败需要整单
   回滚重来"这个现有语义上是否可接受，还是需要改成别的错误处理策略？
4. `save_finance_customer_mapping()` 补 `_invalidate_chart_options_cache()` 是否可以直接纳入下一批
   顺手修掉？
