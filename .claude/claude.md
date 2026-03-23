# 两平米软件库 · 项目上下文

## 维护规范
- 每次发生**架构调整、功能变更、接口变更、数据库结构变更**时，必须同步更新本文件，保持与代码实际状态一致。

## 技术栈
- **桌面端**：Electron + Vue 3 + Vite（electron-vite）
- **前端**：Vue 3 Composition API、Vue Router、Pinia、Element Plus、Axios
- **后端**：Python Flask + SQLAlchemy + PyMySQL + bcrypt + openpyxl
- **数据库**：MySQL（host: 47.99.100.138，库名: tmt_db）
- **存储**：阿里云 OSS（tmt-oss，华东1杭州）
- **更新**：electron-updater（generic provider）

## 项目结构
```
tmt-software/
├── electron/
│   ├── main/
│   │   ├── index.ts        # 主进程入口、IPC handlers
│   │   │                   # initUpdater 在 login-success 里调用
│   │   │                   # destroyUpdater 在 logout 里调用
│   │   │                   # minimize/maximize/unmaximize IPC handlers
│   │   ├── window.ts       # 窗口创建
│   │   │                   # 登录窗口：420×640，resizable:false
│   │   │                   # 主窗口：800×600，resizable:false
│   │   │                   # backgroundColor: #ede8dc，frame:false
│   │   ├── python.ts       # Flask子进程管理，端口8765
│   │   └── updater.ts      # electron-updater封装
│   │                       # autoDownload=false, forceDevUpdateConfig=true
│   └── preload/
│       └── index.ts        # contextBridge暴露electronAPI
├── src/
│   ├── main.js
│   ├── App.vue
│   ├── assets/
│   │   ├── author.png
│   │   ├── logo-banner.png
│   │   ├── icons/
│   │   │   ├── icon_table.png
│   │   │   ├── icon_image.png
│   │   │   └── icon_echart.png
│   │   └── images/
│   │       └── image_model_tip.png   # 型号简码说明图
│   ├── api/
│   │   └── http.js         # axios实例，baseURL固定127.0.0.1:8765，timeout:30000
│   │                       # 响应拦截器：res => res.data（已解一层）
│   │                       # 调用方直接用 res.success / res.data / res.message
│   ├── composables/
│   │   ├── usePermission.js      # 权限判断composable，见下方说明
│   │   ├── useSortable.js        # SortableJS 轻量封装，initSortable(el, onEnd)
│   │   ├── useFinishedImage.js   # 成品展开行图片/裁剪逻辑
│   │   └── useFinishedParams.js  # 成品展开行参数区逻辑（GROUP_DEFS 也从此导出）
│   ├── utils/
│   │   └── version.js      # checkUpdateType(current, latest) → 'none'|'optional'|'force'
│   ├── styles/
│   │   └── themes.css      # 全局CSS变量，主题A（奶油纸质，默认）
│   ├── routers/
│   │   └── index.js        # Hash路由
│   │                       # /login、/index、/product
│   │                       # /admin/users、/admin/permissions、/admin/version-release
│   ├── components/
│   │   ├── common/
│   │   │   ├── GToast.vue
│   │   │   └── WindowControls.vue  # top:11px，right:14px，z-index:10000
│   │   ├── user/
│   │   │   └── UserSettingsDrawer.vue
│   │   └── update/
│   │       └── UpdateDialog.vue
│   └── views/
│       ├── loginViews/
│       │   └── page-login.vue
│       ├── indexViews/
│       │   └── page-index.vue
│       ├── productViews/
│       │   ├── page-product.vue      # 主框架：顶部导航 + 概览/表格/图片/图表
│       │   ├── ProductTable.vue      # 表格视图
│       │   ├── FinishedExpandRow.vue # 成品展开行组件
│       │   ├── ProductImage.vue      # 图片视图（待开发）
│       │   ├── ProductImport.vue     # 导入ERP数据弹窗
│       │   ├── ProductRules.vue      # 编码规则弹窗
│       │   ├── ProductCategory.vue   # 分类管理弹窗
│       │   ├── ProductTag.vue        # 标签管理弹窗
│       │   └── ProductParam.vue      # 参数键名管理弹窗（概览页数据管理区入口）
│       └── adminViews/
│           ├── page-users.vue
│           ├── page-permissions.vue
│           └── page-version-release.vue
├── backend/
│   ├── app.py              # Flask工厂函数，注册蓝图
│   │                       # SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
│   ├── result.py           # Result.ok/fail → { success, message, data }
│   ├── .env
│   ├── database/
│   │   ├── base.py
│   │   ├── models/
│   │   │   ├── account/        __init__.py   User/Role/Permission
│   │   │   ├── version/        __init__.py   AppVersion
│   │   │   └── product/
│   │   │       ├── __init__.py               from . import param（注册模型到元数据）
│   │   │       ├── import_raw.py             ImportProductRaw
│   │   │       ├── erp_code_rules.py         ErpCodeRule
│   │   │       ├── category.py               ProductCategory/ProductSeries/ProductModel
│   │   │       ├── finished.py               ProductFinished/ProductPackaged/ProductTag
│   │   │       └── param.py                  ProductParamKey/ProductFinishedParam
│   │   └── repository/
│   │       ├── account/        __init__.py
│   │       ├── version/        __init__.py
│   │       └── product/
│   │           ├── import_raw.py
│   │           ├── erp_code_rules.py
│   │           ├── finished.py               FinishedRepository
│   │           ├── tag.py                    TagRepository
│   │           └── param.py                  ParamRepository
│   ├── services/
│   │   ├── account/        __init__.py   AccountService
│   │   ├── version/        __init__.py   VersionService
│   │   └── product/
│   │       ├── import_raw.py             ImportProductService
│   │       ├── erp_code_rules.py         ErpCodeRuleService
│   │       ├── tag.py                    TagService
│   │       └── param.py                  ParamService
│   ├── routes/
│   │   ├── account/        __init__.py   /api/account/*
│   │   ├── version/        __init__.py   /api/version/*
│   │   └── product/
│   │       ├── import_raw.py             /api/product/*
│   │       ├── finished.py               /api/product/finished/*
│   │       ├── erp_code_rules.py         /api/erp-code-rules/*
│   │       ├── category.py               /api/category/*
│   │       ├── tag.py                    /api/product/tags/*
│   │       └── param.py                  /api/product/params/*
│   └── storage/
│       └── client.py
├── dev-app-update.yml
├── electron-builder.yml
├── electron.vite.config.ts
└── package.json            # version: "1.0.1"
```

