# 模拟手控系统 · 手控器外观重做完成交接

日期：2026-08-03
状态：本地实现与 Web 生产构建完成，未部署

## 本次范围

仅修改 `src/components/lab/HandsetDevice.vue`。未修改氛围灯、按键层、时间流速层、Pinia store 或状态机。

## 已完成

- 依据用户提供的 2048×813 参考图重新量取屏幕位置：参考图屏幕左上角约为 `(405, 127)`，换算至 863×345 外壳坐标后采用 `left: 171px; top: 54px`；屏幕仍保持固定 `320×240px`。
- 依据参考图重新量取 NFC 图形中心：参考图约为 `(1550, 406)`，换算后约为外壳坐标 `(653, 172)`；交互区域采用 `left: 599px; top: 112px; width: 108px; height: 120px`，中心对齐该位置。
- NFC 图形由文字 `N` + `)))` 改为内联 SVG 路径，保留原 `store.triggerNfc()` 点击逻辑，并补充键盘焦点样式和 `aria-label`。
- 外壳材质改为多层工业设计渲染效果：压铸边缘、顶部菲涅尔柔光、底部暗角、内外投影及细磨砂纹理；删除原有斜向高光带。
- 屏幕圆角、边框和嵌入阴影按参考图收紧，强化嵌入壳体的层次。

## 验证

- `npm.cmd run build:web`：通过，Vite 5.4.21，3968 modules transformed，生产构建成功。
- 保留黑屏点击唤醒和 NFC 独立点击的原事件处理函数，未修改数据逻辑。
- 构建输出仍有项目既存的大 chunk 提示，不影响本次构建成功。

## 待核验

- 尚未在浏览器中对 `/lab` 做最终截图比对；建议由 Claude Code 部署前在实际页面检查缩放到 0.55 后的磨砂颗粒、边缘高光与参考图观感。
- 部署仍由 Claude Code 执行，需上传完整 `dist-web/`，不要只上传本次生成的单个 hash 文件。

## 320×240 TFT 画布复核（用户补充要求）

- 功能定义采用 TFT `320×240px`（4:3）作为真实模拟分辨率。
- 复核发现旧 CSS 虽写有 `width: 320px; height: 240px`，但默认 `content-box` 加 2px border 后，完整节点外尺寸会成为 324×244，容易在 DevTools 中误判。
- 已将尺寸集中为 `--screen-width: 320px` / `--screen-height: 240px`，并同时锁定 width/min-width/max-width 与 height/min-height/max-height。
- 屏幕边框改为不占盒模型空间的 `outline`，因此 `.handset-screen` 节点现在严格为 320×240 CSS px。
- 外壳仍使用 `transform: scale(0.55)` 适配页面，所以最终肉眼显示约为 176×132px；该缩放发生在合成阶段，不改变内部 320×240 布局坐标系和 4:3 比例。
- 修正后重新执行 `npm.cmd run build:web`：通过，3968 modules transformed。

## 主页内容重做（用户补充图片）

- 用户提供新的升降桌产品图作为主页中央主体；通过内置 imagegen 的 background-extraction 流程生成纯绿底版本，再用官方 skill helper 去色转为透明 PNG。
- 最终项目资产：`src/assets/lab/desk-home.png`，已按 alpha 边界裁掉无效留白，保留桌板、双腿、脚座、桌下框架及控制器。
- `HandsetDevice.vue` 已移除原 CSS 方块拼成的桌子，改为静态 import 透明产品图。
- 320×240 主页按原参考图重新布局：40px 状态栏、28px 轮廓头像、用户名、HOT/铃铛/WiFi 状态、顶部页签线、左右页面提示线、两张 80×160 控制卡及中央桌图。
- 默认未刷 NFC 时主页用户名显示“米仔”，刷 NFC 后仍显示 `store.currentUser`。
- Playwright 实际页面核验：唤醒屏幕后 `.handset-screen.offsetWidth/offsetHeight = 320×240`，合成显示矩形为 176×132（0.55 缩放）；中央桌体完整显示且未被两侧控制卡遮挡。
- 最终执行 `npm.cmd run build:web`：通过，3969 modules transformed；仅有项目既存的大 chunk 提示。
- 未部署，交由 Claude Code 审核并上传完整 `dist-web/`。

## Element Plus 图标统一

- 按用户意见，将主页头像、铃铛、联网/离线、上下箭头统一为 `@element-plus/icons-vue`：`UserFilled`、`Bell`、`Connection`、`CircleCloseFilled`、`ArrowUp`、`ArrowDown`。
- NFC 在 Element Plus 中无对应图标，继续使用专用 SVG。
- `npm.cmd run build:web` 再次通过，3969 modules transformed。

## Iconify 图标体系替换（2026-08-04）

- 按用户要求安装 `@iconify/vue` 与 `@iconify-json/mdi`，同步更新 `package.json` / `package-lock.json`。
- 手控器主页头像、铃铛、联网/离线、上下箭头全部改由 Iconify Vue 渲染。
- NFC 改为组合 Iconify MDI 的 `nfc` 与 `contactless-payment`，删除原手写 SVG。
- 新增 `src/components/lab/handsetIconify.js`，仅保存本页使用的 8 个 MDI 图标数据；不打包完整 MDI JSON，也不在浏览器运行时请求 Iconify CDN。
- `npm.cmd run build:web`：通过，3971 modules transformed。
- npm 安装报告当前依赖树有 38 个 vulnerability（2 low / 7 moderate / 25 high / 4 critical）；本次未执行可能引入破坏性升级的 `npm audit fix`，需另行审计。

## NFC 指定图标调整

- 安装 `@iconify-json/lets-icons`，NFC 按用户指定改为 `lets-icons:nfc`。
- 删除此前 MDI `nfc` + `contactless-payment` 的组合渲染及对应冗余图标数据。
- 仍采用静态提取方式，不依赖运行时 CDN。
- `npm.cmd run build:web`：通过，3971 modules transformed。
