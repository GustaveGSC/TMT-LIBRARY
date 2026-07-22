# 交接说明 · Claude → Codex（第十五轮，周期二 P3 结构重构·后端）

日期：2026-07-22

前端这边（周期二 P3 结构重构）已经在做了：删了一个孤立组件（`LifecycleManager.vue`），把 `dataMgmtViews`/`AftersaleCasesTable` 的表格样式统一接到主题变量，抽了一个公共表格组件 `DataTable.vue` 和编辑弹窗 `PackagedEditDialog.vue`，修正了一处 `views/components` 目录归属（`FinishedExpandRow.vue` 挪到 `components/product/`）。现在轮到后端这部分，按 `handoff/2026-07-21-session-close.md` 记录的清单来。

**原则不变：按模块小步迁移，每批保持接口不变，补回归测试，不要一次性大重构。** 这一轮先挑一个风险最低、验证最容易的项目起步。

## 建议先做：根目录脚本堆积

`backend/` 根目录下混杂了核心基础设施文件和一次性脚本，已经确认下面这些是纯粹的独立脚本（用 `grep` 全项目搜索确认过，没有被任何其它模块 `import`，只会被人手动 `python xxx.py` 执行）：

- `backfill_days_since_purchase.py`
- `backfill_image_dimensions.py`
- `create_cost_tables.py`
- `create_packaged_equivalents.py`
- `seed_permissions.py`
- `seed_roles.py`
- `simulate_match.py`

建议新建 `backend/scripts/`，把这几个搬进去。因为没有任何模块 import 它们，这个移动本身不会破坏任何 import 链，风险几乎为零，主要工作是：
1. 确认搬完之后脚本自己内部的 `sys.path`/相对 import（如果有引用 `from database... import`）还能正常跑——多数应该是靠 `backend/` 本身在 `sys.path` 上，搬到子目录后可能需要脚本顶部加一行 `sys.path.insert(0, ...)` 或者用 `python -m scripts.xxx` 的方式跑，你决定怎么处理更顺手。
2. 如果项目里有文档/README/部署脚本引用了这几个文件的旧路径（比如 `.claude/CLAUDE.md` 的"关键路径"一节提到了 `backend/create_reason_keyword_rules.py`、`backend/create_ecr_reminders.py`、`backend/model_manager.py`），搬完之后記得同步这些引用，麻烦顺手检查一下这几个是不是也该一起归类（`create_reason_keyword_rules.py`、`create_ecr_reminders.py` 看名字应该属于同一类一次性建表脚本，但我没验证过有没有被其它模块引用，你确认一下）。

**不要动**的：`aftersale_export_tasks.py`——虽然名字看起来像脚本，但实际被 `routes/aftersale/__init__.py` 和一个测试文件 import，是正式业务代码，不属于这次清理范围。

## 后面按顺序处理的清单（这次不用一起做，供你自己排期）

1. **`model_manager.py`/`utils.py`/`auth.py` 定位模糊**：`model_manager.py` 目前是裸 `import model_manager`（靠 `backend/` 在 sys.path 根上），被 `app.py` 和售后 repository 里好几处 `import model_manager` 引用，涉及语义向量模型加载。如果要挪到更合适的位置（比如 `services/aftersale/` 或单独 `ml/` 目录），影响面比脚本清理大一些，建议放后面。`utils.py` 被非常多模块引用（几乎所有 model 文件都在用它的 `now_cst()`），改动前先评估值不值得动，可能维持现状、只是心里清楚它的定位就够了，不一定非要搬。
2. **`routes/config` 分层缺失**：具体缺什么分层，麻烦你实际看一下 `backend/routes/config/__init__.py` 现状后自行判断怎么补。
3. **`rd/cost` 命名不对称**：`backend/routes/rd/cost.py`（902行）和 `backend/routes/rd/__init__.py`（1761行）——这两个文件本身已经不小了，命名不对称具体指什么、要不要顺便拆分大文件，你决定。
4. **RD 路由文件过大（1700行）**：`backend/routes/rd/__init__.py`，可能需要按功能（ECR/ECN/变更提醒等）拆成几个子模块。
5. **`rd`/`product` 边界重叠**：需要你具体排查两边有没有职责不清的地方。
6. **售后 repository 是"上帝模块"（3907行）**：`backend/database/repository/aftersale/__init__.py`，这是这次清单里规模最大的一项，涉及查询逻辑很多、和语义匹配（`model_manager`）耦合，建议放最后做，而且做之前最好先梳理一下这个文件里有哪些逻辑分组（比如"简称匹配"“原因匹配”“统计查询”"导出任务"），分批拆成子模块，每拆一块跑一遍现有测试确认没有行为变化。
7. **HTTP 路径风格不统一**：具体哪些接口风格不统一需要你自己扫一遍 `api.md` 或路由定义确认，我这边没有实际证据，之前只是记了这一条待办。

## 验证要求

- 每一步照例 `python -m pytest` + `python -m compileall -q backend` + `git diff --check`
- 涉及路径搬动的，注意搜索确认没有遗漏的 import 引用（这次我已经帮你确认过第一批脚本没有被引用，后面几项你搬之前自己搜一遍）
- 不涉及数据库变更，不需要迁移、不需要备份
- 完成一批写一份交接文档，说明改了什么、验证方式、下一步建议从哪继续

## 协作方式

独立 worktree/分支。这次不是紧急任务，可以按你自己的节奏来，不用赶时间；即使中途我们又插队别的紧急任务，这批工作可以随时暂停，下次接着交接文档里记的"下一步"继续，不会丢上下文。
