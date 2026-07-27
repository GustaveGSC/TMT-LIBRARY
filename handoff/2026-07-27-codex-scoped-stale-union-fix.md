# scoped stale UNION 列标签修复交接

## 根因与修复

第二次生产验证证明：旧实现使用 legacy `Query.union()`，再在 helper 内
`subquery()`，在 MySQL/SQLAlchemy 2 组合下会丢失 `source` 的公开列标签，导致
`pairs.c.source` 抛 `AttributeError`。SQLite 恰好可以推断该标签，因此未暴露。

现在组件/通用件影响范围改用 SQLAlchemy Core：

1. 每个分支以 `select(...label('source'), ...label('ecommerce_order_no'))` 创建；
2. `union_all(*branches)` 合并（最终 helper 统一 `DISTINCT`）；
3. helper 将结果显式命名为 `affected_pairs_raw`，再显式选出并命名两列到
   `affected_pairs`。

因此 count 和 UPDATE 使用的列契约不再依赖 legacy ORM compound-query 的方言行为。
先前的 MySQL 排序规则修复保留，两个 return-record JOIN 继续显式统一订单号排序规则。

## 新测试

- 原 SQLite 组件 scope 测试新增三分支 shape：两条组件分支 + 一条 finished-code 分支。
- `mysql_integration` 新增真实只读测试，调用
  `mark_stale_for_component_codes()` 同时覆盖 component 与 finished-code 分支；不存在的
  测试编码保证没有 UPDATE，`SET SESSION TRANSACTION READ ONLY` 防止误写。
- 本地全量 `pytest backend/tests -q` 通过；两项 MySQL integration 因未配置
  `MYSQL_COLLATION_TEST_DATABASE_URL` 跳过，这是预期的本地结果，**不能作为部署放行**。

## 部署门禁（不得省略）

1. 在隔离 MySQL 目录运行：
   `MYSQL_COLLATION_TEST_DATABASE_URL=... pytest -m mysql_integration`，两项必须实际执行通过，不能 skip。
2. 真实 HTTP 按顺序验证三个入口：仓库过滤双向保存、成品-组件添加/删除、通用件对新增/删除；每次核对配置与 stale 标记同事务、任务 lease 已释放。
3. 任何一个入口报错即回退全部本批运行时文件，不能只保留“已验证通过”的单个入口。
