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

// 最小的「像 xlsx」的响应体：前端只校验 zip 头 PK
const XLSX_BODY = Buffer.from([0x50, 0x4B, 0x03, 0x04, 0, 0, 0, 0])
const exportRoute = (page, hits) => page.route('**/api/material/boms/*/export', r => {
  hits.push(Number(new URL(r.request().url()).pathname.split('/').slice(-2)[0]))
  return r.fulfill({ body: XLSX_BODY, contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
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
  const list = [
    { ...bomHead(1, 'F1', 'A02'), material_types: ['finished'] },
    { ...bomHead(2, 'P1', 'A01', { category: '产成品' }), material_types: ['packaged'] },
  ]
  const listParams = []
  await page.route('**/api/material/boms?*', r => {
    const type = new URL(r.request().url()).searchParams.get('material_type')
    listParams.push(type)
    const items = list.filter(b => !type || b.material_types.includes(type))
    return r.fulfill({ json: OK({
      items: items.map(b => ({ ...b, line_count: 2 })), total: items.length, all_total: 2,
      page: 1, page_size: 50,
      type_counts: { finished: 1, packaged: 1, semi: 0, material: 0, useless: 0, unclassified: 0, unmatched: 0 },
    }) })
  })
  await page.route('**/api/material/boms/*/tree', r => r.fulfill({
    json: OK({ bom: list[0], children: TREE }) }))
  let uploaded = false
  await page.route('**/api/material/boms/import', r => {
    uploaded = true
    return r.fulfill({ json: OK({ created: 3, updated: 1, lines: 12, roots: ['F1-A02'],
                                  unmatched: ['S1-A01'], skipped: 5 }) })
  })
  await page.route('**/api/material/items/*', r => r.fulfill({ json: OK(item('P1-A')) }))
  const exportHits = []
  await exportRoute(page, exportHits)

  await page.goto('/#/material')
  await page.locator('.nav-item', { hasText: '物料BOM' }).click()

  await expect(page.locator('.bp-item')).toHaveCount(2)
  // 按物料类型分类：全部 + 有数据的分类；列表项显示物料类型标签
  await expect(page.locator('.bp-type')).toHaveText(['全部2', '成品1', '产成品1'])
  await expect(page.locator('.bp-item').first().locator('.bp-cat-tag')).toHaveText('成品')
  await expect(page.locator('.bp-item').first()).toHaveClass(/active/)
  // 标题显示完整研发编码（成品带完整版本 -A02，而非 ERP 的 -A）；不显示上传文件名
  await expect(page.locator('.bd-drawing')).toHaveText('F1-A02')
  await expect(page.locator('.bd-meta')).not.toContainText('a.xlsx')
  // 列：序号 / 图纸编码 / ERP编码 / 名称 / 数量 / 单位（有物料价格权限时另有单价/金额）
  await expect(page.locator('.bom-tree th')).toHaveText(['序号', '图纸编码', 'ERP编码', '名称', '数量', '单位', '单价', '金额'])
  await expect(page.locator('.bom-tree .bt-seq')).toHaveText(['1', '1.1', '2'])
  // 图纸编码显示完整版本，ERP 编码显示 ERP 里的写法（产成品只到 -A）
  await expect(page.locator('.bom-tree .bt-drawing')).toHaveText(['P1-A01', 'R1-A01', 'S1-A01'])
  await expect(page.locator('.bom-tree .bt-erp')).toHaveText(['P1-A', 'R1-A01'])
  // 序号列固定窄宽度，不再随表格拉伸
  const seqWidth = await page.locator('.bom-tree th').first().evaluate(el => el.getBoundingClientRect().width)
  expect(seqWidth).toBeLessThanOrEqual(121)
  // ERP 里没有的显示「未匹配」
  await expect(page.locator('.bom-tree .bt-none')).toHaveText('未匹配')

  // 一键展开/收起：默认全部展开 → 收起只剩第一层 → 再展开恢复
  const toggle = page.locator('.bd-toggle')
  await expect(toggle).toHaveText('全部收起')
  await toggle.click()
  await expect(toggle).toHaveText('全部展开')
  await expect(page.locator('.bom-tree .bt-seq:visible')).toHaveText(['1', '2'])
  await toggle.click()
  await expect(toggle).toHaveText('全部收起')
  await expect(page.locator('.bom-tree .bt-seq:visible')).toHaveText(['1', '1.1', '2'])

  // 导出：下载当前选中的 BOM
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.locator('.bd-export').click(),
  ])
  expect(download.suggestedFilename()).toBe('BOM-F1-A02.xlsx')
  expect(exportHits).toEqual([1])
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

  // 切换分类：带 material_type 重新请求，列表只剩该类
  await page.locator('.bp-type', { hasText: '产成品' }).click()
  await expect(page.locator('.bp-item')).toHaveCount(1)
  await expect(page.locator('.bp-item .bp-drawing')).toHaveText('P1-A01')
  expect(listParams).toContain('packaged')
  await page.locator('.bp-type', { hasText: '全部' }).click()
  await expect(page.locator('.bp-item')).toHaveCount(2)

  // 点树里的 ERP 编码打开物料卡片
  await page.locator('.bom-tree .bt-erp', { hasText: 'P1-A' }).click()
  await expect(page.locator('.el-dialog__header .mc-erp-code')).toHaveText('P1-A')
})

