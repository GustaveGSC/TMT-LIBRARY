/**
 * 响应式断点 · 唯一数据源
 *
 * CSS 端不能直接读取这里的数字（媒体查询不支持 CSS 自定义属性作为条件），
 * 所以 src/styles/responsive.css 里的 @media / @container 断点数值必须和这里手动保持一致。
 * 修改任意一档阈值时，两处都要改，并在 PR/commit 里注明。
 *
 * 分档依据"内容何时放不下"，不是具体设备型号，覆盖笔记本分辨率+系统缩放
 * （如 1366×768 在 125%/150% 缩放下约等效 1093px/911px CSS 视口）到手机的完整区间。
 * 详见 handoff/2026-07-23-codex-responsive-ui-redesign-proposal.md。
 */

// 每档的下边界（含），单位 px，按从大到小排列
export const BREAKPOINTS = {
  wide:     1440,
  standard: 1200,
  compact:  900,
  tablet:   600,
  mobile:   0,
}

// 与 BREAKPOINTS 对应的 min-width 媒体查询字符串，供 matchMedia 使用
export const MEDIA_QUERIES = {
  wide:     `(min-width: ${BREAKPOINTS.wide}px)`,
  standard: `(min-width: ${BREAKPOINTS.standard}px)`,
  compact:  `(min-width: ${BREAKPOINTS.compact}px)`,
  tablet:   `(min-width: ${BREAKPOINTS.tablet}px)`,
}

// 按视口宽度返回所在档位名
export function modeForWidth(width) {
  if (width >= BREAKPOINTS.wide) return 'wide'
  if (width >= BREAKPOINTS.standard) return 'standard'
  if (width >= BREAKPOINTS.compact) return 'compact'
  if (width >= BREAKPOINTS.tablet) return 'tablet'
  return 'mobile'
}
