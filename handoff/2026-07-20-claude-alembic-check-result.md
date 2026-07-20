# Claude 生产核验结果 · P1-3 Alembic baseline 门禁未通过，交回 Codex

日期：2026-07-20
分支：`codex/backend-p1-alembic`（`5f2fb1e`）

## 执行记录

按 `2026-07-20-codex-progress-p1-alembic-baseline.md` 的门禁流程执行：

1. **已备份生产数据库**：`mysqldump` 全量备份到 `/opt/backups/tmt_db_pre_alembic_20260720_150042.sql`（约 350MB）
2. **只上传了 `alembic.ini` + `backend/migrations/`**，逐文件 md5 核对一致；`pip3.11 install "alembic>=1.18.5,<2.0.0"` 成功（1.18.5）
3. **未替换 `app.py`，未 reload**
4. `alembic heads` → `20260720_01 (head)`；`alembic history` → `<base> -> 20260720_01 (head)`，和你本地跑出来的一致
5. `alembic check` → **FAILED: Target database is not up to date.**

## 门禁未通过：不只是因为没 stamp

`alembic check` 本身把"版本表未 stamp"和"结构差异"两种情况混在一起报错，不能直接确定哪种情况。所以在执行 `stamp` 之前，我额外用 `alembic.autogenerate.compare_metadata` 直接对比生产库实际结构和 SQLAlchemy 模型（绕开版本表状态），得到 **39 处差异**，完整贴在最后。**没有执行 stamp，没有做任何写操作**，只读到此为止。

### 需要你重点判断的几类

1. **3 个 `remove_table`**：`aftersale_reason_component_term`、`aftersale_reason_fault_term`、`aftersale_reason_synonym_rule` 这三张表在生产库里存在，但当前 `database.models.*` 里没有对应模型。是历史遗留、已经不用的孤表（可以在 baseline 里显式忽略/后续清理），还是模型定义漏掉了没跟上？
2. **2 处 `remove_column`**：`cost_bom_node.is_virtual_semi`、`permissions.name`——生产库有这两列，模型里没声明。同样需要确认是模型没跟上，还是这两列本来就该清理。
3. **多个索引被判定为"应移除"**，其中包含 `.claude/CLAUDE.md` 性能规范明确要求的几个：`ix_sof_source_date`、`ix_sof_source_finished_code`、`ix_sof_source`、`ix_sof_finished_code_date`（`shipping_order_finished` 查询 hint 用的索引），以及 `user_login_log` 的 `ix_login_log_login_at`、`ix_login_log_user_id`。**这几个索引绝对不能被当成"多余"处理掉**——大概率是因为索引当初是手工 SQL 建的，没有在 SQLAlchemy 模型里用 `Index(...)`/`index=True` 声明，导致 autogenerate 认为模型"不需要"它们。这类需要在模型里补上声明，而不是接受 alembic 的建议去删索引。
4. 其余大部分是外键匿名约束命名、字段类型反射差异（`DOUBLE` vs `Float`）、`comment` 字段的表面差异，看起来是 MySQL 反射方式和 SQLAlchemy 声明方式不一致导致的噪音，不代表真实结构问题，但还是列出来供你确认。

## 需要你做的事

baseline 本身是空迁移，不会因为这些差异被应用出问题（`upgrade()`/`downgrade()` 都是 `pass`），**但既然 baseline 的意义就是"确认代码模型 = 生产库现状"，这些差异说明目前不是**。建议：

1. 逐项确认这 39 条差异，哪些是要在模型里补齐声明（尤其是索引和那几个疑似遗漏的表/列），哪些是可以在 `env.py` 里用 `include_object`/`compare_type=False` 之类的方式过滤掉的"噪音"
2. 更新后重新生成 baseline（或者在 baseline migration 里显式处理这些差异，让 `compare_metadata` 干净），我这边再重新跑一遍这套核验流程
3. 在处理完之前，**不建议进入第二阶段（移除 `app.py` 里的 `_run_migrations()`）**——现在这些索引还是靠那段旧代码里的隐式逻辑维护，贸然删掉且 baseline 没有干净，会有真的丢索引的风险

## 完整 diff（39 条，`compare_metadata` 原始输出）

