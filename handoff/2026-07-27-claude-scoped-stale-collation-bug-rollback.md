# scoped stale 标记（d926dc3）生产真实测试发现全表 500，已回退

日期：2026-07-27

## 结论

代码审查、结构核验（索引在 live/next 两代际表保持一致）、SQLite 单元测试全部通过后，部署到生产做
真实 HTTP 端到端验证时，第一次真实调用 `POST /api/shipping/warehouses/filter`（仅仅是把仓库
过滤配置原样保存，没有做业务无意义的极端输入）就 500 失败。**三个规则变更入口（仓库过滤配置、
成品-组件关联、通用件对）在真实 MySQL 上现在全部无法保存**，属于会立即被用户撞见的功能级回归，
已回退。

## 根因：`return_record` 与 `shipping_order_finished` 排序规则不一致

```
sqlalchemy.exc.OperationalError: (1267, "Illegal mix of collations
(utf8mb4_0900_ai_ci,IMPLICIT) and (utf8mb4_unicode_ci,IMPLICIT) for operation '='")
[SQL: ... FROM shipping_order_finished INNER JOIN return_record
      ON return_record.ecommerce_order_no = shipping_order_finished.ecommerce_order_no
      WHERE return_record.warehouse_name IN (%(warehouse_name_1_1)s)]
```

生产实测排序规则：

| 列 | 排序规则 |
|---|---|
| `shipping_record.ecommerce_order_no` / `product_code` | `utf8mb4_unicode_ci` |
| `shipping_order_finished.ecommerce_order_no` | `utf8mb4_unicode_ci` |
| `shipping_order_finished.finished_code` | `utf8mb4_0900_ai_ci` |
| `return_record.ecommerce_order_no` / `product_code` / `warehouse_name` | `utf8mb4_0900_ai_ci` |

`return_record.*` 整张表都是 `utf8mb4_0900_ai_ci`，与 `shipping_order_finished.ecommerce_order_no`
的 `utf8mb4_unicode_ci` 不一致。这意味着：

- `mark_stale_for_warehouse_names()`：唯一的 JOIN 就是 `return_record` ↔
  `shipping_order_finished`，**100% 报错，无法工作**；
- `mark_stale_for_component_codes()`：内部用 `UNION` 拼接"正向 shipping_record 命中"和
  "销退 return_record 命中"两条子查询；只要 `component_codes` 非空就一定包含 return_record 分支，
  UNION 里任意一段报错就导致整条语句失败——**成品-组件关联、通用件对的保存也 100% 报错**。

这不是边界数据触发的偶发问题，是排序规则层面的系统性不匹配，任何真实调用都会命中。SQLite 测试
之所以没发现，是因为 SQLite 没有 MySQL 这种按列存储、按连接隐式比较的排序规则概念。

## 生产验证：回滚安全，无数据损坏

失败请求触发后立即核实：

- `return_warehouse_filter` 表里目标仓库的 `is_excluded` 值未变（事务未提交，SQLAlchemy 在
  `_run_rule_change` 的 `except` 分支里 `db.session.rollback()` 正确生效）；
- `shipping_order_finished.is_stale=1` 计数仍为 0；
- 对应的 `shipping_task(task_type='rule_change')` 记录正确落在 `status=error`，`lease_key=NULL`
  （released）。

"规则保存与 stale 标记必须同一事务"这个设计目标本身没有问题——事务原子性在这次真实失败里生效了，
只是查询语句本身在 MySQL 上编译不出结果。

## 已执行的回退

`git revert`-style 手工回退（非 `git revert` 命令，直接检出旧版本文件）以下 5 个运行时文件到
`d926dc3` 之前（`7114f9f`）：

- `backend/database/repository/shipping/__init__.py`
- `backend/routes/product/finished.py`
- `backend/routes/shipping/__init__.py`
- `backend/services/product/finished.py`
- `backend/services/shipping/__init__.py`

同时回退了 `.claude/modules/api.md`/`database.md` 里描述新行为的文档段落（避免文档和实际代码
不一致），删除了针对被回退功能的 `test_shipping_scoped_stale_marking.py`（测试的函数已不存在）。

**没有回退** `20260727_01` 迁移（新增的三个索引）：它们是纯增量 DDL，回退后的旧代码路径完全不
引用它们，留着无害，也不需要走一次 downgrade。

本地 pytest 全绿、compileall 通过后部署到生产：备份好的迁移前状态不需要用，直接同步这 5 个文件、
`systemctl reload`，`/health`/`/ready` 正常，用真实 HTTP 请求重新验证
`POST /api/shipping/warehouses/filter`（原样保存不做改动）现在返回 `200 {"data":{"updated":6}}`，
恢复正常。

## 交给 Codex 的修复方向

不是"加个开关规避"，需要真正解决排序规则不一致：

1. **优先**：在写查询的 JOIN/IN 条件上显式 `COLLATE utf8mb4_unicode_ci`（或统一到
   `utf8mb4_0900_ai_ci`，选哪个排序规则由 Codex 评估对现有索引和其他查询的影响），SQLAlchemy 层面
   可以在 join 条件里用 `func.convert(..., 'utf8mb4_unicode_ci')`或直接写 `text()` 片段；
2. 更根本的方案：评估是否应该在 Alembic 迁移里统一 `return_record` 整表（或至少
   `ecommerce_order_no`/`product_code`）的排序规则到 `utf8mb4_unicode_ci`，消除这个隐患对以后其他
   跨表 JOIN 查询的影响——现在只是这次撞上了，不代表以后不会有其他查询也踩到同样的坑；
3. 无论选哪种方案，都必须补一条**在真实 MySQL（不是 SQLite）上跑的测试**，直接执行
   `mark_stale_for_warehouse_names`/`mark_stale_for_component_codes` 对应的 JOIN 语句，验证不再报
   1267 错误——SQLite 测试无法覆盖这类问题，之前的测试覆盖率盲区已经在这次真实部署里暴露过一次，
   不能再依赖纯 SQLite 单测作为这类跨表查询的唯一门禁；
4. 顺带确认 `shipping_order_finished.finished_code` 的 `utf8mb4_0900_ai_ci` 排序规则是否也会在其他
   现有查询里造成类似隐患（比如 `finished_code` 参与的其他 JOIN）——这次只发现了
   `return_record` 这一处，不代表是唯一一处。

修复后重新走一次真实生产验证（不能只看 SQLite 测试通过就重新部署），我这边再次审查+部署。
