# 物料库·物料BOM（研发 BOM 导入/展开/反查），交接 Codex 评估

状态：**已实现并上线，待评估**（提交 `608d816`，迁移 `20260927_03` 已在生产执行；生产库目前 0 条 BOM，用户尚未正式导入）

本次只要**评估报告**，不要直接改代码。评估结论里需要改的地方，请给出具体改法（到函数/字段级），
由用户确认后再决定谁来改。

---

## 背景与用户已定的产品决策

物料库新增「物料BOM」tab：导入研发 BOM Excel，按层级保存；物料表能看到哪些物料有 BOM；物料卡片能看
下级结构和「被哪些产品使用」。

| # | 决策 | 用户原话/结论 | 实现影响 |
|---|---|---|---|
| 1 | 只收研发 BOM | 「取消采购bom，采购bom只作为价格来源」 | 物料BOM 不做采购格式解析；采购价格仍走既有 `services/rd/cost_import.py` → `cost_material_price`，两者不打通 |
| 2 | 两个来源冲突 | 「只保留研发bom」 | 无来源字段，无冲突合并逻辑 |
| 3 | 版本粒度 | 「研发bom会是 -A01、-A02，但对产品来讲都是 -A」 | 按研发编码+版本存；ERP 编码按「完整版本 → 仅字母版本 → 无版本」匹配，一个 ERP 物料下可挂多个研发版本 |
| 4 | 层级 | 成品、产成品、半成品拥有下级 BOM | 单层存储，查看时逐层展开（见下） |
| 5 | 待定 | 带「.」的 PDM 子零件编码（如 `14CM01007.04`）、`14ST10*` 标准件在 ERP 里不存在 | 目前**照存**并标「未匹配」；变更申请单比对（`change_documents._parse_bom`）是直接跳过这两类。请评估应该怎么处理 |

生产 ERP 编码规律（2026-09-27 查询 `import_product_raw` 得出）：成品/产成品分组编码只到字母版本
（`1101DL01-A`、`1203MFCB01-A`），半成品/原材料/模具带两位数字（`1303001-A01`，同一物料不同版本是不同
ERP 编码，如 `1310001-A01` / `1310001-A02`），少量无版本（`170401001`）。

---

## 已实现内容

### 数据表（迁移 `backend/migrations/versions/20260927_03_add_material_bom.py`）

| 表 | 关键列 | 约束/索引 | 说明 |
|---|---|---|---|
| `material_bom` | `code`(64) `version`(16) `erp_code`(255, 0900_ai_ci, NULL) `name` `spec` `category` `source_file` `imported_by` `imported_at` | `UNIQUE(code, version)`、`INDEX(erp_code)` | 一条 = 一个父件的单层 BOM 表头。`category` 是研发一级分类去掉编号前缀（成品/产成品/半成品/外贸成品…） |
| `material_bom_line` | `bom_id`(FK CASCADE) `seq` `code` `version` `erp_code` `name` `spec` `category` `qty`(NUMERIC 14,4, asdecimal=False) `unit` | `INDEX(bom_id)`、`INDEX(erp_code)`、`INDEX(code, version)` | 直接子件行。子件自身若有 BOM，靠 `(code, version)` 找到对应 `material_bom` |

模型在 `backend/database/models/product/material.py` 末尾（`MaterialBom` / `MaterialBomLine`）。

### 服务 `backend/services/product/material_bom.py`

- `parse_bom_rows(data: bytes)`：`load_workbook(read_only=False)` 读活动表；表头识别**复用**
  `services.rd.change_documents._bom_columns`（PDM 格式要求 层次/物料编码/版本/一级分类/二级分类/描述/数量/单位/状态；
  ERP 格式要求 层次/图号/品名/规格/数量/单位/状态）。PDM：`name = 描述 or 二/三级分类拼接`、`spec = 规格列`；
  ERP：`图号` 按最后一个 `-` 拆 code/version。数量解析失败按 1。**不过滤任何编码**（与 ECR 不同）。
- `build_single_level_boms(rows)`：按 `层次` 字符串找父级（`level[:rfind('.')]`），每个有子行的父件生成一份单层 BOM；
  同一父件在文件里被多次展开时**只取第一次**（记录 `owner` 层次，其余整段跳过）；同一父件下同一子件多行**合并数量**。
- `MaterialBomService._erp_resolver(pairs)`：一次性把候选编码（`code`、`code-version`、`code-字母`）分批 1000 个 `IN` 查
  `import_product_raw`，返回解析函数。
- `import_file(data, filename, username)`：已存在的同 `(code, version)` 表头**先批量删旧子件行再原地更新**，新的插入；
  逐个 BOM `flush` 拿 id 后 `add` 子件行，最后一次 `commit`。返回 `{created, updated, lines, roots[], unmatched[]}`。
