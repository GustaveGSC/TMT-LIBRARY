import { test, expect } from '@playwright/test'

// 物料卡片排版：第一行 图片 | ERP 信息，其下 人工维护、价格 通栏（用户 2026-09-27 指定）
const OK = (data) => ({ success: true, message: '', data })
const USER = {
  id: 1, username: 'admin', display_name: '管理员', roles: ['admin'],
  permissions: ['material:view', 'material:edit', 'material:price'],
}
const ITEM = {
  code: '14ST02001-A01', name: '锁紧六角螺母', short_name: '螺母', category: null,
  spec: 'M6', erp_spec: 'M6', group_code: '14ST', group_name: '原材料_标准件',
  categories: ['material'], category_labels: ['原材料'], category_source: 'rule',
  rule_categories: ['material'], rule_source: 'rule', type_override: [],
  status: '已发布', is_disabled: false, remark: '', cover_image: null,
  latest_price: 0.12, latest_price_source: 'manual', has_cost_node: true,
  can_add_price: true, cost_notes: '',
}

test('物料卡片按 图片|ERP / 人工维护 / 价格 排版', async ({ page }) => {
  await page.addInitScript((u) => {
    localStorage.setItem('user', JSON.stringify(u))
    localStorage.setItem('login_time', String(Date.now()))
  }, USER)
  // 只拦后端接口：dev 下 Vite 把 @/api/http 模块也挂在 /api/http.js，脚本请求必须放行，否则白屏
  await page.route(url => new URL(url).pathname.startsWith('/api/'), r =>
    r.request().resourceType() === 'script' ? r.continue() : r.fulfill({ json: OK([]) }))
  await page.route('**/api/account/me', r => r.fulfill({ json: OK(USER) }))
  await page.route('**/api/material/items?*', r => r.fulfill({ json: OK({ items: [ITEM], total: 1, page: 1, page_size: 50 }) }))
  await page.route('**/api/material/items/14ST02001-A01', r => r.fulfill({ json: OK(ITEM) }))
  await page.route('**/api/material/items/14ST02001-A01/prices', r => r.fulfill({ json: OK([
    { id: 1, price_date: '2026-09-01', unit_price: 0.12, supplier_name: '供应商A', source: 'manual' },
  ]) }))

  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/#/material')
  await page.locator('.code-link', { hasText: '14ST02001-A01' }).click()
  const card = page.locator('.material-card')
  await expect(card.locator('.mc-erp')).toBeVisible()

  const img = await card.locator('.mc-top-image').boundingBox()
  const erp = await card.locator('.mc-erp').boundingBox()
  const sections = card.locator('.mc-scroll > .mc-section')
  const manual = await sections.nth(0).boundingBox()
  const price = await sections.nth(1).boundingBox()

  // 第一行：图片在左、ERP 在右，顶部对齐
  expect(img.x).toBeLessThan(erp.x)
  expect(Math.abs(img.y - erp.y)).toBeLessThan(2)
  // 人工维护在第一行下方且通栏；价格在人工维护下方且通栏
  expect(manual.y).toBeGreaterThan(erp.y + erp.height - 1)
  expect(price.y).toBeGreaterThan(manual.y + manual.height - 1)
  expect(Math.abs(manual.width - (erp.x + erp.width - img.x))).toBeLessThan(2)
  expect(Math.abs(price.width - manual.width)).toBeLessThan(2)

  await page.locator('.el-dialog').screenshot({ path: 'test-results/material-card-layout.png' })
})
