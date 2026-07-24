import { test, expect } from '@playwright/test'
import { mockProductPage } from './fixtures/productPage.js'

// 产品生命周期更新任务：D批同款短轮询改造，见
// handoff/2026-07-24-claude-product-lifecycle-task-handoff.md。
// 验证：不再创建 EventSource，轮询 /api/product/lifecycle/tasks/<id>，
// 409 接管已有任务，终态停止，组件卸载后停止。

test('生命周期更新走短轮询，不使用 SSE，终态后停止', async ({ page }) => {
  await mockProductPage(page)

  await page.route('**/api/product/lifecycle/update', (route) =>
    route.fulfill({ json: { success: true, message: '', data: { task_id: 'lifecycle-task-1' } } })
  )

  let pollCount = 0
  await page.route('**/api/product/lifecycle/tasks/*', async (route) => {
    pollCount += 1
    const status = pollCount < 2 ? 'running' : 'done'
    await route.fulfill({
      json: {
        success: true,
        message: '',
        data: {
          task_id: 'lifecycle-task-1',
          task_type: 'product_lifecycle',
          status,
          progress: status === 'running'
            ? { step: 'processing', current: pollCount * 100, total: 403 }
            : { step: 'done' },
          result: status === 'done' ? { updated: 1, total_models: 403 } : null,
          message: '',
        },
      },
    })
  })

  const sseRequests = []
  page.on('request', (req) => {
    if (req.url().includes('/lifecycle/progress/')) sseRequests.push(req.url())
  })

  await page.goto('/#/product')
  await page.waitForLoadState('networkidle')

  await page.getByRole('button', { name: '更新生命周期' }).click()
  await expect(page.getByText('生命周期更新完成')).toBeVisible({ timeout: 10000 })

  expect(pollCount).toBeGreaterThanOrEqual(2)
  expect(sseRequests).toEqual([])

  const countAtDone = pollCount
  await page.waitForTimeout(1500)
  expect(pollCount).toBe(countAtDone)
})

test('409 时接管已有任务的 task_id 继续轮询', async ({ page }) => {
  await mockProductPage(page)

  await page.route('**/api/product/lifecycle/update', (route) =>
    route.fulfill({
      status: 409,
      json: {
        success: false,
        message: '已有产品生命周期更新任务正在运行，请等待其结束后重试',
        data: { task_id: 'existing-lifecycle-task' },
      },
    })
  )

  let polledTaskId = null
  await page.route('**/api/product/lifecycle/tasks/*', async (route) => {
    const url = new URL(route.request().url())
    polledTaskId = url.pathname.split('/').pop()
    await route.fulfill({
      json: {
        success: true,
        message: '',
        data: {
          task_id: polledTaskId,
          task_type: 'product_lifecycle',
          status: 'done',
          progress: { step: 'done' },
          result: { updated: 0, total_models: 403 },
          message: '',
        },
      },
    })
  })

  await page.goto('/#/product')
  await page.waitForLoadState('networkidle')

  await page.getByRole('button', { name: '更新生命周期' }).click()

  await expect(page.getByText('已有产品生命周期更新任务正在运行，请等待其结束后重试')).toBeVisible()
  await expect.poll(() => polledTaskId).toBe('existing-lifecycle-task')
})

test('离开页面后停止轮询', async ({ page }) => {
  await mockProductPage(page)

  await page.route('**/api/product/lifecycle/update', (route) =>
    route.fulfill({ json: { success: true, message: '', data: { task_id: 'lifecycle-task-unmount' } } })
  )

  let pollCount = 0
  await page.route('**/api/product/lifecycle/tasks/*', async (route) => {
    pollCount += 1
    await route.fulfill({
      json: {
        success: true,
        message: '',
        data: {
          task_id: 'lifecycle-task-unmount',
          task_type: 'product_lifecycle',
          status: 'running',
          progress: { step: 'processing', current: 1, total: 403 },
          result: null,
          message: '',
        },
      },
    })
  })

  await page.goto('/#/product')
  await page.waitForLoadState('networkidle')
  await page.getByRole('button', { name: '更新生命周期' }).click()

  await expect.poll(() => pollCount).toBeGreaterThanOrEqual(1)

  await page.goto('/#/index')
  await page.waitForLoadState('networkidle')

  const countAfterLeaving = pollCount
  await page.waitForTimeout(2000)
  expect(pollCount).toBe(countAfterLeaving)
})
