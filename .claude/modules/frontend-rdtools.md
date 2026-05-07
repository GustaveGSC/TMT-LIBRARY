# 研发工具页（frontend-rdtools）

## 路由与入口

| 项 | 值 |
|---|---|
| 路由 | `/rd-tools` |
| 页面组件 | `src/views/rdToolsViews/page-rd-tools.vue` |
| 权限码 | `rd:view`（查看）、`rd:edit`（编辑）、`rd:admin`（管理变更提醒） |
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

图标使用 `@phosphor-icons/vue`（`PhHouseLine / PhArrowsLeftRight / PhClipboardText / PhBell`）。

---

## PDM 转 BOM（PdmToBomForm.vue）

`src/components/rdTools/PdmToBomForm.vue`，4态状态机：`idle → processing → error/ready`。

### 工作流程

1. 点击「选择文件」→ `electronAPI.showOpenDialog`（仅 `.xlsx`）
2. 点击「处理」→ `POST /api/rd/pdm2bom/process`（发送本地文件路径）
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

`src/components/rdTools/EcrForm.vue`，整体布局为左右双列 + 底部固定提醒区。

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
- 通过 `window.electronAPI.showOpenDialog` 选择文件（本地路径）
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

### 变更提醒区（底部固定）

- 从 `GET /api/rd/reminders` 加载在架提醒
- 所有在架提醒必须**全部勾选**才能通过导出校验
- `canAdminRd` 用户可打开「管理变更提醒」弹窗（新建 / 下架 / 重新上架）

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
| POST | `/ecr/compare-bom` | `rd:view` | 比对两份 BOM，返回 `{ changes, stats }` |
| GET | `/reminders` | `rd:view` | 返回所有在架提醒 |
| GET | `/reminders/all` | `rd:admin` | 返回全部提醒（含下架历史） |
| POST | `/reminders` | `rd:admin` | 新建变更提醒 |
| PUT | `/reminders/<id>` | `rd:admin` | 编辑提醒内容/备注 |
| PUT | `/reminders/<id>/deactivate` | `rd:admin` | 下架提醒（软删除） |
| PUT | `/reminders/<id>/activate` | `rd:admin` | 重新上架提醒 |

`rd:admin` 权限通过请求头 `X-User-Roles` / `X-User-Permissions` 透传，前端在每次需要鉴权的调用中手动注入：
```js
headers: { 'X-User-Roles': roles.join(','), 'X-User-Permissions': permissions.join(',') }
```

---

## 数据库

| 表 | 模型 | 文件 |
|---|---|---|
| `ecr_reminder` | `EcrReminder` | `backend/database/models/rd/__init__.py` |

字段：`id / content / notes / is_active / created_by / created_at / updated_at`

建表脚本：`backend/create_ecr_reminders.py`

---

## preload API 补充

ECR/ECN 导出新增了两个 preload 方法（CLAUDE.md 未列出）：

```typescript
window.electronAPI.showSaveDialog(options)  // → { canceled, filePath }
window.electronAPI.saveFile(filePath, data) // 将 ArrayBuffer 写入本地文件
```