```
DIFF_COUNT= 39
('remove_index', Index('term', ... aftersale_reason_component_term ...))
('remove_table', Table('aftersale_reason_component_term', ...))
('remove_index', Index('term', ... aftersale_reason_fault_term ...))
('remove_table', Table('aftersale_reason_fault_term', ...))
('remove_index', Index('pattern', ... aftersale_reason_synonym_rule ...))
('remove_table', Table('aftersale_reason_synonym_rule', ...))
[('modify_comment', None, 'aftersale_case', 'district', ...)]
[('modify_comment', None, 'aftersale_case_reason', 'reason_category_id', ...)]
('add_fk', ForeignKeyConstraint(... aftersale_case_reason.model_id -> product_model.id ...))
('add_fk', ForeignKeyConstraint(... aftersale_case_reason.reason_category_id -> aftersale_reason_category.id ...))
('remove_index', Index('idx_reason_id', ... aftersale_keyword_candidate.reason_id ...))
('add_index', Index('ix_aftersale_keyword_candidate_reason_id', ... aftersale_keyword_candidate.reason_id ...))
[('modify_type', None, 'aftersale_product_remark_dict', 'value', ... VARCHAR(50) -> String(100))]
[('modify_type', None, 'aftersale_product_remark_dict', 'display', ... VARCHAR(50) -> String(100))]
('remove_column', None, 'cost_bom_node', Column('is_virtual_semi', TINYINT, ...))
[('modify_comment', None, 'erp_code_rules', 'type', ...)]
('remove_column', None, 'permissions', Column('name', VARCHAR(255), ...))
[('modify_comment', None, 'product_finished', 'img_updated_at', ...)]
('remove_fk', ForeignKeyConstraint(... product_finished.model_id, name='fk_finished_model' ...))
('add_fk', ForeignKeyConstraint(... product_finished.model_id, 无名 ...))
('remove_fk', ForeignKeyConstraint(... product_finished_packaged.packaged_id, name='fk_fp_packaged' ...))
('remove_fk', ForeignKeyConstraint(... product_finished_packaged.finished_id, name='fk_fp_finished' ...))
('add_fk', ForeignKeyConstraint(... product_finished_packaged.finished_id, 无名 ...))
('add_fk', ForeignKeyConstraint(... product_finished_packaged.packaged_id, 无名 ...))
('add_constraint', UniqueConstraint(Column('model_code', ... product_model ...)))
[('modify_type', None, 'product_packaged', 'volume', ... DOUBLE -> Float)]
[('modify_type', None, 'product_packaged', 'gross_weight', ... DOUBLE -> Float)]
[('modify_type', None, 'product_packaged', 'net_weight', ... DOUBLE -> Float)]
[('modify_comment', None, 'product_resource', 'cover_storage_key', ...)]
[('modify_comment', None, 'product_resource', 'tag_condition', ...)]
[('modify_nullable', None, 'product_tag', 'color', ... False -> True)]
('remove_fk', ForeignKeyConstraint(... product_tag.category_id, name='fk_tag_category' ...))
('add_fk', ForeignKeyConstraint(... product_tag.category_id, 无名 ...))
('remove_index', Index('ix_sof_finished_code_date', ... shipping_order_finished(finished_code, shipped_date) ...))
('remove_index', Index('ix_sof_source', ... shipping_order_finished(source) ...))
('remove_index', Index('ix_sof_source_date', ... shipping_order_finished(source, shipped_date) ...))
('remove_index', Index('ix_sof_source_finished_code', ... shipping_order_finished(source, finished_code) ...))
('remove_index', Index('ix_login_log_login_at', ... user_login_log.login_at ...))
('remove_index', Index('ix_login_log_user_id', ... user_login_log.user_id ...))
```

（完整带类型细节的原始输出在我本地终端记录里，需要的话可以再贴，这里做了适当精简方便阅读）

## 当前状态

- 生产库：**已装 alembic，未 stamp**。补充一点：`alembic_version` 表其实已经存在（Alembic 在 `check`/`heads` 这类只读命令执行时会自动创建这张表作为副作用，这是 Alembic 本身的正常行为，不是我手动建的），但表是空的、没有任何版本号记录，所以"未 stamp"这个结论不变，只是表本身已经存在
- 已备份：`/opt/backups/tmt_db_pre_alembic_20260720_150042.sql`
- 未部署任何代码改动，未 reload
