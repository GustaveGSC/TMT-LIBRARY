# 研发物料门禁后端交接（Codex → Claude）

## 已完成

- 新增 `material_gate` 模型、repository、service 与 Alembic revision `20260925_01`。
- 迁移创建物料门禁表并删除旧 `ecr_reminder`；旧自由文本提醒按已确认方案不迁移。downgrade 只恢复旧表结构，不恢复旧数据。
- 删除旧 reminders 路由/service/repository，新增以下接口：
  - `GET /api/rd/material-gates`
  - `GET /api/rd/material-gates/all`
  - `POST /api/rd/material-gates`
  - `PUT /api/rd/material-gates/<id>`
  - `PUT /api/rd/material-gates/<id>/activate|deactivate`
  - `POST /api/rd/material-gates/check`
  - `POST /api/rd/material-gates/check-file`
- 管理接口严格要求 `rd:admin`；两个校验 POST 沿用 RD blueprint 的 `rd:edit`，未自行放宽。
- 同一物料编码只允许一条在架门禁；新增、编辑在架记录、重新上架均执行重复校验。
- `check` 对输入编码去空、去重，只返回在架命中，响应严格分为 `warn` / `block`。
- `check-file` 仅接收 `.xlsx`，复用上传安全校验，优先识别“物料编码”列，其次“品号”列。
- `compare_bom()` 仅增加纯数据字段 `after_codes`，未引入 DB/Flask 依赖。
- `pdm2bom_process()` 增加去重排序后的 `material_codes`。
- 更新 `rd:admin` 种子描述以及 API/数据库文档。

## 验证

- 门禁、路由、迁移、RD Excel、上传安全相关测试：`48 passed`。
- `python -m alembic heads`：`20260925_01 (head)`。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过（仅既有 CRLF 提示）。
- 全量后端测试：除 4 个与本批无关的旧权限预期外均通过；失败都仍用 `product:view` 访问已经切换为 `material:view/material:price` 的物料接口：
  - `test_material_combos.py::test_combo_routes_enforce_view_and_edit_permissions`
  - `test_material_library.py::test_material_route_rejects_invalid_sort_field`
  - `test_material_library.py::test_material_route_returns_expression_error_as_400`
  - `test_material_prices.py::test_price_routes_enforce_rd_permissions_without_requiring_product_edit`

## 部署与联调提醒

1. 本批未部署。请先备份数据库，再执行 `alembic upgrade head`，随后按项目纪律 reload。
2. 迁移会永久删除旧 `ecr_reminder` 数据；这是需求明确的替换行为，部署前仍建议只读确认旧表行数并记录。
3. 后端应先部署并确认接口响应，再部署已完成的前端，避免门禁页面短暂永久 fail-open。
4. 联调重点核对：`after_codes`、`material_codes`、`check/check-file` 四处字段形状，以及 block 命中后按钮禁用。
5. 工作区存在本批开始前的其他未提交改动；本批没有触碰 `src/`，提交时对重叠文档/代码采用了选择性暂存。
