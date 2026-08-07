# 物料库 · 售后物料组合后端完成

日期：2026-08-07  
对象：Claude Code

## 已完成

### 数据库

- 新增 `material_combo` 与 `material_combo_item` 模型。
- 新增 Alembic revision `20260807_01`，迁移链保持单头。
- `material_combo_item.material_code` 在模型与迁移中均显式声明
  `utf8mb4_0900_ai_ci`，与 `import_product_raw.code` 对齐。
- 明细通过 `combo_id` 外键 `ON DELETE CASCADE`；`material_code` 不设 ERP 外键。
- 唯一约束：组合名称唯一、同一组合内物料编码唯一。
- `migrations/env.py` 已显式导入新模型，避免 autogenerate 漏表。

### 后端接口

新增以下接口，沿用 material 蓝图的 `product:view` / `product:edit` 门禁：

- `GET /api/material/combos`
- `GET /api/material/combos/categories`
- `GET /api/material/combos/<id>`
- `POST /api/material/combos`
- `PUT /api/material/combos/<id>`
- `DELETE /api/material/combos/<id>`

实现内容：

- 列表支持 `keyword/category/is_disabled`，返回 `{items,total}`。
- 列表固定三次查询：组合、全部明细、ERP/人工展示字段；无循环查询。
- POST/PUT 严格校验名称、布尔值、整数、正整数数量和重复编码。
- PUT 对明细整体替换，保存与替换在同一事务内提交。
- UNIQUE 约束兜底并捕获 `IntegrityError`；组合重名返回“组合名称已存在”。
- ERP 物料不存在时保留明细，返回 `is_missing:true` 和空展示字段。
- 删除组合依赖数据库级 CASCADE 删除明细。
- `created_by` 记录创建人的用户名。

### 文档

- 已更新 `.claude/modules/api.md`。
- 已更新 `.claude/modules/database.md`。

## 自动化验证

- 新增 `backend/tests/test_material_combos.py`，覆盖：
  - MySQL DDL 中 `material_code` 的 0900 排序规则；
  - 创建、读取、整体替换、删除；
  - 缺失 ERP 物料保留与 `is_missing`；
  - 非法数量、重复编码、组合重名；
  - 列表固定三条 SELECT；
  - 真实 Cookie JWT + CSRF 下 viewer/editor 权限隔离。
- Alembic 基线门禁已更新到新 head，并验证 SQLite 从 baseline 升级会创建两张新表。
- `pytest -q`：300 项通过，2 项跳过。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。
- `alembic heads`：`20260807_01 (head)`。

## 未执行

- 未部署、未连接或修改生产数据库。
- 本地 SQLite 无法验证 MySQL collation 的真实 JOIN 行为；只完成了编译后 DDL 断言。

## Claude 部署门禁

1. 部署前备份数据库。
2. 执行 `alembic upgrade head`，确认 current 为 `20260807_01`。
3. 用 `SHOW FULL COLUMNS` 确认 `material_combo_item.material_code` 为
   `utf8mb4_0900_ai_ci`。
4. 在真实 MySQL 上创建含正常 ERP 编码和不存在编码的测试组合，调用列表/详情，确认 JOIN
   不报 collation 错误且不存在编码返回 `is_missing:true`。
5. 验证重名、非法数量、重复编码、整体替换和 DELETE CASCADE。
6. 用 viewer/editor 两档真实账号验证 GET/写接口权限。
7. 清理测试组合后再 reload，按既有纪律复核 `/health`、`/ready` 和 journal。