- `list_boms(keyword, category, page, page_size)`：LIKE 搜 code/erp_code/name/spec；子件数一条 GROUP BY；另有一条 DISTINCT category。
- `tree(bom_id)`：逐层 BFS——每层一条查子件行、一条按 `tuple_(code, version).in_(...)` 查子 BOM，最多 20 层；
  构建时用 path 集合防环；名称/规格用一条查询从 `import_product_raw` 取 ERP 的覆盖文件里的。
- `for_material(erp_code, bom_id=None)`：
  - `versions`：`material_bom.erp_code == erp_code`，按 `version DESC`（默认选第一条）；`tree` 复用 `tree()`
  - `direct_parents`：`material_bom_line.erp_code == erp_code` 的所在 BOM
  - `top_products`：从直接上级按 `(code, version)` 逐层往上找，某层父件不再被任何子件行引用就算顶层，最多 20 层
- `codes_with_bom(erp_codes)`：物料表当前页一条 DISTINCT 查询；`MaterialService.list_items` 里调用，给每行加 `has_bom`
  （列表从 3 条业务查询变 4 条，`test_default_sorted_list_keeps_four_business_queries_when_caches_are_warm` 已同步）。

### 接口（`backend/routes/product/material.py`，`material_bp`：GET 需 `material:view`，POST/DELETE 需 `material:edit`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/material/boms/import` | multipart `file`，只收 `.xlsx`；`read_spreadsheet_upload` 做大小/行数校验；**同步处理**，不走后台线程 |
| GET | `/api/material/boms` | `?keyword=&category=&page=&page_size=`（≤200） |
| GET | `/api/material/boms/<id>/tree` | 完整多层展开 |
| DELETE | `/api/material/boms/<id>` | 只删这一层，下级半成品自己的 BOM 不动 |
| GET | `/api/material/items/<path:code>/bom` | `?bom_id=`，物料卡片用 |

路由匹配已有测试：`/items/A/B/bom` 命中 `material_item_bom` 且不被 `/items/<path:code>` 吞掉。

### 前端（已完成，仅供了解契约，不需要评估 UI）

`MaterialBomPanel.vue`（tab：左列表+右树+导入结果弹窗）、`MaterialBomTree.vue`（el-table 树）、
`MaterialItemsPanel.vue`（BOM 标记列）、`MaterialCard.vue`（BOM 区：版本切换 / 被使用 / 卡片内跳转+返回）。

### 已做的验证

- `backend/tests/test_material_bom.py`（6 个，SQLite）：断言
  ① PDM 解析层次顺序与 `category='成品'`；单层拆分结果、重复展开只取第一次（`R9` 不出现）、同父同子合并数量；
  ② 成品 `F1-A01 → F1-A`、半成品 `M1-A01 → M1-A01`，`unmatched == ['R9-A01','S1-A01']`；同版本二次导入 `created=0, updated=3`
  且子件数量被覆盖；新版本 A02 导入后 `for_material('F1-A').versions == ['A02','A01']`；
  ③ 树三层展开且名称取 ERP；④ 原材料的直接上级/最终产品、顶层成品无上级、`codes_with_bom`；
  ⑤ 未知表头报「无法识别」；⑥ 路由不冲突。
- 物料库原有测试：`test_material_library.py` / `test_material_combos.py` 除 3 个**既有**权限基线失败外全部通过
  （`test_material_route_rejects_invalid_sort_field`、`test_material_route_returns_expression_error_as_400`、
  `test_combo_routes_enforce_view_and_edit_permissions`，改动前即失败）。
- Playwright `tests/e2e/material-bom.spec.js` + `material-card-layout.spec.js`：15 个通过（接口全 mock）。
- 生产只读验证：用户给过的真实 PDM 文件（`2001SY01` 外贸成品，226 行）解析为 34 份单层 BOM、192 个不同编码，
  114 个匹配到 ERP；`2001SY01-A01 → 2001SY01-A`、`2101SYZM01-A01 → 2101SYZM01-A`、`1307008-A01 → 1307008-A01`。
  78 个未匹配 = 68 个带「.」子零件 + 6 个 `14ST10*` + 4 个其他。**未写入生产数据**。

---

## 请重点评估的问题

按我自己的判断列出已知风险，请逐条给结论（成立/不成立/严重程度）并补充我没看到的。

