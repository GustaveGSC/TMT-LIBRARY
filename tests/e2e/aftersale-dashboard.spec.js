import { test, expect } from '@playwright/test'
import { VIEWPORTS } from './viewports.js'
import { BREAKPOINTS } from '../../src/utils/responsiveBreakpoints.js'
import { mockAftersaleDashboard } from './fixtures/aftersaleDashboard.js'
import {
  assertResponsiveLayoutHealthy,
  assertContainerScrollsWhenOverflowing,
  collectConsoleErrors,
  assertNoConsoleErrors,
} from './layoutAssertions.js'

// 第2批：AftersaleDashboard 响应式布局回归，复用 ShippingDashboard 试点验证过的布局
// 原则（唯一滚动容器、grid minmax 保底、elementFromPoint 命中测试、真实滚动能力断言、
// 抽屉完整交互），但不复制 Shipping 的具体 CSS/选择器——售后页面结构不同（无 Top10/地图，
// 有 chart-bottom-bar 第三行），独立建的 API fixture。
// 见 handoff/2026-07-24-codex-shipping-responsive-rereview.md。

const KEY_SELECTORS = [
  '[data-testid="aftersale-chart"]',
]

const CRITICAL_VIEWPORTS = VIEWPORTS.filter(v =>
  ['1093x614-1366x768-at-125pct', '911x512-1366x768-at-150pct', '844x390-mobile-landscape', '1920x1080-standard-desktop'].includes(v.name)
)

async function gotoAftersaleDashboard(page) {
  await mockAftersaleDashboard(page)
  await page.goto('/#/aftersale')
  // page-aftersale.vue 默认激活"概览"Tab，AftersaleDashboard 挂在"图表"Tab 下，懒加载
  // （v-if="mountedTabs.chart"），需要先点击切到图表 Tab 才会挂载
  await page.getByRole('button', { name: '图表', exact: true }).click()
  await page.waitForLoadState('networkidle')
}

/** 筛选入口在紧凑布局下是抽屉触发按钮，宽屏/标准桌面下是常驻侧栏本身 */
async function filterEntrySelector(width) {
  return width < BREAKPOINTS.standard
    ? '[data-testid="aftersale-filter-toggle"]'
    : '[data-testid="aftersale-filter-panel"]'
}

test.describe('AftersaleDashboard · 默认视图（产品维度）响应式回归', () => {
  for (const viewport of VIEWPORTS) {
    test(`${viewport.name}`, async ({ page }) => {
      const consoleErrors = collectConsoleErrors(page)
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await gotoAftersaleDashboard(page)

      const keySelectors = [...KEY_SELECTORS, await filterEntrySelector(viewport.width)]
      await assertResponsiveLayoutHealthy(page, { keySelectors })
      assertNoConsoleErrors(consoleErrors)
    })
  }
})

// 售后没有 Top10/地图这类附加面板，"复杂视图"对应的是切换到子维度（原因/发货物料/渠道/地域）
test.describe('AftersaleDashboard · 子维度视图响应式回归（重点档位）', () => {
  for (const viewport of CRITICAL_VIEWPORTS) {
    test(`${viewport.name}`, async ({ page }) => {
      const consoleErrors = collectConsoleErrors(page)
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await gotoAftersaleDashboard(page)

      const waitForChartData = () => page.waitForResponse((res) => res.url().includes('/api/aftersale/chart-data'))
      await Promise.all([
        waitForChartData(),
        page.locator('.gb-btn', { hasText: '原因' }).first().click(),
      ])
      await page.waitForTimeout(200)

      const keySelectors = [...KEY_SELECTORS, await filterEntrySelector(viewport.width)]
      await assertResponsiveLayoutHealthy(page, { keySelectors })
      assertNoConsoleErrors(consoleErrors)
    })
  }
})

test.describe('AftersaleDashboard · content-panel 滚动兜底在极端矮视口下真实生效', () => {
  test('844x260（工具栏 + 图表最小高度 + 底部控制栏之和明显超过视口高度）', async ({ page }) => {
    await page.setViewportSize({ width: 844, height: 260 })
    await gotoAftersaleDashboard(page)
    await assertContainerScrollsWhenOverflowing(page, '.content-panel')
  })
})

test.describe('AftersaleDashboard · 筛选抽屉完整交互（打开—可达—关闭）', () => {
  const DRAWER_VIEWPORTS = [
    { name: '1093x614-compact-desktop', width: 1093, height: 614 },
    { name: '390x844-mobile-portrait', width: 390, height: 844 },
  ]

  for (const viewport of DRAWER_VIEWPORTS) {
    test(viewport.name, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await gotoAftersaleDashboard(page)

      const panel = page.locator('[data-testid="aftersale-filter-panel"]')

      // 关闭状态：面板在视口外
      const closedBox = await panel.boundingBox()
      expect(closedBox.x, '筛选抽屉初始应处于关闭状态').toBeLessThan(0)

      // 打开（等 0.28s 过渡动画结束再读取几何位置）
      await page.locator('[data-testid="aftersale-filter-toggle"]').click()
      await expect(panel, '点击筛选按钮后抽屉应可见').toBeVisible()
      await expect(panel).toHaveClass(/is-open/)
      await page.waitForTimeout(350)
      const openBox = await panel.boundingBox()
      expect(openBox.x, '抽屉打开后面板应进入视口范围内').toBeGreaterThanOrEqual(0)

      // 操作区可达：查询按钮
      const queryBtn = page.locator('.btn-query')
      await expect(queryBtn, '抽屉打开后「查询」按钮应可见可达').toBeVisible()
      const queryHit = await queryBtn.evaluate((el) => {
        const rect = el.getBoundingClientRect()
        const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
        return !!hit && el.contains(hit)
      })
      expect(queryHit, '「查询」按钮中心点命中测试失败').toBe(true)

      // 关闭
      await page.locator('.filter-close-btn').click()
      await expect(panel).not.toHaveClass(/is-open/)
      await page.waitForTimeout(350)
      const closedAgainBox = await panel.boundingBox()
      expect(closedAgainBox.x, '点击关闭按钮后面板应回到视口外').toBeLessThan(0)
    })
  }
})

// 2026-07-24 复核发现：紧凑档打开抽屉后跨断点变宽再缩回，抽屉会带着残留的
// "打开"状态自动重新出现。真实的"打开→跨 1200px 变宽→缩回紧凑档"三段式验证。
test.describe('AftersaleDashboard · 跨断点动态回归（紧凑↔宽屏切换不残留抽屉状态）', () => {
  test('紧凑档打开抽屉 → 拖宽过 1200px → 缩回紧凑档，抽屉不应自动重新出现', async ({ page }) => {
    await page.setViewportSize({ width: 1093, height: 700 })
    await gotoAftersaleDashboard(page)

    const panel = page.locator('[data-testid="aftersale-filter-panel"]')
    await page.locator('[data-testid="aftersale-filter-toggle"]').click()
    await expect(panel).toHaveClass(/is-open/)
    await page.waitForTimeout(350)

    await page.setViewportSize({ width: 1400, height: 700 })
    await page.waitForTimeout(100)

    await page.setViewportSize({ width: 1093, height: 700 })
    await page.waitForTimeout(350)

    await expect(panel, '重新进入紧凑档后抽屉不应带着上次的打开状态自动出现').not.toHaveClass(/is-open/)
    const box = await panel.boundingBox()
    expect(box.x, '抽屉应处于关闭状态（视口外）').toBeLessThan(0)
  })
})
