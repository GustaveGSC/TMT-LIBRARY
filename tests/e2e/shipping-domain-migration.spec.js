import { test, expect } from '@playwright/test'
import { mockDataMgmtPage, WAREHOUSE_LIST_RESPONSE } from './fixtures/dataMgmt.js'
import { mockShippingDashboard } from './fixtures/shippingDashboard.js'
import { assertResponsiveLayoutHealthy, collectConsoleErrors, assertNoConsoleErrors } from './layoutAssertions.js'

const OVERFLOW_CHECK_VIEWPORTS = [
  { name: '1920x1080-standard-desktop', width: 1920, height: 1080 },
  { name: '1093x614-1366x768-at-125pct', width: 1093, height: 614 },
  { name: '844x390-mobile-landscape',    width: 844,  height: 390 },
]

// 数据管理入口迁移到发货数据域，见
// handoff/2026-07-24-claude-data-management-migration-plan.md。
// /shipping 现在是带子路由的业务壳：
//   /shipping            分析看板
//   /shipping/orders     订单明细
//   /shipping/imports    数据接入
//   /shipping/settings   规则设置
//   /shipping/maintenance 数据维护
// 旧 /data-mgmt 重定向到 /shipping/imports；首页移除独立"数据管理"卡片。

test('/data-mgmt 自动跳转到 /shipping/imports', async ({ page }) => {
  await mockDataMgmtPage(page)
  await page.goto('/#/data-mgmt')
  await page.waitForLoadState('networkidle')
  await expect(page).toHaveURL(/#\/shipping\/imports$/)
})

test('首页不再显示独立的"数据管理"卡片', async ({ page }) => {
  await mockDataMgmtPage(page)
  await page.goto('/#/index')
  await page.waitForLoadState('networkidle')
  await expect(page.getByText('数据管理', { exact: true })).toHaveCount(0)
  // 发货数据入口仍然存在
  await expect(page.getByText('发货数据', { exact: true })).toBeVisible()
})

test('viewer(shipping:view) 能进入五个子路由但看不到写入口', async ({ page }) => {
  await mockDataMgmtPage(page, { permissions: ['shipping:view'] })
  await mockShippingDashboard(page)
  // mockShippingDashboard 自带 shipping:edit 权限，这里补一个后注册的 addInitScript
  // 把权限收紧回只读，验证 viewer 场景（addInitScript 按注册顺序执行，后者生效）
  await page.addInitScript(() => {
    localStorage.setItem('user', JSON.stringify({
      id: 1, username: 'e2e-tester', display_name: 'E2E 测试账号',
      roles: [], permissions: ['shipping:view'],
    }))
  })
  await page.route('**/api/shipping/warehouses', (route) =>
    route.fulfill({ json: WAREHOUSE_LIST_RESPONSE })
  )

  // 分析看板
  await page.goto('/#/shipping')
  await page.waitForLoadState('networkidle')
  await expect(page.locator('[data-testid="shipping-chart"]')).toBeVisible()

  // 订单明细：viewer 至少能看到页面本体，不做写操作断言（订单页无独立写入口）
  await page.goto('/#/shipping/orders')
  await page.waitForLoadState('networkidle')

  // 数据接入：看不到"开始导入"按钮
  await page.goto('/#/shipping/imports')
  await page.waitForLoadState('networkidle')
  await expect(page.getByRole('button', { name: '开始导入' })).toHaveCount(0)

  // 规则设置：仓库过滤开关禁用、无保存按钮
  await page.goto('/#/shipping/settings')
  await page.waitForLoadState('networkidle')
  await page.getByRole('button', { name: '仓库过滤配置' }).click({ force: true })
  await expect(page.locator('[data-testid="warehouse-save-btn"]')).toHaveCount(0)

  // 数据维护：看不到"重建全部成品组合"按钮
  await page.goto('/#/shipping/maintenance')
  await page.waitForLoadState('networkidle')
  await expect(page.getByRole('button', { name: '重建全部成品组合' })).toHaveCount(0)
})

test('editor(shipping:edit) 能看到对应写入口', async ({ page }) => {
  await mockDataMgmtPage(page, { permissions: ['shipping:view', 'shipping:edit'] })
  await mockShippingDashboard(page)
  await page.route('**/api/shipping/warehouses', (route) =>
    route.fulfill({ json: WAREHOUSE_LIST_RESPONSE })
  )

  await page.goto('/#/shipping/imports')
  await page.waitForLoadState('networkidle')
  await expect(page.getByRole('button', { name: '开始导入' }).first()).toBeVisible()

  await page.goto('/#/shipping/settings')
  await page.waitForLoadState('networkidle')
  await page.getByRole('button', { name: '仓库过滤配置' }).click({ force: true })
  await expect(page.locator('[data-testid="warehouse-save-btn"]')).toBeVisible()

  await page.goto('/#/shipping/maintenance')
  await page.waitForLoadState('networkidle')
  await expect(page.getByRole('button', { name: '重建全部成品组合' })).toBeVisible()
})

test('直接访问子路由激活态正确，刷新后不丢失页面', async ({ page }) => {
  await mockDataMgmtPage(page)
  await mockShippingDashboard(page)

  await page.goto('/#/shipping/settings')
  await page.waitForLoadState('networkidle')
  await expect(page.getByRole('button', { name: '规则设置' })).toHaveClass(/active/)

  // 刷新页面，应仍停留在 /shipping/settings 且导航态正确
  await page.reload()
  await page.waitForLoadState('networkidle')
  await expect(page).toHaveURL(/#\/shipping\/settings$/)
  await expect(page.getByRole('button', { name: '规则设置' })).toHaveClass(/active/)
})

test('设置页用 query 记录当前 Tab，刷新后保持', async ({ page }) => {
  await mockDataMgmtPage(page)

  await page.goto('/#/shipping/settings')
  await page.waitForLoadState('networkidle')
  await page.getByRole('button', { name: '产成品通用件配置' }).click({ force: true })
  await expect(page).toHaveURL(/tab=equivalent/)

  await page.reload()
  await page.waitForLoadState('networkidle')
  await expect(page.getByRole('button', { name: '产成品通用件配置' })).toHaveClass(/active/)
})

test.describe('规则设置页顶部导航与内容区无横向溢出', () => {
  for (const viewport of OVERFLOW_CHECK_VIEWPORTS) {
    test(viewport.name, async ({ page }) => {
      await mockDataMgmtPage(page)
      await page.route('**/api/shipping/warehouses', (route) =>
        route.fulfill({ json: WAREHOUSE_LIST_RESPONSE })
      )
      const errors = collectConsoleErrors(page)
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto('/#/shipping/settings')
      await page.waitForLoadState('networkidle')

      await assertResponsiveLayoutHealthy(page, {
        keySelectors: ['[data-testid="shipping-nav"]'],
      })
      assertNoConsoleErrors(errors)
    })
  }
})

test('切换五个子路由不产生控制台错误或未打桩请求', async ({ page }) => {
  await mockDataMgmtPage(page)
  await mockShippingDashboard(page)
  await page.route('**/api/shipping/warehouses', (route) =>
    route.fulfill({ json: WAREHOUSE_LIST_RESPONSE })
  )
  const errors = collectConsoleErrors(page)

  for (const path of ['/shipping', '/shipping/orders', '/shipping/imports', '/shipping/settings', '/shipping/maintenance']) {
    await page.goto(`/#${path}`)
    await page.waitForLoadState('networkidle')
  }

  assertNoConsoleErrors(errors)
})
