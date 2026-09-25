# 研发工具页（frontend-rdtools）

## 路由与入口

| 项 | 值 |
|---|---|
| 路由 | `/rd-tools` |
| 页面组件 | `src/views/rdToolsViews/page-rd-tools.vue` |
| 权限码 | `rd:view`（查看）、`rd:edit`（编辑）、`rd:admin`（管理物料门禁） |
| composable | `canViewRd / canEditRd / canAdminRd`（来自 `usePermission`） |

页面挂载时调用 `window.electronAPI.maximizeApp()`，返回时调用 `unmaximizeApp()`。

---

## Tab 结构

| key | 标题 | 组件 | 状态 |
|---|---|---|---|
| `home` | 主页 | 工具卡片网格 | 已上线 |
| `pdm2bom` | PDM转BOM | `PdmToBomForm.vue` | 已上线 |
| `ecr` | 变更申请单填写 | `EcrForm.vue` | 已上线 |
| `ecn` | 变更通知单填写 | `EcnForm.vue` | 已上线 |
| `cost` | BOM成本 | `BomCost.vue` | 已上线 |
| `gate` | 材料清单校验 | `MaterialGateCheckPage.vue` | 已上线（2026-09-25） |

图标使用 `@phosphor-icons/vue`（`PhHouseLine / PhArrowsLeftRight / PhClipboardText / PhBell / PhCurrencyDollar / PhShieldWarning`）。

**主页分组**（2026-09-25 起）：`home` tab 内的工具卡片网格分两组展示——"功能"组包含
`tabs.slice(1)` 的全部 tab（点击切换 `activeTab`）；"设置"组只对 `canAdminRd` 用户显示，目前只有
一张"物料门禁维护"卡片，点击**不切换 tab**，而是打开 `page-rd-tools.vue` 页面级的
`showGateMgmtDialog`（`<MaterialGateManageDialog v-model="showGateMgmtDialog" />`，和
`AppBottomBar` 同级挂在页面根部）。门禁维护入口不再放在"变更申请单填写"里。

---

## PDM 转 BOM（PdmToBomForm.vue）

`src/components/rdTools/PdmToBomForm.vue`，4态状态机：`idle → processing → error/ready`。

### 工作流程

1. 点击「选择文件」→ `electronAPI.showOpenDialog`（仅 `.xlsx`，Electron 已停用，该分支实际不可达；Web 端用原生文件选择）
2. 点击「处理」→ `POST /api/rd/pdm2bom/process`（multipart 上传，字段名 `pdm_file`；2026-07-22 起后端移除了旧的 JSON 路径协议，不再接受 `file_path` 字段，详见 `handoff/2026-07-22-codex-rd-upload-security.md`）
3. 后端返回 `{ columns, table_data, error_map, required_col_indices, total_level }`
4. **有错误**（`error_map` 非空）→ 显示可编辑错误表格，错误行黄底，缺失格红底；用户可直接编辑后点「重新校验」（本地重校，不再往返后端）
5. **无错误** → 就绪态，显示两个导出按钮

### 导出

| 按钮 | 接口 | 输入 | 文件名 |
|---|---|---|---|
| 导出 ERP 物料 xlsx | `POST /api/rd/pdm2bom/export-erp` | `columns, table_data` | `ERP-{品号}.xlsx` |
| 导出 BOM xlsx | `POST /api/rd/pdm2bom/export-bom` | `columns, table_data, total_level` | `BOM-{品号}.xlsx` |

导出均返回 `arraybuffer`，通过 `showSaveDialog` + `saveFile` 落盘。

### 后端常量（`backend/routes/rd/__init__.py`）

| 常量 | 说明 |
|---|---|
| `_PTB_CHECKED_COLUMNS` | 20个必填PDM列名，用于校验 |
| `_PTB_COLUMNS_TO_MATERIAL` | 46个PDM列名，按位置对应物料模板第6行起 |
| `_PTB_COLUMNS_TO_BOM` | 13个逻辑名，映射BOM模板列 |
| `_PTB_RESOURCES_DIR` | `backend/resources/`（模板目录） |

