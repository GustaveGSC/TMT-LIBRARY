# Codex 方案：全站低分辨率与高缩放响应式改造

日期：2026-07-23  
状态：方案定案建议，未修改前端代码。

## 一、目标

解决以下场景中的内容裁切、布局挤压和控件变形：

- 1366×768、1440×900 等笔记本屏幕；
- Windows 125%、150%、175% 显示缩放；
- 浏览器 125%～200% 缩放；
- 窄窗口、分屏窗口；
- 低高度横屏；
- 手机和平板。

不以“所有内容必须始终塞进一屏”为目标。空间不足时允许单方向滚动、折叠、抽屉和分栏转单栏，但不能丢失功能、重叠、裁切或把主内容压缩成不可用区域。

## 二、对 Claude 审计的判断

| Claude 结论 | Codex 判断 |
|---|---|
| 280px + 190px 固定侧栏挤压图表 | 正确，是截图的主要宽度根因 |
| 768px 到桌面之间存在断点真空 | 正确，高缩放笔记本最容易落在约 900～1100 CSS px |
| AftersaleDashboard 没有响应式 | 正确，应列为首批高风险页面 |
| 全局 overflow:hidden 放大裁切 | 正确，但不建议直接全局改成 auto；应先建立统一页面滚动契约 |
| 第一批只加 1200～1280 断点或 clamp | 不足；只能缓解侧栏，无法解决结构耗尽、低高度、工具栏和底部控制栏 |
| 先改两个仪表盘 | 同意，但应先定全局规范和测试矩阵，再用两个仪表盘验证 |

## 三、独立发现的遗漏

### 1. 高缩放同时减少有效高度

问题不只发生在宽度。1366×768 在 150% 缩放下，有效 CSS 视口高度可能只有约 500px。当前大量页面使用：

- `height: 100vh`
- 页面根 `overflow: hidden`
- 固定头部、工具栏、底部栏
- 内容区没有完整的 `min-height: 0 + overflow:auto`

因此即使宽度修好，底部操作仍可能被裁掉。

### 2. 工具栏和底部控制栏没有优先级降级

ShippingDashboard 顶部三段工具栏、地图 Top10 和底部维度控制同时占空间；AftersaleDashboard 还有固定高度工具栏、底部控制条和维度栏。

目前桌面布局默认所有控件单行展示。空间不足时应按顺序：

1. 隐藏非必要文字标签，保留图标和 tooltip；
2. 工具栏换成两行；
3. 次要控件收入“更多”菜单；
4. 底部维度栏允许换行或单轴横向滚动；
5. 不得继续压缩图表画布。

### 3. 固定宽度不仅存在于两个仪表盘

审计还发现：

- AftersaleProcess 左栏 280px；
- ProductCategory/ProductTag 左栏 240px；
- 管理页搜索框 280px；
- RD 表单预览表存在 760/960px 最小宽度；
- 多个弹窗、表格列和输入框有固定宽度；
- 多个页面 `100vw/100vh + overflow:hidden`。

这些需要按页面类型治理，不能只给两个组件补媒体查询。

### 4. CSS 与 JavaScript 断点可能分叉

现有页面常用 `window.innerWidth <= 768` 控制渲染，同时 CSS 又各自维护 `@media`。新增桌面紧凑断点后，如果继续各写一份数字，会出现 CSS 已进入紧凑布局但 Vue 仍渲染桌面控件的问题。

需要统一响应式 token 和一个 `matchMedia` composable，不直接散落 `window.innerWidth`。

### 5. 表格是合理的二维滚动例外

数据表和大型 BOM/ECN 预览不能强行把所有列压到 320px。主流做法是：

- 页面本身只纵向滚动；
- 表格容器内部横向滚动；
- 核心列 sticky；
- 次要列在紧凑模式隐藏或进入详情；
- 操作列保持可达。

这比整体缩放表格更可读。

## 四、技术路线定案

采用“流式 token + 结构断点 + 容器查询 + 明确滚动区”的混合方案。

### 1. clamp() 的使用边界

适合：

- 页面 padding、gap；
- 普通卡片宽度；
- 非关键侧栏在宽屏到标准桌面间的平滑变化；
- 弹窗最大宽度。

