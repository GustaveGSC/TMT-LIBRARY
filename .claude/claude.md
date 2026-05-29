# 两平米软件库 · 项目上下文

## 维护规范
架构/功能/接口/数据库变更时必须同步更新**对应模块文档**（`.claude/modules/*.md`）。本文件只保留全项目共识、路径索引与设计规范，**不要把具体功能的实现细节、接口字段、表结构全文写进本文件**——那些内容写在对应 module 里，需要时再打开。
模块文档位于 `.claude/modules/`，按需读取：
- `database.md` — 数据库表结构
- `api.md` — 后端接口列表
- `frontend-product.md` — 产品库前端
- `frontend-data-mgmt.md` — 数据管理 & 发货图表
- `frontend-aftersale.md` — 售后数据（前端面板、简称/原因词典配置入口、与后端的交互说明）
- `frontend-admin.md` — 管理页注意事项
- `frontend-rdtools.md` — 研发工具页（ECR变更申请单、ECN变更通知单、变更提醒）

## 技术栈
- **桌面端**：Electron + Vue 3 + Vite（electron-vite）
- **Web 端**：同一套 Vue 代码，`npm run build:web` → `dist-web/`，部署于 47.99.100.138（nginx + gunicorn）
- **前端**：Vue 3 Composition API、Pinia、Element Plus、Axios
- **后端**：Python Flask + SQLAlchemy + PyMySQL，端口 8765
- **数据库**：MySQL（host: 47.99.100.138，库名: tmt_db）
- **存储**：阿里云 OSS（tmt-oss，华东1杭州）OSS_BASE_URL=`https://tmt-oss.oss-cn-hangzhou.aliyuncs.com/tmt-library`

## 关键路径
```
electron/main/index.ts   # 主进程、IPC、updater 生命周期；桌面端直连云端后端（不再启动本地 Flask）
electron/main/window.ts  # 登录窗 420×640 / 主窗 800×600，frame:false，bg:#ede8dc
electron/main/python.ts  # 已不使用（桌面端改为直连云端）
src/api/http.js          # axios；getBaseURL() 已 export：Electron→http://47.99.100.138，Web→VITE_API_BASE 或代理
src/routers/index.js     # Hash路由：/login /index /product /shipping /data-mgmt /aftersale /rd-tools /admin/*
src/styles/themes.css    # 全局CSS变量（勿硬编码颜色）
backend/app.py           # Flask 工厂；SQLAlchemy QueuePool(size=2, pre_ping, recycle=1800) + connect/read/write 超时（见源码）
backend/create_reason_keyword_rules.py  # 售后「原因词典」相关表初始化与种子数据（表结构见 database.md）
backend/create_ecr_reminders.py        # 研发工具「ECR提醒」相关表初始化与种子数据
backend/model_manager.py               # 模型/系列管理工具（研发工具辅助脚本）
backend/result.py        # Result.ok/fail → { success, message, data }
```

## 性能与负载规范

服务器资源有限（双核云主机 1.675GB RAM + QueuePool size=2），**每次后端开发必须评估 DB 查询数量**。

### 后端常见陷阱
- **N+1 查询**：访问 SQLAlchemy `lazy=True` 关系属性（如 `r.category_obj.name`）会对每个对象触发一次 SELECT。修法：用 `joinedload` / `selectinload`，或先 `with_entities` 批量拿 id 再一次性查关联表。
- **`get_cross_filter_options`**：每次调用 6 条 JOIN 查询，前端筛选变化时触发。不要在该函数里再加维度。
- **`get_chart_data`**：每次切 Tab / 下钻都触发一次，必须保持 O(维度数) 条查询，不能出现循环内 lazy load。
- **`auto_match`**：每次调用查全量 `AftersaleReason`，不要在循环或批量流程里频繁调用。

### 前端常见陷阱
- **`watch(x, fn)` 无防抖**：watch 立即触发 API 请求时，快速交互会打爆请求队列。非用户主动操作（如 drillDim 内部联动）的 watch 必须加防抖或用 `_isDrilling` 等 flag 跳过。
- **deep watch 触发面过宽**：`watch(filters, ..., { deep: true })` 任何子字段变化都会触发，注意叠加效果（一次操作可能同时触发 `loadCrossFilterOptions` + `loadChartData` 两个请求）。
- **两阶段加载**（cases + reasons）：页面打开时会连发 2 条查询，不要在轮询或频繁刷新场景里使用。

## 设计规范
| 用途 | 值 |
|---|---|
| 背景色 | `#ede8dc` |
| 主色 | `#c4883a`，hover `#e09050` |
| 卡片背景 | `#ffffff`，边框 `#e0d4c0` |
| 主文字 | `#3a3028` / `#2c2420` |
| 次级文字 | `#6b5e4e`，辅助 `#8a7a6a` |
| 表格行 | bg `#fff`，hover `#faf7f2`，表头 `#f5f0e8` |
| 圆角 | 输入框/按钮 10px，卡片 12px |
| 字体 | `'Microsoft YaHei UI', 'Microsoft YaHei', 'PingFang SC', sans-serif` |
| z-index | 强制更新遮罩 1000 < WindowControls 1500 < el-dialog 2000 |
| 滚动条 | width:4px，透明轨道 |
| 图标 | 导航用 PNG（`src/assets/icons/`），其他用 Element Plus 图标 |

## 多端开发规范