### 模板文件

- `backend/resources/template_material.xlsx`：物料导入模板，数据从第6行填入（前5行为表头）
- `backend/resources/template_bom.xlsx`：BOM导入模板，数据从第6行填入

### 过滤规则（与原 PyQt5 一致）

- 跳过品号含 `.` 的行
- 跳过品号前6位为 `14ST10` 的行
- 跳过全空行

---

## ECR 变更申请单（EcrForm.vue）

`src/components/rdTools/EcrForm.vue`，整体布局：`ecr-form-wrap`（flex 列）→ `ecr-body`（flex 行，含表单区 + 笔记抽屉）→ 底部变更提醒区。

### 表单字段

| 字段 | 默认值 | 说明 |
|---|---|---|
| `issuing_unit` | `'研发部'` | 发出单位 |
| `date` | 今日 | 自动填入，禁止编辑 |
| `ecr_code` | 自动生成 | 格式 `ECR.YYYYMMDD-NN`，由 `sessionStorage` 管理当日序号，挂载时预生成（不消耗），导出时正式消耗 |
| `project` | — | 变更项目名称 |
| `change_type` | `'设计变更'` | 变更类型：设计变更 / 制程变更 / 其他 |
| `distribution` | `['采购','生产','生管','品管']` | 分发单位（多选） |
| `change_reason` | `'结构优化'` | 变更原因（单选）：品质不良/价格变动/设计优化/结构优化/成本优化/工艺优化/其他 |
| `change_subject` | — | 变更主题（textarea） |
| `change_desc` | — | 变更内容说明（textarea） |

### BOM 比对（右列）

- 支持多个变更组（`bomGroups`），每组独立选择「变更前」和「变更审核中」两个 `.xlsx` 文件
- 通过 `window.electronAPI.showOpenDialog` 选择文件（Electron 已停用，该分支实际不可达）；Web 端用原生文件选择，上传时走 multipart（字段名 `bom_before`/`bom_after`），后端不再接受 `bom_before_path`/`bom_after_path` JSON 字段
- 比对结果须手动确认（`confirmed = true`）后才纳入预览/导出
- `allChanges` 计算属性汇总所有已确认组的变更行

**BOM 文件格式要求**（后端校验）：
- 必要列：`层次 / 图号 / 品名 / 规格 / 数量 / 单位 / 状态`
- 变更前文件：只校验列名，**不**校验状态是否全为「已发布」
- 变更审核中：状态列不能全是「已发布」

**BOM 比对变更类型**：
- 版本变更（通用/非通用审核中）：生成 **cancel + add 两行**，cancel 行浅红底色
- 纯数量变更：生成**单行**，`change_method = '数量变更'`，`qty_desc = 'X→Y 单位'`（显示在取替代关系列）
- 纯新增 / 纯删除：各生成一行

**版本号推算规则**：
- 图号格式：`{编码}-{版本号}`，版本号如 `A01`（字母+数字）
- 通用变更审核中 → 数字+1：`A01 → A02`
- 非通用变更审核中 → 字母+1，数字重置01：`A01 → B01`
- 规格中版本号同步更新，支持 `-版本` 和 `_版本` 两种前缀格式

**导出 Excel 明细表（18列）**：
- 取替代关系（col 10）：cancel+add 对合并两行，填 `change_kind`；单行填 `qty_desc` 或 `change_kind`
- 填写人员行：右对齐

### 物料门禁校验（2026-09-25 起替代原"变更提醒"，已上线）

> 交接文档：`handoff/2026-09-25-codex-rd-material-gate-backend.md`（需求）、
> `handoff/2026-09-25-codex-rd-material-gate-backend-complete.md`（Codex 实现回执）。
> 迁移 `20260925_01` 已在生产执行（`ecr_reminder` 表已删除，下架前 11 条历史记录归档在
> `handoff/archives/2026-09-25-ecr_reminder-final-backup.json`，其中 3 条是下架前仍在架的提醒，
> 内容未自动迁移为门禁，如有需要按业务含义手动在物料门禁里重建）。

