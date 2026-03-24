<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import { useFinishedStore } from '@/stores/product/finished'
import { ensureTableData } from '@/stores/product'

// ── 响应式状态 ────────────────────────────────────
const finishedStore = useFinishedStore()
const chartEl       = ref(null)          // ECharts 挂载容器
let   chartInst     = null               // ECharts 实例（非响应式，避免 Vue 深代理破坏内部状态）
let   resizeObs     = null               // ResizeObserver 实例

// 状态筛选
const filterStatus = ref('')

const STATUS_TABS = [
  { key: '',           label: '全部'     },
  { key: 'recorded',   label: '已录入'   },
  { key: 'unrecorded', label: '未录入'   },
  { key: 'ignored',    label: '无需录入' },
]

// 品类配色（与 page-product.vue 一致）
const CAT_COLORS = ['#c4883a', '#4a8fc0', '#6ab47a', '#9c6fba', '#e07070', '#70aacc', '#e0a040', '#7abcaa']

// ── 计算属性 ──────────────────────────────────────
// 按状态筛选
const filteredItems = computed(() => {
  if (!filterStatus.value) return finishedStore.rawItems
  return finishedStore.rawItems.filter(r => r.status === filterStatus.value)
})

const totalCount = computed(() => filteredItems.value.length)

// 将筛选后数据转换为旭日图树形结构：品类 → 系列 → 型号（叶节点 value = 该型号下成品数）
const sunburstData = computed(() => buildSunburstData(filteredItems.value))

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  // 若数据尚未加载（直接从概览导航过来），则先加载
  if (!finishedStore.loaded) {
    await ensureTableData()
  }
  initChart()
})

onUnmounted(() => {
  resizeObs?.disconnect()
  if (chartInst) {
    chartInst.dispose()
    chartInst = null
  }
})

// 数据或筛选变化时重新渲染
watch([sunburstData, totalCount], () => {
  renderChart()
})

// ── 方法 ──────────────────────────────────────────

/**
 * 将 hex 颜色与白色混合，生成指定程度的浅色
 * @param {string} hex  原色，如 '#c4883a'
 * @param {number} t    混合量 0=原色  1=纯白
 */
function tintColor(hex, t) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  const tr = Math.round(r + (255 - r) * t).toString(16).padStart(2, '0')
  const tg = Math.round(g + (255 - g) * t).toString(16).padStart(2, '0')
  const tb = Math.round(b + (255 - b) * t).toString(16).padStart(2, '0')
  return `#${tr}${tg}${tb}`
}

/**
 * 将成品列表转换为旭日图树：品类 → 系列 → 型号
 * 返回品类数组（直接作为 series.data，ECharts 旭日图不需要单个根节点）
 * 三环颜色：品类=原色，系列=与白混合40%，型号=与白混合72%
 */
function buildSunburstData(items) {
  // catMap: category → series → model → { count, products: [{name, name_en}] }
  const catMap = new Map()

  for (const r of items) {
    const cat    = r.category_name || '未分类'
    const series = r.series_name   || '(无系列)'
    const model  = r.model_code    || '(无型号)'

    if (!catMap.has(cat)) catMap.set(cat, new Map())
    const seriesMap = catMap.get(cat)
    if (!seriesMap.has(series)) seriesMap.set(series, new Map())
    const modelMap = seriesMap.get(series)
    if (!modelMap.has(model)) modelMap.set(model, { count: 0, products: [] })
    const entry = modelMap.get(model)
    entry.count++
    entry.products.push({ name: r.name || '', name_en: r.name_en || '' })
  }

  const result = []
  let colorIdx = 0

  for (const [catName, seriesMap] of catMap) {
    const catColor    = CAT_COLORS[colorIdx % CAT_COLORS.length]
    const seriesColor = tintColor(catColor, 0.40)  // 中亮，与品类明显区分
    const modelColor  = tintColor(catColor, 0.72)  // 浅色，与系列明显区分
    colorIdx++
    const catChildren = []
    let   catTotal    = 0

    for (const [seriesName, modelMap] of seriesMap) {
      const seriesChildren = []
      let   seriesTotal    = 0

      for (const [modelCode, { count, products }] of modelMap) {
        seriesTotal += count
        // products 存入节点，供 tooltip formatter 读取
        seriesChildren.push({
          name:      modelCode,
          value:     count,
          products,
          itemStyle: { color: modelColor },
        })
      }

      catTotal += seriesTotal
      catChildren.push({
        name:      seriesName,
        value:     seriesTotal,
        itemStyle: { color: seriesColor },
        children:  seriesChildren,
      })
    }

    result.push({
      name:      catName,
      value:     catTotal,
      itemStyle: { color: catColor },
      children:  catChildren,
    })
  }

  return result
}