## 设计规范
- **背景色**：`#ede8dc`
- **主色**：`#c4883a`（棕金），hover：`#e09050`
- **卡片背景**：`#ffffff`
- **边框**：`#e0d4c0`
- **字体**：`'Microsoft YaHei UI', 'Microsoft YaHei', 'PingFang SC', 'Helvetica Neue', sans-serif`
- **等宽字体**：`'Microsoft YaHei UI', 'Microsoft YaHei', monospace`
- **圆角**：10px（输入框/按钮），12px（卡片）
- **CSS变量**统一在 `src/styles/themes.css` 管理，不硬编码颜色
- **z-index 层级**：强制更新遮罩(1000) < WindowControls(1500) < el-dialog(2000)
- **滚动条**：width:4px，透明轨道，border颜色thumb
- **图标**：导航/快捷操作用 PNG（`src/assets/icons/`），其他用 Element Plus 图标
- **文字颜色**：主文字`#3a3028`/`#2c2420`，次级`#6b5e4e`，辅助`#8a7a6a`
- **表格**：行底色`#fff`，hover `#faf7f2`，表头背景`#f5f0e8`

## Vue文件规范
- 文件顺序：`<script setup>` → `<template>` → `<style scoped>`
- script内分区注释：导入 / 响应式状态 / 计算属性 / 生命周期 / 方法
- 所有逻辑需要有注释
- **所有页面必须引入 WindowControls**
  - 登录页：`<WindowControls />`
  - 其他所有页面：`<WindowControls :confirm-close="true" confirm-text="确认退出两平米软件库？" />`
- Vite 中动态图片路径必须用 `import` 引入，不能在模板里写字符串 `@/...`
- Element Plus 图标统一从 `@element-plus/icons-vue` 引入