原"变更提醒"（自由文本 + 全部勾选确认才能导出，挂在 `EcrForm.vue` 底部可拖拽区域）已整体移除，
改为按**物料编码**登记门禁（级别 `warn` 提醒 / `block` 禁止），在两个上传流程里自动校验：

- **变更申请单填写**（`EcrForm.vue`）：每个 BOM 变更组比对完成后，对 `compare-bom` 返回的
  `after_codes`（after 文件里出现的全部物料编码，不止 diff 出来的变动项）调用
  `POST /api/rd/material-gates/check`；命中 `block` 时该组"确认此变更"按钮禁用，无法纳入导出；
  命中 `warn` 仅提示不阻断。
- **PDM转BOM**（`PdmToBomForm.vue`）：`process` 返回后对 `material_codes`（去重后的"品号"列，
  注意这里列名是**品号**不是物料编码，两个上传流程的源文件格式不同）做同样校验；`revalidate()`
  人工改过品号后会重新扫一遍；命中 `block` 时导出按钮禁用。
- **材料清单校验**（独立 tab，`MaterialGateCheckPage.vue`）：上传任意带"物料编码"或"品号"列的
  Excel，调 `POST /api/rd/material-gates/check-file`，单独展示命中结果，不生成任何单据，也不依赖
  前两个流程。

**命中展示改为弹窗**（2026-09-25 第二次修改，用户反馈"需要是一个dialog面板"）：三处校验点检测到
命中（或校验接口本身异常）时自动弹出 `MaterialGateHitDialog.vue`，不再用行内 banner；block 在前
warn 在后分区展示，每项显示"名称 + 物料编码 + 门禁原因"。关闭弹窗后原位置会留一条可点击的小提示条
（`.gate-reopen-hint`，三个组件各自实现，非共享组件）用于重新打开，命中 block 时提示条变红色。
门禁维护入口同一批也从 `EcrForm.vue`/`MaterialGateCheckPage.vue` 里移除，统一放到研发工具首页
"设置"分组（见上）。

> **`name` 字段待补**：`MaterialGateHitDialog.vue` 要显示的"名称"来自门禁记录自身登记的 `name`
> 字段（管理员新增门禁时一并填写"这个编码对应的是什么"，不是从上传文件解析出来的），但后端
> `check`/`check-file` 的响应目前还没有这个字段——已交接 Codex
> （`handoff/2026-09-25-codex-rd-material-gate-name-spec.md`，未部署；**只加 `name` 一个字段**，
> 早期版本要求过的 `spec` 已被用户反馈撤回，改成单一名称输入）。`MaterialGateManageDialog.vue`
> 的新增/编辑表单已经加了这个输入框，`POST/PUT` 会带上 `name`，但旧后端目前会**静默忽略**这个
> 多出来的字段（不报错，也不保存），所以现在填了会看起来"消失"；命中弹窗在字段缺失时兜底显示
> "（未登记名称）"。后端这批交付并重新部署前，不要以为这个功能已经完整。

共用组件：
- `src/composables/useMaterialGateCheck.js` — 包装 `check` 接口调用，返回 `{warn, block, ok}`
  （`ok:false` 表示接口异常，调用方需要提示但不当成"无命中"处理）
- `src/components/rdTools/MaterialGateHitDialog.vue` — 命中结果弹窗（block 红色不可关闭分区、warn
  黄色分区），三处校验点共用，`ok:false` 时展示"校验未完成"提示
- `src/components/rdTools/MaterialGateManageDialog.vue` — 门禁 CRUD 弹窗（新增/编辑/上下架，含
  `name` 字段），页面级单例挂在 `page-rd-tools.vue`

### 个人笔记

