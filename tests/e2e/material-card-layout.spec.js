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
  images: [],
}
// 1x1 PNG，避免 mock 场景下图片加载失败撑不开
const PX = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII='

async function openCard(page, item) {
  await page.addInitScript((u) => {
    localStorage.setItem('user', JSON.stringify(u))
    localStorage.setItem('login_time', String(Date.now()))
  }, USER)
  await page.route(url => new URL(url).pathname.startsWith('/api/'), r =>
    r.request().resourceType() === 'script' ? r.continue() : r.fulfill({ json: OK([]) }))
  await page.route('**/api/account/me', r => r.fulfill({ json: OK(USER) }))
  await page.route('**/api/material/items?*', r => r.fulfill({ json: OK({ items: [item], total: 1, page: 1, page_size: 50 }) }))
  await page.route('**/api/material/items/14ST02001-A01', r => r.fulfill({ json: OK(item) }))
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/#/material')
  await page.locator('.code-link', { hasText: '14ST02001-A01' }).click()
  await expect(page.locator('.material-card .mc-erp')).toBeVisible()
  return page.locator('.material-card')
}

test('无图时图片区域直接显示圆形新增按键', async ({ page }) => {
  const card = await openCard(page, ITEM)
  const solo = card.locator('.mc-image-empty .mc-round-btn.solo')
  await expect(solo).toBeVisible()
  await card.locator('.mc-top').screenshot({ path: 'test-results/material-card-empty.png' })
  await expect(card.locator('.mc-img-mask')).toHaveCount(0)
})

test('多图：悬停出现 新增/编辑/删除/查看 圆形按键，缩略图可切换', async ({ page }) => {
  const card = await openCard(page, { ...ITEM, images: [
    { id: 1, url: PX, orig_url: null, sort_order: 0 },
    { id: 2, url: PX, orig_url: null, sort_order: 1 },
  ] })
  const mask = card.locator('.mc-img-mask')
  await expect(mask).toHaveCSS('opacity', '0')
  await card.locator('.mc-image').hover()
  await expect(mask).toHaveCSS('opacity', '1')
  await page.locator('.el-dialog').screenshot({ path: 'test-results/material-card-hover.png' })
  const titles = await mask.locator('.mc-round-btn').evaluateAll(els => els.map(e => e.title))
  expect(titles).toEqual(['新增图片', '编辑（替换当前图片）', '删除当前图片', '查看大图'])
  const box = await mask.locator('.mc-round-btn').first().boundingBox()
  expect(Math.abs(box.width - box.height)).toBeLessThan(1)   // 圆形按键
  await expect(card.locator('.mc-img-count')).toHaveText('1 / 2')
  await card.locator('.mc-thumb').nth(1).click()
  await expect(card.locator('.mc-img-count')).toHaveText('2 / 2')
  await card.locator('.mc-image').hover()
  await mask.locator('.mc-round-btn[title="查看大图"]').click()
  await expect(page.locator('.viewer-media')).toBeVisible()
  await page.locator('.material-card').page().keyboard.press('Escape')
})

// 大图/小图的尺寸差异不能影响图片框大小
const svg = (w, h) => 'data:image/svg+xml;utf8,' + encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"><rect width="${w}" height="${h}" fill="#c4883a"/></svg>`)

test('图片框尺寸固定，不随图片实际尺寸变化', async ({ page }) => {
  const card = await openCard(page, { ...ITEM, images: [
    { id: 1, url: svg(1600, 3000), orig_url: null, sort_order: 0 },
    { id: 2, url: svg(40, 20), orig_url: null, sort_order: 1 },
  ] })
  await page.waitForTimeout(500)
  const frame = card.locator('.mc-image')
  const big = await frame.boundingBox()
  await card.locator('.mc-thumb').nth(1).click()
  await page.waitForTimeout(100)
  const small = await frame.boundingBox()
  expect(Math.round(big.height)).toBe(220)
  expect(Math.abs(big.height - small.height)).toBeLessThan(1)
  expect(Math.abs(big.width - small.width)).toBeLessThan(1)
  // 图片不能溢出框
  const imgBox = await frame.locator('img').boundingBox()
  expect(imgBox.height).toBeLessThanOrEqual(small.height + 1)
})

// 0 / 1 / 多张图时，图片列与整张卡片的尺寸必须完全一致
for (const n of [0, 1, 12]) {
  test(`图片数量为 ${n} 时卡片尺寸不变`, async ({ page }) => {
    const images = Array.from({ length: n }, (_, i) => ({ id: i + 1, url: PX, orig_url: null, sort_order: i }))
    const card = await openCard(page, { ...ITEM, images })
    await page.waitForTimeout(500)
    const col = await card.locator('.mc-top-image').boundingBox()
    const top = await card.locator('.mc-top').boundingBox()
    const dialog = await page.locator('.el-dialog').boundingBox()
    expect(Math.round(col.height)).toBe(276)
    await card.locator('.mc-top').screenshot({ path: `test-results/material-card-top-${n}.png` })
    await expect(card.locator('.mc-thumb')).toHaveCount(n)
    // 记录到标题里便于对比三种情况；具体数值在下面三条断言里锁死
    test.info().annotations.push({ type: 'size', description: `${n}: top=${top.height} dialog=${dialog.width}x${dialog.height}` })
    expect(Math.round(top.height)).toBe(276)
    expect(Math.round(dialog.width)).toBe(900)
    if (n === 0) {
      const box = await card.locator('.mc-image').boundingBox()
      expect(Math.round(box.height)).toBe(276)
    } else {
      const strip = await card.locator('.mc-thumbs').boundingBox()
      expect(Math.round(strip.y + strip.height)).toBe(Math.round(col.y + col.height))
    }
  })
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
  await page.waitForTimeout(500)   // 等 el-dialog 打开动画结束再量坐标

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
