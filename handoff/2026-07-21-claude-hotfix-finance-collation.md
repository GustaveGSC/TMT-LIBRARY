# 紧急交接 · Claude 直接修复财务客户简称查询排序规则冲突

日期：2026-07-21
提交：`ea936f7`（master，非独立分支——线上功能不可用，经用户同意直接在 master 上修复并部署）

## 背景

`FinanceCustomerMapping.vue` 上线后首次调用 `GET /api/shipping/finance-customer-aliases` 即生产 500：

```
pymysql.err.OperationalError: (1271, "Illegal mix of collations for operation 'UNION'")
```

## 根因

`shipping_record` 表整体排序规则是 `utf8mb4_unicode_ci`，`return_record` 表整体是 `utf8mb4_0900_ai_ci`（两张表历史建表时字符集/排序规则默认值不同，这是既有的表级差异，不是这次迁移引入的）。`20260721_02` 迁移给两表加 `customer_alias` 列时未显式指定排序规则，各自继承了所在表的默认值，导致两个字段排序规则不同。`get_finance_customer_aliases` 里对两表结果 `UNION ALL` 时，MySQL 要求参与集合运算的列排序规则一致，直接报错。

SQLite 独立迁移测试覆盖不到这个问题（SQLite 没有排序规则概念），本地 pytest 全绿但生产 MySQL 直接炸，是这次审查的盲区。

## 修复

`backend/database/repository/shipping/__init__.py`，`get_finance_customer_aliases`：
- `counts_for()` 里 `model.customer_alias.label(...)` 改为 `model.customer_alias.collate('utf8mb4_unicode_ci').label(...)`
- 外层 `outerjoin` 条件里 `ShippingFinanceCustomerMapping.customer_alias` 也显式 `.collate('utf8mb4_unicode_ci')` 再比较（`shipping_finance_customer_mapping` 表本身是 `utf8mb4_unicode_ci`，和 shipping_record 一致，但担心 GROUP BY 派生列可能丢失显式排序规则，一并加上更保险）

只改了这一个函数的两处比较表达式，未动 schema、未动其它查询路径。已用生产库直接跑等价 SQL 验证（UNION ALL 不再报错），部署（scp 单文件 + reload，md5 核对一致）并确认 gunicorn 无崩溃。

## 需要 Codex 核实/处理的事项

1. **确认这个修法本身没问题**：`.collate()` 只影响这一条查询里的比较/UNION 行为，不改变列的存储排序规则，属于查询层面的临时对齐，不是长期修复。
2. **是否要把两表排序规则彻底统一**：`shipping_record`/`return_record`/`shipping_finance_customer_mapping` 三张表排序规则不一致（`utf8mb4_unicode_ci` / `utf8mb4_0900_ai_ci` / `utf8mb4_unicode_ci`）是历史遗留问题，这次只是撞上了它。如果后续还有其它跨表 UNION/JOIN 涉及 return_record 的字符串字段，同样的坑还会再出现一次。要不要开一个后续任务把 `return_record` 表排序规则 `ALTER TABLE ... CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci` 统一掉？这个改动比较重（要锁表、扫全表 1.6 万行，虽然量不大但要评估索引重建耗时），建议 Codex 评估后决定是否值得做、什么时候做。
3. 如果决定不统一表级排序规则，麻烦帮忙把 `.claude/modules/database.md` 补一句"return_record 排序规则历史遗留为 utf8mb4_0900_ai_ci，与其它财务相关表不同，涉及 UNION/JOIN 时需显式 COLLATE"，避免以后再有人踩到。

## 越界说明

按 `AGENTS.md` 目录权限，`backend/` 应由 Codex 写入，这次是例外：线上新功能上线即报 500，属于用户可感知的当场故障，且改动范围明确可控（两行显式 `.collate()`，不涉及 schema/业务逻辑），经用户当面确认后直接修复止损。之后没有再修改 `backend/` 下其它内容，Codex 可以正常按自己的节奏接手上面列的后续事项。

---

## 追加 · 第二次热修（同一天）：财务导入 UPSERT 报 "Unknown column 'new.xxx'"

