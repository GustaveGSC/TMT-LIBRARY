# 部署记录 · 周期二 P3 后端维护脚本归档（第十五轮第一批）

日期：2026-07-22

## 背景

周期二（P3 结构重构）后端部分启动，第一批处理"根目录脚本堆积"：7 个确认无任何模块引用的一次性维护脚本从 `backend/` 根目录搬到 `backend/scripts/`。交接文档：`handoff/2026-07-22-codex-handoff-15.md` → `handoff/2026-07-22-codex-backend-script-cleanup.md`。

## 审查结论

`codex/backend-script-cleanup`（`409b48a`）审查通过：

- 7 个脚本（`backfill_days_since_purchase.py`/`backfill_image_dimensions.py`/`create_cost_tables.py`/`create_packaged_equivalents.py`/`seed_permissions.py`/`seed_roles.py`/`simulate_match.py`）移动后，`sys.path` 计算方式正确改为基于脚本自身新路径反推 `backend/` 目录（`os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`），`create_cost_tables.py` 的 `.env` 加载路径、`simulate_match.py` 的工作目录切换都同步改了。
- `test_operational_safety.py` 里读取 `seed_permissions.py` 源码校验 `product:delete` 权限不回归的测试，路径同步更新。
- `.claude/claude.md` 顺手清理了两条已经不存在于仓库的陈旧脚本引用（`create_reason_keyword_rules.py`、`create_ecr_reminders.py`）。
- 确认 `aftersale_export_tasks.py`（被 `routes/aftersale` 和测试 import 的正式业务代码）未被误动。
- 本地复跑 `pytest`：110 passed。

## 部署

这批不涉及应用运行时代码（这7个脚本从未被任何模块 import，只是人工按需执行），不需要 `alembic upgrade`、不需要 `systemctl reload`。仍然按纪律把服务器同步一致：

1. 服务器新建 `backend/scripts/` 目录，scp 上传 7 个新脚本，md5 逐一核对一致。
2. 删除服务器上残留的 7 个旧路径副本（`backend/*.py` 根目录下的同名文件）。
3. 实测其中一个脚本（`seed_permissions.py`）在新路径下能否正常运行：直接执行，输出全部"跳过（已存在）"——幂等逻辑生效，未产生任何数据变化，同时验证了新路径下 `sys.path`/`.env` 加载都正确。
4. 其余 6 个脚本用 `ast.parse` 做语法校验通过（未逐一实际执行，因为部分脚本如 `create_cost_tables.py`/`create_packaged_equivalents.py` 会产生真实建表/写入副作用，没有必要为了验证语法就真的跑一遍）。

## 顺带发现（未处理，仅记录）

服务器 `/opt/tmt-library/backend/` 根目录下还有三个文件不在本地 git 仓库里：`add_2m2kids_tag.py`、`replace_tms.py`、`resource.py`。这些应该是历史上某次手动 scp 上传、跑过一次性任务后忘记清理的遗留文件，和这次的脚本归档无关，没有动它们（也没有确认它们的具体用途，不确定能不能删）。如果之后要继续清理服务器目录，需要先确认这三个文件的来源和是否还需要保留。

## 影响说明

- 无接口变更、无数据库变更、无需前端构建。
- 后续手工运行这几个维护脚本时，路径要改成 `python3.11 /opt/tmt-library/backend/scripts/<name>.py`。
