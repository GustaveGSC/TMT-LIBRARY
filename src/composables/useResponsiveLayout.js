import { computed, ref } from 'vue'
import { MEDIA_QUERIES } from '@/utils/responsiveBreakpoints'

/**
 * useResponsiveLayout — 统一的响应式档位判断
 *
 * 替代页面里各自散落的 `window.innerWidth <= 768` + 各写一份 resize 监听。
 * 实现为模块级单例：整个应用只注册一组 matchMedia 监听器（ES module 只会
 * 被求值一次），任意数量组件调用 useResponsiveLayout() 共享同一个响应式
 * 状态，不会重复监听窗口事件。
 *
 * 档位定义见 src/utils/responsiveBreakpoints.js，同一份数据源，
 * CSS 侧数值需保持一致，一致性由 tests/e2e/breakpoint-consistency.spec.js 校验。
 *
 * 用法：
 *   const { mode, isCompactOrBelow, isTabletOrBelow, isMobile } = useResponsiveLayout()
 */

const TIER_ORDER = ['wide', 'standard', 'compact', 'tablet']

function computeMode(mediaQueryLists) {
  for (const tier of TIER_ORDER) {
    if (mediaQueryLists[tier].matches) return tier
  }
  return 'mobile'
}

function createResponsiveState() {
  const mode = ref('wide')

  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return mode
  }

  const mediaQueryLists = Object.fromEntries(
    TIER_ORDER.map(tier => [tier, window.matchMedia(MEDIA_QUERIES[tier])])
  )

  mode.value = computeMode(mediaQueryLists)

  const handleChange = () => { mode.value = computeMode(mediaQueryLists) }
  for (const mql of Object.values(mediaQueryLists)) {
    mql.addEventListener('change', handleChange)
  }

  return mode
}

// 模块只在首次 import 时求值一次，天然是单例；不需要 onMounted/onUnmounted 挂钩
const sharedMode = createResponsiveState()

export function useResponsiveLayout() {
  const mode = computed(() => sharedMode.value)

  const isWide     = computed(() => mode.value === 'wide')
  const isStandard = computed(() => mode.value === 'standard')
  const isCompact  = computed(() => mode.value === 'compact')
  const isTablet   = computed(() => mode.value === 'tablet')
  const isMobile   = computed(() => mode.value === 'mobile')

  // 常用的"及以下"判断：例如筛选栏该不该切换成抽屉
  const TIER_RANK = { wide: 4, standard: 3, compact: 2, tablet: 1, mobile: 0 }
  const isCompactOrBelow = computed(() => TIER_RANK[mode.value] <= TIER_RANK.compact)
  const isTabletOrBelow  = computed(() => TIER_RANK[mode.value] <= TIER_RANK.tablet)

  return {
    mode,
    isWide,
    isStandard,
    isCompact,
    isTablet,
    isMobile,
    isCompactOrBelow,
    isTabletOrBelow,
  }
}
