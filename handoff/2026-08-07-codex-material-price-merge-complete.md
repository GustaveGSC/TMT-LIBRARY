# 物料价格并入物料库 · 后端完成

日期：2026-08-07  
对象：Claude Code

## 实现结论

- 价格继续唯一存储在 `cost_material_price`，没有新增价格表或迁移。
- `cost_bom_node.notes` 保持独立“成本备注”，未与 `product_material.remark` 合并。
- `is_purchased_semi` 保持成本节点属性，不混入物料基础属性。
- 本批未实现价格排序；避免为 8,091 行物料破坏数据库分页或做全表内存排序。
- `GET /api/rd/cost/nodes` 及供应商旧接口本批均保留，未扩大下线范围。

## 字段级权限

- `GET /api/material/items`：只有 `rd:view` 用户的每行响应才出现
  `latest_price/latest_price_source`；无权限时字段整体不存在。
- `GET /api/material/items/<code>`：只有 `rd:view` 用户才额外获得
  `has_cost_node/cost_node_id/latest_price/latest_price_source/cost_notes/`
  `is_purchased_semi/cost_node_type`。
- 新价格接口使用独立 `material_cost_bp`：基础要求 `product:view`，读操作再要求
  `rd:view`，写操作再要求 `rd:edit`，不依赖 `product:edit`。
- `price_state=has|none` 仅 `rd:view` 可用；无权限调用返回 403。

## 新接口

- `GET /api/material/items/<code>/prices`
- `POST /api/material/items/<code>/prices`
- `GET /api/material/items/<code>/usages`
- `PATCH /api/material/prices/<price_id>`（本期只修改 `supplier_name`）
- `DELETE /api/material/prices/<price_id>`

价格列表复用原成本接口语义并附 `order_no`；手工新增价格固定写入 `source=manual`。

## 节点与匹配

- 查询优先按 `code_with_version` 精确定位，找不到时按复用的
  `services.rd.cost_import._strip_version()` 结果查基础 `code`。
- 首次加价时才惰性创建节点；卡片打开不会创建成本数据。
- 节点字段来自物料库；`node_type` 优先级为 semi → finished/packaged → material。
- `-A01/-B01` 去版本后撞同一基础码时复用既有节点，测试确认只生成一个 node、两条价格。
- 列表最新价用当页 code/base code 一条批量查询；具备 `rd:view` 时相对原列表只增加一条 SELECT。
- `price_state` 使用数据库相关 EXISTS；MySQL 分支对
  `cost_bom_node.code_with_version` 显式应用 `utf8mb4_0900_ai_ci`，不做全表 Python 分页。

## 自动化验证

- 新增 `backend/tests/test_material_prices.py`，覆盖：
  - 节点惰性创建及版本撞码复用；
  - node_type 推断；
  - 列表新增查询数恰好为 1；
  - 无 `rd:view` 时列表/详情成本字段完全不存在；
  - 只有 `product:view + rd:edit`（无 product:edit）仍可新增价格；
  - 价格列表、供应商修改、删除、空使用记录；
  - `price_state=has|none`；
  - 非法价格不创建节点。
- 物料域定向测试：34 项通过。
- 全量 `pytest -q`：304 项通过，2 项跳过。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。
- `alembic heads`：`20260807_01 (head)`，本批无迁移。

## 文档

- 已更新 `.claude/modules/api.md`。
- 已更新 `.claude/modules/database.md`。

## 未执行及部署门禁

- 未部署、未连接生产数据库。
- SQLite 无法覆盖 MySQL collation，Claude 部署后必须用真实 MySQL 逐条验证：
  1. 列表、详情、prices、usages 均无 1267；
  2. 现有 130 个节点按 `code_with_version` 对账原成本接口；
  3. 无节点物料首次加价的字段及 node_type；
  4. 两个版本复用同一基础节点；
  5. viewer/rd viewer/rd editor 三档权限；
  6. 物料列表查询数增量不超过 1；
  7. BOM 快照、成本树和成本预估回归。
