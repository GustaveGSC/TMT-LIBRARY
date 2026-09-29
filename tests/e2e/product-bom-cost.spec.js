import { test, expect } from '@playwright/test'

// 产品库成品卡片「BOM」「成本」两个分区：复用物料库的 BOM 弹窗 / 成本视图 / 物料卡片
// 权限相互独立：material:view 才显示 BOM；material:price 才显示成本
const OK = (data) => ({ success: true, message: '', data })
const ROW = { code: '1108SG07-A', name: '书桌', model_name: '书桌', name_en: 'Desk' }
const HEAD = {
  id: 1, code: '1108SG07', version: 'A01', drawing: '1108SG07-A01', erp_code: '1108SG07-A', name: '书桌',
  imported_by: 'admin', imported_at: '2026-09-27 10:00', line_count: 2,
}
const TREE = [
  { id: '1', code: 'P1', version: 'A01', drawing: 'P1-A01', erp_code: 'P1-A', name: '桌面', qty: 1, unit: 'PCS',
    unit_price: 24, amount: 24, price_source: 'calc', price_date: null, missing: 0 },
]
const CALC = {
  bom: HEAD, versions: [{ id: 1, drawing: '1108SG07-A01' }],
  current: { unit_price: 24, missing: 0, priced: 4, total: 4, price_source: 'calc', price_date: null },
  started: { date: '2024-01-01', order_no: 'F-SC20240101-001' },
  missing_items: [{ drawing: 'S1-A01', erp_code: 'S1-A', name: '螺钉', qty: 4, parents: ['1108SG07-A01'] }],
  composition: [{ drawing: 'P1-A01', erp_code: 'P1-A', name: '桌面', qty: 1, amount: 24, share: 1 }],
  history: [{ batch_id: 1, order_no: 'F-SC20240101-001', date: '2024-01-01', unit_price: 24, related: true, delta: null }],
}

async function setup(page, permissions) {
  const user = { id: 1, username: 'admin', display_name: '管理员', roles: [], permissions,
                 department_id: 1, employee_no: '001' }
  await page.addInitScript((u) => {
    localStorage.setItem('user', JSON.stringify(u))
    localStorage.setItem('login_time', String(Date.now()))
  }, user)
  // 兜底 mock 必须放行 script：dev 下 @/api/http 模块就挂在 /api/http.js
  await page.route(url => new URL(url).pathname.startsWith('/api/'), r =>
    r.request().resourceType() === 'script' ? r.continue() : r.fulfill({ json: OK([]) }))
  await page.route('**/api/account/me', r => r.fulfill({ json: OK(user) }))
  await page.route('**/api/product/finished*', r => r.fulfill({ json: OK({ items: [ROW], total: 1 }) }))
  const calls = []
  await page.route('**/api/material/**', r => {
    const path = new URL(r.request().url()).pathname
    calls.push(path)
    if (path.endsWith('/bom')) return r.fulfill({ json: OK({ versions: [HEAD], direct_parents: [], top_products: [] }) })
    if (path.endsWith('/calc-price')) return r.fulfill({ json: OK(CALC) })
    if (path.endsWith('/tree')) return r.fulfill({ json: OK({ bom: { ...HEAD, unit_price: 24, missing: 0 }, children: TREE }) })
    if (path.endsWith('/price-batches')) return r.fulfill({ json: OK([]) })
    if (/\/api\/material\/items\/[^/]+$/.test(path)) {
      const code = decodeURIComponent(path.split('/').pop())
      return r.fulfill({ json: OK({ code, name: `ERP${code}`, group_code: 'G', group_name: '组',
        categories: ['packaged'], category_source: 'group', rule_categories: ['packaged'], rule_source: 'group',
        type_override: [], status: '已发布', is_disabled: false, remark: '', images: [], product_images: [] }) })
    }
    return r.fulfill({ json: OK([]) })
  })
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/#/product')
  await page.getByText('表格', { exact: true }).click()
  await page.locator('.el-table__row', { hasText: ROW.code }).first().locator('.el-table__expand-icon').click()
  return calls
}

// 分区定位：按分区标题（「BOM」「成本」各只出现在一个分区标题里）
const secOf = (page, title) =>
  page.locator('.eg-sec').filter({ has: page.locator('.eg-sec-hd', { hasText: title }) })