| # | 风险点 | 我目前的判断 | 希望你给出 |
|---|---|---|---|
| R1 | **ERP 编码在导入时固化**：`erp_code` 只在导入那一刻匹配，之后 ERP 物料表重导新增了编码，旧 BOM 不会自动关联 | 可能要在 `import_product_service.import_rows` 后重算，或改成读时匹配 | 选哪种、代价（重算的 SQL 量） |
| R2 | **过期的下级 BOM 永不清理**：父件重导后某个半成品不再是子件，它自己的 BOM 仍留着；某节点在新文件里是叶子（没展开）也不会清掉它原有的 BOM | 我倾向于这是正确语义（单层 BOM 是独立资产），但需要确认 | 语义是否合理，是否需要「孤儿 BOM」提示 |
| R3 | **层次列若是数值单元格**：`_level_str` 把 float `1.1` 转成 `'1.1'`，`1.10` 也会变成 `'1.1'` 冲突 | 真实样例是文本，但 ERP 导出不确定 | 是否需要拒绝数值层次或按 `number_format` 还原 |
| R4 | **大小写/排序规则**：新表 `code`/`version` 未显式指定 collation，MySQL 默认 ai_ci 不区分大小写；Python 里 `existing` 字典按原样字符串做 key，若文件里出现 `a01` 与库里 `A01`，会漏判为新建而触发唯一约束 500 | 概率低但会 500 | 是否规范化（统一大写/strip）或显式 collation |
| R5 | **导入同步执行**：`read_only=False` 整表载入 + 逐行 `ws.cell()`，在单 worker（1.7GB 内存，`-w 1 --timeout 1800`）上大文件会阻塞所有请求 | 研发 BOM 一般几百行，问题不大；但没有行数/BOM 数上限以外的保护 | 是否需要 `read_only=True` + `iter_rows`、或上限 |
| R6 | **反查口径不一致**：直接上级按 `erp_code` 找，往上走按 `(code, version)` 找；同一 ERP 物料的多个研发版本各自被不同上级引用时，`top_products` 会合并它们 | 我认为合并是期望行为，但请确认没有漏/重 | 口径是否正确 |
| R7 | **跳过规则**：带「.」子零件和 `14ST10*` 是否应像 ECR 一样跳过；若跳过，数量是否要并到上级 | 待用户决定（决策表第 5 行） | 给出建议方案与理由，供用户选 |
| R8 | **复用 ECR 私有函数**：`material_bom.py` 直接 import `change_documents` 的 `_bom_columns/_level_str/_numeric_code_text/_category_name` | 能用但耦合，ECR 改表头规则会连带影响 | 是否抽到公共模块（如 `services/common/bom_excel.py`） |
| R9 | **查询量**：`tree` 每层 2 条 + ERP 名称 1 条；`for_material` 约 3 + 2×层数；`list_items` 多 1 条 | 符合 CLAUDE.md「O(层数)、禁止循环内 lazy load」 | 在 MySQL 上 `tuple_ IN` 能否走 `ix_material_bom_line_code_version` / 唯一索引，给 EXPLAIN 结论 |
| R10 | **测试只在 SQLite**：未覆盖 MySQL 专有行为（R4 的大小写、tuple IN、`Numeric asdecimal`）；ERP（图号）格式没有测试 | 缺口 | 需要补哪些测试，断言什么 |
| R11 | **事务**：导入中途异常时依赖请求结束的 session remove 回滚；删旧子件行是 `synchronize_session=False` 的批量 DELETE | 应该没问题 | 确认是否需要显式 `rollback` |

另外请顺带评估：
- `cost_bom_node` / `cost_bom_line`（研发成本导入里已有一套 BOM 层级数据）与本次 `material_bom` 是否应该打通或互相引用。
  之前的架构决定是「物料主数据新建表、否决复用 `cost_bom_node`」，本次沿用；如果你认为 BOM 这一块应该复用，请说明理由。
- `DELETE /boms/<id>` 目前是硬删除，无二次校验被谁引用（引用关系靠 `(code, version)` 松耦合，删了父件不影响子件）。

---

## 不需要做的

- 不要改前端 UI、样式和交互（用户逐项确认过）。
- 不要引入采购 BOM 导入。
- 不要直接改生产数据或执行迁移。
- 评估阶段不要提交代码改动。

---

## 期望交付物

`handoff/2026-09-2X-codex-material-bom-evaluation-report.md`，结构：

1. **结论摘要**：能否保持现状上线使用；必须先修的问题（P0）有哪些。
2. **逐条评估**：R1–R11 + 你新发现的问题，每条给 严重程度（P0/P1/P2）、证据（代码位置/复现数据/EXPLAIN）、建议改法（到函数/字段级）。
3. **R7 跳过规则的方案对比表**（照存 / 跳过 / 跳过并把数量并到上级），供用户选择。
4. **建议的修复分批**：每批改哪些文件、是否需要迁移、需要新增的测试及其断言内容。

## Claude 后续动作

收到评估报告后：整理 P0/P1 给用户确认 → 按用户决定分工修复（后端是否交给你实现由用户定）→
构建部署、生产验证（届时用户会导入第一份真实研发 BOM）。
