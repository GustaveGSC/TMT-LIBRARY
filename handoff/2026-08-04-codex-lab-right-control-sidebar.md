# 模拟手控系统右侧控制台布局交接

日期：2026-08-04  
执行方：Codex  
接收方：Claude Code（审核与部署）

## 完成内容

- 将基础控制、持久状态、触发状态、身份模拟从手控器下方移至页面右侧。
- 页面调整为“左侧设备演示区 + 右侧状态控制台”的桌面双栏布局。
- 左侧统一容纳氛围灯、手控器和时间流速，并在可用高度内垂直居中。
- 右侧控制台改为紧凑单列卡片，缩减卡片间距和内边距，保证常见桌面视口无需上下滚动即可完整操作。
- 1080px 以下自动回落为上下布局；回落时控制卡片恢复双列，760px 以下再改为单列。
- 状态栏通知铃铛统一改为黑色。
- 触发型状态不再提供“运动前提”人工选择；运动状态保留在 store 中，供后续屏幕升降/倾斜操作自动写入和判断。
- 遇阻按钮仍严格依赖实际运动状态，设备静止时不可触发。

## 修改文件

- `src/views/labViews/page-lab.vue`
- `src/components/lab/HandsetControlPanel.vue`
- `src/components/lab/HandsetDevice.vue`
- `src/stores/lab/handset.js`

## 验证

- `npm.cmd run build:web` 构建通过（Vite 5.4.21，3971 modules transformed）。
- 仅有项目原有的大 chunk 警告，无新增编译错误。

## Claude 待办

- 在目标 Electron/桌面窗口尺寸下审核右侧控制台的实际间距。
- 审核通过后按项目纪律部署完整 `dist-web/`。
- Codex 未执行部署。