## electronAPI（preload暴露）
```typescript
window.electronAPI = {
  getApiBase, getVersion, loginSuccess, logout, quitApp,
  openExternal, showOpenDialog,
  minimizeApp:   () => void
  maximizeApp:   () => void
  unmaximizeApp: () => void
  updater: { check, download, install, on, off }
}
```

## HTTP 响应规范
```javascript
// 后端统一返回
{ success: true/false, message: '...', data: ... }

// 前端调用（axios已解一层）
const res = await http.get('/api/...')
if (res.success) { /* res.data */ }
else { errorMsg = res.message }
```

## 数据库表

### 账号
```
users             id, username, password(bcrypt), display_name, is_active, created_at, updated_at
roles             id, name, description
permissions       id, code, name, description
user_roles        user_id, role_id
role_permissions  role_id, permission_id
```

### 版本
```
app_version       id, version, description, download_url, created_at
```

### 产品库
```
import_product_raw
  id, code(UNIQUE), name, group_code, group_name, imported_at
  # Excel列：品号(0)/品名(1)/规格(2)/品号群组(7)/群组名称(8)
  # name = 品名（去除「（已停用）」）+ 规格

erp_code_rules
  id, prefix, type(finished/packaged/semi/material), description, created_at
  # UNIQUE(prefix, type)，同一前缀可对应多个类型，无优先级
  # type含义：finished=成品，packaged=产成品，semi=半成品，material=物料

product_category
  id, name(UNIQUE), sort_order, created_at

product_series
  id, category_id(FK), code(UNIQUE), name, sort_order, created_at

product_model
  id, series_id(FK), code(UNIQUE), name, name_en, model_code(UNIQUE), sort_order, created_at

product_finished
  id, code(UNIQUE), status, model_id(FK→product_model),
  listed_yymm, delisted_yymm, market(domestic/foreign/both),
  cover_image, created_at, updated_at
  # status: unrecorded=未录入, recorded=已录入, ignored=无需录入
  # market: domestic=内销, foreign=外贸, both=内外销

product_packaged
  id, code(UNIQUE), name, length, width, height,
  volume, gross_weight, net_weight, created_at, updated_at

product_finished_packaged
  finished_id(FK), packaged_id(FK), PRIMARY KEY(finished_id, packaged_id)

product_tag
  id, name(UNIQUE), color(default:#c4883a), created_at

product_finished_tag
  finished_id(FK), tag_id(FK), PRIMARY KEY(finished_id, tag_id)

product_param_key
  id, name(VARCHAR 64), group_name(VARCHAR 20), sort_order, created_at
  # group_name: dimension=尺寸, config=配置, brand=品牌, other=其他
  # UNIQUE(name, group_name)

product_finished_param
  id, finished_id(FK→product_finished CASCADE), key_id(FK→product_param_key CASCADE),
  value(VARCHAR 255), sort_order, created_at, updated_at
  # UNIQUE(finished_id, key_id)
  # 保存使用 Upsert（按 key_id 对比已有记录，更新/插入/删除）
```

## 后端接口（完整）
```
GET    /health

POST   /api/account/login
GET    /api/account/users
POST   /api/account/users
PUT    /api/account/users/:id
DELETE /api/account/users/:id
POST   /api/account/users/:id/roles/:id
DELETE /api/account/users/:id/roles/:id
GET    /api/account/roles
POST   /api/account/roles
DELETE /api/account/roles/:id
POST   /api/account/roles/:id/permissions/:code
GET    /api/account/permissions
POST   /api/account/permissions
PUT    /api/account/permissions/:id

GET    /api/version/latest
GET    /api/version/list
POST   /api/version/
POST   /api/version/upload

POST   /api/product/import/preview
POST   /api/product/import
GET    /api/product/stats
GET    /api/product/finished
POST   /api/product/finished
GET    /api/product/packaged/all
GET    /api/product/packaged/candidates
POST   /api/product/packaged
GET    /api/product/finished/:id/packaged
POST   /api/product/finished/:id/packaged/:id
DELETE /api/product/finished/:id/packaged/:id

GET    /api/erp-code-rules/
POST   /api/erp-code-rules/
PUT    /api/erp-code-rules/:id
DELETE /api/erp-code-rules/:id

GET    /api/category/tree
POST   /api/category/categories
PUT    /api/category/categories/:id
DELETE /api/category/categories/:id
POST   /api/category/series
PUT    /api/category/series/:id
DELETE /api/category/series/:id
POST   /api/category/models
PUT    /api/category/models/:id
DELETE /api/category/models/:id

GET    /api/product/tags/
POST   /api/product/tags/
PUT    /api/product/tags/:id
DELETE /api/product/tags/:id
POST   /api/product/tags/finished/:finished_id/:tag_id
DELETE /api/product/tags/finished/:finished_id/:tag_id

GET    /api/product/params/keys                       # 所有键名按分组聚合
POST   /api/product/params/keys                       # 创建键名 {name, group_name, sort_order?}
PUT    /api/product/params/keys/:key_id               # 更新键名
DELETE /api/product/params/keys/:key_id               # 删除键名（返回 usage_count 供前端二次确认）
GET    /api/product/params/finished/:finished_id      # 获取成品参数，按分组聚合
POST   /api/product/params/finished/:finished_id      # 全量 Upsert 保存成品参数
```