- 操作栏（form-actions）左侧有跑道圆形「笔记」按钮（橙色边框 + `EditPen` 图标），激活时变实心橙
- 点击后从右侧滑入笔记抽屉（覆盖，不挤压内容），左边缘可拖拽调整宽度（200px ~ 520px）
- 抽屉左边缘 6px 拖拽手柄（`startNotesResize`）；标题栏「—」最小化按钮收起
- **笔记按用户隔离**：请求头 `X-Username` 传当前登录用户名，后端按此筛选，数据存 `ecr_note` 表
- 每条笔记独立卡片；悬浮显示「编辑」和删除按钮；删除有 `ElMessageBox.confirm` 二次确认
- 编辑时卡片内显示 textarea（橙色边框），`Ctrl+Enter` 保存，`Esc` 取消

### 预览 & 导出

- **预览**：弹窗内渲染申请单样式（HTML 表格，宽1200px）
- **导出申请单 XLSX**：`POST /api/rd/ecr/export` → `arraybuffer` → `showSaveDialog` → `saveFile`

---

## ECN 变更通知单（EcnForm.vue）

`src/components/rdTools/EcnForm.vue`，独立 Tab，布局为左右双列（左：信息填写，右：明细预览）。

### 工作流程

1. 上传已导出的 ECR xlsx → `POST /api/rd/ecr/parse-ecr` 解析 → 自动填充表单和明细
2. 确认/补填 ECN 专属字段（导入方式、影响文件、负责人）
3. 预览 → 导出 XLSX（`POST /api/rd/ecr/export-ecn`）
4. **清空 ECR 文件** → 调用 `resetForm()`，所有字段（含基本信息）全部清空

### 表单字段

**来自 ECR 解析（可手动修改）**：

| 字段 | ECR 位置 | 说明 |
|---|---|---|
| `ecr.issuing_unit` | row3 col2 | 发出单位 |
| `ecr.date` | row3 col4 | 日期 |
| `ecr.ecr_code` | row3 col7 | ECR 变更编码 |
| `ecr.project` | row3 col10 | 变更项目 |
| `ecr.distribution` | row4 | 分发单位（多选，从 ☑/☐ 文本解析） |
| `ecr.change_reason` | row5 | 变更原因 |
| `ecr.change_desc` | row9 | 变更内容说明 |

**ECN 专属字段**：

| 字段 | 默认值 | 说明 |
|---|---|---|
| `form.ecn_code` | 自动生成 | 据报编号，格式 `ECN.YYYYMMDD.NN`，导出时正式消耗序号 |
| `form.product` | 来自 `ecr.project` | 产品型号 |
| `form.import_method` | `'立即导入'` | 导入方式（单选）：立即导入 / 清化库存 / 随单导入 |
| `form.affected_files` | `['图纸','BOM']` | 影响文件（多选） |
| `form.responsible` | 来自 ECR `submitter` | 负责人（ECR 填写人员行解析） |

### ECN Excel 结构

**表头（第3行，共15列）**：
`发出单位(1) | 值(2-3) | 产品型号(4) | 值(5-7) | 负责人(8) | 值(9-10) | 日期(11) | 值(12) | ECN编号(13-15)`

**信息行（4-8行）**：导入方式 / 分发单位 / 变更原因 / 变更内容 / 影响文件

**明细表（第9行表头起，共15列）**：

| 列 | 内容 | 来源 |
|---|---|---|
| 1 | 序号 | — |
| 2-3 | 主件图号（合并） | ECR/BOM |
| 4-5 | 图号（合并） | ECR/BOM |
| 6 | 层次 | ECR/BOM |
| 7-8 | 品名（合并） | ECR/BOM |
| 9-10 | 规格（合并） | ECR/BOM |
| 11 | 变更方式 | ECR col9 / BOM比对 |
| 12 | 取替代关系 | ECR col10（`substitution`），cancel+add对合并两行；BOM比对时用 `qty_desc`/`change_kind` |
| 13 | 处理意见 | ECR col17（`handling`） |
| 14 | 负责人 | ECR col18（`responsible_person`） |
| 15 | 备注 | 空白 |

