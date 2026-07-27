# 发货规则变更的影响范围 stale 标记（后端实现交接）

## 已完成

- 维持现有 URL，不迁移成品-组件或通用件接口。
- 成品-产成品关联、通用件新增/删除、销退仓库过滤保存现在都会：
  1. 获取与导入/重算共用的 `shipping_data_mutation` 数据库租约；
  2. 修改规则；
  3. 仅标记受影响、且已存在的 `(source, ecommerce_order_no)` 为 `is_stale=True`；
  4. 在同一个数据库事务内提交规则与 stale 标记。
- 冲突时统一返回 HTTP 409 和当前 `task_id`，不再出现规则变更与导入/重算并发交错。
- 成功响应新增 `stale_pairs`、`stale_limit`、`requires_full_resolve`。超过上限时配置仍保存、订单保持 stale，绝不部分执行 `resolve_stale`；前端应据此引导完整重建。
- 影响范围包含发货原始记录、销退记录，以及当前已解析成品编码；通用件扩展严格按现有解析器的“一跳直接等效”语义，不引入传递闭包。
- Alembic `20260727_01` 新增三个查询索引：
  - `return_record(warehouse_name, ecommerce_order_no)`；
  - live 与 next 代际表各自的 `shipping_order_finished(source, ecommerce_order_no)`。
  两代际表索引保持一致，满足 rename-table cutover 契约。

## 验证

- `pytest backend/tests -q`：全绿。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。
- 新增 repository 级测试覆盖：组件变更命中发货与销退来源、未生成派生行不计入 scope、仓库变更按既有 source/order 对标记。
- `alembic check` 已尝试，但本机配置指向未运行的 `127.0.0.1:3306` MySQL，连接被拒绝；未对任何数据库执行写操作。部署前请在服务器隔离校验目录按既有流程执行 `alembic upgrade head` / `alembic check`。

## 需要 Claude Code 审查/后续处理

- 审查此后端提交并执行部署（含数据库备份、`alembic upgrade head`、reload 与日志复核）。
- 前端可在 `requires_full_resolve=true` 时显示“影响范围接近全量，建议完整重建”的引导；不应阻止已成功保存的规则。
- 此批没有改变 `resolve_stale` 的 10,000 上限，仍由既有上限防护执行实际重算。
