import { test, expect } from '@playwright/test'

// 采购工具：主页入口按 purchase:view 显示；导入价格 = 上传 → 预览确认价格日期 → 导入
const OK = (data) => ({ success: true, message: '', data })

async function login(page, permissions) {
  const user = { id: 1, username: 'buyer', display_name: '采购', roles: [], permissions,
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

const PREVIEW = (priceDate, newCount = 3) => ({
  order_no: '2M2-SC20240620-050', suggested_date: '2024-06-20', price_date: priceDate,
  sheets: 1, line_count: 8,
  items: [
    { code: 'R1', name: '方管', price: 1.5, kind: 'material', status: newCount ? 'new' : 'skip', in_erp: true },
    { code: 'R2', name: '螺钉', price: 2, kind: 'material', status: newCount ? 'new' : 'skip', in_erp: true },
    { code: 'S9', name: '外购配件包', price: 10, kind: 'semi', status: newCount ? 'new' : 'skip', in_erp: false },
  ],
  new_count: newCount, skip_count: 3 - newCount,
  special_semis: [{ code: 'S9', name: '外购配件包', price: 10, kind: 'semi' }],
  zero_items: [{ code: 'R5', name: '胶水', in_erp: true }],
  conflicts: [{ code: 'R1', prices: [1.5, 1.6] }],
  warnings: [],
})

test('采购工具：预览确认日期后导入价格，记录可见', async ({ page }) => {
  await login(page, ['purchase:view', 'material:price'])
  const previewDates = []
  await page.route('**/api/purchase/price-import/preview', async r => {
    const body = r.request().postData() || ''
    const m = body.match(/name="price_date"\r\n\r\n([0-9-]+)/)
    previewDates.push(m ? m[1] : null)
    // 选 2024-06-20 以外的日期都是新价格；06-20 当天已导入过 → 全部同日同价
    const day = m ? m[1] : '2024-06-20'
    return r.fulfill({ json: OK(PREVIEW(day, day === '2024-06-20' ? 0 : 3)) })
  })
  let imported = null
  await page.route('**/api/purchase/price-import', r => {
    const m = (r.request().postData() || '').match(/name="price_date"\r\n\r\n([0-9-]+)/)
    imported = m && m[1]
    return r.fulfill({ json: OK({ batch_id: 9, order_no: '2M2-SC20240620-050', price_date: imported,
                                  created: 3, skipped: 0, special_semis: 1, zero_count: 1, conflicts: [] }) })
  })
  const historyRows = [{ id: 9, order_no: '2M2-SC20240620-050', price_date: '2024-07-01', price_count: 3,
                         created_by: 'buyer', created_at: '2026-09-27 20:00' }]
  let historyCalls = 0
  await page.route('**/api/purchase/price-import/history', r => {
    historyCalls++
    return r.fulfill({ json: OK(historyCalls > 1 ? historyRows : []) })
  })

  await page.goto('/#/index')
  await page.getByText('采购工具', { exact: true }).click()
  await expect(page).toHaveURL(/#\/purchase-tools/)
  await page.locator('.tool-card', { hasText: '导入价格' }).click()

  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    page.locator('.prc button', { hasText: '选择采购 BOM' }).click(),
  ])
  await chooser.setFiles({ name: 'bom.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                           buffer: Buffer.from('x') })

  // 默认用订单号日期；当天已有同价 → 新增 0，导入按键不可用
  await expect(page.locator('.prc-date input')).toHaveValue('2024-06-20')
  await expect(page.locator('.prc-stats > div').first()).toContainText('0')
  await expect(page.locator('.prc-actions button', { hasText: '确认导入' })).toBeDisabled()

  // 改日期 → 带新日期重新预览 → 3 条新增
  await page.locator('.prc-date input').fill('2024-07-01')
  await page.locator('.prc-date input').press('Enter')
  await expect.poll(() => previewDates.at(-1)).toBe('2024-07-01')
  await expect(page.locator('.prc-stats > div').first()).toContainText('3')
  await expect(page.locator('.prc-table').first().locator('.tag-semi')).toHaveText('特例半成品')
  await page.screenshot({ path: 'test-results/purchase-price-preview.png', fullPage: false })

  await page.locator('.prc-tabs button', { hasText: '无价格' }).click()
  await expect(page.locator('.prc-table').first()).toContainText('胶水')

  await page.locator('.prc-actions button', { hasText: '确认导入' }).click()
  await page.locator('.el-message-box button', { hasText: '导入' }).click()
  await expect(page.locator('.prc-result')).toContainText('新增 3 条')
  expect(imported).toBe('2024-07-01')
  await expect(page.locator('.prc-card').last()).toContainText('2M2-SC20240620-050')
})

test('没有物料价格权限：可以进入采购工具但不能导入', async ({ page }) => {
  await login(page, ['purchase:view'])
  await page.goto('/#/purchase-tools')
  await page.locator('.tool-card', { hasText: '导入价格' }).click()
  await expect(page.locator('.prc-warn')).toContainText('material:price')
  await expect(page.locator('.prc button', { hasText: '选择采购 BOM' })).toHaveCount(0)
})

test('没有 purchase:view：主页不显示采购工具', async ({ page }) => {
  await login(page, ['product:view'])
  await page.goto('/#/index')
  await expect(page.getByText('产品库', { exact: true })).toBeVisible()
  await expect(page.getByText('采购工具', { exact: true })).toHaveCount(0)
})
