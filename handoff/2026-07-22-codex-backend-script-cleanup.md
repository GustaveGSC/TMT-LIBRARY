# 交接说明 · Codex → Claude（周期二 P3：后端维护脚本归档）

日期：2026-07-22

## 完成内容

- 提交：`409b48a refactor(backend): archive maintenance scripts`
- 分支/worktree：`codex/backend-script-cleanup` / `E:/Project/tmt-library/.worktrees/codex-script-cleanup`
- 将以下 7 个一次性维护脚本从 `backend/` 根目录移动到 `backend/scripts/`：
  - `backfill_days_since_purchase.py`
  - `backfill_image_dimensions.py`
  - `create_cost_tables.py`
  - `create_packaged_equivalents.py`
  - `seed_permissions.py`
  - `seed_roles.py`
  - `simulate_match.py`
- 每个直接运行的脚本都改为从自身新位置计算 `BACKEND_DIR` 并加入 `sys.path`；`create_cost_tables.py` 继续明确加载 `backend/.env`，`simulate_match.py` 继续把工作目录设为 `backend/`。
- 脚本说明中的运行命令统一为从项目根目录执行 `python backend/scripts/<name>.py`。
- `seed_roles.py` 中提示先运行权限脚本的路径已同步。
- 更新 `test_operational_safety.py` 对权限种子源码的路径，继续保护 `product:delete` 不会回归。
- `.claude/claude.md` 的关键路径改为统一说明 `backend/scripts/`；其中原先列出的 `backend/create_reason_keyword_rules.py`、`backend/create_ecr_reminders.py` 实际已不存在于仓库，也没有可移动文件，因此移除了这两条陈旧入口。
- `backend/aftersale_export_tasks.py` 未改动。

## 验证

- `python -m pytest backend/tests -q`：110 passed。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。
- 全仓库排查长期代码/测试/当前文档，没有剩余旧路径引用；历史 `handoff/` 作为时间点记录未改写。
- 本批不涉及接口、数据库结构、运行中业务模块或部署。

## 合并注意事项

- 只需合并 `409b48a` 和本交接文档提交；不需要 Alembic、reload 或前端构建。
- 服务器若仍需手工运行这些维护脚本，使用新路径，例如：
  `python3.11 /opt/tmt-library/backend/scripts/seed_permissions.py`。
- 这批文件移动不会自动删除服务器上的旧脚本副本（常规 scp 只上传新文件）。如希望生产目录结构也收口，Claude 部署时应先核对新脚本已上传，再单独删除上述 7 个旧路径；这些脚本不被服务 import，删除无需 reload。

## 下一批建议

按第十五轮清单继续时，建议先只读评估 `model_manager.py` 的真实职责和 import 面，再决定“保留根目录并补说明”还是迁移到专门模块；不要把 `utils.py` 与它绑在同一批。若希望继续做纯结构低风险项，也可以先审查 `routes/config` 的职责与测试覆盖，再决定是否拆分。

本批未部署、未 push，未修改 `src/` 或 Electron。
