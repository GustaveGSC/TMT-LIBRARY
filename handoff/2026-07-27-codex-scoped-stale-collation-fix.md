# scoped stale 标记排序规则修复交接

## 修复内容

生产故障确认后，所有 `return_record.ecommerce_order_no` 与
`shipping_order_finished.ecommerce_order_no` 的 stale 影响范围 JOIN 改为：

```sql
return_record.ecommerce_order_no COLLATE utf8mb4_unicode_ci
  = shipping_order_finished.ecommerce_order_no
```

只转换 `return_record` 一侧；resolved 表一侧保留其历史
`utf8mb4_unicode_ci`，避免原比较触发 MySQL 1267，同时尽量保留 resolved
表订单号索引作为 lookup 候选。SQLite 路径维持普通等号比较，避免伪造 MySQL
排序规则。

本次仅修复这次 stale 查询实际触发的两个跨表订单号 JOIN。`finished_code`
与产品表的其他既有 JOIN 不在本批擅自改动；后续若做全库排序规则归一化，应单独
评估索引重建、表锁和现有查询语义。

## 新门禁

- 新增 MySQL SQL 编译断言，要求生成 `COLLATE utf8mb4_unicode_ci`。
- 新增 `mysql_integration` 只读集成测试：配置
  `MYSQL_COLLATION_TEST_DATABASE_URL` 指向隔离 MySQL 且具备与生产相同的列排序规则后，
  会真实执行问题 JOIN；默认本地环境明确跳过，不能把 SQLite 通过当成 MySQL 通过。

## 验证

- `pytest backend/tests -q`：全绿，MySQL 集成门禁因未配置隔离 MySQL 而跳过。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。

## 部署前强制步骤（Claude Code）

1. 在服务器隔离验证目录运行此分支代码，不直接覆盖运行目录。
2. 用生产排序规则的只读 MySQL 连接执行 `MYSQL_COLLATION_TEST_DATABASE_URL=... pytest -m mysql_integration`；必须实际执行、不可跳过。
3. 对三个入口各做一次真实 HTTP 验证：仓库配置原样保存、成品-组件无业务变化的保存、通用件对新增/删除使用可回滚的测试数据。
4. 每次验证同时确认：HTTP 不是 500、规则与 stale 标记同事务、任务终态释放 lease。通过后才合并/部署。
