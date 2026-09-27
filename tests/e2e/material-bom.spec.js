import { test, expect } from '@playwright/test'

// 物料BOM：研发 BOM 导入/浏览（物料BOM tab）+ 物料表 BOM 标记 + 物料卡片 BOM 区（下级结构/被使用）
const OK = (data) => ({ success: true, message: '', data })
const USER = {
  id: 1, username: 'admin', display_name: '管理员', roles: ['admin'],
  permissions: ['material:view', 'material:edit', 'material:price'],
}

const bomHead = (id, code, version, extra = {}) => ({
  id, code, version, drawing: `${code}-${version}`, erp_code: `${code}-A`, name: `名称${code}`,
  spec: null, category: '成品', source_file: 'a.xlsx', imported_by: 'admin',
  imported_at: '2026-09-27 10:00', ...extra,
})
const TREE = [
  { id: '1-1', code: 'P1', version: 'A01', drawing: 'P1-A01', erp_code: 'P1-A', name: '桌面',
    spec: null, category: '产成品', qty: 1, unit: 'PCS', bom_id: 2,
    children: [
      { id: '2-1', code: 'R1', version: 'A01', drawing: 'R1-A01', erp_code: 'R1-A01', name: '方管',
        spec: null, category: '原材料', qty: 3, unit: 'PCS', bom_id: null },
    ] },
  { id: '1-2', code: 'S1', version: 'A01', drawing: 'S1-A01', erp_code: null, name: '螺钉',
    spec: null, category: '原材料', qty: 4, unit: 'PCS', bom_id: null },
]
const item = (code, extra = {}) => ({
  code, name: `ERP${code}`, short_name: null, category: null, spec: null, erp_spec: null,
  group_code: 'G', group_name: '组', categories: ['finished'], category_source: 'group',
  rule_categories: ['finished'], rule_source: 'group', type_override: [],
  status: '已发布', is_disabled: false, remark: '', images: [], product_images: [],
  has_bom: false, ...extra,
})

async function setup(page) {
  await page.addInitScript((u) => {
    localStorage.setItem('user', JSON.stringify(u))
    localStorage.setItem('login_time', String(Date.now()))
  }, USER)
  // 兜底 mock 必须放行 script：dev 下 @/api/http 模块就挂在 /api/http.js
  await page.route(url => new URL(url).pathname.startsWith('/api/'), r =>
    r.request().resourceType() === 'script' ? r.continue() : r.fulfill({ json: OK([]) }))
  await page.route('**/api/account/me', r => r.fulfill({ json: OK(USER) }))
  await page.setViewportSize({ width: 1440, height: 900 })
}

test('物料BOM tab：列表、多层结构、导入结果', async ({ page }) => {
  await setup(page)
  const list = [bomHead(1, 'F1', 'A02'), bomHead(2, 'P1', 'A01', { category: '产成品' })]
  await page.route('**/api/material/boms?*', r => r.fulfill({
    json: OK({ items: list.map(b => ({ ...b, line_count: 2 })), total: 2, page: 1, page_size: 50,
               categories: ['产成品', '成品'] }) }))
  await page.route('**/api/material/boms/*/tree', r => r.fulfill({
    json: OK({ bom: list[0], children: TREE }) }))
  let uploaded = false
  await page.route('**/api/material/boms/import', r => {
    uploaded = true
    return r.fulfill({ json: OK({ created: 3, updated: 1, lines: 12, roots: ['F1-A02'],
                                  unmatched: ['S1-A01'], skipped: 5 }) })
  })
  await page.route('**/api/material/items/*', r => r.fulfill({ json: OK(item('P1-A')) }))

  await page.goto('/#/material')
  await page.locator('.nav-item', { hasText: '物料BOM' }).click()

  await expect(page.locator('.bp-item')).toHaveCount(2)
  await expect(page.locator('.bp-item').first()).toHaveClass(/active/)
  await expect(page.locator('.bd-drawing')).toHaveText('F1-A02')
  // 默认全部展开：P1 / R1 / S1 三行；没匹配到 ERP 的显示「未匹配」
  await expect(page.locator('.bom-tree .bt-drawing')).toHaveText(['P1-A01', 'R1-A01', 'S1-A01'])
  await expect(page.locator('.bom-tree .bt-none')).toHaveText('未匹配')
  await page.screenshot({ path: 'test-results/material-bom-panel.png' })

  // 导入：选文件后直接上传，弹结果
  await page.locator('.bp-toolbar input[type=file]').setInputFiles({
    name: 'bom.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: Buffer.from('x'),
  })
  await expect(page.locator('.ir-stats b')).toHaveText(['3', '1', '12'])
  await expect(page.locator('.ir-codes')).toHaveText('S1-A01')
  await expect(page.locator('.ir-muted')).toContainText('已按规则跳过 5 行')
  expect(uploaded).toBe(true)
  await page.locator('.el-dialog button', { hasText: '知道了' }).click()

  // 点树里的 ERP 编码打开物料卡片
  await page.locator('.bom-tree .bt-erp', { hasText: 'P1-A' }).click()
  await expect(page.locator('.el-dialog__header .mc-erp-code')).toHaveText('P1-A')
})

