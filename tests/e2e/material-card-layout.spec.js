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
  await expect(page.locator('.el-dialog__header .mc-erp-code')).toBeVisible()
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

test('物料卡片：编码/名称/状态作为标题栏，图片|人工维护，价格通栏，字段对齐', async ({ page }) => {
  const card = await openCard(page, { ...ITEM, name: '成品_桌类_德罗 (V1.1)手摇1.8米榉木白色_A' })
  await page.waitForTimeout(500)   // 等 el-dialog 打开动画结束再量坐标

  const erp = page.locator('.el-dialog__header .mc-erp-line')
  const erpBox = await erp.boundingBox()
  const img = await card.locator('.mc-top-image').boundingBox()
  const manual = await card.locator('.mc-manual').boundingBox()
  const price = await card.locator('.mc-scroll > .mc-section').last().boundingBox()

  // 这一行就是弹窗标题：原生标题和原生右上角关闭都不渲染；下方有分割线
  await expect(page.locator('.el-dialog .el-dialog__title')).toHaveCount(0)
  await expect(page.locator('.el-dialog .el-dialog__headerbtn')).toHaveCount(0)
  expect(erpBox.y + erpBox.height).toBeLessThanOrEqual(img.y + 1)
  const lineStyle = await erp.evaluate(el => {
    const cs = getComputedStyle(el)
    return { bottom: cs.borderBottomWidth, style: cs.borderBottomStyle, bg: cs.backgroundColor }
  })
  expect(lineStyle.bottom).not.toBe('0px')
  expect(lineStyle.style).toBe('solid')
  expect(lineStyle.bg).toBe('rgba(0, 0, 0, 0)')
  // 只显示编码、名称、启用状态角标：无字段标签、不显示分组和 ERP 原始状态文字
  await expect(erp).not.toContainText('编码')
  await expect(erp).not.toContainText('名称')
  await expect(erp).not.toContainText('分组')
  await expect(erp).not.toContainText(ITEM.status)
  await expect(erp.locator('.ro-badge')).toHaveText('启用')
  // 编码 17px 黑色加粗、无标签样式；名称 15px 不加粗
  const code = await erp.locator('.mc-erp-code').evaluate(el => {
    const cs = getComputedStyle(el)
    return { w: Number(cs.fontWeight), size: parseFloat(cs.fontSize), border: cs.borderTopWidth, bg: cs.backgroundColor, color: cs.color }
  })
  expect(code.w).toBeGreaterThanOrEqual(600)
  expect(code.size).toBe(17)
  expect(code.color).toBe('rgb(0, 0, 0)')
  expect(code.border).toBe('0px')
  expect(code.bg).toBe('rgba(0, 0, 0, 0)')
  const name = await erp.locator('.mc-erp-name').evaluate(el => {
    const cs = getComputedStyle(el)
    return { w: Number(cs.fontWeight), size: parseFloat(cs.fontSize) }
  })
  expect(name.w).toBeLessThan(600)
  expect(name.size).toBe(15)
  // 状态紧挨名称；原状态位置（最右侧）是「关闭」按键
  const nameBox = await erp.locator('.mc-erp-name').boundingBox()
  const badgeBox = await erp.locator('.ro-badge').boundingBox()
  const closeBox = await erp.locator('.mc-close-btn').boundingBox()
  expect(badgeBox.x - (nameBox.x + nameBox.width)).toBeLessThan(16)
  expect(closeBox.x).toBeGreaterThan(badgeBox.x + badgeBox.width)
  expect(Math.abs((closeBox.x + closeBox.width) - (erpBox.x + erpBox.width))).toBeLessThan(1)
  await expect(erp.locator('.mc-close-btn')).toHaveText('关闭')

  // 图片在左、人工维护在右，等高；价格在下方通栏
  expect(img.x).toBeLessThan(manual.x)
  expect(Math.abs(img.y - manual.y)).toBeLessThan(1)
  expect(Math.abs(img.height - manual.height)).toBeLessThan(1)
  const rowWidth = manual.x + manual.width - img.x
  expect(price.y).toBeGreaterThan(img.y + img.height - 1)
  expect(Math.abs(price.width - rowWidth)).toBeLessThan(1)

  // 人工维护里所有控件左边缘在同一条竖线上，标签同宽
  const controlLefts = await card.locator(
    '.mc-manual .mt-box, .mc-manual .mc-input, .mc-manual .mc-textarea',
  ).evaluateAll(els => els.map(e => Math.round(e.getBoundingClientRect().left)))
  expect(new Set(controlLefts).size).toBe(1)
  const labelWidths = await card.locator('.mc-manual .mc-field > label')
    .evaluateAll(els => els.map(e => Math.round(e.getBoundingClientRect().width)))
  expect(new Set(labelWidths).size).toBe(1)

  await page.locator('.el-dialog').screenshot({ path: 'test-results/material-card-layout.png' })
  await erp.locator('.mc-close-btn').click()
  await expect(page.locator('.material-card')).toBeHidden()
})

// 名称很长时单行省略，不能把卡片撑高
test('ERP 名称过长时单行省略、悬停可看全文', async ({ page }) => {
  const longName = '成品_桌类_德罗 (V1.1)手摇1.8米榉木白色_A_外贸专供_带储物抽屉与书架组合_加长加宽版本_二代'
  const card = await openCard(page, { ...ITEM, name: longName })
  await page.waitForTimeout(500)
  // 名称只占一行：元素高度不超过一行行高
  const nameBox = await page.locator('.el-dialog__header .mc-erp-name').evaluate(el => ({
    h: el.getBoundingClientRect().height, lh: parseFloat(getComputedStyle(el).lineHeight) || 0,
    size: parseFloat(getComputedStyle(el).fontSize),
  }))
  expect(nameBox.h).toBeLessThan((nameBox.lh || nameBox.size * 1.5) + 1)
  await expect(page.locator('.el-dialog__header .mc-erp-name')).toHaveAttribute('title', longName)
})

// 单独指定物料类型时提示最长，也不能把右侧区域撑高
test('单独指定物料类型时人工维护区仍与图片列等高', async ({ page }) => {
  const card = await openCard(page, {
    ...ITEM, categories: ['useless'], category_source: 'manual', type_override: ['useless'],
    rule_categories: ['finished', 'packaged'], rule_source: 'rule',
  })
  await page.waitForTimeout(500)
  const img = await card.locator('.mc-top-image').boundingBox()
  const manual = await card.locator('.mc-manual').boundingBox()
  expect(Math.abs(img.height - manual.height)).toBeLessThan(1)
  await expect(card.locator('.mt-hint')).toHaveAttribute('title', /若取消单独指定/)
  await page.locator('.el-dialog').screenshot({ path: 'test-results/material-card-manual.png' })
})
