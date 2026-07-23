# Claude 交接：低分辨率/高缩放下页面显示异常，方案待 Codex 核查

日期：2026-07-23  
状态：只读调研 + 方案草案，未动代码，请 Codex 核查方案合理性后再决定是否/如何实施。

## 一、问题现象

用户反馈：屏幕分辨率较低，或系统设置了显示缩放（如125%/150%）时，页面会出现"一屏只能显示很小一部分内容"或"UI变形错位"。用户提供的截图是 `ShippingDashboard.vue`（发货数据看板），图表被压缩成一条窄缝，四周大片留白。

## 二、调研结论（只读审计，未改代码）

### 根因1：固定像素侧边栏不收缩

`ShippingDashboard.vue` 顶层三段式布局：

```
.dashboard-root   { flex: 1; display: flex; padding: 5px; gap: 4px; }
.filter-panel     { width: 280px; flex-shrink: 0; ... }   /* 左侧筛选栏，绝对像素，不允许收缩 */
.content-panel    { flex: 1; min-width: 0; ... }           /* 图表区吃剩余空间 */
.map-rank-panel   { width: 190px; flex-shrink: 0; ... }     /* 地图模式下排行榜，同样固定 */
```

视口越窄，图表区能拿到的空间 = 总宽度 − 280px − 190px − padding/gap，越接近 0。这是截图问题的直接原因。ECharts 本身响应式正常（`ResizeObserver` + `window.resize` 双重触发 `resize()`），图表只是如实铺满了被挤压后的小空间。

### 根因2：响应式断点存在"真空区"

全仓库搜索确认：现有断点只有 `max-width: 768px`（手机竖屏）和横屏 `max-height: 600px` 两档，`src/styles/themes.css`（全局主题文件）不含任何 `@media`。768px～桌面全尺寸之间完全没有断点覆盖——而这段区间恰好是笔记本分辨率（1366×768、1440×900）+ 系统缩放（125%/150%）换算出的等效 CSS 视口最常落入的区间（例：1366px 物理宽度 125%缩放 ≈ 1093px 等效视口，150%缩放 ≈ 911px）。

### 根因3：`AftersaleDashboard.vue` 零响应式

结构和发货看板几乎一致（`.filter-panel { width: 270px; flex-shrink: 0; }`），但**没有任何 `@media` 断点**，连手机端适配都没做。风险高于发货看板。

### 根因4：全局 `overflow: hidden` 放大裁切效果

`src/app.vue`、`src/index.html` 对 `html, body, #app` 设置 `height:100%; overflow:hidden`，全局不存在页面级滚动。任何页面若实际内容高度超出视口，多出部分直接被裁掉而非出现滚动条，需要各页面自行在内部管理滚动区域（`min-height:0` + `overflow-y:auto`），一旦漏配就会在小视口下"内容看不见"而不是"能滚动看到"。

### 排除项：Electron 相关

`electron/main/window.ts` 主窗口默认 800×600 且启动不自动最大化，理论上也会诱发同类问题，但 Electron 桌面端已正式停止支持（`handoff/2026-07-21-electron-support-end-decision.md`），不建议为此投入，本次方案只针对 Web 端。

## 三、我（Claude）拟定的分批方案

**第一批**：给 `ShippingDashboard.vue`/`AftersaleDashboard.vue` 加一档"小尺寸桌面"断点（约1200~1280px），侧边栏宽度在该档下收窄（如280px→200px）或改为 `clamp(200px, 18vw, 280px)` 随视口平滑缩放；工具栏/卡片头等固定px高度视情况压缩。

**第二批**：给 `AftersaleDashboard.vue` 补齐至少和发货看板一样的 768px 手机端断点（目前是零，这是明确的功能缺口，与"优化"性质不同，应该独立对待）。

**第三批**：审计各主要页面内部滚动容器配置是否正确（`min-height:0`+`overflow-y:auto`），把"内容超高被裁切"兜底成"能滚动"，降低前两批未完全覆盖场景的影响。

## 四、请 Codex 核查的点

1. 上述根因分析是否有遗漏或误判——我是从前端视角审计的，如果后端/整体架构层面有我没考虑到的因素（比如是否有页面级别的配置会影响这个），麻烦指出。
2. 分批顺序和范围是否合理，尤其第一批"加一档断点 vs 改成 clamp() 连续缩放"这两种技术路线，你怎么判断风险和收益的取舍？
3. 是否有比"逐页面补断点"更系统性的方案（比如全局布局组件抽象、统一的响应式 token/变量），值得在动手改具体页面前先定下来，避免每个页面各自为战、以后又要重新统一。
4. 这项工作影响面较广（截图页面 + AftersaleDashboard + 其他仪表盘/列表页），要不要先只做 `ShippingDashboard.vue`/`AftersaleDashboard.vue` 这两个仪表盘验证方案有效，再决定要不要推广到其他页面，还是一开始就该定一个全局规范再统一套用。

用户明确要求先出方案不动手，等你核查完再决定下一步，所以这份文档目前只是审计+草案，没有任何代码改动。
