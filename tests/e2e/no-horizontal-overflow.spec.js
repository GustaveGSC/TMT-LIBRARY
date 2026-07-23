import { test } from '@playwright/test'
import { VIEWPORTS } from './viewports.js'
import { assertResponsiveLayoutHealthy, collectConsoleErrors, assertNoConsoleErrors } from './layoutAssertions.js'

// 第0批基线测试：只覆盖登录页（公开，不需要账号）。
// 其余需要登录态的页面（仪表盘/管理页等）留到对应改造批次时再补——
// 可以用 page.route() 拦截 API + 注入最小用户状态覆盖布局回归，不需要等真实测试账号，
// 生产账号只用于单独的联调冒烟测试（见 handoff/2026-07-23-codex-responsive-baseline-review.md）。
const KEY_SELECTORS = ['[data-testid="login-username"]', '[data-testid="login-submit"]']

test.describe('登录页 · 响应式布局回归', () => {
  for (const viewport of VIEWPORTS) {
    test(`${viewport.name}`, async ({ page }) => {
      const consoleErrors = collectConsoleErrors(page)

      // 布局测试不依赖真实后端；登录页会拉取轮播语句，测试环境没有后端时会 500，
      // 属于环境噪音，不是布局问题，用固定 fixture 屏蔽掉
      await page.route('**/api/config/login-mottos', (route) =>
        route.fulfill({ json: { success: true, message: '', data: [] } })
      )

      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto('/#/login')
      await page.waitForLoadState('networkidle')

      await assertResponsiveLayoutHealthy(page, { keySelectors: KEY_SELECTORS })
      assertNoConsoleErrors(consoleErrors)
    })
  }
})
