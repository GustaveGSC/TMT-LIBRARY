# Codex 交接：物料供应商主数据后端完成

## 完成内容

- 新增 `material_supplier` 供应商主数据表，支持联系方式、备注和创建人。
- `cost_material_price` 新增可空 `supplier_id`，外键删除策略为 `ON DELETE SET NULL`，原 `supplier_name` 保留为历史快照。
- Alembic revision `20260810_01`：创建主表、从旧价格的非空供应商名称去重回填主数据及 `supplier_id`，并支持完整 downgrade。
- 新增供应商列表、选项、关联物料、新增、编辑、删除 API，分别使用 `rd:view` / `rd:edit` 权限。
- 供应商列表用聚合查询返回价格数、物料数和分组摘要；跨 `cost_bom_node.code_with_version` / `import_product_raw.code` JOIN 显式指定 `utf8mb4_0900_ai_ci`。
- 通过聚合总数检测 `GROUP_CONCAT` 截断，响应提供 `groups_truncated`，不将静默截断当作完整数据。
- 价格新增/修改支持 `supplier_id` 或自由文本 `supplier_name`；ID 优先，新名称自动登记，空值清除关联。
- 供应商改名会同步历史价格的 `supplier_name` 快照。
- 有价格引用时普通删除返回冲突和 `price_count`；`force=true` 才删除主数据，价格记录保留且 `supplier_id` 置空。
- 已更新 `.claude/modules/api.md` 和 `database.md`。

## 验证

- `python -m pytest backend/tests -q`：全量通过（2 项环境性 skip）。
- 新增 Alembic 真实 upgrade/downgrade 测试：重复旧供应商只生成一条主数据，历史价格回填同一 ID，空值不变，回退干净。
- `python -m compileall -q backend`：通过。
- `python -m alembic heads`：`20260810_01 (head)`。
- `git diff --check`：通过。

## 部署与生产门禁

- Codex **未部署**，请 Claude Code 按项目纪律执行。
- 部署前备份数据库，执行 `alembic upgrade head`，再 reload gunicorn。
- 生产 MySQL 必验：
  1. 现有“优固”价格回填到唯一供应商主数据；
  2. 供应商列表聚合不出现 collation 1267；
  3. 自由文本新建供应商后，价格同时有 `supplier_id` 和名称快照；
  4. 被引用供应商普通删除被拦截，force 删除后价格仍在且 ID 置空；
  5. 无 `rd:view` / `rd:edit` 用户分别无法读/写供应商数据。

## 前端联调

- Claude Code 可开始新增“供应商” tab，仅对研发权限可见。
- 价格卡片的供应商输入可改成可搜索、可自由创建的下拉；提交时优先传 `supplier_id`，新文本传 `supplier_name`。
- 本批未实施 `-S1/-C1` 编码归一化，该规则尚未获业务确认。
