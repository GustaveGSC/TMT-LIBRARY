import { test, expect } from '@playwright/test'
import { VIEWPORTS } from './viewports.js'

// 第0批基线测试：只覆盖登录页（公开，不需要账号）。
// 其余需要登录态的页面（仪表盘/管理页等）留到对应改造批次时再补，
// 因为跑通登录流程需要一个真实可用的测试账号，目前仓库里没有，
// 不能在 CI/自动化里硬编码真实密码。等有专用测试账号后在这里扩展。
test.describe('登录页 · 无横向滚动回归', () => {
  for (const viewport of VIEWPORTS) {
    test(`${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto('/#/login')
      await page.waitForLoadState('networkidle')

      const { scrollWidth, clientWidth } = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }))

      expect(
        scrollWidth,
        `视口 ${viewport.width}x${viewport.height} 下出现横向溢出：scrollWidth=${scrollWidth} > clientWidth=${clientWidth}`
      ).toBeLessThanOrEqual(clientWidth)
    })
  }
})