**页脚区**：
- 品管追踪记录行（跨2行）：生产 / 服务 / 品管 / 生管 / 研发 各部门签名格
- 确认日期行
- 备注行
- 结案行：品管签名 + 日期

**Logo**：左上角，距左边缘 5px、距上边缘 3px（`OneCellAnchor` + EMU偏移，ECR 和 ECN 相同）

### ECR 解析（`_parse_ecr_rows_xlsx` / `_parse_ecr_rows_xls`）

每行读取的字段（1-indexed for xlsx，0-indexed for xls）：

| 字段名 | xlsx col | xls col | 说明 |
|---|---|---|---|
| `change_method` | 9 | 8 | 变更方式 |
| `substitution` | 10 | 9 | 取替代关系 |
| `change_kind` | 11 | 10 | 研发列（变更类型） |
| `level` | 4 | 3 | 层次 |
| `name` | 5 | 4 | 品名 |
| `spec` | 7 | 6 | 规格 |
| `handling` | 17 | 16 | 处置方式 |
| `responsible_person` | 18 | 17 | 责任人 |

`submitter`（负责人）：扫描末尾行，找「填写人员：xxx」格式提取。

---

## 后端接口（prefix: `/api/rd`）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/ecr/export` | `rd:view` | 生成 ECR xlsx，返回 arraybuffer |
| POST | `/ecr/parse-ecr` | `rd:view` | 解析 ECR xlsx/xls，返回表单字段和变更明细（含 substitution/handling/responsible_person） |
| POST | `/ecr/export-ecn` | `rd:view` | 生成 ECN xlsx，返回 arraybuffer |
| POST | `/ecr/compare-bom` | `rd:edit` | 比对两份 BOM，返回 `{ changes, stats, after_codes }` |
| GET | `/material-gates` | `rd:view` | 返回所有在架门禁 |
| GET | `/material-gates/all` | `rd:admin` | 返回全部门禁（含下架历史） |
| POST | `/material-gates` | `rd:admin` | 新建门禁（`code/level/reason`），同编码已有在架记录则拒绝 |
| PUT | `/material-gates/<id>` | `rd:admin` | 编辑门禁 |
| PUT | `/material-gates/<id>/deactivate` | `rd:admin` | 下架门禁（软删除） |
| PUT | `/material-gates/<id>/activate` | `rd:admin` | 重新上架门禁（同编码已有其它在架记录则拒绝） |
| POST | `/material-gates/check` | `rd:edit` | body `{codes:[...]}` → `{warn:[{code,reason}], block:[{code,reason}]}` |
| POST | `/material-gates/check-file` | `rd:edit` | 上传 `.xlsx`（字段名 `file`），优先识别"物料编码"列，其次"品号"列，返回 `{scanned_count, warn, block}` |
| GET | `/notes` | `rd:view` | 返回当前用户笔记（按 `X-Username` 隔离，倒序） |
| POST | `/notes` | `rd:view` | 新建笔记 |
| PUT | `/notes/<id>` | `rd:view` | 编辑笔记内容（只能改自己的） |
| DELETE | `/notes/<id>` | `rd:view` | 删除笔记（只能删自己的） |

`rd:admin` 权限由服务端从 JWT token 解析（`@require_auth` + `is_rd_admin()`），前端**无需**手动注入 `X-User-Roles` / `X-User-Permissions` 请求头（旧方案已移除）。鉴权凭据通过 httpOnly Cookie（`tmt_session`）自动携带，不再走 `Authorization: Bearer <token>`；写请求需要 `http.js` 从 `tmt_csrf` Cookie 读值附加的 `X-CSRF-Token` 请求头（浏览器自动处理，组件代码无需关心）。

笔记接口仍通过 `X-Username` 请求头识别用户（待迁移至 JWT），前端从 `localStorage.user.username` 取值注入。

---

## 数据库

