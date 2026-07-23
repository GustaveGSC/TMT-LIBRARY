import { test } from '@playwright/test'
import { VIEWPORTS } from './viewports.js'
import { BREAKPOINTS } from '../../src/utils/responsiveBreakpoints.js'
import { mockShippingDashboard } from './fixtures/shippingDashboard.js'
import { assertResponsiveLayoutHealthy, collectConsoleErrors, assertNoConsoleErrors } from './layoutAssertions.js'

// 第1批试点：ShippingDashboard 响应式布局回归。
// 用 page.route() 拦截接口 + 注入前端路由守卫需要的最小登录态，不依赖真实测试账号——
// 前端路由权限判断只看 localStorage.user 的 roles/permissions，真实后端鉴权由后端测试覆盖。
// 见 handoff/2026-07-23-codex-responsive-baseline-review.md。

const KEY_SELECTORS = [
  '[data-testid="shipping-chart"]',
]

// 三档最容易暴露"低高度 + 缩放后等效窄视口"问题，额外覆盖地图+Top10榜单场景
const MAP_VIEW_VIEWPORTS = VIEWPORTS.filter(v =>
  ['1093x614-1366x768-at-125pct', '911x512-1366x768-at-150pct', '844x390-mobile-landscape', '1920x1080-standard-desktop'].includes(v.name)
)

async function gotoShippingDashboard(page) {
  await mockShippingDashboard(page)
  await page.goto('/#/shipping')
  await page.waitForLoadState('networkidle')
}

/** 筛选入口在紧凑布局下是抽屉触发按钮，宽屏/标准桌面下是常驻侧栏本身 */
async function filterEntrySelector(width) {
  return width < BREAKPOINTS.standard
    ? '[data-testid="shipping-filter-toggle"]'
    : '[data-testid="shipping-filter-panel"]'
}

/** 切换到"地域 groupBy + 地图图表类型"，触发 Top10 榜单面板；紧凑布局下维度选择在
 *  toolbar 里的 el-select，宽屏/标准桌面下是底部维度按钮，两条路径分开处理。
 *  必须先切 groupBy 再点地图类型——地图图表类型只在地域维度下可用，顺序颠倒按钮会是禁用态 */
async function switchToMapByRegion(page, width) {
  const waitForChartData = () =>
    page.waitForResponse((res) => res.url().includes('/api/shipping/chart-data'))

  if (width < BREAKPOINTS.standard) {
    await page.locator('.mobile-dim-select').click()
    await Promise.all([
      waitForChartData(),
      page.getByRole('option', { name: '地域', exact: true }).click(),
    ])
  } else {
    await Promise.all([
      waitForChartData(),
      page.locator('.gb-btn', { hasText: '地域' }).click(),
    ])
  }
  await page.locator('.ct-btn[title="地图"]').click()
  await page.waitForTimeout(200) // ECharts resize/渲染
}

test.describe('ShippingDashboard · 默认视图（柱状图/产品维度）响应式回归', () => {
  for (const viewport of VIEWPORTS) {
    test(`${viewport.name}`, async ({ page }) => {
      const consoleErrors = collectConsoleErrors(page)
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await gotoShippingDashboard(page)

      const keySelectors = [...KEY_SELECTORS, await filterEntrySelector(viewport.width)]
      await assertResponsiveLayoutHealthy(page, { keySelectors })
      assertNoConsoleErrors(consoleErrors)
    })
  }
})

test.describe('ShippingDashboard · 地图+Top10榜单视图响应式回归（低高度重点档位）', () => {
  for (const viewport of MAP_VIEW_VIEWPORTS) {
    test(`${viewport.name}`, async ({ page }) => {
      const consoleErrors = collectConsoleErrors(page)
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await gotoShippingDashboard(page)
      await switchToMapByRegion(page, viewport.width)

      const keySelectors = [
        ...KEY_SELECTORS,
        await filterEntrySelector(viewport.width),
        '[data-testid="shipping-rank-panel"]',
      ]
      await assertResponsiveLayoutHealthy(page, { keySelectors })
      assertNoConsoleErrors(consoleErrors)
    })
  }
})
