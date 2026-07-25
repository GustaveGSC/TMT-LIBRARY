import { test, expect } from '@playwright/test'
import { mockDataMgmtPage } from './fixtures/dataMgmt.js'

// 发货/财务导入取消前端适配：用真实按钮驱动 POST /api/shipping/tasks/:id/cancel，
// 以后端轮询返回的 cancellable 为准显示/隐藏按钮，不在前端自行按 task_type 推断。
// 见交接要求：正常取消、重复点击、取消与 committing 竞争、cancelled 终态、
// 不支持取消的任务无按钮、组件卸载停止轮询。

const TASK_ID = 'cancel-e2e-task-1'

function mockTaskPolling(page, statusSequence) {
  let pollIndex = 0
  return page.route(`**/api/shipping/tasks/${TASK_ID}`, async (route) => {
    const state = statusSequence[Math.min(pollIndex, statusSequence.length - 1)]
    pollIndex += 1
    await route.fulfill({
      json: {
        success: true,
        message: '',
        data: {
          task_id: TASK_ID,
          task_type: 'import_shipping',
          status: state.status,
          progress: state.progress ?? { step: state.status },
          result: state.result ?? null,
          message: state.message ?? '',
          cancellable: state.cancellable ?? false,
          cancel_requested: state.cancel_requested ?? false,
        },
      },
    })
  })
}

async function gotoImportsPage(page) {
  await page.goto('/#/shipping/imports')
  await page.waitForLoadState('networkidle')
}

async function startShippingImport(page) {
  await page.route('**/api/shipping/import/shipping', (route) =>
    route.fulfill({ json: { success: true, message: '', data: { task_id: TASK_ID } } })
  )
  const fileInput = page.locator('.data-import input[type="file"]')
  await fileInput.setInputFiles({
    name: 'probe.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('电商主订单号,单据日期\nX,2026-07-24\n'),
  })
  await page.locator('.data-import .import-btn').click()
}

test('取消导入：点击后禁用按钮显示"正在取消"，终态展示已回滚文案', async ({ page }) => {
  await mockDataMgmtPage(page)
  await gotoImportsPage(page)

  await mockTaskPolling(page, [
    { status: 'running', cancellable: true, progress: { step: 'inserting', current: 1, total: 10 } },
    { status: 'running', cancellable: false, cancel_requested: true, progress: { step: 'inserting', current: 2, total: 10 } },
    { status: 'cancelled', message: '导入已中止，业务数据已回滚' },
  ])

  let cancelCalls = 0
  await page.route(`**/api/shipping/tasks/${TASK_ID}/cancel`, async (route) => {
    cancelCalls += 1
    await route.fulfill({
      json: {
        success: true,
        message: '已发送取消请求',
        data: { task_id: TASK_ID, task_type: 'import_shipping', status: 'running', cancellable: false, cancel_requested: true },
      },
    })
  })

  await startShippingImport(page)

  const cancelBtn = page.locator('.data-import [data-testid="task-cancel-btn"]')
  await expect(cancelBtn).toBeVisible()
  await expect(cancelBtn).toHaveText('取消导入')
  await cancelBtn.click()

  await expect(cancelBtn).toBeDisabled()
  await expect(cancelBtn).toHaveText('正在取消…')

  await expect(page.getByText('已取消，所有导入数据已回滚')).toBeVisible({ timeout: 10000 })
  expect(cancelCalls).toBe(1)
})

test('重复点击取消按钮只发一次请求', async ({ page }) => {
  await mockDataMgmtPage(page)
  await gotoImportsPage(page)

  await mockTaskPolling(page, [
    { status: 'running', cancellable: true, progress: { step: 'inserting', current: 1, total: 100 } },
  ])

  let cancelCalls = 0
  await page.route(`**/api/shipping/tasks/${TASK_ID}/cancel`, async (route) => {
    cancelCalls += 1
    // 故意延迟响应，模拟请求进行中时的重复点击窗口
    await new Promise((resolve) => setTimeout(resolve, 300))
    await route.fulfill({
      json: {
        success: true,
        message: '已发送取消请求',
        data: { task_id: TASK_ID, task_type: 'import_shipping', status: 'running', cancellable: false, cancel_requested: true },
      },
    })
  })

  await startShippingImport(page)

  const cancelBtn = page.locator('.data-import [data-testid="task-cancel-btn"]')
  await expect(cancelBtn).toBeVisible()
  await cancelBtn.click()
  await cancelBtn.click({ force: true })
  await cancelBtn.click({ force: true })

  await page.waitForTimeout(600)
  expect(cancelCalls).toBe(1)
})

