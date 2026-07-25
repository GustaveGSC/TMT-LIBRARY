import { test, expect } from '@playwright/test'
import { mockDataMgmtPage } from './fixtures/dataMgmt.js'

// C 批：resolve_all/resolve_stale 现在走 staging/cutover，后端已把它们加入可取消类型。
// 见 handoff/2026-07-25-codex-shipping-staging-cutover-handoff.md 第4节前端协作项。
// 后端契约已稳定，但本批（含"完成发货"元数据口径）与前端一起推迟到统一发布窗口，先只验证行为。

const TASK_ID = 'resolve-cancel-task-1'

// "重建全部成品组合"入口已临时禁用（FULL_RESOLVE_TEMPORARILY_DISABLED，见
// ShippingMaintenancePage.vue）：生产门禁实测发现全表 DELETE 超过 read_timeout 导致任务失败，
// 见 handoff/2026-07-25-claude-staging-cutover-gate-test-report.md。这里整体 skip，
// 保留用例不删，等后端改为 RENAME TABLE 型 cutover、前端恢复入口后再取消 skip。
test.describe.skip('ShippingMaintenancePage：重建全部成品组合取消', () => {
  async function gotoMaintenance(page) {
    await mockDataMgmtPage(page)
    await page.goto('/#/shipping/maintenance')
    await page.waitForLoadState('networkidle')
  }

  test('取消请求成功：按钮禁用显示"正在取消"，终态展示线上数据保持不变', async ({ page }) => {
    await gotoMaintenance(page)
    await page.route('**/api/shipping/resolve-all', (route) =>
      route.fulfill({ json: { success: true, message: '', data: { task_id: TASK_ID } } })
    )
    let pollIndex = 0
    const sequence = [
      { status: 'running', cancellable: true, progress: { step: 'resolving', current: 1, total: 10 } },
      { status: 'running', cancellable: false, cancel_requested: true, progress: { step: 'resolving', current: 2, total: 10 } },
      { status: 'cancelled', message: '重算已取消，线上数据保持不变' },
    ]
    await page.route(`**/api/shipping/tasks/${TASK_ID}`, async (route) => {
      const state = sequence[Math.min(pollIndex, sequence.length - 1)]
      pollIndex += 1
      await route.fulfill({
        json: {
          success: true, message: '',
          data: {
            task_id: TASK_ID, task_type: 'resolve_all', status: state.status,
            progress: state.progress ?? { step: state.status }, result: state.result ?? null,
            message: state.message ?? '',
            cancellable: state.cancellable ?? false, cancel_requested: state.cancel_requested ?? false,
          },
        },
      })
    })
    let cancelCalls = 0
    await page.route(`**/api/shipping/tasks/${TASK_ID}/cancel`, async (route) => {
      cancelCalls += 1
      await route.fulfill({
        json: {
          success: true, message: '已发送取消请求',
          data: { task_id: TASK_ID, task_type: 'resolve_all', status: 'running', cancellable: false, cancel_requested: true },
        },
      })
    })

    await page.getByRole('button', { name: '重建全部成品组合' }).click({ force: true })
    await page.getByRole('button', { name: '确认重建' }).click()

    const cancelBtn = page.locator('[data-testid="task-cancel-btn"]')
    await expect(cancelBtn).toBeVisible()
    await cancelBtn.click()
    await expect(cancelBtn).toBeDisabled()
    await expect(cancelBtn).toHaveText('正在取消…')

    await expect(page.getByText('重算已取消，线上数据保持不变')).toBeVisible({ timeout: 10000 })
    expect(cancelCalls).toBe(1)
  })

  test('取消与 committing 竞争：提交方胜出展示后端文案，不显示取消成功', async ({ page }) => {
    await gotoMaintenance(page)
    await page.route('**/api/shipping/resolve-all', (route) =>
      route.fulfill({ json: { success: true, message: '', data: { task_id: TASK_ID } } })
    )
    let pollIndex = 0
    const sequence = [
      { status: 'running', cancellable: true, progress: { step: 'resolving', current: 1, total: 10 } },
      { status: 'committing', cancellable: false, progress: { step: 'committing' } },
      { status: 'done', result: { resolved: 10, staged_rows: 10, deleted_rows: 10, inserted_rows: 10, cleanup_pending: false } },
    ]
    await page.route(`**/api/shipping/tasks/${TASK_ID}`, async (route) => {
      const state = sequence[Math.min(pollIndex, sequence.length - 1)]
      pollIndex += 1
      await route.fulfill({
        json: {
          success: true, message: '',
          data: {
            task_id: TASK_ID, task_type: 'resolve_all', status: state.status,
            progress: state.progress ?? { step: state.status }, result: state.result ?? null,
            message: state.message ?? '',
            cancellable: state.cancellable ?? false, cancel_requested: state.cancel_requested ?? false,
          },
        },
      })
    })
    await page.route(`**/api/shipping/tasks/${TASK_ID}/cancel`, async (route) => {
      await route.fulfill({
        status: 409,
        json: {
          success: false, message: '任务正在提交最终结果，已无法取消',
          data: { task_id: TASK_ID, task_type: 'resolve_all', status: 'committing', cancellable: false, cancel_requested: false },
        },
      })
    })

    await page.getByRole('button', { name: '重建全部成品组合' }).click({ force: true })
    await page.getByRole('button', { name: '确认重建' }).click()

    const cancelBtn = page.locator('[data-testid="task-cancel-btn"]')
    await expect(cancelBtn).toBeVisible()
    await cancelBtn.click()

    await expect(page.getByText('任务正在提交最终结果，已无法取消')).toBeVisible()
    await expect(page.getByText('重算已取消，线上数据保持不变')).toHaveCount(0)
    await expect(page.getByText('刷新完成，共处理 10 条订单')).toBeVisible({ timeout: 10000 })
  })

  test('离开页面（组件卸载）后停止轮询', async ({ page }) => {
    await gotoMaintenance(page)
    await page.route('**/api/shipping/resolve-all', (route) =>
      route.fulfill({ json: { success: true, message: '', data: { task_id: TASK_ID } } })
    )
    let pollCount = 0
    await page.route(`**/api/shipping/tasks/${TASK_ID}`, async (route) => {
      pollCount += 1
      await route.fulfill({
        json: {
          success: true, message: '',
          data: {
            task_id: TASK_ID, task_type: 'resolve_all', status: 'running',
            progress: { step: 'resolving', current: 1, total: 100 }, result: null, message: '',
            cancellable: true, cancel_requested: false,
          },
        },
      })
    })

    await page.getByRole('button', { name: '重建全部成品组合' }).click({ force: true })
    await page.getByRole('button', { name: '确认重建' }).click()
    await expect.poll(() => pollCount).toBeGreaterThanOrEqual(1)

    await page.goto('/#/index')
    await page.waitForLoadState('networkidle')
    const countAfterLeaving = pollCount
    await page.waitForTimeout(2000)
    expect(pollCount).toBe(countAfterLeaving)
  })
})

