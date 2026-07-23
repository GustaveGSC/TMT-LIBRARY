import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { BREAKPOINTS, modeForWidth } from '@/utils/responsiveBreakpoints'

/**
 * useResponsiveLayout — 统一的响应式档位判断
 *
 * 替代页面里各自散落的 `window.innerWidth <= 768` + 各写一份 resize 监听。
 * 档位定义见 src/utils/responsiveBreakpoints.js，同一份数据源，避免
 * CSS 已经进入紧凑布局、JS 却还在渲染桌面控件这种分叉。
 *
 * 用法：
 *   const { mode, isCompactOrBelow, isTabletOrBelow, isMobile } = useResponsiveLayout()
 */
export function useResponsiveLayout() {
  const width = ref(typeof window !== 'undefined' ? window.innerWidth : BREAKPOINTS.wide)

  function onResize() {
    width.value = window.innerWidth
  }

  onMounted(() => window.addEventListener('resize', onResize))
  onBeforeUnmount(() => window.removeEventListener('resize', onResize))

  const mode = computed(() => modeForWidth(width.value))

  const isWide     = computed(() => mode.value === 'wide')
  const isStandard = computed(() => mode.value === 'standard')
  const isCompact  = computed(() => mode.value === 'compact')
  const isTablet   = computed(() => mode.value === 'tablet')
  const isMobile   = computed(() => mode.value === 'mobile')

  // 常用的"及以下"判断：例如筛选栏该不该切换成抽屉
  const isCompactOrBelow = computed(() => width.value < BREAKPOINTS.standard)
  const isTabletOrBelow  = computed(() => width.value < BREAKPOINTS.compact)

  return {
    width,
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