示例：

```css
--space-page: clamp(8px, 1.2vw, 20px);
--filter-width: clamp(220px, 18vw, 280px);
```

不适合：

- 把 280px 侧栏无限缩到 120px；
- 缩小字体来维持单行；
- 对整个页面使用 `transform: scale()` 或 CSS `zoom`；
- 用 `devicePixelRatio` 判断 Windows 缩放。

当内容达到最小可用宽度后，必须改变结构，而不是继续 clamp。

### 2. 结构断点

断点以内容何时放不下为准，不以设备品牌为准。初始规范：

| 模式 | 有效 CSS 宽度 | 布局策略 |
|---|---:|---|
| wide | ≥1440 | 完整侧栏、完整标签、多列 |
| standard | 1200～1439 | 流式缩小间距/侧栏，工具栏允许轻度压缩 |
| compact | 900～1199 | 筛选栏变抽屉；工具栏两行；次要侧栏折叠 |
| tablet | 600～899 | 单主内容列；筛选/排行均为抽屉或弹层 |
| mobile | <600 | 手机专用单列、底部抽屉、精简工具栏 |

现有 768px 手机逻辑可在试点阶段兼容，最终统一成 token。精确阈值应通过内容压测微调，不把数字散落到每个页面。

### 3. 容器查询

页面级导航使用 viewport media query；仪表盘工具栏、卡片、图表附属面板使用 container query：

```css
.dashboard-content {
  container: dashboard / inline-size;
}

@container dashboard (inline-size < 900px) {
  /* 工具栏换行、标签隐藏、排行折叠 */
}
```

这样组件根据自己真正拿到的空间适配，不受外部侧栏或未来页面嵌套影响。

### 4. 页面滚动契约

不建议直接把全局 `html/body/#app overflow:hidden` 一次性改成 auto，这会破坏已有全屏图表、固定抽屉和双栏编辑器。

先引入统一页面壳语义：

```css
.app-page {
  min-inline-size: 0;
  min-block-size: 0;
  block-size: 100dvh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.app-page__body {
  flex: 1;
  min-inline-size: 0;
  min-block-size: 0;
  overflow: auto;
}
```

页面明确选择：

- `page-scroll`：管理页、表单页，内容区纵向滚动；
- `workspace`：仪表盘、编辑器，外壳固定，指定子面板滚动；
- `table-scroll`：表格内部允许横向滚动；
- `drawer-scroll`：抽屉 body 滚动，头尾固定。

移动浏览器页面高度使用 `100dvh`，避免地址栏造成 `100vh` 裁切。

## 五、两个仪表盘试点设计

### ShippingDashboard

#### wide / standard

- 筛选栏使用 `clamp(220px, 18vw, 280px)`；
- Top10 使用 `clamp(150px, 12vw, 190px)`；
- 图表区设置真实最小可用宽度，不满足时触发结构变化；
- 工具栏允许 label 优先级降级。

#### compact（约 900～1199）

- 左侧筛选栏改为 overlay drawer，不再占据主布局宽度；
- 顶部增加明确“筛选”按钮和已应用筛选数量；
- Top10 改为可折叠侧栏或图表内抽屉；
- 工具栏两行：第一行指标/数据源，第二行图表类型；
- 底部维度按钮允许横向滚动或“更多维度”菜单；
- 图表始终获得主要空间。

#### tablet / mobile

- 主体单列；
- 筛选和排行使用全高/底部抽屉；
- 仅保留核心图表操作；
- 全屏图表继续使用现有能力，但需验证横竖屏和 `dvh`。

### AftersaleDashboard

- 与 ShippingDashboard 复用同一响应式骨架和筛选抽屉行为；
- 补 compact/tablet/mobile 全部模式；
- 底部“未销售产品”长 radio 文案在 compact 下改 select 或“更多设置”；
- 维度选择栏在 compact 下折叠，不能和底部控制条共同挤占画布；
- 页面最低高度不足时，控制区滚动或折叠，图表保留可用最小高度。

## 六、全站页面类型治理