test('取消与 committing 竞争：提交方胜出时展示后端文案，不显示取消成功', async ({ page }) => {
  await mockDataMgmtPage(page)
  await gotoImportsPage(page)

  await mockTaskPolling(page, [
    { status: 'running', cancellable: true, progress: { step: 'inserting', current: 1, total: 10 } },
    { status: 'committing', cancellable: false, progress: { step: 'committing' } },
    { status: 'done', result: { total: 1, inserted: 1, skipped: 0, skipped_rows: [] } },
  ])

  await page.route(`**/api/shipping/tasks/${TASK_ID}/cancel`, async (route) => {
    await route.fulfill({
      status: 409,
      json: {
        success: false,
        message: '任务正在提交最终结果，已无法取消',
        data: { task_id: TASK_ID, task_type: 'import_shipping', status: 'committing', cancellable: false, cancel_requested: false },
      },
    })
  })

  await startShippingImport(page)

  const cancelBtn = page.locator('.data-import [data-testid="task-cancel-btn"]')
  await expect(cancelBtn).toBeVisible()
  await cancelBtn.click()

  await expect(page.getByText('任务正在提交最终结果，已无法取消')).toBeVisible()
  await expect(cancelBtn).toHaveText('正在提交，无法取消')
  await expect(cancelBtn).toBeDisabled()

  // 不能出现"已取消"文案——提交方胜出，任务最终会成功
  await expect(page.getByText('已取消，所有导入数据已回滚')).toHaveCount(0)
  await expect(page.getByText('导入成功')).toBeVisible({ timeout: 10000 })
})

test('resolve_stale 在 cancellable:false 时不显示取消入口', async ({ page }) => {
  await mockDataMgmtPage(page)

  // resolve_all（数据维护页）"重建全部成品组合"入口已临时禁用，见
  // handoff/2026-07-25-claude-staging-cutover-gate-test-report.md（全表 DELETE 超时门禁未通过）。
  // 对应交互测试挪到 tests/e2e/shipping-resolve-cancel.spec.js 并整体 skip，等后端重新设计
  // cutover、前端恢复入口后再取消 skip。这里只保留 resolve_stale 场景。

  // resolve_stale（规则设置 → 操作人分类）
  await page.route('**/api/shipping/resolve', (route) =>
    route.fulfill({ json: { success: true, message: '', data: { task_id: 'resolve-stale-task' } } })
  )
  await page.route('**/api/shipping/tasks/resolve-stale-task', (route) =>
    route.fulfill({
      json: {
        success: true, message: '',
        data: {
          task_id: 'resolve-stale-task', task_type: 'resolve_stale', status: 'running',
          progress: { step: 'resolving' }, result: null, message: '',
          cancellable: false, cancel_requested: false,
        },
      },
    })
  )
  await page.route('**/api/shipping/stats', (route) =>
    route.fulfill({ json: { success: true, message: '', data: { stale_count: 3 } } })
  )
  await page.goto('/#/shipping/settings')
  await page.waitForLoadState('networkidle')
  const resolveBtn = page.getByRole('button', { name: /刷新成品组合/ })
  if (await resolveBtn.count()) {
    await resolveBtn.click({ force: true })
  }
  await expect(page.locator('[data-testid="task-cancel-btn"]')).toHaveCount(0)
})

test('离开页面（组件卸载）后停止轮询', async ({ page }) => {
  await mockDataMgmtPage(page)
  await gotoImportsPage(page)

  let pollCount = 0
  await page.route(`**/api/shipping/tasks/${TASK_ID}`, async (route) => {
    pollCount += 1
    await route.fulfill({
      json: {
        success: true, message: '',
        data: {
          task_id: TASK_ID, task_type: 'import_shipping', status: 'running',
          progress: { step: 'inserting', current: 1, total: 100 }, result: null, message: '',
          cancellable: true, cancel_requested: false,
        },
      },
    })
  })

  await startShippingImport(page)
  await expect.poll(() => pollCount).toBeGreaterThanOrEqual(1)

  await page.goto('/#/index')
  await page.waitForLoadState('networkidle')

  const countAfterLeaving = pollCount
  await page.waitForTimeout(2000)
  expect(pollCount).toBe(countAfterLeaving)
})