## OSS结构
```
tmt-oss/tmt-library/
├── releases/        latest.yml、setup-x.x.x.exe、*.blockmap
├── products/
│   ├── images/{product_id}/
│   └── documents/{product_id}/
└── avatars/
```
- 上传 key 格式：`tmt-library/releases/{filename}`（含前缀，勿省略 `tmt-library/`）
- OSS_BASE_URL=`https://tmt-oss.oss-cn-hangzhou.aliyuncs.com/tmt-library`

## 版本规则
- `Beta x.x.x` → 强制更新
- 主版本或次版本变更 → 强制更新
- 仅修订版变更 → 可选更新（红点提示）
- 当前版本：`1.0.1`

## 权限设计
```
product:view / product:edit / product:delete
shipping:view / shipping:edit / shipping:export
aftersale:view / aftersale:edit / aftersale:export
rd:view / rd:edit
```
- admin 角色后端直接放行
- **isAdmin 判断**：`userInfo.roles?.includes('admin')`（roles 是字符串数组）
- **login 返回的 userInfo 结构**：
  ```json
  { "id", "username", "display_name", "is_active",
    "roles": ["admin"],          // 字符串数组
    "permissions": ["product:edit", ...],  // 所有角色权限码去重合并
    "created_at" }
  ```
- username==='admin'：不可删除、不可禁用、不显示分配角色按钮

## usePermission composable
```javascript
// src/composables/usePermission.js
import { usePermission } from '@/composables/usePermission'
const { isAdmin, can, canEditProduct, canViewProduct, canDeleteProduct } = usePermission()

// can('product:edit') → true/false（admin直接返回true）
```

## page-product.vue 说明
- `onMounted`：调用 `maximizeApp()`
- 返回按钮：先 `unmaximizeApp()` 再 `router.back()`
- 顶部导航：概览(SVG inline) / 表格(PNG) / 图片(PNG) / 图表(PNG)
- active 状态：文字加粗 + 主色 + 底部2px橙色指示线，无背景填充
- 数据管理区：导入数据 / 编码规则 / 分类管理 / 标签管理 / **参数管理**
- **数据管理区需要 `product:edit` 权限才显示**（`v-if="canEditProduct"`）

## ProductTable.vue 说明
- 双表格布局：成品表（上）+ 产成品表（下）
- 成品表展开行：`<FinishedExpandRow :row="row" @saved="finishedStore.load()" />`
- `expandedCode = ref(null)`，`expandedKeys = computed(() => expandedCode.value ? [expandedCode.value] : [])`
- `:expand-row-keys="expandedKeys"`，`:row-key="r => r.code"`
- 动态列宽：canvas measureText，watch rawItems.length + onMounted 触发
- COL_DEFS 含 market 列（销售市场，排在上市年月前）
- FILTER_FIELDS 含 market
- MARKET_LABELS = `{ domestic: '内销', foreign: '外贸', both: '内外销' }`
- 排序：英文名称、系列名称、销售市场均有排序按钮；产成品清单、生命周期、状态不排序
- **产成品表**：`PK_COL_DEFS` + `pkColWidths`，watch `finishedStore.selectedPackaged` 触发动态列宽计算；`border` + `resizable` + `show-overflow-tooltip`

