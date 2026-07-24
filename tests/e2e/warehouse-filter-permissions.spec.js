import { test, expect } from '@playwright/test'
import { mockDataMgmtPage, WAREHOUSE_LIST_RESPONSE } from './fixtures/dataMgmt.js'

// 仓库过滤配置：shipping:view 用户应看到只读状态（开关禁用、无保存按钮），
// shipping:edit 用户应能正常编辑并保存。
// 见 handoff/2026-07-24-claude-handoff-26.md 前端协作项第1条。

async function gotoWarehouseConfig(page) {
  await page.goto('/#/data-mgmt')
  await page.waitForLoadState('networkidle')
  await page.getByRole('button', { name: '数据配置' }).click({ force: true })
  await page.getByRole('button', { name: '仓库过滤配置' }).click({ force: true })
  await expect(page.locator('[data-testid="warehouse-row"]').first()).toBeVisible()
}

test('viewer (shipping:view only) 看不到保存入口，开关不可操作', async ({ page }) => {
  await mockDataMgmtPage(page, { permissions: ['shipping:view'] })
  await page.route('**/api/shipping/warehouses', (route) =>
    route.fulfill({ json: WAREHOUSE_LIST_RESPONSE })
  )

  await gotoWarehouseConfig(page)

  // 保存按钮整体不渲染
  await expect(page.locator('[data-testid="warehouse-save-btn"]')).toHaveCount(0)

  // 开关渲染但禁用，不能切换
  const toggle = page.locator('[data-testid="warehouse-toggle"]').first()
  await expect(toggle).toBeVisible()
  await expect(toggle.locator('input')).toBeDisabled()
})

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
