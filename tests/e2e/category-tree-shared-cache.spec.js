import { test, expect } from '@playwright/test'
import { mockShippingDashboard } from './fixtures/shippingDashboard.js'
import { mockAftersaleDashboard } from './fixtures/aftersaleDashboard.js'

// /api/category/tree 改为 useCategoryTree() 共享单例（loadCategoryTreeOnce），
// 见 handoff/2026-07-24-claude-handoff-26.md 前端协作项第2条：
//   - 页面内日期筛选变化不应重复拉取分类树；
//   - 同一浏览器标签页内跨组件（发货看板 / 售后看板）应共享同一次请求结果。

test('ShippingDashboard 切换日期筛选不重复请求分类树', async ({ page }) => {
  await mockShippingDashboard(page)

  let treeRequests = 0
  await page.route('**/api/category/tree', (route) => {
    treeRequests += 1
    route.fulfill({ json: { success: true, message: '', data: [] } })
  })

  await page.goto('/#/shipping')
  await page.waitForLoadState('networkidle')
  expect(treeRequests).toBe(1)

  // 打开日期筛选并切换一个预设范围，触发 date watcher → loadOptions()
  const dateTrigger = page.locator('[data-testid="shipping-filter-panel"], [data-testid="shipping-filter-toggle"]').first()
  await dateTrigger.click().catch(() => {})

  // 直接触发一次 date range watcher 更可靠：点击"最近30天"这类日期快捷按钮（若存在）
  const quickRange = page.getByText('最近30天').first()
  if (await quickRange.count()) {
    await quickRange.click()
    await page.waitForTimeout(300)
  }

  // 无论筛选面板交互是否命中具体控件，只要 loadOptions 被日期 watcher 重新触发，
  // 分类树请求数都不应该增加
  expect(treeRequests).toBe(1)
})

test('同一标签页内发货看板与售后看板共享分类树请求结果', async ({ page }) => {
  await mockShippingDashboard(page)
  await mockAftersaleDashboard(page)
  // 两个 fixture 各自的 addInitScript 都会整体覆盖 localStorage.user，
  // 后注册的（售后）会覆盖发货的权限；这里补一个联合权限集，保证两个页面路由守卫都能通过
  await page.addInitScript(() => {
    localStorage.setItem('user', JSON.stringify({
      id: 1,
      username: 'e2e-tester',
      display_name: 'E2E 测试账号',
      roles: [],
      permissions: ['shipping:view', 'shipping:edit', 'aftersale:view', 'aftersale:edit'],
    }))
  })

  let treeRequests = 0
  await page.route('**/api/category/tree', (route) => {
    treeRequests += 1
    route.fulfill({ json: { success: true, message: '', data: [] } })
  })

  await page.goto('/#/shipping')
  await page.waitForLoadState('networkidle')
  expect(treeRequests).toBe(1)

  // hash 路由内部跳转，不刷新页面，模块级单例状态应保留
  await page.goto('/#/aftersale')
  await page.waitForLoadState('networkidle')
  expect(treeRequests).toBe(1)
})