test('物料表 BOM 标记 + 物料卡片：BOM下级按研发版本列出并弹窗查看、被使用分区、卡片内跳转', async ({ page }) => {
  await setup(page)
  const F = item('F1-A', { has_bom: true })
  const R = item('R1-A01', { categories: ['material'], rule_categories: ['material'] })
  await page.route('**/api/material/items?*', r => r.fulfill({
    json: OK({ items: [F, R], total: 2, page: 1, page_size: 50 }) }))
  await page.route(url => /\/api\/material\/items\/[^/]+$/.test(new URL(url).pathname), r => {
    const code = decodeURIComponent(new URL(r.request().url()).pathname.split('/').pop())
    return r.fulfill({ json: OK(code === 'R1-A01' ? R : F) })
  })
  await page.route('**/api/material/items/*/bom*', r => {
    const u = new URL(r.request().url())
    if (u.pathname.includes('R1-A01')) {
      return r.fulfill({ json: OK({
        versions: [],
        direct_parents: [{ ...bomHead(2, 'P1', 'A01', { category: '产成品' }), qty: 3, unit: 'PCS', child_drawing: 'R1-A01' }],
        top_products: [bomHead(1, 'F1', 'A02')],
      }) })
    }
    return r.fulfill({ json: OK({
      versions: [{ ...bomHead(1, 'F1', 'A02'), line_count: 2 }, { ...bomHead(3, 'F1', 'A01'), line_count: 5 }],
      direct_parents: [], top_products: [],
    }) })
  })
  const treeRequests = []
  await page.route('**/api/material/boms/*/tree', r => {
    const id = Number(new URL(r.request().url()).pathname.split('/').slice(-2)[0])
    treeRequests.push(id)
    return r.fulfill({ json: OK({ bom: bomHead(id, 'F1', id === 1 ? 'A02' : 'A01'), children: TREE }) })
  })

  await page.goto('/#/material')
  // 物料表：有 BOM 的行显示标记，没有的不显示
  await expect(page.locator('.bom-mark')).toHaveCount(1)
  await page.locator('.bom-mark').click()
  const card = page.locator('.material-card')
  await expect(page.locator('.el-dialog__header .mc-erp-code')).toHaveText('F1-A')

  // BOM下级与被使用是两个独立分区
  const bomSec = card.locator('.mc-bom')
  const usedSec = card.locator('.mc-used')
  await expect(bomSec.locator('.mc-section-title')).toContainText('BOM下级')
  // 1 个 ERP 物料挂 2 个研发 BOM：两个都列出来，各带下级数量；卡片里不直接展开树
  await expect(bomSec.locator('.bom-drawing')).toHaveText(['F1-A02', 'F1-A01'])
  await expect(bomSec.locator('tbody tr').nth(1)).toContainText('5 项')
  await expect(bomSec.locator('.bom-tree')).toHaveCount(0)
  // 没有被使用：整个分区隐藏
  await expect(usedSec).toHaveCount(0)
  await bomSec.scrollIntoViewIfNeeded()
  await page.locator('.el-dialog.material-card-dialog').screenshot({ path: 'test-results/material-card-bom.png' })

  // 点第二个版本的「查看」：单独弹窗显示该版本的完整结构
  await bomSec.locator('.bom-view-btn').nth(1).click()
  const dlg = page.locator('.el-dialog.material-bom-dialog')
  await expect(dlg.locator('.bom-dlg-code')).toHaveText('F1-A01')
  await expect(dlg.locator('.bt-seq')).toHaveText(['1', '1.1', '2'])
  expect(treeRequests).toEqual([3])
  // 弹窗里也有一键展开/收起
  const dlgToggle = dlg.locator('.bom-dlg-toggle')
  await dlgToggle.click()
  await expect(dlg.locator('.bt-seq:visible')).toHaveText(['1', '2'])
  await dlgToggle.click()
  await expect(dlg.locator('.bt-seq:visible')).toHaveText(['1', '1.1', '2'])
  // 弹窗里也能导出
  const exportHits = []
  await exportRoute(page, exportHits)
  const [dlgDownload] = await Promise.all([
    page.waitForEvent('download'),
    dlg.locator('.bom-dlg-export').click(),
  ])
  expect(dlgDownload.suggestedFilename()).toBe('BOM-F1-A01.xlsx')
  expect(exportHits).toEqual([3])
  // 弹窗更大：宽度明显超过卡片
  const dlgBox = await dlg.boundingBox()
  expect(dlgBox.width).toBeGreaterThan(1200)

  // 筛选：命中「方管」→ 保留上级 P1（序号仍是原层级编号），命中行高亮
  await dlg.locator('.bom-dlg-search input').fill('方管')
  await expect(dlg.locator('.bt-seq')).toHaveText(['1', '1.1'])
  await expect(dlg.locator('.bom-dlg-hit')).toContainText('匹配 1 项')
  await expect(dlg.locator('tr.bt-hit-row')).toHaveCount(1)
  await dlg.screenshot({ path: 'test-results/material-card-bom-dialog.png' })

  // 弹窗里点子件编码：关弹窗，卡片内跳到该物料，出现返回按钮
  await dlg.locator('.bt-erp', { hasText: 'R1-A01' }).click()
  await expect(dlg).toBeHidden()
  await expect(page.locator('.el-dialog__header .mc-back-btn')).toBeVisible()
  // 返回：回到原物料，并重新打开刚才的 BOM 弹窗（保留筛选词）
  await page.locator('.el-dialog__header .mc-back-btn').click()
  await expect(page.locator('.el-dialog__header .mc-erp-code')).toHaveText('F1-A')
  await expect(dlg).toBeVisible()
  await expect(dlg.locator('.bom-dlg-code')).toHaveText('F1-A01')
  await expect(dlg.locator('.bom-dlg-search input')).toHaveValue('方管')
  await expect(page.locator('.el-dialog__header .mc-back-btn')).toHaveCount(0)
  await dlg.locator('.el-dialog__headerbtn').click()
  await expect(dlg).toBeHidden()

  // 打开原材料 R1：没有下级 BOM，被使用分区显示最终产品和直接上级
  await page.locator('.el-dialog__header .mc-close-btn').click()
  await page.locator('.code-link', { hasText: 'R1-A01' }).click()
  await expect(page.locator('.el-dialog__header .mc-erp-code')).toHaveText('R1-A01')
  // 没有下级 BOM：整个分区隐藏
  await expect(bomSec).toHaveCount(0)
  await expect(usedSec.locator('.mc-section-title')).toContainText('1 个最终产品')
  await expect(usedSec.locator('.used-chip')).toContainText('F1-A02')
  await expect(usedSec.locator('.cost-table tbody tr')).toHaveCount(1)
  await usedSec.scrollIntoViewIfNeeded()
  await page.locator('.el-dialog.material-card-dialog').screenshot({ path: 'test-results/material-card-bom-used.png' })

  // 点最终产品跳到 F1-A，再返回 R1-A01
  await usedSec.locator('.used-chip').click()
  await expect(page.locator('.el-dialog__header .mc-erp-code')).toHaveText('F1-A')
  await page.locator('.el-dialog__header .mc-back-btn').click()
  await expect(page.locator('.el-dialog__header .mc-erp-code')).toHaveText('R1-A01')
})

