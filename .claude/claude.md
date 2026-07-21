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
- **桌面端（已暂停，2026-07-21）**：Electron + Vue 3 + Vite（electron-vite）。决策：正式停止支持现有 Electron 客户端，代码保留但不再投入新功能开发或验证，不制作/发布新安装包，详见 `handoff/2026-07-21-electron-support-end-decision.md`。新功能默认只需支持 Web 端，不用再兼容 Electron。
- **Web 端**：同一套 Vue 代码，`npm run build:web` → `dist-web/`，部署于 tmt-library.cn（nginx + gunicorn，HTTPS）
- **前端**：Vue 3 Composition API、Pinia、Element Plus、Axios
- **后端**：Python Flask + SQLAlchemy + PyMySQL，端口 8765
- **数据库**：MySQL（host: 47.99.100.138，库名: tmt_db）
- **存储**：阿里云 OSS（tmt-oss，华东1杭州）OSS_BASE_URL=`https://tmt-oss.oss-cn-hangzhou.aliyuncs.com/tmt-library`

## 关键路径
```
electron/main/index.ts   # 主进程/IPC（桌面端已暂停，代码保留不再维护）
electron/main/window.ts  # 登录窗/主窗（桌面端已暂停，代码保留不再维护）
electron/main/python.ts  # 已不使用
src/api/http.js          # axios；getBaseURL() 已 export：Electron→https://tmt-library.cn，Web→VITE_API_BASE 或代理
src/routers/index.js     # Hash路由：/login /index /product /shipping /data-mgmt /aftersale /rd-tools /admin/*
src/styles/themes.css    # 全局CSS变量（勿硬编码颜色）
backend/app.py           # Flask 工厂；SQLAlchemy QueuePool + connect/read/write 超时（见源码）
                          # 生产：1 个 Gunicorn worker，POOL_SIZE=5 + MAX_OVERFLOW=5（.env 显式配置），单进程理论峰值 10 个数据库连接
backend/create_reason_keyword_rules.py  # 售后「原因词典」相关表初始化与种子数据（表结构见 database.md）
backend/create_ecr_reminders.py        # 研发工具「ECR提醒」相关表初始化与种子数据
backend/model_manager.py               # 模型/系列管理工具（研发工具辅助脚本）
backend/result.py        # Result.ok/fail → { success, message, data }
```

## 性能与负载规范

服务器资源有限（双核云主机 1.675GB RAM，单 Gunicorn worker，QueuePool 5+5 共 10 连接上限），**每次后端开发必须评估 DB 查询数量**。

### 后端常见陷阱
- **N+1 查询**：访问 SQLAlchemy `lazy=True` 关系属性（如 `r.category_obj.name`）会对每个对象触发一次 SELECT。修法：用 `joinedload` / `selectinload`，或先 `with_entities` 批量拿 id 再一次性查关联表。
- **`get_cross_filter_options`**：每次调用 6 条 JOIN 查询，前端筛选变化时触发。不要在该函数里再加维度。
- **`get_chart_data`**：每次切 Tab / 下钻都触发一次，必须保持 O(维度数) 条查询，不能出现循环内 lazy load。
- **`auto_match`**：每次调用查全量 `AftersaleReason`，不要在循环或批量流程里频繁调用。
- **`shipping_order_finished` 低选择性索引**：`source` 列仅 2 个值（shipping/finance），MySQL 优化器不自动选复合索引。所有对该表的查询必须加 `with_hint(sof, 'USE INDEX (...)', dialect_name='mysql')`：有日期范围用 `ix_sof_source_date`，否则用 `ix_sof_source_finished_code`。
- **`get_chart_options` 缓存**：该函数结果已做模块级内存缓存（5 分钟 TTL，key=source+日期范围）。导入/resolve-all 完成后必须调 `_invalidate_chart_options_cache()` 清缓存，否则新数据不生效。
- **trade_type 过滤禁止走 JOIN**：`needs_trade_filter` 不得触发 JOIN 产品表。FTP 系列判断通过 `_get_ftp_finished_codes()` 缓存集合 + `finished_code IN (...)` 实现，避免每次查询都 JOIN ProductModel/ProductSeries。

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

**桌面端（Electron）已暂停（2026-07-21），新功能默认只需支持 Web 端**，不用再兼容 Electron。以下 `isElectron` 相关说明保留供桌面端代码本身参考（不删除现有代码），新功能不需要按此分支处理。

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

# 前端部署（本机 Git Bash 没有 rsync，用 tar+scp+服务器端解压覆盖）
cd e:/Project/tmt-library
tar -czf /tmp/dist-web-deploy.tar.gz -C dist-web .
scp /tmp/dist-web-deploy.tar.gz tmt:/tmp/dist-web-deploy.tar.gz
ssh tmt "mkdir -p /tmp/dist-web-new && tar xzf /tmp/dist-web-deploy.tar.gz -C /tmp/dist-web-new \
  && cp -r /var/www/tmt-library /var/www/tmt-library.old \
  && rm -rf /var/www/tmt-library/* && cp -r /tmp/dist-web-new/. /var/www/tmt-library/ \
  && rm -rf /tmp/dist-web-new /tmp/dist-web-deploy.tar.gz"
# 验证线上首页 index.html 里的 assets/index-*.js hash 和本地构建一致后，再删 /var/www/tmt-library.old
# ⚠️ 必须传完整 dist 目录，不能只传部分文件（Vite 每次构建所有 hash 都会变，只传部分会导致页面白屏）

# 后端部署（按需上传修改的文件，然后 reload）
scp e:/Project/tmt-library/backend/路径/__init__.py tmt:/opt/tmt-library/backend/路径/__init__.py
ssh tmt "systemctl reload gunicorn"
# ⚠️ 用 reload（SIGHUP 优雅替换 worker），不要用 fuser -k + restart（SIGKILL 冷启动会导致内存压力，SSH/VNC 卡死数小时）
# ⚠️ reload 后不要只看一次 `systemctl is-active`——worker 可能先报 active 后台再崩溃重启循环。
#    要等几秒后再查一遍 `systemctl status` + `journalctl -u gunicorn -n 20`，确认 master 进程没有变化、无崩溃退出记录
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

## electronAPI（preload 暴露，桌面端已暂停，仅存档）
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
权限码：`product:view/edit`、`shipping:view/edit/export`、`aftersale:view/edit/export`、`rd:view/edit`
- rd 路由对应研发工具页（`/rd-tools`），权限码 `rd:view/edit`
- admin 角色后端直接放行；isAdmin 判断：`userInfo.roles?.includes('admin')`
- username==='admin' 或 'author'：不可删除/禁用，不显示分配角色按钮（后端拦截）
- author 账号：开发者专用，admin 权限，用户列表仅 author 登录时可见

```javascript
// usePermission composable
import { usePermission } from '@/composables/usePermission'
const { isAdmin, can, canEditProduct, canViewProduct } = usePermission()
```

## 版本规则
- `Beta x.x.x` 或主/次版本变更 → 强制更新
- 仅修订版变更 → 可选更新（红点提示）
- 当前版本以 `package.json` 的 `version` 字段为准，本文件不再手工复制具体版本号（历史上出现过手工复制的数字过期没同步的问题）
- OSS上传 key 格式：`tmt-library/releases/{filename}`（含前缀）
