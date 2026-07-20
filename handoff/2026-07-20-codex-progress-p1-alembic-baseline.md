# Codex 后端进度 · P1-3 Alembic baseline 第一阶段

日期：2026-07-20
分支：`codex/backend-p1-alembic`

## 本阶段完成内容

- 添加 Alembic 依赖与根目录 `alembic.ini`。
- 添加 `backend/migrations/env.py`，显式加载全部 56 张模型/关联表，数据库连接沿用生产 `.env`。
- 添加唯一 head：`20260720_01`，这是刻意为空的生产现状 baseline，upgrade/downgrade 均不执行任何业务 DDL。
- 添加 baseline 操作手册和自动化测试。
- 保留 `backend/app.py::_run_migrations()` 原样，尚未加入启动 revision 检查。

## 本地验证

```text
python -m pytest                         30 passed
python -m compileall -q backend          通过
git diff --check                         通过
python -m alembic -c alembic.ini heads   20260720_01 (head)
python -m alembic -c alembic.ini history <base> -> 20260720_01 (head)
```

离线执行 `upgrade head --sql` 只生成：

1. 创建 `alembic_version`。
2. 写入版本号 `20260720_01`。

没有业务表的 CREATE/ALTER/DROP。

自动化测试还使用临时 SQLite 模拟一个已存在业务表的数据库：stamp 后执行 `upgrade head`，业务表集合完全不变。

## 生产门禁：请 Claude 执行并回传结果

先备份生产数据库。仅上传 baseline 工具文件（`alembic.ini`、`backend/migrations/`）和安装 Alembic；不要替换 `app.py`，也不需要 reload。确认 Alembic 使用服务器实际 `backend/.env` 后，在生产库执行：

```bash
cd /opt/tmt-library
pip3.11 install "alembic>=1.18.5,<2.0.0"
python3.11 -m alembic -c alembic.ini heads
python3.11 -m alembic -c alembic.ini history
python3.11 -m alembic -c alembic.ini check
```

`alembic check` 是结构差异检查。如果报告模型和生产库有差异，停止，不要 stamp，把完整差异交回 Codex审查。

只有 `check` 确认无新的 upgrade operations 后才执行：

```bash
python3.11 -m alembic -c alembic.ini stamp 20260720_01
python3.11 -m alembic -c alembic.ini current
python3.11 -m alembic -c alembic.ini upgrade head
```

预期：`current` 显示 `20260720_01 (head)`，随后 `upgrade head` 是空操作。

## 第二阶段（尚未授权执行）

Claude 回传生产 baseline 验证通过后，Codex再：

1. 删除 `create_app()` 对 `_run_migrations()` 的调用和旧隐式 DDL。
2. 添加只读 revision 检查，数据库不在 head 时拒绝启动。
3. 添加启动 fail-fast 自动化测试。
4. 更新部署顺序为：备份 → `alembic upgrade head` → reload。

本阶段未连接生产库、未 stamp、未部署、未 push。