test('物料BOM：导入校验失败逐条列出；删除被引用的 BOM 需二次确认', async ({ page }) => {
  await setup(page)
  const list = [bomHead(2, 'M1', 'A01', { category: '半成品' })]
  await page.route('**/api/material/boms?*', r => r.fulfill({
    json: OK({ items: list.map(b => ({ ...b, line_count: 1, material_types: ['semi'] })), total: 1,
               all_total: 1, page: 1, page_size: 50, type_counts: { semi: 1 } }) }))
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

// 计价：有物料价格权限时，BOM 树显示单价/金额，按计价日期现算；卡片价格区显示按 BOM 计算的价格与历史
const PRICED_TREE = [
  { id: '1', code: 'P1', version: 'A01', drawing: 'P1-A01', erp_code: 'P1-A', name: '桌面', qty: 1, unit: 'PCS',
    unit_price: 24, amount: 24, price_source: 'calc', price_date: null, missing: 0,
    children: [
      { id: '1/2', code: 'R1', version: 'A01', drawing: 'R1-A01', erp_code: 'R1-A01', name: '方管', qty: 6, unit: 'PCS',
        unit_price: 4, amount: 24, price_source: 'material', price_date: '2024-06-01', missing: 0 },
    ] },
  { id: '3', code: 'S1', version: 'A01', drawing: 'S1-A01', erp_code: null, name: '螺钉', qty: 4, unit: 'PCS',
    unit_price: null, amount: null, price_source: null, price_date: null, missing: 1 },
]

test('BOM 计价：单价/金额列、合计、计价日期；卡片显示按 BOM 计算的价格', async ({ page }) => {
  await setup(page)
  const head = { ...bomHead(1, 'F1', 'A02'), material_types: ['finished'] }
  await page.route('**/api/material/boms?*', r => r.fulfill({ json: OK({
    items: [{ ...head, line_count: 2 }], total: 1, all_total: 1, page: 1, page_size: 50,
    type_counts: { finished: 1 } }) }))
  const treeDates = []
  await page.route('**/api/material/boms/*/tree*', r => {
    const d = new URL(r.request().url()).searchParams.get('price_date')
    treeDates.push(d)
    return r.fulfill({ json: OK({
      bom: { ...head, unit_price: d ? 20 : 24, missing: 1, price_source: 'calc', priced_as_of: d },
      children: PRICED_TREE }) })
  })
  await page.route('**/api/material/items/*', r => r.fulfill({ json: OK(item('F1-A')) }))
  await page.route('**/api/material/items/*/bom', r => r.fulfill({ json: OK({
    versions: [{ ...head, line_count: 2 }], direct_parents: [], top_products: [] }) }))
  await page.route('**/api/material/price-batches', r => r.fulfill({ json: OK([
    { id: 5, order_no: '2M2-SC20250522-025', price_date: '2025-05-22', price_count: 133 },
    { id: 4, order_no: '2M2-SC20240301-001', price_date: '2024-03-01', price_count: 40 },
  ]) }))
  await page.route('**/api/material/items/*/calc-price', r => r.fulfill({ json: OK({
    bom: head, versions: [{ id: 1, drawing: 'F1-A02' }],
    current: { unit_price: 24, missing: 1, price_source: 'calc', price_date: null },
    history: [{ date: '2024-06-01', unit_price: 24, missing: 1 }, { date: '2024-01-01', unit_price: 18, missing: 1 }],
  }) }))
  await page.route('**/api/material/items/*/prices', r => r.fulfill({ json: OK([
    { id: 2, unit_price: 26, price_date: '2025-05-22', order_no: '2M2-SC20250522-025', source: 'bom_import', supplier_name: null },
    { id: 1, unit_price: 22, price_date: '2024-06-20', order_no: '2M2-SC20240620-050', source: 'bom_import', supplier_name: null },
    { id: 3, unit_price: 25, price_date: null, order_no: '', source: 'manual', supplier_name: null },
  ]) }))
  let usagesCalled = false
  await page.route('**/api/material/items/*/usages', r => { usagesCalled = true; return r.fulfill({ json: OK([]) }) })

  await page.goto('/#/material')
  await page.locator('.nav-item', { hasText: '物料BOM' }).click()
  await expect(page.locator('.bom-tree th')).toHaveText(['序号', '图纸编码', 'ERP编码', '名称', '数量', '单位', '单价', '金额'])
  // 部件价格由下级计算（蓝色）；缺价显示 —，部件带「缺N」
  await expect(page.locator('.bom-tree .bt-price').first()).toHaveText('¥24')
  await expect(page.locator('.bom-tree .bt-price.src-calc')).toHaveCount(1)
  await expect(page.locator('.bom-tree .bt-price.src-none')).toHaveText('—')
  await expect(page.locator('.bd-total')).toContainText('¥24')
  await expect(page.locator('.bd-total .bd-miss')).toHaveText('缺 1 项价格')
  await page.screenshot({ path: 'test-results/material-bom-priced.png' })
  // 所有列都在可视范围内（不被挤进横向滚动区）
  const fits = await page.locator('.bom-tree').evaluate(t => {
    const wrap = t.querySelector('.el-table__body-wrapper .el-scrollbar__wrap') || t
    return wrap.scrollWidth <= wrap.clientWidth + 1
  })
  expect(fits).toBe(true)

  // 计价依据：单独一行；不手动选日期，按 年 → 月 → 订单 树状选择
  const priceRow = page.locator('.bd-price-row')
  await expect(priceRow).toContainText('合计')
  const headBox = await page.locator('.bd-head').boundingBox()
  const rowBox = await priceRow.boundingBox()
  expect(rowBox.y).toBeGreaterThanOrEqual(headBox.y + headBox.height - 1)
  await priceRow.locator('.pb-select').click()
  const popper = page.locator('.price-batch-popper:visible')
  // 默认展开最近一年、最近一月：能看到 最新价格 / 2025年 / 5月 / 该月订单 / 2024年
  await expect(popper.locator('.pb-latest')).toHaveText('最新价格')
  await expect(popper.locator('.pb-group:visible')).toHaveText(['2025年', '5月', '2024年'])
  await expect(popper.locator('.pb-order:visible')).toHaveText(['2M2-SC20250522-025'])
  await page.waitForTimeout(400)
  await page.screenshot({ path: 'test-results/material-bom-price-tree.png' })
  // 展开 2024年 → 3月，选订单
  await popper.locator('.pb-group', { hasText: '2024年' }).click()
  await popper.locator('.pb-group', { hasText: '3月' }).click()
  await popper.locator('.pb-order', { hasText: '2M2-SC20240301-001' }).click()
  await expect.poll(() => treeDates.at(-1)).toBe('2024-03-01')
  await expect(page.locator('.bd-total')).toContainText('¥20')
  await expect(priceRow.locator('.pb-select')).toContainText('2M2-SC20240301-001 · 2024-03-01')
  await page.screenshot({ path: 'test-results/material-bom-priced-batch.png' })

  // 物料卡片：价格区显示按 BOM 计算的价格与价格变化历史
  await page.locator('.bd-drawing').click()
  const card = page.locator('.material-card')
  await expect(card.locator('.calc-box .calc-val')).toHaveText('¥24')
  await expect(card.locator('.calc-box .calc-miss')).toHaveText('缺 1 项价格')
  await card.locator('.calc-toggle').click()
  await expect(card.locator('.calc-history tbody tr')).toHaveCount(2)
  await card.locator('.calc-box').scrollIntoViewIfNeeded()
  await page.locator('.el-dialog.material-card-dialog').screenshot({ path: 'test-results/material-card-calc-price.png' })

  // 价格记录：没有「使用记录」，每条带导入时的订单号（手动价格显示 —）
  await expect(card.locator('.cost-count')).toHaveText('价格记录（3）')
  await expect(card.getByText('使用记录')).toHaveCount(0)
  expect(usagesCalled).toBe(false)
  const priceTable = card.locator('.cost-table').last()
  await expect(priceTable.locator('th')).toContainText(['日期', '单价', '订单号'])
  await expect(priceTable.locator('tbody tr').first().locator('.order-tag')).toHaveText('2M2-SC20250522-025')
  await expect(priceTable.locator('.order-tag')).toHaveCount(2)
  await expect(priceTable.locator('tbody tr').nth(2)).toContainText('—')

  // 价格趋势：弹窗画出价格记录与按 BOM 计算两条线
  await priceTable.scrollIntoViewIfNeeded()
  await priceTable.screenshot({ path: 'test-results/material-price-records.png' })
  await card.locator('.cost-trend').click()
  const trend = page.locator('.el-dialog.price-trend-dialog')
  await expect(trend).toBeVisible()
  await expect(trend.locator('.pt-chart canvas')).toHaveCount(1)
  await page.waitForTimeout(600)
  await trend.screenshot({ path: 'test-results/material-price-trend.png' })
})