test('物料表 BOM 标记 + 物料卡片 BOM 区：版本、被使用、卡片内跳转与返回', async ({ page }) => {
  await setup(page)
  const F = item('F1-A', { has_bom: true })
  const R = item('R1-A01', { categories: ['material'], rule_categories: ['material'] })
  await page.route('**/api/material/items?*', r => r.fulfill({
    json: OK({ items: [F, R], total: 2, page: 1, page_size: 50 }) }))
  await page.route(url => /\/api\/material\/items\/[^/]+$/.test(new URL(url).pathname), r => {
    const code = decodeURIComponent(new URL(r.request().url()).pathname.split('/').pop())
    return r.fulfill({ json: OK(code === 'R1-A01' ? R : F) })
  })
  const bomRequests = []
  await page.route('**/api/material/items/*/bom*', r => {
    const u = new URL(r.request().url())
    bomRequests.push(u.pathname + u.search)
    if (u.pathname.includes('R1-A01')) {
      return r.fulfill({ json: OK({
        versions: [], selected_id: null, tree: [],
        direct_parents: [{ ...bomHead(2, 'P1', 'A01', { category: '产成品' }), qty: 3, unit: 'PCS', child_drawing: 'R1-A01' }],
        top_products: [bomHead(1, 'F1', 'A02')],
      }) })
    }
    return r.fulfill({ json: OK({
      versions: [bomHead(1, 'F1', 'A02'), bomHead(3, 'F1', 'A01')], selected_id: 1,
      tree: TREE, direct_parents: [], top_products: [],
    }) })
  })

  await page.goto('/#/material')
  // 物料表：有 BOM 的行显示标记，没有的不显示
  await expect(page.locator('.bom-mark')).toHaveCount(1)
  await page.locator('.bom-mark').click()
  const card = page.locator('.material-card')
  await expect(page.locator('.el-dialog__header .mc-erp-code')).toHaveText('F1-A')

  // 下级结构：多版本时有版本下拉；树默认只展开第一层
  const bomSec = card.locator('.mc-bom')
  await expect(bomSec.locator('.cost-tab.active')).toContainText('下级结构（2）')
  await expect(bomSec.locator('.bom-ver')).toBeVisible()
  // 折叠的子行仍在 DOM 里（el-table 只是隐藏），所以只数可见的
  await expect(bomSec.locator('.bt-drawing:visible')).toHaveText(['P1-A01', 'S1-A01'])
  await bomSec.scrollIntoViewIfNeeded()
  await page.locator('.el-dialog').screenshot({ path: 'test-results/material-card-bom.png' })

  // 切换研发版本：带 bom_id 重新请求
  await bomSec.locator('.bom-ver').click()
  await page.locator('.el-select-dropdown__item', { hasText: '研发版本 A01' }).click()
  await expect.poll(() => bomRequests.some(u => u.includes('bom_id=3'))).toBe(true)

  // 点子件 ERP 编码在卡片内跳转 → 没有自身 BOM、被使用，默认切到「被使用」
  await bomSec.locator('.bt-erp', { hasText: 'P1-A' }).click()
  // P1-A 在 mock 里返回 F 的详情；这里只验证跳转发生并出现返回按钮
  await expect(page.locator('.el-dialog__header .mc-back-btn')).toBeVisible()
  await page.locator('.el-dialog__header .mc-back-btn').click()
  await expect(page.locator('.el-dialog__header .mc-back-btn')).toHaveCount(0)

  // 关闭后打开原材料 R1：默认显示「被使用」
  await page.locator('.el-dialog__header .mc-close-btn').click()
  await page.locator('.code-link', { hasText: 'R1-A01' }).click()
  await expect(page.locator('.el-dialog__header .mc-erp-code')).toHaveText('R1-A01')
  await expect(bomSec.locator('.cost-tab.active')).toContainText('被使用（1 个产品）')
  await expect(bomSec.locator('.used-chip')).toContainText('F1-A02')
  await expect(bomSec.locator('.cost-table tbody tr')).toHaveCount(1)
  await bomSec.scrollIntoViewIfNeeded()
  await page.locator('.el-dialog').screenshot({ path: 'test-results/material-card-bom-used.png' })

  // 点最终产品跳到 F1-A，再返回 R1-A01
  await bomSec.locator('.used-chip').click()
  await expect(page.locator('.el-dialog__header .mc-erp-code')).toHaveText('F1-A')
  await page.locator('.el-dialog__header .mc-back-btn').click()
  await expect(page.locator('.el-dialog__header .mc-erp-code')).toHaveText('R1-A01')
})