test('BOM 和成本分成两个分区，各自展开才加载；可查看 BOM、点物料打开物料卡片', async ({ page }) => {
  // 带 material:edit：验证产品库里打开的内容仍是只读
  const calls = await setup(page, ['product:view', 'material:view', 'material:edit', 'material:price'])
  const bomSec = secOf(page, 'BOM')
  const costSec = secOf(page, '成本')
  await expect(bomSec).toBeVisible()
  await expect(costSec).toBeVisible()
  expect(calls.some(p => p.endsWith('/bom') || p.endsWith('/calc-price'))).toBe(false)

  // BOM 分区：只加载 BOM
  await bomSec.locator('.eg-sec-hd').click()
  await expect(bomSec.locator('.bom-ver-table')).toContainText('1108SG07-A01')
  // 不显示「下级」列
  await expect(bomSec.locator('.bom-ver-table th')).toHaveText(['图纸编码', '名称', '导入', ''])
  expect(calls).toContain('/api/material/items/1108SG07-A/bom')
  expect(calls.some(p => p.endsWith('/calc-price'))).toBe(false)
  await expect(bomSec.locator('.cost-view')).toHaveCount(0)

  // 成本分区：只加载成本
  await costSec.locator('.eg-sec-hd').click()
  await expect(costSec.locator('.cost-view .cv-val')).toHaveText('¥24')
  await expect(costSec.locator('.cost-view')).toContainText('F-SC20240101-001')
  await costSec.scrollIntoViewIfNeeded()
  await page.locator('.ec-sections').screenshot({ path: 'test-results/product-bom-cost.png' })

  // 查看 BOM → 弹窗树
  await bomSec.locator('.bom-view-btn').click()
  const dlg = page.locator('.material-bom-dialog')
  await expect(dlg.locator('.bom-dlg-code')).toHaveText('1108SG07-A01')
  await expect(dlg).toContainText('桌面')
  await expect(dlg.locator('.bom-dlg-total')).toContainText('¥24')
  await page.keyboard.press('Escape')

  // 缺价清单只读：没有「标记不计价」
  await costSec.locator('.cv-tabs button', { hasText: '缺价清单' }).click()
  await expect(costSec.locator('.cost-view')).toContainText('S1-A')
  await expect(costSec.locator('.np-btn')).toHaveCount(0)

  // 成本构成里点物料编码 → 打开物料卡片（只读：没有保存、图片编辑、添加/删除价格）
  await costSec.locator('.cv-tabs button', { hasText: '成本构成' }).click()
  await costSec.locator('.cost-view .bom-link', { hasText: 'P1-A01' }).click()
  const card = page.locator('.material-card-dialog')
  await expect(card).toBeVisible()
  expect(calls).toContain('/api/material/items/P1-A')
  await expect(card.locator('.mc-manual textarea')).toBeDisabled()
  await expect(card.locator('.mc-save-btn')).toHaveCount(0)
  await expect(card.locator('.mc-round-btn[title="新增图片"]')).toHaveCount(0)
  await expect(card.locator('.cost-add')).toHaveCount(0)
  await expect(card.locator('.del-btn')).toHaveCount(0)
})

test('只有 material:view：只有 BOM 分区，不请求成本', async ({ page }) => {
  const calls = await setup(page, ['product:view', 'material:view'])
  await expect(secOf(page, 'BOM')).toBeVisible()
  await expect(secOf(page, '成本')).toHaveCount(0)
  await secOf(page, 'BOM').locator('.eg-sec-hd').click()
  await expect(secOf(page, 'BOM').locator('.bom-ver-table')).toContainText('1108SG07-A01')
  expect(calls.some(p => p.endsWith('/calc-price'))).toBe(false)
})

test('只有 material:price：只有成本分区，不请求 BOM，物料编码不可点', async ({ page }) => {
  const calls = await setup(page, ['product:view', 'material:price'])
  await expect(secOf(page, '成本')).toBeVisible()
  await expect(secOf(page, 'BOM')).toHaveCount(0)
  const costSec = secOf(page, '成本')
  await costSec.locator('.eg-sec-hd').click()
  await expect(costSec.locator('.cost-view .cv-val')).toHaveText('¥24')
  await costSec.locator('.cv-tabs button', { hasText: '成本构成' }).click()
  await expect(costSec.locator('.cost-view')).toContainText('P1-A01')
  await expect(costSec.locator('.cost-view .bom-link')).toHaveCount(0)
  expect(calls.some(p => p.endsWith('/bom'))).toBe(false)
})

test('没有物料权限：两个分区都不显示', async ({ page }) => {
  await setup(page, ['product:view'])
  await expect(page.locator('.ec-sections')).toBeVisible()
  await expect(secOf(page, 'BOM')).toHaveCount(0)
  await expect(secOf(page, '成本')).toHaveCount(0)
})