## FinishedExpandRow.vue 说明
- Props: `row`（Object）；Emits: `saved`
- **权限控制**：无 `product:edit` 权限时隐藏编辑/保存按钮，`···` 按钮始终显示（下载/复制/粘贴）
- **`···` 菜单**：复制（仅查看模式可用）/ 粘贴（仅编辑模式可用）；复制内容不含图片，含参数
- **composable 拆分**：
  - `useFinishedImage(props)` — 图片/裁剪逻辑（localCoverImage / savedCoverImage / cropperInst 等）
  - `useFinishedParams(props)` — 参数区逻辑（GROUP_DEFS 也从此导出）
- **布局**（宽度1000px）：
  ```
  ec-top（编码 + lc-badge + [编辑按钮] + ···按钮）
  ec-row（图片卡片238×238 | 信息卡片flex:1）
  ec-sections（折叠：参数/数据）
  ```
- **查看模式7行**：
  ```
  行1：中文名称（全宽）+ [内销tag if market=domestic/both]
  行2：英文名称（全宽）+ [外贸tag if market=foreign/both]
  行3：品类 / 系列编码 / 上市年月
  行4：型号编码 / 系列名称 / 退市年月
  行5：体积(m³) / 毛重(kg) / 净重(kg)
  行6：包装清单（全宽）
  行7：标签（全宽）
  ```
- **编辑模式7行**（行列结构与查看模式相同）：
  ```
  行1：el-autocomplete(中文名称) + 内销checkbox（最右）
  行2：el-autocomplete(英文名称) + 外贸checkbox（最右）
  行3：el-autocomplete(品类) / el-autocomplete(系列编码) / el-date-picker(上市年月)
  行4：el-autocomplete(型号编码[+?说明按钮]) / el-autocomplete(系列名称) / el-date-picker(退市年月)
  行5：体积/毛重/净重（只读）
  行6：包装清单（只读）
  行7：录入状态 select
  ```
- **型号简码说明按钮**：`?` 圆形按钮位于"型号简码"文字右侧，点击弹出 el-popover 显示 `src/assets/images/image_model_tip.png`
- **保存失败反馈**：`res.success` 为 false 或图片上传失败时 `ElMessage.error(res.message)`
- market checkbox → resolveMarket() → 'domestic'/'foreign'/'both'/''
- eg-lbl 宽80px，居中，背景#faf7f2，右边框分隔
- eg-row min-height:34px，不用固定height

## FinishedExpandRow 参数区说明
- **折叠区 ec-sections 包含两个子节**：参数 / 数据
- **参数节**：4个固定分组横排卡片（尺寸/配置/品牌/其他），由 `GROUP_DEFS` 定义
  - 分组定义（`useFinishedParams.js` 导出）：
    ```js
    { key: 'dimension', label: '尺寸', color: '#c4883a', bg: '#fff7ed' }
    { key: 'config',    label: '配置', color: '#3a7bc8', bg: '#edf4ff' }
    { key: 'brand',     label: '品牌', color: '#9c6fba', bg: '#f5eeff' }
    { key: 'other',     label: '其他', color: '#4a9a5a', bg: '#edf8ef' }
    ```
  - 参数项结构：`{ key_id, key_name, value, state: 'original'|'added'|'deleted' }`
  - `original` 项删除 → 标记红色+删除线+撤回按钮，保存时排除；`added` 项删除 → 直接移除
  - 支持拖动排序（SortableJS），sort_order = 保存时的数组下标
  - **独立编辑模式**：不进入主行编辑也可单独编辑参数（参数区右上角 ✎ 按钮）
  - 添加参数通过 el-dialog（el-select filterable allow-create + el-input），键名可选库中已有或自由输入
  - 键名库通过「参数管理」弹窗维护（page-product.vue 概览页数据管理区）
- **数据节**：占位，含两张卡片（发货数据 / 售后数据），待开发