提交：`2a97801`

### 背景

用户拆分财务文件后开始真实重导，`import/finance` 任务执行到 `bulk_insert_shipping` 时报错：

```
pymysql.err.OperationalError: (1054, "Unknown column 'new.channel_name' in 'field list'")
```

### 根因（比排序规则那次更系统性，值得重点核实）

`bulk_insert_shipping`/`bulk_insert_return` 用 `mysql_insert(Model)`（不带 `.values()`）+ `db.session.execute(stmt, [dict, dict, ...])` 做 executemany。SQLAlchemy 2.0 在这种"无显式 values，直接给 executemany 参数列表"的模式下，会按**第一行参数字典里值不为 None 的 key** 动态推导 INSERT 的列集合——某一分块（`CHUNK=100`）的第一行如果某个可空字段恰好是 `None`（比如 `channel_name`/`product_name`/`spec`/`province`/`city`/`district`/`customer_alias` 这些财务数据里经常缺失的字段），这一列就会被整批从 INSERT 列表里静默剔除。

但 `on_duplicate_key_update()` 里 `stmt.inserted.channel_name` 等引用的是固定列集合（写代码时约定好的，不随行内容变化）。MySQL 8.0.19+ 的 `INSERT ... AS new ON DUPLICATE KEY UPDATE col = new.col` 语法里，`new.col` 只能引用实际出现在 INSERT 列表里的列——列被动态剔除后，`new.channel_name` 就变成不存在的列，MySQL 直接报错。

**实际影响面**：这不是某条脏数据触发的边界情况，而是"每 100 行分一批，只要某批次第一行任意一个可空字段是 None 就整批炸"——对真实财务数据（很多字段本来就经常为空）几乎是必然会撞上的概率问题，且哪一批会炸取决于文件里数据的具体排列顺序，复现具有随机性、不好用固定测试用例覆盖，这也是为什么之前 104 项测试全过但生产环境导入真实数据立刻暴露。

`test_finance_customer_mapping.py` 里 `test_bulk_writes_use_mysql_upsert_and_preserve_existing_alias_on_missing_value` 这个测试用 `monkeypatch` mock 掉了 `db.session.execute`，只断言编译出的 SQL 字符串包含 `ON DUPLICATE KEY UPDATE` / `customer_alias = coalesce(`，没有真正对着 MySQL 执行过 UPSERT，所以没能捕捉到这个运行时行为。

### 修复

两个函数都改成显式 `.values({col: bindparam(col) for col in _COLUMNS})`，`_COLUMNS` 是固定的列名元组，INSERT 列集合不再依赖任何一行的实际内容。已在生产库开事务验证（故意构造首行多列为 None 的场景）不再报错，随后 rollback（未写入任何数据），reload 后确认无崩溃。

### 需要 Codex 核实的事项

1. 这个"executemany + 无 values() 时按首行非 None 值推导列表"是 SQLAlchemy 2.0 的既有行为（不是这次改动引入的新 bug 触发条件），但只有从 `INSERT IGNORE` 换成真正读 `stmt.inserted.xxx` 的 `ON DUPLICATE KEY UPDATE` 之后才会暴露成生产报错（`INSERT IGNORE` 版本没有 `on_duplicate_key_update` 子句，不存在"引用了未出现的列"这个问题）。麻烦确认一下这个诊断是否准确。
2. 建议以后凡是 `mysql_insert(...).on_duplicate_key_update(...)` 这种模式，都固定用显式 `.values()`／`bindparam` 写法，不要依赖 SQLAlchemy 从 executemany 参数自动推导列集合——这类 bug 具有"看测试全过、上真实数据才炸、且不稳定复现"的特征，比较危险，值得写进项目规范或代码审查清单。
3. 测试补充建议：`test_finance_customer_mapping.py` 里针对 UPSERT 的测试目前只 mock 了 `execute` 断言编译后的 SQL 文本，建议补一个不 mock、真正对 MySQL（哪怕是临时表）执行一次 UPSERT 的用例，并且构造"分块首行某可空列为 None"这个具体场景，避免同类问题以后再从生产环境才发现。

