import { expect } from '@playwright/test'

/**
 * 响应式回归的公共断言集合。
 *
 * 只测"根节点没有横向溢出"会有假阴性：页面如果用 overflow:hidden 把超出视口
 * 的内容直接裁掉，这条检查照样通过，但用户其实看不到内容。这里额外校验
 * 关键元素是否真的可见、可达（必要时允许纵向滚动到达，不允许被裁掉/挤没）。
 */
export async function assertResponsiveLayoutHealthy(page, { keySelectors = [] } = {}) {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(
    scrollWidth,
    `根节点出现横向溢出：scrollWidth=${scrollWidth} > clientWidth=${clientWidth}`
  ).toBeLessThanOrEqual(clientWidth)

  for (const selector of keySelectors) {
    const locator = page.locator(selector)
    await expect(locator, `关键元素 ${selector} 应当存在且可见`).toBeVisible()

    const box = await locator.boundingBox()
    expect(box, `关键元素 ${selector} 拿不到有效的布局盒模型（可能被压缩为0尺寸）`).not.toBeNull()
    expect(box.width, `关键元素 ${selector} 宽度被压缩为 0`).toBeGreaterThan(0)
    expect(box.height, `关键元素 ${selector} 高度被压缩为 0`).toBeGreaterThan(0)

    // 允许通过纵向滚动到达（workspace/page-scroll 契约下都合理），
    // 但不允许横向滚动、不允许被遮挡/裁切到不可达
    await locator.scrollIntoViewIfNeeded()
    await expect(locator, `关键元素 ${selector} 滚动后仍不在可视区域内，可能被裁切`).toBeInViewport()

    // toBeInViewport() 只比较元素自身的 bounding rect 和浏览器视口，不会发现"元素被祖先的
    // overflow:hidden 裁掉、但自身仍有几何坐标"这类假阳性——flex/grid 布局下子元素超出容器
    // 时依然会算出一个 boundingBox，即使视觉上完全不可见。用 elementFromPoint 在元素中心点
    // 做一次真实命中测试，命中不到自己（或自己的后代）就说明被裁切/遮挡。
    const isActuallyPainted = await locator.evaluate((el) => {
      const rect = el.getBoundingClientRect()
      const cx = rect.left + rect.width / 2
      const cy = rect.top + rect.height / 2
      const hit = document.elementFromPoint(cx, cy)
      return !!hit && el.contains(hit)
    })
    expect(
      isActuallyPainted,
      `关键元素 ${selector} 中心点命中测试失败：几何坐标存在但实际不可见，很可能被祖先的 overflow:hidden 裁切或被其他元素遮挡`
    ).toBe(true)
  }
}

/** 收集页面加载期间的控制台 error 级别日志（Vue/ECharts 布局异常等），配合 assertNoConsoleErrors 使用 */
export function collectConsoleErrors(page) {
  const errors = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })
  page.on('pageerror', (err) => errors.push(err.message))
  return errors
}

export function assertNoConsoleErrors(errors) {
  expect(errors, `页面加载期间出现控制台错误：\n${errors.join('\n')}`).toEqual([])
}
