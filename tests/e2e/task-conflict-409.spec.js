import { test, expect } from '@playwright/test'
import { mockDataMgmtPage } from './fixtures/dataMgmt.js'

// 导入/重算类接口共享同一把数据库级任务租约，同一时间只能有一个在跑；
// 冲突时后端返回 409 + { success:false, message, data:{ task_id } }。
// 前端不应只提示"任务冲突"就结束，而要用 data.task_id 接入该任务已有的
// 进度查看链路（这里用"重建全部成品组合"按钮 resolve-all 验证，见
// handoff/2026-07-24-claude-handoff-26.md 前端协作项第3条）。
// "刷新全局数据"已在财务导入工作流A批改名为"重建全部成品组合"，并移到独立的
// /shipping/maintenance 页面，见 handoff/2026-07-24-claude-data-management-migration-plan.md。
// D批(handoff-33)把进度查看从 SSE 改成对 /api/shipping/tasks/<id> 的短轮询。

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

  let polledTaskId = null
  await page.route('**/api/shipping/tasks/*', async (route) => {
    const url = new URL(route.request().url())
    polledTaskId = url.pathname.split('/').pop()
    await route.fulfill({
      json: {
        success: true,
        message: '',
        data: {
          task_id: polledTaskId,
          task_type: 'resolve_all',
          status: 'done',
          progress: { step: 'done' },
          result: { resolved: 42 },
          message: '',
        },
      },
    })
  })

  await page.goto('/#/shipping/maintenance')
  await page.waitForLoadState('networkidle')

  await page.getByRole('button', { name: '重建全部成品组合' }).click({ force: true })
  await page.getByRole('button', { name: '确认重建' }).click()

  // 后端文案要展示出来，而不是被吞掉
  await expect(page.getByText('已有发货数据任务（导入发货清单）正在运行，请稍后再试')).toBeVisible()

  // 接入的是冲突响应里指向的那个已存在任务，而不是发起一个新任务
  await expect.poll(() => polledTaskId).toBe(RUNNING_TASK_ID)
})