**优先级：Web 端 > 桌面端（Electron）**，新功能默认同时支持两端。

### 环境判断
```js
import { isElectron } from '@/utils/platform'
// isElectron = !!window.electronAPI
```
- 文件下载、本地对话框、窗口控制等功能用 `isElectron` 分支处理
- Web 端不可用的 Electron 专属功能需优雅降级（隐藏或禁用，不报错）

### 手机端适配规范
- 使用 `isMobile = ref(window.innerWidth <= 768)` + `resize` 监听检测，`onBeforeUnmount` 时移除监听
- 断点：`@media (max-width: 768px)`（竖屏手机），`@media (orientation: landscape) and (max-height: 600px)`（横屏手机）
- 手机端表格：`v-if="!isMobile"` 隐藏非核心列，保留核心标识列和状态列
- 手机端弹窗/抽屉：使用 `el-drawer direction="btt"` 替代 `el-dialog`，`isMobile` 判断切换
- iOS Safari 滚动：抽屉打开时需 `document.body.style.position = 'fixed'`，关闭时还原（否则 body `overflow:hidden` 会拦截固定元素内的触摸滚动）
- 全局 `html, body, #app { overflow: hidden }` 来自 `app.vue`，某页面需要滚动时在该页 `onMounted/onBeforeUnmount` 中临时修改 `document.documentElement/body.style.overflow`，不要改 `app.vue` 全局样式
- 部署后用 Chrome DevTools → 手机模拟器（375px/iPhone SE）验证竖屏和横屏

### 构建与部署
```bash
npm run build:web          # 构建 web 端 → dist-web/

# SSH 配置（C:\Users\gusta\.ssh\config）：
# Host tmt → HostName 47.99.100.138，User root，密钥 ~/.ssh/id_ed25519
# 服务器后端路径：/opt/tmt-library/backend/

# 前端部署（rsync，只传有变化的文件，比 scp -r 快）
rsync -az --checksum e:/Project/tmt-library/dist-web/. tmt:/var/www/tmt-library/
# ⚠️ 必须传完整 dist 目录，不能只传部分文件（Vite 每次构建所有 hash 都会变，只传部分会导致页面白屏）

# 后端部署（按需上传修改的文件，然后 reload）
scp e:/Project/tmt-library/backend/路径/__init__.py tmt:/opt/tmt-library/backend/路径/__init__.py
ssh tmt "systemctl reload gunicorn"
# ⚠️ 用 reload（SIGHUP 优雅替换 worker），不要用 fuser -k + restart（SIGKILL 冷启动会导致内存压力，SSH/VNC 卡死数小时）
# 注：服务器内存紧张（1.7GB，MySQL 占 ~400MB，gunicorn 占 ~190MB），冷启动需申请 190MB 但仅剩 ~120MB 空余
```

### dist-web 被 VS Code 锁定时的构建方法
```bash
# 临时改 vite.config.web.ts 的 outDir 为 dist-web-build，构建完改回来
# 或在 .vscode/settings.json 加：{ "files.exclude": { "dist-web": true } }
```

## Vue 文件规范
- 文件顺序：`<script setup>` → `<template>` → `<style scoped>`
- script 内分区注释：导入 / 响应式状态 / 计算属性 / 生命周期 / 方法，所有逻辑需注释
- 动态图片路径必须用 `import` 引入，不能在模板写字符串 `@/...`
- Element Plus 图标从 `@element-plus/icons-vue` 引入
- **所有页面必须引入 WindowControls**：
  - 登录页：`<WindowControls />`（showMaximize默认true，登录页不需要传）
  - 其他页：`<WindowControls :confirm-close="true" confirm-text="确认退出两平米软件库？" />`

## HTTP 响应规范
```javascript
// 后端统一返回 { success, message, data }
const res = await http.get('/api/...')
if (res.success) { /* use res.data */ } else { errorMsg = res.message }
```

## electronAPI（preload 暴露）
```typescript
window.electronAPI = {
  getApiBase, getVersion, loginSuccess, logout, quitApp, openExternal, showOpenDialog,
  minimizeApp, maximizeApp, unmaximizeApp,
  onMaximize(cb), onUnmaximize(cb),   // 主进程转发窗口事件
  showSaveDialog(options),             // 文件另存对话框 → { canceled, filePath }
  saveFile(filePath, data),            // 将 ArrayBuffer 写入本地文件（ECR 导出使用）
  updater: { check, download, install, on, off }
}
```

## 权限设计
权限码：`product:view/edit/delete`、`shipping:view/edit/export`、`aftersale:view/edit/export`、`rd:view/edit`
- rd 路由对应研发工具页（`/rd-tools`），权限码 `rd:view/edit`
- admin 角色后端直接放行；isAdmin 判断：`userInfo.roles?.includes('admin')`
- username==='admin' 或 'author'：不可删除/禁用，不显示分配角色按钮（后端拦截）
- author 账号：开发者专用，admin 权限，用户列表仅 author 登录时可见

```javascript
// usePermission composable
import { usePermission } from '@/composables/usePermission'
const { isAdmin, can, canEditProduct, canViewProduct, canDeleteProduct } = usePermission()
```

## 版本规则
- `Beta x.x.x` 或主/次版本变更 → 强制更新
- 仅修订版变更 → 可选更新（红点提示）
- 当前版本：`1.1.5`（以 package.json 为准）
- OSS上传 key 格式：`tmt-library/releases/{filename}`（含前缀）