test('物料BOM：导入校验失败逐条列出；删除被引用的 BOM 需二次确认', async ({ page }) => {
  await setup(page)
  const list = [bomHead(2, 'M1', 'A01', { category: '半成品' })]
  await page.route('**/api/material/boms?*', r => r.fulfill({
    json: OK({ items: list.map(b => ({ ...b, line_count: 1 })), total: 1, page: 1, page_size: 50,
               categories: ['半成品'] }) }))
  await page.route('**/api/material/boms/*/tree', r => r.fulfill({
    json: OK({ bom: list[0], children: [] }) }))
  await page.route('**/api/material/boms/import', r => r.fulfill({
    json: { success: false, message: '第 5 行数量「abc」无效；第 9 行层次「1.1」是数字格式，请把层次列设为文本后重新导出', data: null } }))
  const deletes = []
  await page.route('**/api/material/boms/2*', r => {
    if (r.request().method() !== 'DELETE') return r.fallback()
    const force = new URL(r.request().url()).searchParams.get('force')
    deletes.push(force)
    if (!force) {
      return r.fulfill({ json: { success: false, message: '被引用', data: {
        needs_force: true, references: [bomHead(1, 'F1', 'A01'), bomHead(3, 'P1', 'A01')] } } })
    }
    return r.fulfill({ json: OK(null) })
  })

  await page.goto('/#/material')
  await page.locator('.nav-item', { hasText: '物料BOM' }).click()
  await expect(page.locator('.bd-drawing')).toHaveText('M1-A01')

  // 导入失败：弹窗逐条列出错误
  await page.locator('.bp-toolbar input[type=file]').setInputFiles({
    name: 'bad.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: Buffer.from('x'),
  })
  await expect(page.locator('.ie-list li')).toHaveCount(2)
  await expect(page.locator('.ie-list li').first()).toHaveText('第 5 行数量「abc」无效')
  await page.locator('.el-dialog button', { hasText: '知道了' }).click()

  // 删除：第一次确认 → 后端说被引用 → 列出上级再确认 → 带 force 删除
  await page.locator('.bd-del').click()
  await page.locator('.el-message-box button', { hasText: '删除' }).click()
  // 第一个确认框关闭动画期间两个 message box 同时在 DOM 里，按标题定位第二个
  const second = page.locator('.el-message-box', { hasText: '仍被引用' })
  await expect(second).toContainText('F1-A01')
  await expect(second).toContainText('P1-A01')
  await second.locator('button', { hasText: '仍然删除' }).click()
  await expect.poll(() => deletes).toEqual([null, '1'])
})
