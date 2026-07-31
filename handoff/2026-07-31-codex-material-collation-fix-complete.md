# 物料库 JOIN 键排序规则收口，交接 Claude

日期：2026-07-31  
状态：代码完成、本地验证通过、**未部署**

## 修复

- 保留已 stamp 的 `20260731_01` 原样不动。
- 新增 Alembic `20260731_02`：
  - MySQL：将 `product_material.code` 改为 `utf8mb4_0900_ai_ci`
  - MySQL：将 `erp_group_category.group_code` 改为 `utf8mb4_0900_ai_ci`
  - SQLite 等非 MySQL 环境为空操作
- 模型层使用 SQLAlchemy dialect variant：
  - MySQL DDL 显式生成 `COLLATE utf8mb4_0900_ai_ci`
  - SQLite 仍使用普通 String，不引入不存在的 MySQL collation
- 没有修改 `import_product_raw` 或其他历史业务表。

## 为什么两个键都处理

`product_material.code` 当前已经参与 LEFT JOIN，是本次生产 500 的直接原因。
`erp_group_category.group_code` 当前主要在 Python 映射中消费，但它与
`import_product_raw.group_code` 是同一业务键；现在空表阶段一并对齐，避免后续 SQL JOIN
再次踩中同一排序规则裂缝。

## 验证

- Alembic 单 head：`20260731_02`
- 全量 pytest 通过（既有环境项除外）
- 新增 MySQL DDL 编译断言，确认两个键都带 `utf8mb4_0900_ai_ci`
- SQLite baseline upgrade 继续通过，证明新 revision 在 SQLite 不执行 MySQL ALTER
- `compileall` / `git diff --check` 通过

## 部署

生产已经由 Claude 手工执行了等价 ALTER，因此本 revision 在生产执行应为幂等式结构确认
（MySQL 仍可能短暂取得 metadata lock）。建议：

1. 先查 `information_schema.columns`，确认两列当前均为 `utf8mb4_0900_ai_ci`。
2. 低使用时段执行 `alembic upgrade head` 到 `20260731_02`。
3. 再查列排序规则与 `alembic current`。
4. reload 后验证 `/health`、`/ready`、`GET /api/material/items`。

本次只有模型和迁移变化，不改变 API 契约。
