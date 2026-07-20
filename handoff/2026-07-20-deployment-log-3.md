# 部署记录 · Alembic baseline 正式确立

日期：2026-07-20

## 三轮核验过程回顾

1. 第一轮：`5f2fb1e` baseline 首版，`compare_metadata` 发现 39 处真实差异，未 stamp，交回 Codex
2. 第二轮：`bf582e4` 收敛到 12 处，其中 6 处是外键 `ondelete` 语义被漏改（不是命名问题），未 stamp，交回 Codex
3. 第三轮：`7beb8cf` 补回 `ondelete='SET NULL'`/`ondelete='CASCADE'`，并确认 `compare_comments=False` 在 alembic 1.18.5 下无效（comment 比较由独立 autogenerate plugin 实现），改用 `autogenerate_plugins` 精确排除 comments 插件 → **核验 DIFF_COUNT=0**

第三轮核验方式和前两轮一致：改动打包到隔离目录 `/opt/alembic_verify/`，指向生产库只读比对，跑完清理，全程未碰 `/opt/tmt-library/backend/` 运行目录。

## 本次操作记录（DIFF_COUNT=0 之后）

1. 部署 alembic 工具文件（`alembic.ini`、`backend/migrations/` 全部）+ 6 个改动过的模型/仓储文件（`database/models/account`、`aftersale`、`product/category`、`product/finished`、`shipping`、`database/repository/account`），md5 全部核对一致
2. `alembic stamp 20260720_01` → 成功
3. `alembic current` → `20260720_01 (head)`
4. `alembic upgrade head` → 无输出（真正的空操作）
5. `alembic check` → `No new upgrade operations detected.`（确认 comments 插件已被正确排除，其余结构比较插件如 types/constraints/tables 仍在工作）
6. `systemctl reload gunicorn`，服务存活，`/health` 200，登录接口正常响应

## 顺带处理

合并 `codex/backend-p1-alembic` 时发现 `.claude/CLAUDE.md`（仓库里实际路径是小写 `.claude/claude.md`）有一处此前（P1-5 核实那次）编辑过但从未真正提交的改动——Windows 文件系统大小写不敏感，我当时用 `git add .claude/CLAUDE.md`（大写路径）没有被 git 正确识别为对已跟踪的 `.claude/claude.md`（小写）文件的修改，导致改动一直是本地未提交状态。Codex 在核实生产环境时发现了这个残留并提醒（`52162af` 合并前主动没有触碰它，只是提示我）。已补提交（`dd06c9a`）。

**后续注意**：本仓库里 `.claude/CLAUDE.md` 这个路径引用在双方文档里都出现过，但 git 实际跟踪的大小写是 `.claude/claude.md`。以后 `git add`/脚本引用这个路径时统一用小写，避免同样问题再发生。

## 第二阶段（尚未授权执行）

按 Codex 的 baseline 交接文档，下一步是：
1. 删除 `create_app()` 对 `_run_migrations()` 的调用和旧隐式 DDL
2. 添加只读 revision 检查，数据库不在 head 时拒绝启动
3. 添加启动 fail-fast 自动化测试
4. 更新部署顺序为：备份 → `alembic upgrade head` → reload

这部分还没开始，等 Codex 那边继续。

## 未部署

前端改动仍未部署。
