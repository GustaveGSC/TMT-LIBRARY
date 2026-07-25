import { test, expect } from '@playwright/test'
import { mockDataMgmtPage } from './fixtures/dataMgmt.js'

// 财务导入结果新增 customer_alias_conflicts_count/_order_nos/_truncated 三个字段
// （见 handoff/2026-07-25-codex-deterministic-resolver-implementation.md）。
// 后端契约已稳定，但整批（含"完成发货"元数据口径）与 C 批 staging/cutover 一起发布，
// 前端本次先完成实现和测试，不单独部署。

const TASK_ID = 'finance-conflicts-task-1'

test('财务导入结果展示客户简称冲突数量，可展开清单并显示截断提示', async ({ page }) => {
  await mockDataMgmtPage(page)
  await page.goto('/#/shipping/imports')
  await page.waitForLoadState('networkidle')

  await page.route('**/api/shipping/import/finance', (route) =>
    route.fulfill({ json: { success: true, message: '', data: { task_id: TASK_ID } } })
  )
  await page.route(`**/api/shipping/tasks/${TASK_ID}`, (route) =>
    route.fulfill({
      json: {
        success: true,
        message: '',
        data: {
          task_id: TASK_ID,
          task_type: 'import_finance',
          status: 'done',
          progress: { step: 'done' },
          result: {
            total: 300, inserted: 100, updated: 50, inserted_returns: 0, updated_returns: 0,
            skipped: 0, skipped_returns: 0, skipped_rows: [], aftersale_filtered: 0,
            customer_alias_conflicts_count: 102,
            customer_alias_conflicts_order_nos: Array.from({ length: 100 }, (_, i) => `ORDER-${String(i).padStart(3, '0')}`),
            customer_alias_conflicts_truncated: true,
          },
          message: '',
          cancellable: false,
          cancel_requested: false,
        },
      },
    })
  )

  const fileInput = page.locator('.finance-import input[type="file"]')
  await fileInput.setInputFiles({
    name: 'finance_probe.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('电商主订单号,单据日期,部门名称,数量\nX,2026-07-24,,1\n'),
  })
  await page.locator('.finance-import .import-btn').click()

  const conflictCard = page.locator('.finance-import .result-card.warning')
  await expect(conflictCard).toBeVisible({ timeout: 10000 })
  await expect(conflictCard.locator('.rc-val')).toHaveText('102')

  await conflictCard.click()
  await expect(page.getByText('客户简称冲突订单')).toBeVisible()
  await expect(page.getByText(/共 102 单存在冲突，仅展示前 100 单/)).toBeVisible()
  await expect(page.getByText('ORDER-000')).toBeVisible()
})

test('无客户简称冲突时不展示对应卡片', async ({ page }) => {
  await mockDataMgmtPage(page)
  await page.goto('/#/shipping/imports')
  await page.waitForLoadState('networkidle')

  await page.route('**/api/shipping/import/finance', (route) =>
    route.fulfill({ json: { success: true, message: '', data: { task_id: TASK_ID } } })
  )
  await page.route(`**/api/shipping/tasks/${TASK_ID}`, (route) =>
    route.fulfill({
      json: {
        success: true,
        message: '',
        data: {
          task_id: TASK_ID,
          task_type: 'import_finance',
          status: 'done',
          progress: { step: 'done' },
          result: {
            total: 10, inserted: 10, updated: 0, inserted_returns: 0, updated_returns: 0,
            skipped: 0, skipped_returns: 0, skipped_rows: [], aftersale_filtered: 0,
            customer_alias_conflicts_count: 0,
            customer_alias_conflicts_order_nos: [],
            customer_alias_conflicts_truncated: false,
          },
          message: '',
          cancellable: false,
          cancel_requested: false,
        },
      },
    })
  )

  const fileInput = page.locator('.finance-import input[type="file"]')
  await fileInput.setInputFiles({
    name: 'finance_probe2.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('电商主订单号,单据日期,部门名称,数量\nX,2026-07-24,,1\n'),
  })
  await page.locator('.finance-import .import-btn').click()

  await expect(page.locator('.finance-import .result-wrap')).toBeVisible({ timeout: 10000 })
  await expect(page.locator('.finance-import .result-card.warning')).toHaveCount(0)
})
