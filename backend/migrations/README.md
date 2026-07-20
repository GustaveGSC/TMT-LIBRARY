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
- Alembic 1.18 的注释比较由 `alembic.autogenerate.comments` 插件提供；项目通过 `autogenerate_plugins` 精确排除该插件，不使用无效的 `compare_comments=False`。
- `stamp` 只写入 `alembic_version`，baseline 本身不得执行业务 DDL。
- `current` 必须显示 `20260720_01 (head)`。
- stamp 后再次执行 `upgrade head` 必须为空操作。

应用启动只读校验数据库 revision，必须与迁移脚本的唯一 head 完全一致；不再自动建表、补列、写种子数据或执行 upgrade。可用 `ALEMBIC_CONFIG` 覆盖 `alembic.ini` 路径。

## 后续变更

```bash
python -m alembic -c alembic.ini revision --autogenerate -m "描述"
python -m alembic -c alembic.ini upgrade head
```

所有自动生成迁移必须人工审查 upgrade/downgrade，部署前先备份并单独执行迁移，再 reload 应用。

生产部署固定顺序：

1. 备份数据库。
2. 先部署迁移脚本，不替换应用代码。
3. 执行 `python -m alembic -c alembic.ini upgrade head`。
4. 执行 `python -m alembic -c alembic.ini current`，确认显示唯一 head。
5. 部署对应的后端代码，再执行 `systemctl reload gunicorn` 并检查 `/health`。

如果漏做第 3 步，新 worker 会 fail-fast，避免旧结构承载新代码；此时先完成迁移，再 reload，禁止通过恢复启动时隐式 DDL 绕过门禁。
