import { test, expect } from '@playwright/test'
import { mockDataMgmtPage } from './fixtures/dataMgmt.js'

// D批(handoff-33)：发货后台任务进度从 SSE 改为对 /api/shipping/tasks/<id> 的短轮询。
// 这里验证：不再创建 EventSource，请求间隔约1秒且不重叠，终态(done)后立即停止轮询。

test('resolve-all 进度改为短轮询，不再使用 SSE，终态后停止', async ({ page }) => {
  await mockDataMgmtPage(page)

  await page.route('**/api/shipping/resolve-all', (route) =>
    route.fulfill({
      json: { success: true, message: '', data: { task_id: 'poll-task-1' } },
    })
  )

  const requestTimestamps = []
  let pollCount = 0
  let inFlight = false
  let overlapDetected = false

  await page.route('**/api/shipping/tasks/*', async (route) => {
    if (inFlight) overlapDetected = true
    inFlight = true
    requestTimestamps.push(Date.now())
    pollCount += 1

    // 前两次仍在跑，第三次才结束，用来验证真的是"轮询"而不是一次性拿到终态
    const status = pollCount < 3 ? 'running' : 'done'
    await route.fulfill({
      json: {
        success: true,
        message: '',
        data: {
          task_id: 'poll-task-1',
          task_type: 'resolve_all',
          status,
          progress: status === 'running'
            ? { step: 'resolving', current: pollCount * 100, total: 300 }
            : { step: 'done' },
          result: status === 'done' ? { resolved: 300 } : null,
          message: '',
        },
      },
    })
    inFlight = false
  })

  const sseRequests = []
  page.on('request', (req) => {
    if (req.url().includes('/import/progress/')) sseRequests.push(req.url())
  })

  await page.goto('/#/shipping/maintenance')
  await page.waitForLoadState('networkidle')

  await page.getByRole('button', { name: '重建全部成品组合' }).click({ force: true })
  await page.getByRole('button', { name: '确认重建' }).click()

  await expect(page.getByText('刷新完成')).toBeVisible({ timeout: 10000 })

  expect(pollCount).toBeGreaterThanOrEqual(3)
  expect(overlapDetected).toBe(false)
  expect(sseRequests).toEqual([])

  // 相邻两次轮询间隔应接近 1 秒（允许网络/事件循环抖动）
  for (let i = 1; i < requestTimestamps.length; i++) {
    const gap = requestTimestamps[i] - requestTimestamps[i - 1]
    expect(gap).toBeGreaterThan(700)
    expect(gap).toBeLessThan(2000)
  }

  // 终态后不应再继续轮询
  const countAtDone = pollCount
  await page.waitForTimeout(1500)
  expect(pollCount).toBe(countAtDone)
})

test('离开页面（组件卸载）后停止轮询', async ({ page }) => {
  await mockDataMgmtPage(page)

  await page.route('**/api/shipping/resolve-all', (route) =>
    route.fulfill({
      json: { success: true, message: '', data: { task_id: 'poll-task-unmount' } },
    })
  )

  let pollCount = 0
  await page.route('**/api/shipping/tasks/*', async (route) => {
    pollCount += 1
    // 一直保持 running，模拟长任务，验证卸载后不再继续轮询而不是自然结束
    await route.fulfill({
      json: {
        success: true,
        message: '',
        data: {
          task_id: 'poll-task-unmount',
          task_type: 'resolve_all',
          status: 'running',
          progress: { step: 'resolving', current: 1, total: 100 },
          result: null,
          message: '',
        },
      },
    })
  })

  await page.goto('/#/shipping/maintenance')
  await page.waitForLoadState('networkidle')

  await page.getByRole('button', { name: '重建全部成品组合' }).click({ force: true })
  await page.getByRole('button', { name: '确认重建' }).click()

  await expect.poll(() => pollCount).toBeGreaterThanOrEqual(1)

  // 离开页面，卸载 ShippingMaintenancePage
  await page.goto('/#/index')
  await page.waitForLoadState('networkidle')

  const countAfterLeaving = pollCount
  await page.waitForTimeout(2000)
  expect(pollCount).toBe(countAfterLeaving)
})