## ProductParam.vue 说明
- 概览页数据管理区的「参数管理」按钮打开，需要 `product:edit` 权限
- 弹窗固定高度 400px，内容不随 Tab 切换变化
- 布局：顶部4个分组 Tab（尺寸/配置/品牌/其他）+ 左侧键名列表 + 右侧编辑表单
- 支持新增/编辑/排序/删除，删除前调接口返回 usage_count 做二次确认

## ProductTag.vue 说明
- 弹窗内容：左侧标签列表（220px）+ 右侧编辑表单
- 支持新增/编辑/删除，颜色选择器（8预设色 + 自定义）
- 接口路径注意加尾斜杠：`/api/product/tags/`（GET/POST），`/api/product/tags/:id`（PUT/DELETE）

## ProductRules.vue 说明
- 顶部筛选tabs：全部/成品/产成品/半成品/物料
- 表头固定，表体最大高度220px可滚动
- 新增/编辑表单内嵌在弹窗下方（卡片形式）
- 类型颜色：finished=#c4883a，packaged=#4a8fc0，semi=#9c6fba，material=#6ab47a

## page-users.vue / page-permissions.vue 注意事项
- `roles` 是字符串数组，不是对象数组
- isAdminUser: `row.roles?.includes('admin')`（不是 `.some(r => r.name === 'admin')`）
- 角色tag渲染：`:key="role"` `{{ role }}`（不是 `role.id` / `role.name`）
- handleAssignRole：先 loadRoles()，再通过 name 匹配 allRoles 里的 id
- role.permissions 是字符串数组（权限码），不是对象数组
- handleBindPermissions: `currentPerms.value = row.permissions || []`（不需要 map）

## UserSettingsDrawer.vue 注意事项
- isAdmin: `userInfo.value.roles?.includes('admin')`（不是 `.some(r => r.name === 'admin')`）

## Pinia Store 结构
```
src/stores/product/
├── index.js      # 产品库主store
├── finished.js   # 成品store（含FIELD_GETTER、filters含market、FILTER_FIELDS含market）
└── packaged.js   # 产成品store
```

## UI 页面设计职责（Frontend Developer）
涉及 UI 页面设计与实现时，须遵循以下原则（参考 `.claude/Frontend Developer.md`）：

### 核心要求
- **像素级还原**：严格按设计规范实现，颜色/间距/圆角/字体均以本文件「设计规范」为准
- **组件复用**：优先复用已有组件和样式类，复用率目标 > 80%，避免重复声明
- **用户体验**：交互状态（hover/focus/disabled/loading）必须完整，添加适当过渡动画（transition 0.15s~0.2s）
- **反馈清晰**：操作结果（成功/失败/加载中）必须有明确的视觉反馈

### 表单与弹窗规范
- 必填字段校验：提交前校验，错误信息就近显示（红色 `#d05a3c`，12px）
- Dialog 弹窗：`width` 根据内容合理设定，`:close-on-click-modal="false"`，有明确的取消/确认按钮
- 加载状态：按钮 `:disabled="submitting"`，文案改为「提交中…」/「保存中…」

### 可访问性
- 按钮须有语义（`button` 元素，非 `div`）
- 图标按钮须有 `title` 或 aria-label
- 键盘可操作：表单输入框支持 `@keyup.enter` 触发提交

### 性能
- 数据懒加载：下拉候选、分类树等在首次交互时加载，加载完成后缓存
- 列表渲染：合理使用 `:key`，避免不必要的重渲染

## /api/product/stats 返回结构
```json
{
  "total_finished":    <int>,   // 符合 finished 编码规则的 import 记录数
  "unprocessed":       <int>,   // total_finished - product_finished 表记录数
  "last_imported_at":  "YYYY-MM-DD" | null,
  "days_since_import": <int> | null,
  "categories": [
    { "description": "xxx", "count": <int> }   // 按 erp_code_rules description 分组，按数量降序
  ]
}
```

## 待开发
- [ ] FinishedExpandRow autocomplete 候选接真实数据（/api/category/tree）
- [ ] FinishedExpandRow 标签行接真实数据（/api/product/tags/）
- [ ] FinishedExpandRow 数据节：发货数据 / 售后数据（接真实数据）
- [ ] ProductImage 接真实数据（OSS 图片）
- [ ] 图表视图实现
- [ ] 用户头像
- [ ] 更多主题配色
- [ ] Mac打包验证