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
| `pdm2bom` | PDM转BOM | — | 即将上线（占位） |
| `ecr` | 变更申请单填写 | `EcrForm.vue` | 已上线 |
| `ecn` | 变更通知单填写 | — | 即将上线（占位） |

图标使用 `@phosphor-icons/vue`（`PhHouseLine / PhArrowsLeftRight / PhClipboardText / PhBell`）。

---

## ECR 变更申请单（EcrForm.vue）

`src/components/rdTools/EcrForm.vue`，整体布局为左右双列 + 底部固定提醒区。

### 表单字段

| 字段 | 说明 |
|---|---|
| `issuing_unit` | 发出单位（默认「研发部」） |
| `date` | 日期（自动填今日，禁止编辑） |
| `ecr_code` | 变更编码，格式 `ECR.YYYYMMDD-NN`，由 `sessionStorage` 管理当日序号，挂载时预生成（不消耗序号），导出时正式消耗 |
| `project` | 变更项目名称 |
| `change_type` | 变更类型：设计变更 / 制程变更 / 其他（其他需补充说明） |
| `distribution` | 分发单位（多选）：研发/业务/采购/生产/生管/品牌/服务/品管 |
| `change_reason` | 变更原因（单选）：品质不良/价格变动/设计优化/结构优化/成本优化/工艺优化/其他 |
| `change_subject` | 变更主题（textarea） |
| `change_desc` | 变更内容说明（textarea） |

### BOM 比对（右列）

- 支持多个变更组（`bomGroups`），每组独立选择「变更前」和「变更审核中」两个 `.xlsx` 文件
- 通过 `window.electronAPI.showOpenDialog` 选择文件（本地路径）
- 比对结果须手动确认（`confirmed = true`）后才纳入预览/导出
- `allChanges` 计算属性汇总所有已确认组的变更行

**BOM 文件格式要求**（后端校验）：
- 必要列：`层次 / 图号 / 品名 / 规格 / 数量 / 单位 / 状态`
- 变更前：状态列全部为「已发布」
- 变更审核中：状态列不能全是「已发布」

**版本号推算规则**：
- 图号格式：`{编码}-{版本号}`，版本号如 `A01`（字母+数字）
- 通用变更审核中 → 数字+1：`A01 → A02`
- 非通用变更审核中 → 字母+1，数字重置01：`A01 → B01`

### 变更提醒区（底部固定）

- 从 `GET /api/rd/reminders` 加载在架提醒
- 所有在架提醒必须**全部勾选**才能通过导出校验（`validate()`）
- 勾选状态存于 `reminderChecked`（reactive，session 内有效，不持久化）
- `canAdminRd` 用户可打开「管理变更提醒」弹窗（新建 / 下架 / 重新上架）

### 预览 & 导出

- **预览**：弹窗内渲染申请单样式（HTML 表格，宽1200px）
- **导出 XLSX**：
  1. 调用 `POST /api/rd/ecr/export`，响应为 `arraybuffer`（非标准 JSON）
  2. 调用 `window.electronAPI.showSaveDialog` 让用户选择保存路径
  3. 调用 `window.electronAPI.saveFile(filePath, data)` 写入本地文件
- http.js 请求需设置 `{ responseType: 'arraybuffer' }`，此时 res 直接是 ArrayBuffer，不经过 `{ success, data }` 解包

---

## 后端接口（prefix: `/api/rd`）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/ecr/export` | `rd:view` | 生成 ECR xlsx，返回 arraybuffer |
| POST | `/ecr/compare-bom` | `rd:view` | 比对两份 BOM，返回 `{ changes, stats }` |
| GET | `/reminders` | `rd:view` | 返回所有在架提醒 |
| GET | `/reminders/all` | `rd:admin` | 返回全部提醒（含下架历史） |
| POST | `/reminders` | `rd:admin` | 新建变更提醒 |
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

ECR 导出新增了两个 preload 方法（CLAUDE.md 未列出）：

```typescript
window.electronAPI.showSaveDialog(options)  // → { canceled, filePath }
window.electronAPI.saveFile(filePath, data) // 将 ArrayBuffer 写入本地文件
```
