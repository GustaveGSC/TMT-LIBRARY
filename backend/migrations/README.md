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
