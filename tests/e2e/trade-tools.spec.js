import { test, expect } from '@playwright/test'

// 外贸工具：主页入口按 trade:view 显示；内部「产品改制」目前是方案讨论稿
const OK = (data) => ({ success: true, message: '', data })

async function login(page, permissions) {
  const user = { id: 1, username: 'u1', display_name: '测试', roles: [], permissions,
                 department_id: 1, employee_no: '001' }
  await page.addInitScript((u) => {
    localStorage.setItem('user', JSON.stringify(u))
    localStorage.setItem('login_time', String(Date.now()))
  }, user)
  // 兜底 mock 必须放行 script：dev 下 @/api/http 模块就挂在 /api/http.js
  await page.route(url => new URL(url).pathname.startsWith('/api/'), r =>
    r.request().resourceType() === 'script' ? r.continue() : r.fulfill({ json: OK([]) }))
  await page.route('**/api/account/me', r => r.fulfill({ json: OK(user) }))
  await page.setViewportSize({ width: 1440, height: 900 })
}

test('有 trade:view：主页出现外贸工具，进入后可查看产品改制方案', async ({ page }) => {
  await login(page, ['trade:view'])
  await page.goto('/#/index')
  const entry = page.getByText('外贸工具', { exact: true })
  await expect(entry).toBeVisible()
  await entry.click()
  await expect(page).toHaveURL(/#\/trade-tools/)
  await expect(page.locator('.page-title')).toHaveText('外贸工具')
  await expect(page.locator('.tool-card', { hasText: '产品改制' })).toContainText('方案讨论中')
  await page.screenshot({ path: 'test-results/trade-tools-home.png' })

  await page.locator('.tool-card', { hasText: '产品改制' }).click()
  await expect(page.locator('.plan-title')).toHaveText('产品改制')
  await expect(page.locator('.plan-banner')).toContainText('方案讨论稿')
  await expect(page.locator('.step')).toHaveCount(6)
  await expect(page.locator('.qa')).toHaveCount(7)
  await expect(page.locator('.plan-sec h2', { hasText: '改制提醒清单' })).toBeVisible()
  await page.screenshot({ path: 'test-results/trade-tools-plan.png', fullPage: false })
  await page.locator('.plan-sec').filter({ has: page.locator('h2', { hasText: '改制提醒清单' }) }).screenshot({ path: 'test-results/trade-tools-reminder.png' })
  // 改动规则：区分最外层与部件内部；新建编码示例包含「最外层新增」
  await expect(page.locator('.plan-sec').filter({ has: page.locator('h2', { hasText: '外贸怎么标改动' }) }).locator('th'))
    .toHaveText(['操作', '最外层（成品下一级）', '部件内部'])
  const codeSec = page.locator('.plan-sec').filter({ has: page.locator('h2', { hasText: '哪些需要新建编码' }) })
  await expect(codeSec.locator('.code-tbl')).toContainText('不新建编码')
  await page.locator('.plan-sec').filter({ has: page.locator('h2', { hasText: '外贸怎么标改动' }) }).screenshot({ path: 'test-results/trade-tools-ops.png' })
  await codeSec.screenshot({ path: 'test-results/trade-tools-newcode.png' })
})

test('没有 trade:view：主页不显示外贸工具', async ({ page }) => {
  await login(page, ['product:view'])
  await page.goto('/#/index')
  await expect(page.getByText('产品库', { exact: true })).toBeVisible()
  await expect(page.getByText('外贸工具', { exact: true })).toHaveCount(0)
})