/**
 * 构建 ECharts option
 */
function buildChartOption(data, total) {
  const FONT = "'Microsoft YaHei UI','Microsoft YaHei','PingFang SC',sans-serif"

  return {
    backgroundColor: 'transparent',

    tooltip: {
      trigger: 'item',
      formatter(params) {
        const depth  = (params.treePathInfo?.length ?? 1) - 1  // 1=品类 2=系列 3=型号
        const labels = ['', '品类', '系列', '型号']
        const label  = labels[depth] || '型号'

        let extra = ''
        // 型号节点：列出各成品的中文名和英文名
        if (depth === 3 && params.data?.products?.length) {
          const list    = params.data.products
          const MAX     = 6
          const shown   = list.slice(0, MAX)
          const more    = list.length - MAX
          const rows    = shown.map(p => {
            const cn = p.name    ? `<span style="color:#3a3028">${p.name}</span>` : ''
            const en = p.name_en ? `<span style="color:#8a7a6a;font-size:11px"> / ${p.name_en}</span>` : ''
            return `<div style="padding:1px 0;border-bottom:1px solid #f0e8d8;white-space:nowrap">${cn}${en}</div>`
          }).join('')
          const moreRow = more > 0 ? `<div style="color:#8a7a6a;font-size:11px;padding-top:2px">…还有 ${more} 个</div>` : ''
          extra = `<div style="margin-top:6px">${rows}${moreRow}</div>`
        }

        const countLine = depth < 3
          ? `<div style="color:#6b5e4e">${label} · ${params.value} 个成品</div>`
          : ''
        return `<div style="font-size:13px;color:#3a3028;font-family:${FONT};line-height:1.6;max-width:280px">
          <div style="font-weight:600;margin-bottom:2px">${params.name}</div>
          ${countLine}
          ${extra}
        </div>`
      },
      backgroundColor: '#fff',
      borderColor:     '#e0d4c0',
      borderWidth:     1,
      padding:         [8, 12],
      extraCssText:    'border-radius:8px;box-shadow:0 4px 16px rgba(150,100,50,0.12)',
    },

    graphic: [{
      type: 'group',
      left: 'center',
      top:  'middle',
      z:    100,
      children: [
        {
          type: 'text',
          left: 'center',
          top: -16,
          style: {
            text:       String(total),
            textAlign:  'center',
            fontSize:   30,
            fontWeight: 700,
            fill:       '#c4883a',
            fontFamily: FONT,
          },
        },
        {
          type: 'text',
          left: 'center',
          top:  20,
          style: {
            text:       '个成品',
            textAlign:  'center',
            fontSize:   12,
            fill:       '#8a7a6a',
            fontFamily: FONT,
          },
        },
      ],
    }],

    series: [{
      type:   'sunburst',
      data:   data,
      radius: ['18%', '82%'],
      center: ['50%', '50%'],
      sort:   'desc',
      emphasis: {
        focus: 'ancestor',
        itemStyle: { shadowBlur: 12, shadowColor: 'rgba(0,0,0,0.12)' },
      },
      levels: [
        {},  // 虚拟根（index 0，不显示）
        // 品类环（深色背景，白色文字）
        {
          r0: '18%', r: '42%',
          label: {
            rotate:     'tangential',
            fontSize:   12,
            fontWeight: 600,
            fontFamily: FONT,
            color:      '#fff',
            minAngle:   8,
          },
          itemStyle: { borderColor: '#fff', borderWidth: 2 },
        },
        // 系列环（中亮色背景，深色文字）
        {
          r0: '42%', r: '63%',
          label: {
            rotate:     'tangential',
            fontSize:   11,
            fontFamily: FONT,
            color:      '#3a3028',
            minAngle:   6,
          },
          itemStyle: { borderColor: '#fff', borderWidth: 1.5 },
        },
        // 型号环（浅色背景，深色文字）
        {
          r0: '63%', r: '82%',
          label: {
            rotate:     'tangential',
            fontSize:   10,
            fontFamily: FONT,
            color:      '#5a4a3a',
            minAngle:   5,
          },
          itemStyle: { borderColor: '#fff', borderWidth: 1 },
        },
      ],
    }],
  }
}

