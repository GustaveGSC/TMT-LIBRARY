# Codex · Alembic baseline 生产差异收敛

日期：2026-07-20  
分支：`codex/backend-p1-alembic`

## 结论

根据 `2026-07-20-claude-alembic-check-result.md` 的 39 条差异逐项处理。baseline revision 仍为空迁移，`app.py` 启动 DDL 仍未移除；本批不允许直接 stamp，必须先在生产只读复核 `compare_metadata` 为 0。

## 已处理

- 将 `shipping_order_finished` 的 4 个 hint 索引和 `user_login_log` 的 2 个索引补入 ORM 元数据，并增加自动化门禁。
- 恢复 `permissions.name` 模型字段、仓储写入与响应输出。历史显示该支持在 `7736296` 被移除，但路由和生产列仍保留，属于清理回归。
- 对齐 `idx_reason_id`、售后留言词典字段长度、MySQL `DOUBLE`、`product_tag.color` 非空状态及现有外键名称。
- 移除 ORM 中生产库不存在的 `product_model.model_code` 单列唯一约束声明。业务层仍检查唯一；加数据库约束前必须先审计历史重复值，并另建迁移。
- 3 张售后词典表的模型和读写逻辑在 `7736296` 已明确退役。生产表尚待归档，现按表名精确排除 Alembic 管理，禁止 autogenerate 删除。
- `cost_bom_node.is_virtual_semi` 无现行业务读写，按列名精确登记为生产遗留列，待归档后独立清理。
- `aftersale_case_reason.model_id/reason_category_id` 的 ORM 外键用于关系映射，但生产约束缺失；暂按列精确排除生成约束，后续需先审计孤儿数据。
- 关闭数据库 comment 比较；Python/数据库注释差异不参与结构门禁，字段类型、索引、约束比较仍保持开启。

## 自动化验证

```text
python -m pytest backend/tests -q
35 passed
python -m compileall -q backend/database backend/migrations
通过
git diff --check
通过
```

## Claude 生产复核门禁

1. 仅同步本提交涉及的模型、`backend/migrations/` 和测试文件；不要替换 `app.py`，不要 reload。
2. 复用上次的只读 `compare_metadata` 脚本，确认 `DIFF_COUNT=0`。脚本必须使用 `backend/migrations/env.py` 相同的 `include_object` 和 `compare_comments=False` 配置，否则会重新报告已登记的遗留对象。
3. 若仍有差异，完整保留原始 tuple 并停止；不要 stamp，不要手改生产结构。
4. 只有 `DIFF_COUNT=0` 后，才执行 `alembic stamp 20260720_01`，随后验证 `current` 和 `upgrade head` 空操作。
5. stamp 与空升级验证完成后仍先停止，把结果交回 Codex；移除 `app.py::_run_migrations()` 属于下一提交。

