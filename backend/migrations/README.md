# Alembic 迁移

`20260720_01` 是生产数据库当前结构的空 baseline，不创建、修改或删除业务表。

## 首次接管生产库

先备份数据库，并确保使用的是生产 `.env`。不要直接生成或执行新的 autogenerate migration。

```bash
python -m alembic -c alembic.ini heads
python -m alembic -c alembic.ini history
python -m alembic -c alembic.ini check
python -m alembic -c alembic.ini stamp 20260720_01
python -m alembic -c alembic.ini current
python -m alembic -c alembic.ini upgrade head
```

要求：

- `check` 若报告模型与生产结构存在差异，停止，不要 stamp，先审查差异。
- `env.py` 中的遗留对象清单只用于已确认的生产债务；增加条目前必须写明来源，禁止用宽泛过滤掩盖新差异。
- 当前 3 张退役售后词典表和 `cost_bom_node.is_virtual_semi` 暂不受 Alembic 管理，数据归档后再用独立迁移清理。
- `aftersale_case_reason` 的两个 ORM 外键只用于关系映射，生产约束需在历史脏数据审计后单独补建。
- `stamp` 只写入 `alembic_version`，baseline 本身不得执行业务 DDL。
- `current` 必须显示 `20260720_01 (head)`。
- stamp 后再次执行 `upgrade head` 必须为空操作。

在生产确认以上结果以前，`backend/app.py` 的旧启动迁移保持不变。确认后进入第二阶段：移除 `_run_migrations()`，应用启动只校验数据库 revision，不自动 upgrade。

## 后续变更

```bash
python -m alembic -c alembic.ini revision --autogenerate -m "描述"
python -m alembic -c alembic.ini upgrade head
```

所有自动生成迁移必须人工审查 upgrade/downgrade，部署前先备份并单独执行迁移，再 reload 应用。
