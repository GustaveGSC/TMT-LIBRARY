import { test, expect } from '@playwright/test'
import { mockDataMgmtPage, WAREHOUSE_LIST_RESPONSE } from './fixtures/dataMgmt.js'

// 仓库过滤配置位于 /shipping/settings，该路由现在只对 shipping:edit 开放（见路由 meta），
// shipping:view-only 用户直接访问会被路由守卫拦截回首页，不再是"能进入但只读"。
// viewer 场景的路由拦截断言见 shipping-domain-migration.spec.js。
// 见 handoff/2026-07-24-claude-handoff-26.md 前端协作项第1条。
// 数据管理入口已迁移到 /shipping/settings，见 handoff/2026-07-24-claude-data-management-migration-plan.md。

async function gotoWarehouseConfig(page) {
  await page.goto('/#/shipping/settings')
  await page.waitForLoadState('networkidle')
  await page.getByRole('button', { name: '仓库过滤配置' }).click({ force: true })
  await expect(page.locator('[data-testid="warehouse-row"]').first()).toBeVisible()
}

test('editor (shipping:edit) 可以切换开关并保存', async ({ page }) => {
  await mockDataMgmtPage(page, { permissions: ['shipping:view', 'shipping:edit'] })
  await page.route('**/api/shipping/warehouses', (route) =>
    route.fulfill({ json: WAREHOUSE_LIST_RESPONSE })
  )
  let saveBody = null
  await page.route('**/api/shipping/warehouses/filter', async (route) => {
    saveBody = route.request().postDataJSON()
    await route.fulfill({ json: { success: true, message: '保存成功', data: null } })
  })

  await gotoWarehouseConfig(page)

  const saveBtn = page.locator('[data-testid="warehouse-save-btn"]')
  await expect(saveBtn).toBeVisible()

  const toggle = page.locator('[data-testid="warehouse-toggle"]').first()
  await expect(toggle.locator('input')).toBeEnabled()
  await toggle.click()

  await saveBtn.click()
  await expect(page.getByText('保存成功')).toBeVisible()
  expect(saveBody).not.toBeNull()
})