test.describe('OperatorConfig：旧数据重算取消', () => {
  test('resolving 时显示取消按钮，取消命中后展示线上数据保持不变', async ({ page }) => {
    await mockDataMgmtPage(page)
    await page.route('**/api/shipping/stats', (route) =>
      route.fulfill({ json: { success: true, message: '', data: { stale_count: 5 } } })
    )
    await page.goto('/#/shipping/settings')
    await page.waitForLoadState('networkidle')

    await page.route('**/api/shipping/resolve', (route) =>
      route.fulfill({ json: { success: true, message: '', data: { task_id: TASK_ID } } })
    )
    let pollIndex = 0
    const sequence = [
      { status: 'running', cancellable: true, progress: { step: 'resolving' } },
      { status: 'cancelled', message: '重算已取消，线上数据保持不变' },
    ]
    await page.route(`**/api/shipping/tasks/${TASK_ID}`, async (route) => {
      const state = sequence[Math.min(pollIndex, sequence.length - 1)]
      pollIndex += 1
      await route.fulfill({
        json: {
          success: true, message: '',
          data: {
            task_id: TASK_ID, task_type: 'resolve_stale', status: state.status,
            progress: state.progress ?? { step: state.status }, result: null,
            message: state.message ?? '',
            cancellable: state.cancellable ?? false, cancel_requested: false,
          },
        },
      })
    })
    await page.route(`**/api/shipping/tasks/${TASK_ID}/cancel`, (route) =>
      route.fulfill({
        json: {
          success: true, message: '已发送取消请求',
          data: { task_id: TASK_ID, task_type: 'resolve_stale', status: 'running', cancellable: false, cancel_requested: true },
        },
      })
    )

    const resolveBtn = page.getByRole('button', { name: /刷新成品组合/ })
    await expect(resolveBtn).toBeVisible()
    await resolveBtn.click({ force: true })

    const cancelBtn = page.locator('[data-testid="task-cancel-btn"]')
    await expect(cancelBtn).toBeVisible()
    await cancelBtn.click()

    await expect(page.getByText('重算已取消，线上数据保持不变')).toBeVisible({ timeout: 10000 })
  })
})

test('重建全部成品组合入口临时禁用，按钮不可点击并展示说明', async ({ page }) => {
  await mockDataMgmtPage(page)
  await page.goto('/#/shipping/maintenance')
  await page.waitForLoadState('networkidle')

  const resolveBtn = page.getByRole('button', { name: '重建全部成品组合' })
  await expect(resolveBtn).toBeVisible()
  await expect(resolveBtn).toBeDisabled()
  await expect(page.getByText('当前正在优化，暂不可用')).toBeVisible()

  // 禁用态下点击不应打开确认弹窗
  await resolveBtn.click({ force: true })
  await expect(page.getByRole('button', { name: '确认重建' })).toHaveCount(0)
})