| 表 | 模型 | 文件 | 状态 |
|---|---|---|---|
| `material_gate` | `MaterialGate` | `backend/database/models/rd/__init__.py` | 已上线（迁移 `20260925_01`），字段：`id / code / level / reason / is_active / created_by / created_at / updated_at`，`code` 上有非唯一索引，"同编码只允许一条在架"由应用层校验 |
| `ecr_note` | `EcrNote` | `backend/database/models/rd/__init__.py` | 已上线，字段：`id / username / content / created_at`（建表脚本：`backend/create_ecr_notes.py`） |

`ecr_reminder`（`EcrReminder`）已随这次改动**整体移除**（表+model+repository+service+routes），
迁移里会 `DROP TABLE ecr_reminder`，不保留历史数据（用户明确要求整体替换为门禁机制）。

---

## preload API 补充

ECR/ECN 导出新增了两个 preload 方法（CLAUDE.md 未列出）：

```typescript
window.electronAPI.showSaveDialog(options)  // → { canceled, filePath }
window.electronAPI.saveFile(filePath, data) // 将 ArrayBuffer 写入本地文件
```

---

## BOM 成本库（BomCost.vue）

`src/components/rdTools/BomCost.vue`，研发工具页新增 Tab（`key: 'bom-cost'`）。

### 子 Tab 结构

| key | 标题 | 说明 |
|---|---|---|
| `snapshots` | 成本快照 | 按产成品分组展示，每行含多个订单标签 |
| `nodes` | 物料查询 | 全量物料列表，按物料分类+品号排序，含最新单价 |
| `estimate` | 成本预估 | 基于已有 SKU 或自由组合估算 |

### 成本快照 Tab

- 表格按 `finished_code` 分组，每行显示产成品编码、产成品名称、订单号标签列表
- 点击订单号标签 → 弹出 `el-dialog`（90vw）查看该订单的 BOM 详情
- 删除：`el-dropdown` 下拉选择具体订单，调 `DELETE /api/rd/cost/skus/:sku_id`

**BOM 详情对话框**：
- 标题含产成品编码、名称、订单号
- 列：序号（层级如 `1.1.2`）、品号（含版本，可点击打开物料抽屉）、品名规格、物料分类、供应商（首选）、用量、单价、合计
- 半成品可展开/收拢（默认折叠），▶/▼ 箭头；自制半成品价格=子件合计
- 第一级行（`_depth===0`）加粗
- 底部合计行：顶层行 `total_price` 之和，橙黄色高亮
- 按 `child_code` 排序

**导入流程**（两步）：
1. 选文件 → `POST /preview` → 预览树（含外购半成品标记）
2. 用户标记外购半成品（已导入的自动识别）→ `POST /import`（含 `purchased_semi_codes`）

### 物料查询 Tab

- 默认筛选 `node_type=material`，可切换半成品/成品
- 物料分类：`erp_code_rules` 前缀匹配（后端动态计算，不存储）
- 点击「详情」打开物料详情抽屉（右侧，默认 780px，左边缘可拖拽调整）

### 物料详情抽屉

**基本信息**：品号、含版品号、品名、规格、物料分类（只读）、外购半成品开关（仅半成品显示）、备注
**价格记录**：`cost_material_price` 表数据，含日期、订单号（关联快照）、单价、供应商（内联 `el-input` 可编辑，blur/Enter 触发 `PATCH /prices/:id`）、来源（BOM导入/手动）、删除操作
**使用记录**：`cost_bom_line` 关联记录，含快照日期、订单号、成品品号、数量、单价

### 关键注意事项
- `.nullslast()` 在 MySQL 不支持，`cost.py` 中所有 `order_by` 均不得使用此方法
- `_load_code_rules()` 在 `search_nodes` / `get_sku_bom` / `get_node` 中各自调用（无缓存，每次查 DB）
- `get_sku_bom` 返回 BOM 树时：批量查 `child_spec`、`supplier_name`（首选）、`material_category`；自制半成品 `total_price` 在 Python 侧计算（子件合计）
