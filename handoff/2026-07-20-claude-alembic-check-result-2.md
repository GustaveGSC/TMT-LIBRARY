# Claude 生产核验结果（第二轮）· 39→12，未达 DIFF_COUNT=0，交回 Codex

日期：2026-07-20
分支：`codex/backend-p1-alembic`（`bf582e4`）

## 核验方式（这次做了调整，避免污染生产运行目录）

上一轮直接往 `/opt/tmt-library/backend/` 传文件做核验，这次改成更安全的方式：把改动过的 `backend/`（模型文件 + `migrations/`）打包传到隔离目录 `/opt/alembic_verify/`，指向生产库只读比对，跑完立刻删除临时目录，**全程没有碰 `/opt/tmt-library/backend/` 里正在跑的文件**，避免万一 gunicorn 意外重启（`Restart=on-failure`）加载到检查用的中间状态。

比对用 `EnvironmentContext` + `compare_metadata`，手动复刻了 `env.py` 里的 `include_object`（排除 3 张遗留表和 `cost_bom_node.is_virtual_semi`，排除 2 个"暂缓创建"的外键），并设置 `compare_comments=False`。

## 结果：39 → 12，进度明显，但没到 0

```
DIFF_COUNT= 12
```

### 6 处是 comment 差异（本该被 compare_comments=False 过滤掉，但没有生效）

`aftersale_case.district`、`aftersale_case_reason.reason_category_id`、`erp_code_rules.type`、`product_finished.img_updated_at`、`product_resource.cover_storage_key`、`product_resource.tag_condition` 六个字段的 `modify_comment`。

我验证过 `compare_comments=False` 确实被正确传进了 `MigrationContext.opts`（打印确认过），但这几条 comment 差异依然出现在 `compare_metadata()` 结果里。这看起来像是 alembic 1.18.5 在这个场景下的行为和预期不符（或者这几个字段的 comment 差异走的是别的比较路径，不受这个 flag 控制），需要你确认一下是版本问题还是配置方式问题。这 6 条本身是纯 cosmetic（不影响实际数据/查询），不算阻塞性问题，但既然目标是 DIFF_COUNT=0，还是需要有个明确结论（哪怕结论是"这版本就是不支持完全关掉，先接受这 6 条留在 diff 里，baseline 的空迁移不会因此有任何风险"）。

### 6 处是外键差异，且不只是命名问题——这个需要重点看

这 6 条是 3 组 `remove_fk`/`add_fk` 配对，对应你在 `bf582e4` 里改过命名的三个外键：`fk_finished_model`、`fk_fp_finished`、`fk_fp_packaged`。我核对了具体内容，**问题不是命名没对齐**（命名其实已经对上了），而是：

- 生产库里这三个外键都带 `ondelete='SET NULL'`（`fk_finished_model`）或 `ondelete='CASCADE'`（`fk_fp_finished`、`fk_fp_packaged`）
- 但 `bf582e4` 里给这几个 `db.ForeignKey(...)` 加 `name=` 参数的时候，**没有一并把 `ondelete=` 也加上**，所以模型里现在这几个外键定义是"无 ondelete 行为"

对比你在 `finished.py` 里的改动：

```python
# 改之前
model_id = db.Column(db.Integer, db.ForeignKey('product_model.id'), nullable=True)
# 改之后（只加了 name，没加 ondelete）
model_id = db.Column(db.Integer, db.ForeignKey('product_model.id', name='fk_finished_model'), nullable=True)
```

生产库实际这个外键是 `ondelete='SET NULL'`（我之前那份 39 条差异原始输出里能看到），`product_finished_packaged` 的两个外键同理是 `ondelete='CASCADE'`。**这不是无关紧要的表面差异**——如果以后有人真的照着这份模型定义生成新迁移并执行，会把这三个外键的删除级联行为直接改掉（从"父记录删除时自动处理子记录"变成"报外键约束错误"或者别的默认行为），这是会影响实际业务逻辑的改动，不应该被静默接受。

麻烦在这三处补上原有的 `ondelete`：

```python
model_id = db.Column(db.Integer, db.ForeignKey('product_model.id', name='fk_finished_model', ondelete='SET NULL'), nullable=True)
```

`product_finished_packaged` 的 `finished_id`/`packaged_id` 同理补 `ondelete='CASCADE'`。

## 结论

baseline 迁移本身还是空的，这次核验不管 diff 多少条都不会被应用出问题——但既然咱们的目标是"模型 = 生产库现状"的干净 baseline，这 12 条里至少 6 条外键差异是实质性的，不能直接忽略。建议改完这 3 个外键的 `ondelete` 后我再核一轮；那 6 条 comment 差异请你评估要不要继续深究版本问题，如果确认是 alembic 行为限制、且不影响实际结构，可以在报告里注明清楚，下次由你决定是否可以接受在 DIFF_COUNT>0（仅剩 comment 这类）的情况下推进 stamp。

## 当前状态

- 生产库：**仍未 stamp**（这次核验用的是隔离临时目录，没有碰 `/opt/tmt-library/backend/`，也没有再次触发 alembic_version 建表之类的副作用）
- 已备份：上一轮的 `/opt/backups/tmt_db_pre_alembic_20260720_150042.sql` 仍然有效
- 临时核验目录 `/opt/alembic_verify/` 已清理
- 未部署任何代码改动，未 reload
