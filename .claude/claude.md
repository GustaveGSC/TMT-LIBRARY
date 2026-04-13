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

## 技术栈
- **桌面端**：Electron + Vue 3 + Vite（electron-vite）
- **前端**：Vue 3 Composition API、Pinia、Element Plus、Axios
- **后端**：Python Flask + SQLAlchemy + PyMySQL，端口 8765
- **数据库**：MySQL（host: 47.99.100.138，库名: tmt_db）
- **存储**：阿里云 OSS（tmt-oss，华东1杭州）OSS_BASE_URL=`https://tmt-oss.oss-cn-hangzhou.aliyuncs.com/tmt-library`

## 关键路径
```
electron/main/index.ts   # 主进程、IPC、updater 生命周期
electron/main/window.ts  # 登录窗 420×640 / 主窗 800×600，frame:false，bg:#ede8dc
electron/main/python.ts  # Flask 子进程，退出用 spawnSync taskkill
src/api/http.js          # axios baseURL:127.0.0.1:8765，拦截器已解一层 res.data
src/routers/index.js     # Hash路由：/login /index /product /shipping /data-mgmt /aftersale /admin/*
src/styles/themes.css    # 全局CSS变量（勿硬编码颜色）
backend/app.py           # Flask 工厂；SQLAlchemy NullPool + connect/read/write 超时（见源码）
backend/create_reason_keyword_rules.py  # 售后「原因词典」相关表初始化与种子数据（表结构见 database.md）
backend/result.py        # Result.ok/fail → { success, message, data }
```

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
  updater: { check, download, install, on, off }
}
```

## 权限设计
权限码：`product:view/edit/delete`、`shipping:view/edit/export`、`aftersale:view/edit/export`、`rd:view/edit`
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
- 当前版本：`1.0.3`（以 package.json 为准）
- OSS上传 key 格式：`tmt-library/releases/{filename}`（含前缀）
