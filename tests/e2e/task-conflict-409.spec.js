import { test, expect } from '@playwright/test'
import { mockDataMgmtPage } from './fixtures/dataMgmt.js'

// 导入/重算类接口共享同一把数据库级任务租约，同一时间只能有一个在跑；
// 冲突时后端返回 409 + { success:false, message, data:{ task_id } }。
// 前端不应只提示"任务冲突"就结束，而要用 data.task_id 接入该任务已有的
// 进度查看链路（这里用"刷新全局数据"按钮 resolve-all 验证，见
// handoff/2026-07-24-claude-handoff-26.md 前端协作项第3条）。

const RUNNING_TASK_ID = 'existing-task-id-123'

test('resolve-all 遇到 409 时展示后端文案并接入已有任务的进度流', async ({ page }) => {
  await mockDataMgmtPage(page)

  await page.route('**/api/shipping/resolve-all', (route) =>
    route.fulfill({
      status: 409,
      json: {
        success: false,
        message: '已有发货数据任务（导入发货清单）正在运行，请稍后再试',
        data: { task_id: RUNNING_TASK_ID },
      },
    })
  )

  let progressTaskId = null
  await page.route('**/api/shipping/import/progress/*', async (route) => {
    const url = new URL(route.request().url())
    progressTaskId = url.pathname.split('/').pop()
    // SSE 响应：直接推一条 done 事件后结束流
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: `data: ${JSON.stringify({ step: 'done', data: { resolved: 42 } })}\n\n`,
    })
  })

  await page.goto('/#/data-mgmt')
  await page.waitForLoadState('networkidle')

  await page.getByRole('button', { name: '刷新全局数据' }).click({ force: true })
  await page.getByRole('button', { name: '确认刷新' }).click()

  // 后端文案要展示出来，而不是被吞掉
  await expect(page.getByText('已有发货数据任务（导入发货清单）正在运行，请稍后再试')).toBeVisible()

  // 接入的是冲突响应里指向的那个已存在任务，而不是发起一个新任务
  await expect.poll(() => progressTaskId).toBe(RUNNING_TASK_ID)
})
