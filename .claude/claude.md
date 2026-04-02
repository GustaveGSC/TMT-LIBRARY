# 两平米软件库 · 项目上下文

## 维护规范
- 每次发生**架构调整、功能变更、接口变更、数据库结构变更**时，必须同步更新本文件及相关模块文件，保持与代码实际状态一致。
- 模块详细文档位于 `.claude/modules/`，按需读取：
  - `database.md` — 数据库表结构（账号/版本/发货/售后/产品库）
  - `api.md` — 后端接口完整列表 + /api/product/stats 返回结构
  - `frontend-product.md` — 产品库前端组件（page-product/ProductTable/FinishedExpandRow/ProductChart/ProductImage/ProductParam/ProductTag/ProductRules/Pinia Store）
  - `frontend-data-mgmt.md` — 数据管理 & 发货图表（page-data-mgmt/DataImport/ReturnImport/OperatorConfig/WarehouseConfig/page-shipping/ShippingDashboard）
  - `frontend-aftersale.md` — 售后数据前端（page-aftersale/AftersaleProcess/AftersaleReasonLib/AftersaleDashboard/AftersaleTable）
  - `frontend-admin.md` — 管理页注意事项（page-users/page-permissions/UserSettingsDrawer）

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
│   │   │                   # 主窗口：800×600，resizable:true，minWidth/minHeight:800/600
│   │   │                   # backgroundColor: #ede8dc，frame:false
│   │   ├── python.ts       # Flask子进程管理，端口8765
│   │   │                   # stopPython 用 spawnSync taskkill（同步，确保退出前 backend 已停）
│   │   └── updater.ts      # electron-updater封装
│   │                       # autoDownload=false, forceDevUpdateConfig=true
│   │                       # quitAndInstall 前先调 stopPython()
│   └── preload/
│       └── index.ts        # contextBridge暴露electronAPI
├── src/
│   ├── main.js
│   ├── App.vue
│   ├── assets/
│   │   ├── author.png
│   │   ├── logo-banner.png
│   │   ├── icons/          # icon_table.png / icon_image.png / icon_echart.png
│   │   └── images/
│   │       └── image_model_tip.png   # 型号简码说明图
│   ├── api/
│   │   └── http.js         # axios实例，baseURL固定127.0.0.1:8765，timeout:30000
│   │                       # 响应拦截器：res => res.data（已解一层）
│   ├── composables/
│   │   ├── usePermission.js
│   │   ├── useSortable.js
│   │   ├── useFinishedImage.js
│   │   └── useFinishedParams.js
│   ├── utils/
│   │   └── version.js      # checkUpdateType(current, latest) → 'none'|'optional'|'force'
│   ├── styles/
│   │   └── themes.css      # 全局CSS变量，主题A（奶油纸质，默认）
│   ├── routers/
│   │   └── index.js        # Hash路由
│   │                       # /login、/index、/product、/shipping、/data-mgmt
│   │                       # /admin/users、/admin/permissions、/admin/version-release
│   ├── components/
│   │   ├── common/         # GToast.vue / WindowControls.vue
│   │   ├── user/           # UserSettingsDrawer.vue
│   │   └── update/         # UpdateDialog.vue
│   └── views/
│       ├── loginViews/     # page-login.vue
│       ├── indexViews/     # page-index.vue
│       ├── productViews/   # page-product / ProductTable / FinishedExpandRow / ProductImage / ProductImport / ProductRules / ProductCategory / ProductTag / ProductParam
│       ├── shippingViews/  # page-shipping / ShippingDashboard
│       ├── dataMgmtViews/  # page-data-mgmt / DataImport / ReturnImport / OperatorConfig / WarehouseConfig
│       ├── aftersaleViews/ # page-aftersale / AftersaleProcess / AftersaleReasonLib / AftersaleDashboard / AftersaleTable
│       └── adminViews/     # page-users / page-permissions / page-version-release
├── backend/
│   ├── app.py              # Flask工厂函数，注册蓝图
│   │                       # POOL_SIZE=5, MAX_OVERFLOW=10, POOL_RECYCLE=120s
│   │                       # pool_pre_ping=True, connect/read/write_timeout=10/30/30s
│   ├── result.py           # Result.ok/fail → { success, message, data }
│   ├── database/
│   │   ├── models/         # account / version / shipping / aftersale / product
│   │   └── repository/     # account / version / shipping / aftersale / product
│   ├── services/           # account / version / shipping / aftersale / product
│   ├── routes/             # account / version / shipping / aftersale / product
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
  minimizeApp:    () => void
  maximizeApp:    () => void
  unmaximizeApp:  () => void
  onMaximize:     (cb: () => void) => void   // 主进程转发 maximize 事件
  onUnmaximize:   (cb: () => void) => void   // 主进程转发 unmaximize 事件
  updater: { check, download, install, on, off }
}
```

## WindowControls Props
```
confirmClose  Boolean  default:false  关闭是否需要二次确认
confirmText   String   default:'确认退出两平米软件库？'
showMaximize  Boolean  default:true   是否显示最大化按钮（登录页传 false）
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
- 当前版本：`1.0.1`（package.json 以实际为准）

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
- username==='admin' 或 'author'：不可删除、不可禁用、不显示分配角色按钮（后端 service 层拦截）
- **author 账号**：开发者专用，admin 权限；用户列表仅 author 登录时可见；首页 `disabled:true` 的模块对 author 解锁显示

## usePermission composable
```javascript
import { usePermission } from '@/composables/usePermission'
const { isAdmin, can, canEditProduct, canViewProduct, canDeleteProduct } = usePermission()
// can('product:edit') → true/false（admin直接返回true）
```

## UI 页面设计职责（Frontend Developer）

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

## 待开发
- [ ] FinishedExpandRow autocomplete 候选接真实数据（/api/category/tree）
- [ ] FinishedExpandRow 标签行接真实数据（/api/product/tags/）
- [ ] FinishedExpandRow 数据节：发货数据 / 售后数据（接 /api/shipping/* 真实数据）
- [ ] ProductImage cover_image 接真实 OSS 图片 URL
- [x] ShippingDashboard 图表完善（bar/line/pie/map/同比/环比，按渠道/省份/时间/产品维度，含自定义分组、下钻面包屑、地图 Top10 面板、工具区）
- [x] 销退清单导入（/api/shipping/import/return，ReturnImport.vue，独立 return_record 表）
- [x] 售后数据模块（AftersaleProcess / AftersaleDashboard / AftersaleTable / AftersaleReasonLib，/api/aftersale/*）
- [ ] 产品库图表视图实现
- [ ] 用户头像
- [ ] 更多主题配色
- [ ] Mac打包验证
