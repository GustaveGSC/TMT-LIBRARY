# Claude 部署记录：数据管理入口迁移到发货数据域

日期：2026-07-24

## 变更范围

纯前端，无后端接口/权限码变更，无数据库迁移。对应
`handoff/2026-07-24-claude-data-management-migration-plan.md`。

- `/shipping` 改为带 5 个子路由的业务壳：`/shipping`（分析看板）、`/shipping/orders`（订单明细）、
  `/shipping/imports`（数据接入）、`/shipping/settings`（规则设置）、`/shipping/maintenance`
  （数据维护）；`/data-mgmt` 重定向到 `/shipping/imports`；首页移除独立"数据管理"卡片。
- 新增 `ShippingImportsPage.vue`/`ShippingSettingsPage.vue`/`ShippingMaintenancePage.vue`
  三个组装页面（`src/views/shippingViews/`），复用未物理搬移的 `dataMgmtViews/` 组件。
- "重建全部成品组合"独立到数据维护页，不再是导入流程常驻按钮。
- 补齐 `DataImport`/`FinanceImport`/`OperatorConfig`/`EquivalentConfig`/`TagDimensionConfig`
  的 viewer/editor 权限门控（此前只有 `WarehouseConfig`/`FinanceCustomerMapping` 有），不再仅
  依赖后端 403。
- 删除已被完全替代的 `page-data-mgmt.vue`。
- 更新 `.claude/modules/frontend-data-mgmt.md`，移除 SSE/旧页面结构/"外贸客户匹配"过期描述。

## 验证

- `npm run build:web` 通过。
- Playwright 58 用例全绿，新增 `shipping-domain-migration.spec.js`（10 用例，覆盖重定向、首页卡片
  移除、viewer/editor 五路由权限、直接访问+刷新保持、Tab 用 query 持久化、三档视口无横向溢出、
  切换五路由无控制台错误），更新了 `warehouse-filter-permissions.spec.js`/`task-conflict-409.spec.js`/
  `shipping-task-polling.spec.js` 的导航路径。
- 排查过一次误报：临时脚本里连续 `page.goto()` 后立即 `page.screenshot()`（不等待任何断言）截到了
  过渡帧，看起来像"子路由切换未生效"；改用有自动重试等待的 `expect(...).toBeVisible()` 断言后
  证实内容切换完全正常，两种触发方式（`page.goto` 直接改 hash / 点击顶部导航按钮）都通过，确认是
  截图时序问题不是产品缺陷。
- 部署后手动截图核对 `/shipping/settings` 页面布局（顶部 5 项导航 + 侧边栏三组 Tab + 内容区），
  视觉正常。

## 部署

`tar`+`scp`+服务器端覆盖，线上 `index.html` 引用的 JS hash 与本地构建比对一致
（`index-DfCc9PrH.js`）后删除 `.old` 备份，`https://tmt-library.cn/` 返回 200。

## 遗留

- `dataMgmtViews/` 目录本身未物理搬移（按计划要求，先稳定行为再搬目录）。
- `icon_data_mgmt.png` 资源文件未删除（未使用，留作后续清理）。
