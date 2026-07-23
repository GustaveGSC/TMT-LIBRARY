import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { test, expect } from '@playwright/test'
import { BREAKPOINTS } from '../../src/utils/responsiveBreakpoints.js'

// 防止 JS 断点数据源（responsiveBreakpoints.js）和 CSS 里手写的断点数值漂移。
// CSS 文件里必须保留固定格式的 `BREAKPOINT-<TIER>: <px>` 注释行，见 responsive.css 头部说明。
// 用 process.cwd() 而非 import.meta.url 定位路径：Playwright 对 spec 文件按 CJS 转译，
// 部分环境下 import.meta 在转译后的模块里不可用。
const CSS_PATH = join(process.cwd(), 'src/styles/responsive.css')

test('CSS 断点注释与 responsiveBreakpoints.js 数值一致', () => {
  const css = readFileSync(CSS_PATH, 'utf-8')

  const tiersToCheck = ['wide', 'standard', 'compact', 'tablet']
  for (const tier of tiersToCheck) {
    const pattern = new RegExp(`BREAKPOINT-${tier.toUpperCase()}:\\s*(\\d+)`)
    const match = css.match(pattern)
    expect(
      match,
      `responsive.css 里没找到 "BREAKPOINT-${tier.toUpperCase()}: <px>" 这行注释，一致性校验依赖固定格式`
    ).not.toBeNull()

    const cssValue = Number(match[1])
    expect(
      cssValue,
      `断点 "${tier}" 数值不一致：JS(responsiveBreakpoints.js)=${BREAKPOINTS[tier]}px，CSS(responsive.css)=${cssValue}px`
    ).toBe(BREAKPOINTS[tier])
  }
})
