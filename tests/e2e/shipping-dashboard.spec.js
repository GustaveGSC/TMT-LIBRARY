import { test, expect } from '@playwright/test'
import { VIEWPORTS } from './viewports.js'
import { BREAKPOINTS } from '../../src/utils/responsiveBreakpoints.js'
import { mockShippingDashboard } from './fixtures/shippingDashboard.js'
import {
  assertResponsiveLayoutHealthy,
  assertContainerScrollsWhenOverflowing,
  collectConsoleErrors,
  assertNoConsoleErrors,
} from './layoutAssertions.js'

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

// 2026-07-24 复核发现：源码里 .content-panel{overflow-y:auto} 被同一 @media 块内后面
// 声明的 overflow:hidden 覆盖，实际根本没生效，但当时的测试只验证元素可达/不裁切，
// 测不出"允许滚动的兜底是否真的生效"。这里在一个明确会撑爆可用高度的极端矮视口下，
// 直接断言最终计算样式 + 真实滚动能力，专门堵住这类"源码看似修了，最终样式被覆盖"的回归。
test.describe('ShippingDashboard · content-panel 滚动兜底在极端矮视口下真实生效', () => {
  test('844x260（工具栏 + 图表最小高度之和明显超过视口高度）', async ({ page }) => {
    await page.setViewportSize({ width: 844, height: 260 })
    await gotoShippingDashboard(page)
    await assertContainerScrollsWhenOverflowing(page, '.content-panel')
  })
})

// 2026-07-24 复核要求：只验证筛选按钮存在不够，必须覆盖"打开—操作区可达—关闭"完整交互，
// 才能证明扩大到 <1200px 后复用的既有抽屉机制没有交互回归。
test.describe('ShippingDashboard · 筛选抽屉完整交互（打开—可达—关闭）', () => {
  const DRAWER_VIEWPORTS = [
    { name: '1093x614-compact-desktop', width: 1093, height: 614 },
    { name: '390x844-mobile-portrait', width: 390, height: 844 },
  ]

  for (const viewport of DRAWER_VIEWPORTS) {
    test(viewport.name, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await gotoShippingDashboard(page)

      // 关闭状态：面板在视口外（transform: translateX(-100%)），中心点命中不到自己
      const closedBox = await page.locator('[data-testid="shipping-filter-panel"]').boundingBox()
      expect(closedBox.x, '筛选抽屉初始应处于关闭状态（面板应位于视口左侧之外）').toBeLessThan(0)

      // 打开（面板有 0.28s 的 transform 过渡动画，等动画结束再读取几何位置）
      await page.locator('[data-testid="shipping-filter-toggle"]').click()
      const panel = page.locator('[data-testid="shipping-filter-panel"]')
      await expect(panel, '点击筛选按钮后抽屉应可见').toBeVisible()
      await expect(panel).toHaveClass(/is-open/)
      await page.waitForTimeout(350)
      const openBox = await panel.boundingBox()
      expect(openBox.x, '抽屉打开后面板应进入视口范围内').toBeGreaterThanOrEqual(0)

      // 操作区可达：查询按钮是筛选面板里最核心的操作入口
      const queryBtn = page.locator('.btn-query')
      await expect(queryBtn, '抽屉打开后「查询」按钮应可见可达').toBeVisible()
      const queryHit = await queryBtn.evaluate((el) => {
        const rect = el.getBoundingClientRect()
        const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
        return !!hit && el.contains(hit)
      })
      expect(queryHit, '「查询」按钮中心点命中测试失败，可能被遮罩或其他元素挡住').toBe(true)

      // 关闭：点击面板内的关闭按钮
      await page.locator('.filter-close-btn').click()
      await expect(panel).not.toHaveClass(/is-open/)
      await page.waitForTimeout(350)
      const closedAgainBox = await panel.boundingBox()
      expect(closedAgainBox.x, '点击关闭按钮后面板应回到视口外').toBeLessThan(0)
    })
  }
})

// 2026-07-24 复核发现：紧凑档打开抽屉后，把窗口拖宽跨过 1200px 断点再缩回来，
// 抽屉会带着上次残留的"打开"状态自动重新出现——因为 filterPanelOpen 只在用户
// 主动点击时改变，离开紧凑档时没人清空它。这里做真实的"打开→跨断点变宽→
// 缩回紧凑档"三段式动态视口测试，验证不会自动弹出。
test.describe('ShippingDashboard · 跨断点动态回归（紧凑↔宽屏切换不残留抽屉状态）', () => {
  test('紧凑档打开抽屉 → 拖宽过 1200px → 缩回紧凑档，抽屉不应自动重新出现', async ({ page }) => {
    await page.setViewportSize({ width: 1093, height: 700 })
    await gotoShippingDashboard(page)

    const panel = page.locator('[data-testid="shipping-filter-panel"]')
    await page.locator('[data-testid="shipping-filter-toggle"]').click()
    await expect(panel).toHaveClass(/is-open/)
    await page.waitForTimeout(350)

    // 跨过 1200px 断点，变宽到标准桌面
    await page.setViewportSize({ width: 1400, height: 700 })
    await page.waitForTimeout(100) // matchMedia change 事件 + watch 回调

    // 缩回紧凑档
    await page.setViewportSize({ width: 1093, height: 700 })
    await page.waitForTimeout(350)

    await expect(panel, '重新进入紧凑档后抽屉不应带着上次的打开状态自动出现').not.toHaveClass(/is-open/)
    const box = await panel.boundingBox()
    expect(box.x, '抽屉应处于关闭状态（视口外）').toBeLessThan(0)
  })
})
