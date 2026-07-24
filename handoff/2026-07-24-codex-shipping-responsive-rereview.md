# ShippingDashboard 响应式试点返工复核

日期：2026-07-24  
复核对象：`901d49e`

## 结论

返工审查通过。`ShippingDashboard` 响应式试点可以作为 `AftersaleDashboard` 的迁移模板。

## 核验结果

- 紧凑布局中的 `.content-panel` / `.chart-wrap` 重复声明已合并。
- 最终布局契约为 `overflow-y:auto`、`grid-template-rows:auto minmax(220px, 1fr)` 和图表最小高度 220px。
- 新断言同时验证最终计算样式、`scrollHeight > clientHeight` 以及真实 `scrollTop` 变化，不再只检查源码声明。
- 844×260 极端矮视口确实触发滚动路径。
- 筛选抽屉测试覆盖 compact 桌面和手机两档的打开、核心操作区可达、关闭全过程。
- Playwright：24 项通过。
- `npm run build:web`：通过。
- `git diff --check`：通过。
- 构建后工作区干净。

## 迁移到 AftersaleDashboard 时的边界

- 复用“布局规则”和公共断言，不要直接复制 Shipping 的业务选择器或 fixture 数据结构。
- 继续保持 `isCompactLayout` 与售后页面原有的触屏/移动端业务判断分离。
- 先确认售后页面自己的工具栏、图表叠层和详情面板结构，再确定唯一主滚动容器。
- 为售后页面建立独立 API fixture，并覆盖相同的 8 档默认视图。
- 对售后实际存在的复杂视图选 1093×614、911×512、844×390 和 1920×1080 做重点回归。
- 保留 `elementFromPoint`、真实容器滚动、抽屉完整交互和控制台错误检查。
- 完成后仍需先单独审查售后试点，不要在同一批扩散到管理页或表格页。

## 非阻塞记录

`901d49e` 的提交标题仍写“第0.1批基线收紧”，但实际内容是 Shipping 第1批返工。按项目 Git 纪律不 amend 已有提交，后续交接和部署记录按实际内容引用即可。
