# scoped stale 标记：排序规则修复已生效，但暴露第二个独立 bug，已再次回退

日期：2026-07-27

## 结论

排序规则修复（ff16b3f/880093c/c7781c6）本身是对的：隔离目录用真实生产 MySQL 连接直接执行
`_order_no_join()` 编译断言 + 只读执行问题 JOIN，全部通过；部署后**入口1（仓库过滤配置）真实
HTTP 双向切换验证通过**（200，`stale_pairs=6`，配置已还原）。

但在验证**入口2（成品-组件关联）**时，真实 HTTP 调用
`DELETE /api/product/finished/488/packaged/508` 500 失败，暴露了一个此前从未被排序规则问题
掩盖过的**第二个、完全独立的 bug**。三个规则变更入口里，入口2/入口3（成品-组件关联、通用件对）
都会经过同一段代码，**目前仍然 100% 不可用**，已再次回退到 `7114f9f`（d926dc3 之前）。

## 根因：UNION 查询的匿名子查询丢失显式列名

`backend/database/repository/shipping/__init__.py` 里 `mark_stale_for_component_codes()`：

```python
pair_query = pair_queries[0]
for query in pair_queries[1:]:
    pair_query = pair_query.union(query)
return ShippingRepository._mark_stale_pairs(pair_query)
```

`_mark_stale_pairs()`：

```python
pairs = pair_query.distinct().subquery()
...
db.session.query(pairs.c.source, pairs.c.ecommerce_order_no)
```

生产真实报错：

```
File ".../database/repository/shipping/__init__.py", line 1074, in _mark_stale_pairs
    db.session.query(pairs.c.source, pairs.c.ecommerce_order_no),
File ".../sqlalchemy/sql/base.py", line 1727, in __getattr__
    raise AttributeError(key) from err
AttributeError: source
```

`mark_stale_for_component_codes()` 在 `component_codes` 非空时至少 union 两条查询（正向
`shipping_record` 命中 + 销退 `return_record` 命中），每条子查询都对列做了
`.label('source')`/`.label('ecommerce_order_no')`；但把 **`.union()` 之后的结果再包一层
`.subquery()`** 时，SQLAlchemy 在这条代码路径下没有把子查询的列重新绑定为 `source`/
`ecommerce_order_no`，导致 `pairs.c.source` 访问不到（`AttributeError`）。

`mark_stale_for_warehouse_names()`（入口1用的函数）**没有 union**，只是单条
`.join().filter().distinct().subquery()`，所以 `pairs.c.source` 能正常访问——这就是为什么
入口1真实验证通过，而入口2/3 没有测到。

`finished_codes` 非空时会加第三条 union 分支（`ShippingOrderFinished.finished_code.in_(...)`
直接过滤，不 join），推测同样会触发。

## 为什么 SQLite 单测没发现

现有 `test_shipping_scoped_stale_marking.py` 里
`test_component_scope_marks_existing_raw_and_return_pairs_only` 覆盖的正是
`mark_stale_for_component_codes()` 这条 union 路径——需要确认这条测试当时到底是真的跑通了
`pairs.c.source` 访问，还是测试断言方式本身没有触发这一行代码（比如直接比较
`is_stale` 结果而不是分步调用 `_mark_stale_pairs`），或者 SQLite 方言在 union 后子查询列名
解析上跟 MySQL 行为不同、SQLite 恰好能正确推断列名而 MySQL 方言不能。这次的教训和上次排序规则
一样：**光靠 SQLite 通过不能证明 MySQL 上也没问题**，需要实际确认这条测试路径在 MySQL 下的行为，
而不是假设它和 SQLite 一致。

## 生产验证：回滚安全，无数据损坏

- 失败请求后立即核实 `product_finished_packaged` 里 `(finished_id=488, packaged_id=508)`
  关联仍然存在（事务正确回滚，未产生"表面看关联被删了实际卡在中间状态"的问题）；
- 对应 `shipping_task(task_type='rule_change')` 记录落在 `status=error`，`lease_key=NULL`
  （released，无残留租约）；
- 回退部署后用真实 HTTP 重新验证 `POST /api/product/finished/488/packaged/508`（关联本就存在，
  等价于 no-op 重新关联）返回 `200 {"message":"关联成功","success":true}`，功能恢复。

## 已执行的回退

再次手工检出以下 5 个运行时文件到 `7114f9f`（与第一次排序规则回退相同的基线，即完全撤销
d926dc3 引入的 scoped stale 标记功能，包括这次的排序规则修复）：

- `backend/database/repository/shipping/__init__.py`
- `backend/routes/product/finished.py`
- `backend/routes/shipping/__init__.py`
- `backend/services/product/finished.py`
- `backend/services/shipping/__init__.py`

部署到生产：备份未使用（无 schema/数据变更），直接同步文件 + MD5 核对 + `systemctl reload`，
master PID 未变，`/health`/`/ready` 正常，真实 HTTP 验证功能恢复。

**没有回退** `20260727_01` 索引迁移（纯增量，无害，回退后的旧代码不引用它们）。

## 交给 Codex 的修复方向

1. 修复 `mark_stale_for_component_codes()` 里 union 查询包一层 `.subquery()` 后列名丢失的问题
   —— 可能需要显式给 union 后的子查询/CTE 声明列（例如 `union(...).subquery()` 后用
   `.selectable.columns` 显式重命名，或者改用 `sqlalchemy.union()` 顶层函数 + 显式
   `.c['source']`/位置索引访问而不是属性访问，需要 Codex 判断哪种写法在当前 SQLAlchemy 版本下
   对 MySQL 可靠）；
2. **必须**在真实 MySQL（不能只用 SQLite）上补一条集成测试，直接调用
   `mark_stale_for_component_codes()`（同时覆盟 `component_codes` 和 `finished_codes` 两个
   分支，因为 union 分支数量不同）并断言不抛 `AttributeError`，参照上次排序规则修复引入的
   `mysql_integration` 门禁模式；
3. 顺带检查现有 SQLite 单测为什么没能发现这个 bug——如果是断言方式的盲区，需要一并修正断言，
   不能只加 MySQL 门禁而不理解为什么原有测试没拦住。

修复后同样需要走一次完整的三入口真实 HTTP 验证（这次入口1已经通过，可以保留复用；入口2/3需要
在修复后重新验证）才能再次部署，我这边再次审查+部署。

## 当前生产状态

三个规则变更入口（仓库过滤、成品-组件关联、通用件对）**全部退回到 d926dc3 之前的行为**：
配置保存正常，但**不会**标记任何订单为 `is_stale`（回到这批功能上线之前的状态，与
`resolve_all`/`resolve_stale` 的既有行为一致，不影响其他已上线功能）。