/** 初始化 ResizeObserver，等元素第一次有尺寸时再创建 ECharts 实例
 *  避免 v-show=false 时 offsetWidth=0 导致 ECharts 报错 */
function initChart() {
  if (!chartEl.value) return

  resizeObs = new ResizeObserver(() => {
    if (!chartEl.value?.offsetWidth || !chartEl.value?.offsetHeight) return
    if (!chartInst) {
      // 元素首次出现有效尺寸：创建实例并渲染
      chartInst = echarts.init(chartEl.value, null, { renderer: 'canvas' })
      renderChart()
    } else {
      chartInst.resize()
    }
  })
  resizeObs.observe(chartEl.value)
}

/** 渲染 / 更新图表 */
function renderChart() {
  if (!chartInst) return
  chartInst.setOption(buildChartOption(sunburstData.value, totalCount.value), { notMerge: true })
}
</script>

<template>
  <div class="product-chart">

    <!-- ── 工具栏 ─────────────────────────────────── -->
    <div class="chart-toolbar">
      <!-- 状态筛选 Tab -->
      <div class="filter-tabs">
        <button
          v-for="tab in STATUS_TABS"
          :key="tab.key"
          class="filter-tab"
          :class="{ active: filterStatus === tab.key }"
          @click="filterStatus = tab.key"
        >{{ tab.label }}</button>
      </div>

      <!-- 数量统计 -->
      <span class="chart-count">共 {{ totalCount }} 个成品</span>
    </div>

    <!-- ── 加载中 ──────────────────────────────────── -->
    <div v-if="finishedStore.loading" class="chart-state">
      <div class="state-spinner"></div>
      <span>加载中…</span>
    </div>

    <!-- ── 空状态 ──────────────────────────────────── -->
    <div v-else-if="finishedStore.loaded && !filteredItems.length" class="chart-state">
      <span class="state-empty">没有匹配的成品</span>
    </div>

    <!-- ── 图表容器 ────────────────────────────────── -->
    <!-- v-show 保留 DOM 节点，ResizeObserver 可感知显示时的尺寸变化 -->
    <div
      v-show="!finishedStore.loading && filteredItems.length"
      ref="chartEl"
      class="chart-canvas"
    ></div>

  </div>
</template>

<style scoped>
.product-chart {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'PingFang SC', sans-serif;
}

/* ── 工具栏 ─────────────────────────────────────── */
.chart-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  background: rgba(255, 255, 255, 0.7);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.filter-tabs {
  display: flex;
  gap: 2px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 3px;
}

.filter-tab {
  padding: 4px 10px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.filter-tab:hover { color: var(--text-primary); }
.filter-tab.active {
  background: var(--accent);
  color: #fff;
  font-weight: 500;
}

.chart-count {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-muted);
  flex-shrink: 0;
}

/* ── 加载 / 空状态 ──────────────────────────────── */
.chart-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-muted);
  font-size: 13px;
}

.state-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.state-empty { font-size: 14px; color: var(--text-muted); }

/* ── 图表画布 ────────────────────────────────────── */
.chart-canvas {
  flex: 1;
  min-height: 0;
  /* 不设 padding，让 ECharts 读取准确的 offsetWidth/offsetHeight */
}
</style>
