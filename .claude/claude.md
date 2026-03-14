# 两平米软件库 · 项目上下文

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
│   │   └── icons/
│   │       ├── icon_table.png
│   │       ├── icon_image.png
│   │       └── icon_echart.png
│   ├── api/
│   │   └── http.js         # axios实例，baseURL固定127.0.0.1:8765，timeout:30000
│   │                       # 响应拦截器：res => res.data（已解一层）
│   │                       # 调用方直接用 res.success / res.data / res.message
│   ├── composables/
│   │   └── usePermission.js  # 权限判断composable，见下方说明
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
│       │   └── ProductTag.vue        # 标签管理弹窗
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
│   │   │       ├── __init__.py               （空）
│   │   │       ├── import_raw.py             ImportProductRaw
│   │   │       ├── erp_code_rules.py         ErpCodeRule
│   │   │       ├── category.py               ProductCategory/ProductSeries/ProductModel
│   │   │       └── finished.py               ProductFinished/ProductPackaged/ProductTag
│   │   └── repository/
│   │       ├── account/        __init__.py
│   │       ├── version/        __init__.py
│   │       └── product/
│   │           ├── import_raw.py
│   │           ├── erp_code_rules.py
│   │           ├── finished.py               FinishedRepository
│   │           └── tag.py                    TagRepository
│   ├── services/
│   │   ├── account/        __init__.py   AccountService
│   │   ├── version/        __init__.py   VersionService
│   │   └── product/
│   │       ├── import_raw.py             ImportProductService
│   │       ├── erp_code_rules.py         ErpCodeRuleService
│   │       └── tag.py                    TagService
│   ├── routes/
│   │   ├── account/        __init__.py   /api/account/*
│   │   ├── version/        __init__.py   /api/version/*
│   │   └── product/
│   │       ├── import_raw.py             /api/product/*
│   │       ├── finished.py               /api/product/finished/*
│   │       ├── erp_code_rules.py         /api/erp-code-rules/*
│   │       ├── category.py               /api/category/*
│   │       └── tag.py                    /api/product/tags/*
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
- 数据管理区：导入数据 / 编码规则 / 分类管理 / 标签管理
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

## FinishedExpandRow.vue 说明
- Props: `row`（Object）；Emits: `saved`
- **权限控制**：无 `product:edit` 权限时隐藏编辑/保存按钮，`···` 按钮始终显示（下载/复制/粘贴）
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
  行7：标签（全宽，暂未定义）
  ```
- **编辑模式7行**（行列结构与查看模式相同）：
  ```
  行1：el-autocomplete(中文名称) + 内销checkbox（最右）
  行2：el-autocomplete(英文名称) + 外贸checkbox（最右）
  行3：el-autocomplete(品类) / el-autocomplete(系列编码) / el-date-picker(上市年月)
  行4：el-autocomplete(型号编码) / el-autocomplete(系列名称) / el-date-picker(退市年月)
  行5：体积/毛重/净重（只读）
  行6：包装清单（只读）
  行7：录入状态 select
  ```
- market checkbox → resolveMarket() → 'domestic'/'foreign'/'both'/''
- eg-lbl 宽80px，居中，背景#faf7f2，右边框分隔
- eg-row min-height:34px，不用固定height

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

## 待开发
- [ ] 概览页接真实数据（调用 /api/product/stats，分类数量）
- [ ] FinishedExpandRow autocomplete 候选接真实数据（/api/category/tree）
- [ ] FinishedExpandRow 标签行接真实数据（/api/product/tags/）
- [ ] ProductImage 接真实数据（OSS 图片）
- [ ] 图表视图实现
- [ ] 用户头像
- [ ] 更多主题配色
- [ ] Mac打包验证