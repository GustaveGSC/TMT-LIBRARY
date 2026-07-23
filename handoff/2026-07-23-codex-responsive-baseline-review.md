# 响应式布局第 0 批基线复核

日期：2026-07-23  
复核对象：`f52a1ca feat(responsive): 第0批基线`

## 结论

第 0 批方向正确，构建和现有 8 档 Playwright 用例均通过，但建议先完成一个小范围的“第 0.1 批基线收紧”，再开始 `ShippingDashboard` / `AftersaleDashboard` 试点。

不建议现在直接把页面接入现有基线，原因是断点同步、监听实现和溢出测试各有一个基础性缺口；如果直接进入复杂页面，这些问题会被复制到后续页面。

## 已确认通过

- `src/main.js` 已全局引入 `src/styles/responsive.css`。
- 8 档视口矩阵覆盖桌面、系统缩放后的有效视口、平板和手机横竖屏。
- `npm run build:web` 通过。
- `npm.cmd run test:e2e`：8 项全部通过。
- `git diff --check` 通过。
- 构建后工作区保持干净，`dist-web` 可重复生成。
- `playwright.config.js` 对本机代理环境的兼容处理有效。

## 第 0.1 批必须收紧

### 1. 断点目前不是真正的唯一数据源

`responsiveBreakpoints.js` 定义了 JS 断点，但文件注释明确要求 CSS 中的断点数值“手动保持一致”。目前 `responsive.css` 里也只有断点说明，没有可供后续页面自动复用或校验的机制。

建议二选一：

1. 由 JS 配置生成一个受版本控制的 CSS/SCSS 断点文件；或
2. 保留 JS/CSS 两份声明，但增加自动化一致性测试，解析两端数值并在漂移时失败。

考虑现有 Vite/Vue 栈和改造成本，建议采用方案 2；后续页面开始写 `@media` / `@container` 前必须先有一致性门禁。

### 2. `useResponsiveLayout` 与设计声明不一致

文件说明和交接报告称统一使用 `matchMedia`，实际实现是 `window.innerWidth` 加 `resize` 监听。每个使用该 composable 的组件还会各自注册一套全局 resize 监听器。

建议：

- 改成实际的 `matchMedia` 监听；或
- 做成模块级单例响应状态，只保留一个 viewport 监听源。

优先建议“模块级单例 + matchMedia”，确保多个页面组件不会重复维护窗口监听器。

### 3. 当前溢出测试存在假阴性

现有用例只比较：

```js
document.documentElement.scrollWidth <= document.documentElement.clientWidth
```

如果页面通过 `overflow: hidden` 把超出视口的内容直接裁掉，测试仍会通过，但用户实际仍看不到内容。这正是本轮要解决的主要故障类型之一。

建议在公共断言中同时检查：

- 根节点没有非预期横向滚动；
- 关键可见元素的 `getBoundingClientRect()` 没有越出视口；
- 页面主内容存在可用的纵向滚动容器；
- 关键操作区、图表区和筛选入口可见；
- 控制台没有 Vue/ECharts 布局异常。

登录页可先指定关键选择器；仪表盘试点时为各自页面定义少量稳定的 `data-testid`。

## 登录态测试不需要等待真实测试账号

不建议在 Playwright 中依赖生产或共享测试账号。第 1 批布局回归可以使用：

- `page.route()` 拦截仪表盘 API 并返回固定 fixture；
- 在浏览器上下文中注入前端路由所需的最小用户状态；
- 如路由必须依赖 Cookie，则使用本地测试服务生成的 storage state，而不是硬编码生产凭据。

布局测试关注的是页面在固定数据下是否完整可用，API 真正鉴权另由后端测试覆盖。真实环境的登录联调可以保留为少量独立冒烟测试。

## 第 1 批实施边界

完成第 0.1 批后，可以立即推进两个仪表盘试点。建议顺序：

1. `ShippingDashboard`；
2. 相同布局契约迁移到 `AftersaleDashboard`；
3. 8 档视口全部回归；
4. 再总结可复用模式，推广到管理页和表格页。

试点时注意：

- 不对整页做 `transform: scale()` 或浏览器缩放模拟；
- 不把 `.app-page { block-size: 100dvh }` 盲目套在嵌套组件上，只应用于真正的路由根壳；
- 左侧筛选栏在 compact/tablet 下改抽屉或折叠面板；
- Top 10 榜单在空间不足时移到图表下方；
- 顶部工具栏允许分组换行或折叠，不继续硬塞单行；
- 页面应允许纵向滚动，图表容器负责自适应剩余空间；
- `.table-scroll { overflow-y: hidden }` 不应无差别套用到 Element Plus 表格或包含浮层的容器。

## 交给 Claude Code 的下一步

先完成第 0.1 批（仅基线文件和测试，不改现有业务页面），构建和测试通过后，再进入 `ShippingDashboard` 试点。第 0.1 批不需要单独部署；可与第 1 批页面改造一起部署。