| 页面类型 | 代表页面 | 统一策略 |
|---|---|---|
| 仪表盘 | Shipping/Aftersale/ProductChart | 抽屉筛选、容器查询、图表优先 |
| 管理表格 | users/permissions/login-logs | toolbar wrap、表格内部横滚、页面纵滚 |
| 配置页 | data-mgmt 各配置 | 卡片 `auto-fit/minmax`，表单单列降级 |
| 双栏编辑器 | RD、AftersaleProcess | compact 下左右栏变 tabs/drawer |
| 产品树/分类 | ProductCategory/ProductTag | 左树可折叠或抽屉，不固定挤压右侧 |
| 弹窗/抽屉 | 全站 | `width:min(..., calc(100vw - 32px))`、body 最大高度和滚动 |
| 登录/通用工具 | login/general-tools | 独立检查低高度、横屏和浏览器缩放 |

## 七、实施顺序

### 第 0 批：建立基线与规范

- 新增全局 responsive tokens；
- 新增统一 `useResponsiveLayout`（基于 `matchMedia`）；
- 定义 page-scroll/workspace/table-scroll/drawer-scroll 契约；
- 建立截图和溢出自动化测试；
- 不批量改页面。

### 第 1 批：双仪表盘试点

- ShippingDashboard；
- AftersaleDashboard；
- 提取可复用的筛选抽屉、紧凑工具栏模式；
- 验证 ECharts ResizeObserver 在所有结构切换后正常。

### 第 2 批：页面壳与管理页

- users、permissions、login-logs；
- data-mgmt；
- 各页面补正确纵向滚动容器；
- 表格使用局部横向滚动。

### 第 3 批：复杂工作区

- AftersaleProcess；
- RD tools；
- ProductCategory/ProductTag；
- 双栏转 tabs/drawer。

### 第 4 批：弹窗与全站回归

- 统一 dialog/drawer 尺寸；
- 清理散落断点和直接 `innerWidth`；
- 检查焦点、键盘、tooltip、popover 和 teleport 定位；
- 最后评估是否还能安全放宽全局 overflow。

## 八、自动化与人工验收矩阵

### 建议引入 Playwright

至少覆盖以下 CSS viewport：

| 视口 | 对应场景 |
|---|---|
| 1920×1080 | 标准桌面 |
| 1536×864 | 1920×1080 + 125% 系统缩放的常见等效尺寸 |
| 1280×720 | 低分辨率桌面 |
| 1093×614 | 1366×768 + 125% |
| 911×512 | 1366×768 + 150% |
| 768×1024 | 平板 |
| 390×844 | 手机竖屏 |
| 844×390 | 手机横屏 |

每个关键页面自动断言：

- `document.documentElement.scrollWidth <= clientWidth`，表格等白名单容器除外；
- 关键操作按钮在 viewport 内或可通过滚动到达；
- 图表容器宽高不低于页面定义的可用阈值；
- 打开/关闭筛选抽屉后图表 resize；
- 无元素互相覆盖；
- 截图回归。

人工额外验证：

- Windows 显示缩放 125%、150%、175%；
- Chrome 浏览器缩放 125%、150%、200%；
- 键盘 Tab 可访问抽屉和“更多”菜单；
- 文本不因布局模式切换被缩到不可读；
- 表格只在自身区域横向滚动，页面不出现双轴滚动。

## 九、不建议的方案

- 全站 `transform: scale(0.8)`；
- CSS `zoom`；
- 根据 `devicePixelRatio` 写 Windows 缩放分支；
- 全局把字体从 14px 降到 10px；
- 只增加一个 1200px 断点；
- 所有固定宽度机械替换成百分比；
- 直接全局取消 overflow:hidden；
- 每个页面各写一套断点数字和 resize 监听。

## 十、最终建议

先定全局规范和自动化矩阵，再以 ShippingDashboard + AftersaleDashboard 做试点，验证后逐类推广。不要一开始全站同时改，也不要只靠两个页面的局部 CSS 补丁。

技术选择：

- `clamp()` 负责连续尺寸；
- media query 负责页面结构；
- container query 负责组件内部结构；
- drawer/collapse/wrap/scroll 负责空间不足时的功能保全；
- `100dvh` 和明确滚动容器负责低高度；
- Playwright 负责防止后续页面再次退化。
