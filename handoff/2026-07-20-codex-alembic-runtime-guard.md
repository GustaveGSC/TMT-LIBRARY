# Codex · Alembic 第二阶段启动门禁

日期：2026-07-20  
分支：`codex/backend-p1-alembic-runtime`

## 完成内容

- 删除 `backend/app.py::_run_migrations()` 及其全部启动时建表、补列、修改 Enum 和锁操作。
- 删除随旧迁移入口运行的资料类型隐式 seed；以后 seed 数据必须进入可审查的显式迁移或独立运维步骤。
- 应用启动改为只读 revision 校验：迁移脚本必须只有一个 head，数据库 current heads 必须与其完全一致。
- 配置文件默认读取项目根目录 `alembic.ini`，可用 `ALEMBIC_CONFIG` 显式覆盖。
- 校验位于 `db.init_app()` 之后、蓝图注册和后台模型线程启动之前；缺配置、未 stamp、落后 revision 或多 head 均直接拒绝启动。
- 更新迁移 README，部署顺序固定为：备份 → 先部署迁移脚本 → `alembic upgrade head` → `alembic current` → 部署应用代码 → reload → health。

## 自动化验证

```text
python -m pytest backend/tests -q
44 passed
python -m compileall -q backend
通过
git diff --check
通过
```

覆盖范围包括：当前 revision 正常启动、未 stamp、落后版本、缺少配置、多 head、`create_app()` fail-fast，以及启动文件不存在隐式 `ALTER TABLE`/`Table.create` 回归。

## Claude 部署核验

1. 先确认生产 `alembic current` 仍为 `20260720_01 (head)`。
2. 部署 `backend/app.py`；`backend/migrations/README.md` 不影响运行，可随代码留档。
3. 使用 reload，不要 restart，不要 `--preload`。
4. 验证新 worker 正常接管、`/health` 200、登录接口正常。
5. 查看 gunicorn journal，确认没有 revision mismatch；不需要也不允许再观察到旧 `[migration]` 建表/补列日志。

未部署、未 push。
