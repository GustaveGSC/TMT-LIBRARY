# 模拟手控系统 · 氛围光背景与四向滑动键交接

日期：2026-08-04
状态：本地实现、Playwright 交互核验和 Web 构建完成，未部署

## 氛围灯

- 修改 `src/components/lab/AmbientLightStrip.vue`。
- 漫反射从灯带上方的局部光团改为围绕灯带上下展开的整片背景光场。
- wide/core 两层背景与灯珠均使用 4.2 秒动画周期，色序统一为蓝、青、绿、暖黄、橙红；背景色带与灯珠跑马同步变化。
- 关闭时背景透明、灯珠暗灭；灯带实体保持可见。

## 四向滑动模拟键

- 修改 `src/components/lab/HandsetDevice.vue` 与 `src/components/lab/handsetIconify.js`。
- 手控器左侧新增上、下、左、右四个实体按键，采用独立黑色磨砂底座、倒角键帽、内外阴影、悬停与按压下沉反馈。
- 新增 Iconify MDI `chevron-left` / `chevron-right` 静态图标数据；上下键复用现有 Iconify 图标。
- 屏幕黑屏时方向键禁用；屏幕唤醒后点击方向键，主页内容按相应方向位移并淡化后回弹，模拟滑动手势。
- 动画通过组件内临时 `swipeDirection` 状态实现，约 420ms 自动清除，不修改 Pinia 状态机，也不改变屏幕内容或分辨率。
- 手控器整体展示容器扩宽 86px，外壳右移，为左侧方向键预留真实布局空间。

## 验证

- `npm.cmd run build:web`：通过，3971 modules transformed。
- Playwright 打开 `/lab`，开启屏幕及氛围灯后截图确认布局无重叠。
- 点击“模拟向左滑动”后 50ms：屏幕 class 包含 `swipe-left`；450ms 后已自动清除。
- `.handset-screen` 仍为严格 `320×240`。

## 交给 Claude

- 审核四向键在最终部署页面的按压手感和光场动画同步观感。
- 部署完整 `dist-web/`。

## 四向键视觉简化

- 按用户反馈删除四向键底部整块黑色底座和中央圆点。
- 四颗键帽改为完全独立展示；上下间隔扩大至 18px 左右，左右键之间保留明显空隙。
- 按键组内部尺寸调整为 134×174px，0.55 缩放后的高度约 95.7px；顶部定位为 47px。
- Playwright 实测按键组中心 `339.8500`、手控器外壳中心 `339.8750`，垂直中心误差约 0.025px；按键与外壳水平间距约 12.3px。
- `npm.cmd run build:web`：通过，3971 modules transformed。
