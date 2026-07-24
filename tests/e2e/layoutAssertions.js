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

/**
 * 验证某个"允许滚动兜底"的容器在真实内容超高时确实可以滚动，而不是源码写了
 * overflow:auto/scroll 但被同一 @media 块内后声明的 overflow:hidden 覆盖掉
 * （2026-07-24 ShippingDashboard 试点复核就发现过这类问题：源码看起来有兜底，
 * 最终计算样式却被覆盖，测试当时没测出来）。
 *
 * 用法：在一个明确会造成该容器内容超出可视高度的视口/场景下调用，
 * 断言最终计算 overflow、真实 scrollHeight>clientHeight、且滚动操作确实生效。
 */
export async function assertContainerScrollsWhenOverflowing(page, selector) {
  const locator = page.locator(selector)
  await expect(locator, `滚动容器 ${selector} 应当存在`).toBeVisible()

  const info = await locator.evaluate((el) => ({
    overflowY: getComputedStyle(el).overflowY,
    scrollHeight: el.scrollHeight,
    clientHeight: el.clientHeight,
  }))

  expect(
    ['auto', 'scroll'],
    `滚动容器 ${selector} 最终计算 overflow-y 是 "${info.overflowY}"，不是 auto/scroll——` +
      `可能被同一 @media 块内后面的声明覆盖了`
  ).toContain(info.overflowY)

  expect(
    info.scrollHeight,
    `滚动容器 ${selector} scrollHeight(${info.scrollHeight}) 不大于 clientHeight(${info.clientHeight})，` +
      `当前测试场景没有真正制造出内容超高，断言本身没有覆盖到"允许滚动"这条路径`
  ).toBeGreaterThan(info.clientHeight)

  // 真实滚动操作：设置一个超大 scrollTop，确认浏览器真的接受并处理了滚动，
  // 不是"overflow 属性写对了但因为某些其他原因（如内容被 position:fixed 覆盖）实际滚不动"
  const scrolledTo = await locator.evaluate((el) => {
    el.scrollTop = el.scrollHeight
    return el.scrollTop
  })
  expect(
    scrolledTo,
    `滚动容器 ${selector} 设置 scrollTop 后仍为 0，容器实际无法滚动`
  ).toBeGreaterThan(0)
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
