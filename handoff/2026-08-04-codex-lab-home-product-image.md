# 手控器主页产品图替换交接

日期：2026-08-04  
执行方：Codex  
接收方：Claude Code（审核与部署）

## 完成内容

- 将用户提供的 `C:\Users\gusta\Desktop\112_0013.png` 替换为手控器主页中央产品图。
- 按原图透明像素边界无损裁切，从 1600×2000 整理为 1292×932，去除大面积透明留白。
- 保留原始透明通道、产品完整轮廓和现有屏幕内等比缩放方式。

## 修改文件

- `src/assets/lab/desk-home.png`

## 验证

- 已检查替换后 PNG，产品轮廓完整且透明背景正常。
- `npm.cmd run build:web` 构建通过（Vite 5.4.21，3971 modules transformed）。

## Claude 待办

- 审核 320×240 屏幕主页内的最终显示大小。
- 审核通过后部署完整 `dist-web/`；Codex 未执行部署。
