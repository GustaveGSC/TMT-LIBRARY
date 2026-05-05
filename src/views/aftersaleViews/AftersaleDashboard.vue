<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue' // nextTick 仍用于 drillDown/drillBack
import { ArrowDown, ArrowLeft, ArrowRight, Setting } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import http from '@/api/http.js'
import iconReason   from '@/assets/icons/btn_reason.png'
import iconMaterial from '@/assets/icons/btn_material.png'
import iconShip     from '@/assets/icons/btn_ship.png'
import iconRegion   from '@/assets/icons/btn_region.png'

// ── 常量 ──────────────────────────────────────────
const FONT = "'Microsoft YaHei UI','Microsoft YaHei','PingFang SC',sans-serif"

const DATE_SHORTCUTS = [
  { text: '从2024年起', value: () => [new Date('2024-01-01'), new Date()] },
  { text: '一年内',    value: () => { const s = new Date(); s.setFullYear(s.getFullYear() - 1); return [s, new Date()] } },
  { text: '半年内',    value: () => { const s = new Date(); s.setMonth(s.getMonth() - 6); return [s, new Date()] } },
  { text: '三个月内',  value: () => { const s = new Date(); s.setMonth(s.getMonth() - 3); return [s, new Date()] } },
  { text: '一个月内',  value: () => { const s = new Date(); s.setMonth(s.getMonth() - 1); return [s, new Date()] } },
]

// 子维度 Tab（不含产品，产品是默认视图）
const DIMS = [
  { key: 'reason',         label: '原因', icon: iconReason   },
  { key: 'shipping_alias', label: '物料', icon: iconMaterial },
  { key: 'channel',        label: '渠道', icon: iconShip     },
  { key: 'province',       label: '地域', icon: iconRegion   },
]


// ── 响应式状态 ────────────────────────────────────

// 筛选面板折叠状态
const sections = reactive({
  time:     true,
  product:  true,
  reason:   true,
  shipping: true,
  channel:  true,
  region:   true,
})

// 筛选值
const filters = ref({
  dateRange:            (() => { const s = new Date(); s.setMonth(s.getMonth() - 1); return [s, new Date()] })(),
  maxDaysSincePurchase: 1825, // 售后间隔上限（天），null = 不限
  categoryIds:          [],
  seriesIds:            [],
  modelIds:             [],
  reasonCategoryIds:    [],
  reasonIds:            [],
  shippingAliasIds:     [],

  channelNames:         [],
  provinces:            [],
  cities:               [],
})

// 静态候选数据（初始加载一次）
const categoryTree       = ref([])
const allReasonGroups    = ref([])
const allShippingAliases = ref([])

// 联动筛选后可用 id 集合（null=未加载）
const available = ref({
  channels:           null,
  provinces:          null,
  cities:             null,
  model_ids:          null,
  reason_ids:         null,
  shipping_alias_ids: null,
})

const loadingOpts      = ref(false)
const filterCollapsed  = ref(false)
const hideNoSales      = ref(false)  // 隐藏无同期发货的数据项
let   _filterTimer = null
let   _chartTimer  = null
let   _chartCache  = new Map()       // key: groupBy值('product'/'reason'/...)，value: 接口返回 data

// 图表状态
const groupBy      = ref(null)    // null=产品视图（默认），非null=子维度
const chartData    = ref(null)
const loadingChart = ref(false)
const chartEl      = ref(null)
let   chartInst    = null

// 产品维度下钻面包屑：[{ label, savedCategoryIds, savedSeriesIds, savedModelIds }]
const drillStack = ref([])
// 防止 drillDown/drillBack 修改 filters 时触发清栈
let   _isDrilling = false

// ── 计算属性 ──────────────────────────────────────

/** 当前产品视图的聚合层级（基于左侧筛选选择） */
const effectiveProductLevel = computed(() => {
  if (filters.value.modelIds.length)   return 'model'
  if (filters.value.seriesIds.length)  return 'model'   // 系列已定，显示型号
  if (filters.value.categoryIds.length) return 'series'  // 品类已定，显示系列
  return 'category'
})

/** 产品视图是否还能继续下钻 */
const canDrillDown = computed(() => effectiveProductLevel.value !== 'model')

/** 品类选项：联动过滤，只显示含有可用型号的品类 */
const categoryOpts = computed(() => {
  const avail = available.value.model_ids
  return categoryTree.value
    .filter(c => !avail || (c.series || []).some(s =>
      (s.models || []).some(m => avail.includes(m.id))
    ))
    .map(c => ({ value: c.id, label: c.name }))
})

/** 已选品类对应的系列选项：联动过滤，只显示含有可用型号的系列 */
const seriesOpts = computed(() => {
  const cats = filters.value.categoryIds.length
    ? categoryTree.value.filter(c => filters.value.categoryIds.includes(c.id))
    : categoryTree.value
  const avail = available.value.model_ids
  return cats.flatMap(c =>
    (c.series || [])
      .filter(s => !avail || (s.models || []).some(m => avail.includes(m.id)))
      .map(s => ({ value: s.id, label: s.code, sub: s.name }))
  )
})

const seriesEnabled = computed(() => filters.value.categoryIds.length > 0)

/** 型号选项：联动过滤 */
const modelOpts = computed(() => {
  const sers = filters.value.seriesIds.length
    ? categoryTree.value.flatMap(c => (c.series || []).filter(s => filters.value.seriesIds.includes(s.id)))
    : categoryTree.value.flatMap(c =>
        (c.series || []).filter(() => !filters.value.categoryIds.length || filters.value.categoryIds.includes(c.id))
      )
  const avail = available.value.model_ids
  return sers.flatMap(s =>
    (s.models || [])
      .filter(m => !avail || avail.includes(m.id))
      .map(m => ({ value: m.id, label: m.model_code, sub: m.name }))
  )
})

const modelEnabled = computed(() => filters.value.seriesIds.length > 0 || filters.value.categoryIds.length > 0)

/** 一级分类选项：联动过滤 */
const reasonCatOpts = computed(() => {
  const avail = available.value.reason_ids
  return allReasonGroups.value
    .filter(g => !avail || (g.reasons || []).some(r => avail.includes(r.id)))
    .map(g => ({ value: g.category_id, label: g.category_name }))
})

/** 二级原因选项：联动过滤 */
const reasonOpts = computed(() => {
  const groups = filters.value.reasonCategoryIds.length
    ? allReasonGroups.value.filter(g => filters.value.reasonCategoryIds.includes(g.category_id))
    : allReasonGroups.value
  const avail = available.value.reason_ids
  return groups.flatMap(g =>
    (g.reasons || [])
      .filter(r => !avail || avail.includes(r.id))
      .map(r => ({ value: r.id, label: r.name, sub: g.category_name }))
  )
})

const reasonEnabled = computed(() => filters.value.reasonCategoryIds.length > 0)

/** 发货物料简称选项：联动过滤 */
const shippingAliasOpts = computed(() => {
  const avail = available.value.shipping_alias_ids
  return allShippingAliases.value
    .filter(a => !avail || avail.includes(a.id))
    .map(a => ({ value: a.id, label: a.name }))
})

/** 渠道选项：联动过滤 */
const channelOpts = computed(() =>
  (available.value.channels ?? []).map(c => ({ value: c, label: c }))
)

/** 省份选项：联动过滤 */
const provinceOpts = computed(() =>
  (available.value.provinces ?? []).map(p => ({ value: p, label: p }))
)

/** 城市选项：联动过滤 */
const cityOpts = computed(() =>
  (available.value.cities ?? []).map(c => ({ value: c, label: c }))
)

const cityEnabled = computed(() => filters.value.provinces.length > 0)

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  initChart()  // 先挂载 ResizeObserver，等容器就绪后自动初始化
  await Promise.all([loadStaticOptions(), loadCrossFilterOptions()])
  await loadChartData()
})

onBeforeUnmount(() => {
  chartInst?.dispose()
  chartInst = null
})

// ── Watch ─────────────────────────────────────────

// 任意筛选变化 → 清空图表缓存 + 防抖刷新联动候选选项（始终自动）
watch(filters, () => {
  _chartCache.clear()
  clearTimeout(_filterTimer)
  _filterTimer = setTimeout(() => loadCrossFilterOptions(), 300)
}, { deep: true })

// 非时间筛选变化 → 防抖自动刷新图表（时间/间隔需手动点查询）
watch(
  () => [
    filters.value.categoryIds, filters.value.seriesIds, filters.value.modelIds,
    filters.value.reasonCategoryIds, filters.value.reasonIds,
    filters.value.shippingAliasIds,
    filters.value.channelNames, filters.value.provinces, filters.value.cities,
  ],
  () => {
    clearTimeout(_chartTimer)
    _chartTimer = setTimeout(() => loadChartData(), 300)
  },
  { deep: true }
)

// 产品筛选手动变化时清空下钻栈（drillDown/drillBack 期间用 _isDrilling 跳过）
watch(
  () => [filters.value.categoryIds, filters.value.seriesIds, filters.value.modelIds],
  () => { if (!_isDrilling) drillStack.value = [] },
  { deep: true }
)

// 维度 Tab 切换 → 刷新图表
watch(groupBy, () => loadChartData())

// 隐藏无同期发货 → 直接重渲染（不重新请求数据）
watch(hideNoSales, () => renderChart())

// ── 方法 ──────────────────────────────────────────

async function loadStaticOptions() {
  const [treeRes, reasonRes, shippingRes] = await Promise.all([
    http.get('/api/category/tree'),
    http.get('/api/aftersale/reasons'),
    http.get('/api/aftersale/shipping-aliases'),
  ])
  if (treeRes.success)     categoryTree.value       = treeRes.data
  if (reasonRes.success)   allReasonGroups.value    = reasonRes.data
  if (shippingRes.success) allShippingAliases.value = shippingRes.data
}

/** 构建通用筛选参数（category_ids/series_ids/model_ids 分开传） */
function buildFilterBody() {
  const [start, end] = filters.value.dateRange || []
  return {
    date_start:              start ? formatDate(start) : undefined,
    date_end:                end   ? formatDate(end)   : undefined,
    max_days_since_purchase: filters.value.maxDaysSincePurchase ?? undefined,
    category_ids:            filters.value.categoryIds,
    series_ids:              filters.value.seriesIds,
    model_ids:               filters.value.modelIds,
    reason_ids:              filters.value.reasonIds,
    reason_category_ids:     filters.value.reasonCategoryIds,
    shipping_alias_ids:      filters.value.shippingAliasIds,
    channel_names:           filters.value.channelNames,
    provinces:               filters.value.provinces,
    cities:                  filters.value.cities,
  }
}

async function loadCrossFilterOptions() {
  loadingOpts.value = true
  try {
    const res = await http.post('/api/aftersale/chart-filter-options', buildFilterBody())
    if (res.success) available.value = res.data
  } finally {
    loadingOpts.value = false
  }
}

async function loadChartData() {
  const cacheKey = groupBy.value ?? 'product'

  // 命中缓存：直接渲染，无需等待
  if (_chartCache.has(cacheKey)) {
    chartData.value = _chartCache.get(cacheKey)
    renderChart()
    return
  }

  loadingChart.value = true
  try {
    const body = { ...buildFilterBody(), group_by: cacheKey }
    const res = await http.post('/api/aftersale/chart-data', body)
    if (res.success) {
      _chartCache.set(cacheKey, res.data)
      chartData.value = res.data
      renderChart()
    }
  } finally {
    loadingChart.value = false
  }
}

function formatDate(d) {
  if (!d) return undefined
  if (typeof d === 'string') return d
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}

// ── 图表工具函数 ───────────────────────────────────

/** 销售占比显示格式 */
function fmtSaleRatio(v) {
  if (v === null || v === undefined) return '无同期发货'
  if (v < 0.01) return '< 0.01%'
  return `${v.toFixed(2)}%`
}

/** 工具箱（保存图片 + 还原，withZoom 时加区域缩放） */
function makeToolbox(withZoom = false) {
  return {
    right: 16, top: 12,
    feature: {
      ...(withZoom ? { dataZoom: { title: { zoom: '区域缩放', back: '缩放还原' }, yAxisIndex: 'none' } } : {}),
      restore:     { title: '还原' },
      saveAsImage: { title: '保存图片', pixelRatio: 2 },
    },
    iconStyle: { borderColor: '#8a7a6a' },
    emphasis:  { iconStyle: { borderColor: '#c4883a', color: '#c4883a' } },
  }
}

/** 图表标题：产品/原因/物料/渠道/地域 筛选状态描述 */
function buildChartTitle() {
  function prodDesc() {
    if (filters.value.modelIds.length > 1)    return '部分型号'
    if (filters.value.modelIds.length === 1) {
      for (const c of categoryTree.value) for (const s of c.series || []) for (const m of s.models || []) if (m.id === filters.value.modelIds[0]) return m.model_code
    }
    if (filters.value.seriesIds.length > 1)   return '部分系列'
    if (filters.value.seriesIds.length === 1) {
      for (const c of categoryTree.value) for (const s of c.series || []) if (s.id === filters.value.seriesIds[0]) return s.code
    }
    if (filters.value.categoryIds.length > 1)  return '部分品类'
    if (filters.value.categoryIds.length === 1) return categoryTree.value.find(c => c.id === filters.value.categoryIds[0])?.name ?? '品类'
    return '全部品类'
  }
  function reasonDesc() {
    if (filters.value.reasonIds.length > 1)  return '部分原因'
    if (filters.value.reasonIds.length === 1) {
      for (const g of allReasonGroups.value) { const r = (g.reasons||[]).find(r => r.id === filters.value.reasonIds[0]); if (r) return r.name }
    }
    if (filters.value.reasonCategoryIds.length === 1) return allReasonGroups.value.find(g => g.category_id === filters.value.reasonCategoryIds[0])?.category_name ?? '部分分类'
    return '全部原因'
  }
  function channelDesc() {
    if (filters.value.channelNames.length > 1)  return '部分渠道'
    if (filters.value.channelNames.length === 1) return filters.value.channelNames[0]
    return '全部渠道'
  }
  function regionDesc() {
    const src = filters.value.cities.length ? filters.value.cities : filters.value.provinces
    if (src.length > 1)  return '部分区域'
    if (src.length === 1) return src[0]
    return '全部区域'
  }

  const dimLabel = groupBy.value ? (DIMS.find(d => d.key === groupBy.value)?.label ?? '') + '分布' : '产品分布'
  const gby = groupBy.value
  let parts
  if (gby === 'channel')        parts = [channelDesc(), prodDesc(), reasonDesc(), regionDesc()]
  else if (gby === 'province')  parts = [regionDesc(), prodDesc(), reasonDesc(), channelDesc()]
  else if (gby === 'reason')    parts = [reasonDesc(), prodDesc(), channelDesc(), regionDesc()]
  else                          parts = [prodDesc(), reasonDesc(), channelDesc(), regionDesc()]

  // 去掉"全部"的默认项，只保留有意义的描述
  const defaults = new Set(['全部品类', '全部原因', '全部渠道', '全部区域'])
  const filtered = parts.filter(p => !defaults.has(p))
  const prefix = filtered.length ? filtered.join(' - ') : '全部'
  return `${prefix}   ${dimLabel}`
}

function buildSubtitle() {
  const [start, end] = filters.value.dateRange || []
  if (start && end) return `${formatDate(start)}  ~  ${formatDate(end)}`
  if (start) return `${formatDate(start)} 起`
  return '全部时间'
}

// ── 图表 ──────────────────────────────────────────

function initChart() {
  if (!chartEl.value) return

  // 用 ResizeObserver 等容器有实际尺寸后再初始化，避免 ECharts "0 width/height" 警告
  const ro = new ResizeObserver((entries) => {
    const { width, height } = entries[0].contentRect
    if (!chartInst && width > 0 && height > 0) {
      chartInst = echarts.init(chartEl.value, null, { renderer: 'canvas' })

      // 右击柱子：产品视图下钻 / 维度视图切回产品
      chartInst.on('contextmenu', (params) => {
        params.event?.event?.preventDefault?.()
        if (params.componentType !== 'series' || params.seriesType !== 'bar') return
        if (groupBy.value === null && canDrillDown.value) {
          drillDown(params.name)
        } else if (groupBy.value !== null) {
          drillDim(params.name)
        }
      })

      renderChart()
    } else if (chartInst) {
      chartInst.resize()
    }
  })
  ro.observe(chartEl.value)
}

function renderChart() {
  if (!chartInst || !chartData.value) return
  let items = chartData.value.items || []
  // 仅产品视图下过滤"无同期发货"数据（维度视图 sale_ratio 本就全为 null，不适用此逻辑）
  if (hideNoSales.value && groupBy.value === null) {
    items = items.filter(i => i.sale_ratio !== null && i.sale_ratio !== undefined)
  }
  if (!items.length) { chartInst.clear(); return }

  if (groupBy.value === null) {
    // 产品视图：柱状图 + 占比折线 + 累计占比（Pareto）
    chartInst.setOption(buildProductOption(items), true)
  } else {
    // 子维度视图：标准柱状图
    chartInst.setOption(buildDimOption(items), true)
  }
}

/** 产品视图图表配置：柱 + 占比折线 + 累计折线，右击可下钻 */
function buildProductOption(items) {
  const names  = items.map(i => i.name)
  const values = items.map(i => i.value)
  // 过滤后用实际 items 之和重新作分母，保证占比基于当前可见数据
  const total  = values.reduce((s, v) => s + v, 0) || 1

  const pctData      = values.map(v => total > 0 ? Math.round(v / total * 1000) / 10 : 0)
  const rawSaleRatio  = items.map(i => i.sale_ratio ?? null)
  const hasSaleRatio  = rawSaleRatio.some(v => v !== null)
  // 超出100%时在图表上钳制为101%（Y轴 max=102），用特殊标记表示
  const saleRatioData = rawSaleRatio.map(v => {
    const overflow = v === null || v > 100
    return {
      value:     overflow ? 101 : v,
      itemStyle: overflow ? { color: 'transparent', borderColor: '#7a5cbf', borderWidth: 2 } : undefined,
      symbol:    overflow ? 'triangle' : undefined,
    }
  })
  const cumulData = []
  let running = 0
  for (const v of values) {
    running += v
    cumulData.push(total > 0 ? Math.round(running / total * 1000) / 10 : 0)
  }

  const levelLabel = { category: '品类', series: '系列', model: '型号' }[effectiveProductLevel.value]
  const rotate = names.length > 8 ? 30 : 0

  return {
    backgroundColor: 'transparent',
    title: {
      text: buildChartTitle(),
      subtext: buildSubtitle(),
      left: 10, top: 16,
      textStyle: { color: '#3a3028', fontFamily: FONT, fontSize: 14, fontWeight: '600' },
      subtextStyle: { color: '#8a7a6a', fontFamily: FONT, fontSize: 12 },
    },
    toolbox: makeToolbox(true),
    legend: {
      top: 16, left: 'center', type: 'scroll',
      textStyle: { fontFamily: FONT, fontSize: 13, color: '#6b5e4e' },
      itemWidth: 18, itemHeight: 12, itemGap: 16,
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      textStyle: { fontFamily: FONT },
      formatter(params) {
        const bar   = params.find(p => p.seriesType === 'bar')
        const pct   = params.find(p => p.seriesName === '占比')
        const cumul = params.find(p => p.seriesName === '累计占比')
        const ROW = (marker, name, val) =>
          `<div style="display:flex;justify-content:space-between;align-items:center;gap:20px;line-height:1.8">`+
          `<span>${marker}${name}</span><span style="font-weight:600">${val}</span></div>`
        // 系列/型号：查找全名
        const xName = params[0]?.name ?? ''
        let subName = ''
        if (effectiveProductLevel.value === 'series') {
          for (const c of categoryTree.value) {
            const found = (c.series || []).find(s => s.code === xName)
            if (found) { subName = found.name; break }
          }
        } else if (effectiveProductLevel.value === 'model') {
          for (const c of categoryTree.value) for (const sr of c.series || []) {
            const found = (sr.models || []).find(m => m.model_code === xName)
            if (found) { subName = found.name; break }
          }
        }
        let s = `<div style="font-family:${FONT};font-size:13px;min-width:150px">`
        s += `<div style="font-weight:600;margin-bottom:${subName ? 1 : 4}px;color:#3a3028">${xName}</div>`
        if (subName) s += `<div style="font-size:11px;color:#8a7a6a;margin-bottom:4px">${subName}</div>`
        const dataItem = (chartData.value?.items || []).find(i => i.name === xName)
        const saleRatio = dataItem?.sale_ratio ?? null
        const shipped   = dataItem?.shipped   ?? 0
        const srColor   = '#7a5cbf'
        const srMarker  = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${srColor};margin-right:4px"></span>`
        if (bar)   s += ROW(bar.marker,   '件数',    bar.value)
        if (pct)   s += ROW(pct.marker,   '占比',    `${pct.value}%`)
        if (cumul) s += ROW(cumul.marker, '累计占比', `${cumul.value}%`)
        if (hasSaleRatio || shipped > 0 || saleRatio !== null) {
          s += ROW(srMarker, '销售占比', fmtSaleRatio(saleRatio))
        }
        if (canDrillDown.value) {
          s += `<div style="margin-top:6px;border-top:1px solid #e0d4c0;padding-top:4px;color:#8a7a6a;font-size:11px">右击查看详情</div>`
        }
        return s + '</div>'
      },
    },
    grid: { top: 100, left: 56, right: 80, bottom: rotate ? 110 : 86 },
    dataZoom: [
      {
        type: 'slider', xAxisIndex: 0,
        bottom: rotate ? 36 : 12, height: 20,
        borderColor: '#e0d4c0', fillerColor: 'rgba(196,136,58,0.12)',
        handleStyle: { color: '#c4883a' },
        moveHandleStyle: { color: '#c4883a' },
        selectedDataBackground: { lineStyle: { color: '#c4883a' }, areaStyle: { color: '#c4883a' } },
        textStyle: { fontFamily: FONT, color: '#8a7a6a', fontSize: 11 },
        brushSelect: false,
      },
      { type: 'inside', xAxisIndex: 0 },
    ],
    xAxis: {
      type: 'category', data: names,
      axisLabel: { interval: 0, rotate, fontSize: 12, color: '#6b5e4e', fontFamily: FONT, overflow: 'truncate', width: 80 },
      axisLine: { lineStyle: { color: '#e0d4c0' } },
      axisTick: { lineStyle: { color: '#e0d4c0' } },
    },
    yAxis: [
      {
        type: 'value', name: `${levelLabel}件数`,
        nameTextStyle: { color: '#8a7a6a', fontFamily: FONT, fontSize: 11 },
        axisLabel: { color: '#8a7a6a', fontFamily: FONT, fontSize: 11 },
        splitLine: { lineStyle: { color: '#f0e8d8' } },
        axisLine: { show: true, lineStyle: { color: '#e0d4c0' } },
      },
      {
        type: 'value', min: 0, max: 102, name: '占比%',
        nameTextStyle: { color: '#8a7a6a', fontFamily: FONT, fontSize: 11 },
        axisLabel: { color: '#8a7a6a', fontFamily: FONT, fontSize: 11, formatter: '{value}%' },
        splitLine: { show: false },
        axisLine: { show: true, lineStyle: { color: '#e0d4c0' } },
      },
    ],
    series: [
      {
        name: levelLabel, type: 'bar', data: values, yAxisIndex: 0,
        itemStyle: { color: '#c4883a', borderRadius: [3, 3, 0, 0] },
        emphasis: { itemStyle: { color: '#e09050' } },
        label: { show: names.length <= 16, position: 'top', fontSize: 12, color: '#3a3028', fontFamily: FONT, fontWeight: 'bold' },
      },
      {
        name: '占比', type: 'line', data: pctData, yAxisIndex: 1,
        smooth: true, symbol: 'circle', symbolSize: 4,
        lineStyle: { color: '#4a8fc0', width: 1.5 },
        itemStyle: { color: '#4a8fc0' },
        label: { show: true, fontSize: 11, color: '#4a8fc0', fontFamily: FONT, formatter: p => `${p.value}%` },
      },
      {
        name: '累计占比', type: 'line', data: cumulData, yAxisIndex: 1,
        smooth: true, symbol: 'circle', symbolSize: 4,
        lineStyle: { color: '#e05050', width: 1.5, type: 'dashed' },
        itemStyle: { color: '#e05050' },
        label: { show: true, fontSize: 11, color: '#e05050', fontFamily: FONT, formatter: p => `${p.value}%` },
      },
      ...(hasSaleRatio ? [{
        name: '销售占比', type: 'line', data: saleRatioData, yAxisIndex: 1,
        smooth: true, symbol: 'circle', symbolSize: 6,
        lineStyle: { color: '#7a5cbf', width: 1.5, type: 'dotted' },
        itemStyle: { color: '#7a5cbf' },
        label: {
          show: true, fontSize: 11, color: '#7a5cbf', fontFamily: FONT,
          formatter: p => p.value === 101 ? '' : `${p.value}%`,
        },
        markLine: (() => {
          const overall = chartData.value.summary?.overall_ratio
          if (overall == null) return undefined
          return {
            silent: true,
            symbol: ['none', 'none'],
            lineStyle: { color: '#7a5cbf', type: 'dashed', width: 1.5, opacity: 0.7 },
            label: {
              formatter: `整体 ${overall.toFixed(2)}%`,
              fontFamily: FONT, fontSize: 11, color: '#7a5cbf',
            },
            data: [{ yAxis: overall > 100 ? 101 : overall }],
          }
        })(),
      }] : []),
    ],
  }
}

/** 子维度视图图表配置：柱 + 占比折线 + 累计占比（Pareto） */
function buildDimOption(items) {
  const names         = items.map(i => i.name)
  const values        = items.map(i => i.value)
  // 过滤后用实际 items 之和重新作分母，保证占比基于当前可见数据
  const total         = values.reduce((s, v) => s + v, 0) || 1
  const rawSaleRatio  = items.map(i => i.sale_ratio ?? null)
  const hasSaleRatio  = rawSaleRatio.some(v => v !== null)
  const saleRatioData = rawSaleRatio.map(v => {
    const overflow = v === null || v > 100
    return {
      value:     overflow ? 101 : v,
      itemStyle: overflow ? { color: 'transparent', borderColor: '#7a5cbf', borderWidth: 2 } : undefined,
      symbol:    overflow ? 'triangle' : undefined,
    }
  })

  const pctData   = values.map(v => total > 0 ? Math.round(v / total * 1000) / 10 : 0)
  const cumulData = []
  let running = 0
  for (const v of values) {
    running += v
    cumulData.push(total > 0 ? Math.round(running / total * 1000) / 10 : 0)
  }

  const rotate   = names.length > 8 ? 30 : 0
  const dimLabel = DIMS.find(d => d.key === groupBy.value)?.label ?? ''
  const ROW = (marker, name, val) =>
    `<div style="display:flex;justify-content:space-between;align-items:center;gap:20px;line-height:1.8">` +
    `<span>${marker}${name}</span><span style="font-weight:600">${val}</span></div>`

  return {
    backgroundColor: 'transparent',
    title: {
      text: buildChartTitle(),
      subtext: buildSubtitle(),
      left: 10, top: 16,
      textStyle: { color: '#3a3028', fontFamily: FONT, fontSize: 14, fontWeight: '600' },
      subtextStyle: { color: '#8a7a6a', fontFamily: FONT, fontSize: 12 },
    },
    toolbox: makeToolbox(true),
    legend: {
      top: 16, left: 'center', type: 'scroll',
      textStyle: { fontFamily: FONT, fontSize: 13, color: '#6b5e4e' },
      itemWidth: 18, itemHeight: 12, itemGap: 16,
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      textStyle: { fontFamily: FONT },
      formatter(params) {
        const bar   = params.find(p => p.seriesType === 'bar')
        const pct   = params.find(p => p.seriesName === '占比')
        const cumul = params.find(p => p.seriesName === '累计占比')
        const dataItem  = (chartData.value?.items || []).find(i => i.name === params[0]?.name)
        const saleRatio = dataItem?.sale_ratio ?? null
        const shipped   = dataItem?.shipped   ?? 0
        const srColor   = '#7a5cbf'
        const srMarker  = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${srColor};margin-right:4px"></span>`
        let s = `<div style="font-family:${FONT};font-size:13px;min-width:150px">`
        s += `<div style="font-weight:600;margin-bottom:4px;color:#3a3028">${params[0]?.name}</div>`
        if (bar)   s += ROW(bar.marker,   '件数',    bar.value)
        if (pct)   s += ROW(pct.marker,   '占比',    `${pct.value}%`)
        if (cumul) s += ROW(cumul.marker, '累计占比', `${cumul.value}%`)
        if (hasSaleRatio || shipped > 0 || saleRatio !== null) {
          s += ROW(srMarker, '销售占比', fmtSaleRatio(saleRatio))
        }
        s += `<div style="margin-top:6px;border-top:1px solid #e0d4c0;padding-top:4px;color:#8a7a6a;font-size:11px">右击查看产品详情</div>`
        return s + '</div>'
      },
    },
    grid: { top: 100, left: 56, right: 80, bottom: rotate ? 110 : 86 },
    dataZoom: [
      {
        type: 'slider', xAxisIndex: 0,
        bottom: rotate ? 36 : 12, height: 20,
        borderColor: '#e0d4c0', fillerColor: 'rgba(196,136,58,0.12)',
        handleStyle: { color: '#c4883a' },
        moveHandleStyle: { color: '#c4883a' },
        selectedDataBackground: { lineStyle: { color: '#c4883a' }, areaStyle: { color: '#c4883a' } },
        textStyle: { fontFamily: FONT, color: '#8a7a6a', fontSize: 11 },
        brushSelect: false,
      },
      { type: 'inside', xAxisIndex: 0 },
    ],
    xAxis: {
      type: 'category', data: names,
      axisLabel: { interval: 0, rotate, fontSize: 12, color: '#6b5e4e', fontFamily: FONT, overflow: 'truncate', width: 80 },
      axisLine: { lineStyle: { color: '#e0d4c0' } },
      axisTick: { lineStyle: { color: '#e0d4c0' } },
    },
    yAxis: [
      {
        type: 'value', name: `${dimLabel}件数`,
        nameTextStyle: { color: '#8a7a6a', fontFamily: FONT, fontSize: 11 },
        axisLabel: { color: '#8a7a6a', fontFamily: FONT, fontSize: 11 },
        splitLine: { lineStyle: { color: '#f0e8d8' } },
        axisLine: { show: true, lineStyle: { color: '#e0d4c0' } },
      },
      {
        type: 'value', min: 0, max: 102, name: '占比%',
        nameTextStyle: { color: '#8a7a6a', fontFamily: FONT, fontSize: 11 },
        axisLabel: { color: '#8a7a6a', fontFamily: FONT, fontSize: 11, formatter: '{value}%' },
        splitLine: { show: false },
        axisLine: { show: true, lineStyle: { color: '#e0d4c0' } },
      },
    ],
    series: [
      {
        name: dimLabel, type: 'bar', data: values, yAxisIndex: 0,
        itemStyle: { color: '#c4883a', borderRadius: [3, 3, 0, 0] },
        emphasis: { itemStyle: { color: '#e09050' } },
        label: { show: true, position: 'top', fontSize: 12, color: '#3a3028', fontFamily: FONT, fontWeight: 'bold' },
      },
      {
        name: '占比', type: 'line', data: pctData, yAxisIndex: 1,
        smooth: true, symbol: 'circle', symbolSize: 4,
        lineStyle: { color: '#4a8fc0', width: 1.5 },
        itemStyle: { color: '#4a8fc0' },
        label: { show: true, fontSize: 11, color: '#4a8fc0', fontFamily: FONT, formatter: p => `${p.value}%` },
      },
      {
        name: '累计占比', type: 'line', data: cumulData, yAxisIndex: 1,
        smooth: true, symbol: 'circle', symbolSize: 4,
        lineStyle: { color: '#e05050', width: 1.5, type: 'dashed' },
        itemStyle: { color: '#e05050' },
        label: { show: true, fontSize: 11, color: '#e05050', fontFamily: FONT, formatter: p => `${p.value}%` },
      },
      ...(hasSaleRatio ? [{
        name: '销售占比', type: 'line', data: saleRatioData, yAxisIndex: 1,
        smooth: true, symbol: 'circle', symbolSize: 6,
        lineStyle: { color: '#7a5cbf', width: 1.5, type: 'dotted' },
        itemStyle: { color: '#7a5cbf' },
        label: {
          show: true, fontSize: 11, color: '#7a5cbf', fontFamily: FONT,
          formatter: p => p.value === 101 ? '' : `${p.value}%`,
        },
        markLine: (() => {
          const overall = chartData.value.summary?.overall_ratio
          if (overall == null) return undefined
          return {
            silent: true,
            symbol: ['none', 'none'],
            lineStyle: { color: '#7a5cbf', type: 'dashed', width: 1.5, opacity: 0.7 },
            label: {
              formatter: `整体 ${overall.toFixed(2)}%`,
              fontFamily: FONT, fontSize: 11, color: '#7a5cbf',
            },
            data: [{ yAxis: overall > 100 ? 101 : overall }],
          }
        })(),
      }] : []),
    ],
  }
}

// ── 维度视图右击 → 切回产品视图 ──────────────────────

function drillDim(dimName) {
  const key = groupBy.value
  drillStack.value.push({
    label:                 dimName,
    type:                  'dim',
    savedGroupBy:          key,
    savedCategoryIds:      [...filters.value.categoryIds],
    savedSeriesIds:        [...filters.value.seriesIds],
    savedModelIds:         [...filters.value.modelIds],
    savedReasonCategoryIds:[...filters.value.reasonCategoryIds],
    savedReasonIds:        [...filters.value.reasonIds],
    savedShippingAliasIds: [...filters.value.shippingAliasIds],
    savedChannelNames:     [...filters.value.channelNames],
    savedProvinces:        [...filters.value.provinces],
    savedCities:           [...filters.value.cities],
  })
  _isDrilling = true
  if (key === 'reason') {
    let id = null
    for (const g of allReasonGroups.value) {
      const r = (g.reasons || []).find(r => r.name === dimName)
      if (r) { id = r.id; break }
    }
    if (id != null) filters.value.reasonIds = [id]
  } else if (key === 'shipping_alias') {
    const alias = allShippingAliases.value.find(a => a.name === dimName)
    if (alias) filters.value.shippingAliasIds = [alias.id]
  } else if (key === 'channel') {
    filters.value.channelNames = [dimName]
  } else if (key === 'province') {
    filters.value.provinces = [dimName]
  }
  groupBy.value = null
  nextTick(() => { _isDrilling = false })
}

// ── 产品视图下钻 ───────────────────────────────────

function drillDown(label) {
  const level = effectiveProductLevel.value
  if (level === 'model') return

  // 保存当前 filter 快照
  drillStack.value.push({
    label,
    savedCategoryIds: [...filters.value.categoryIds],
    savedSeriesIds:   [...filters.value.seriesIds],
    savedModelIds:    [...filters.value.modelIds],
  })

  _isDrilling = true
  if (level === 'category') {
    const cat = categoryTree.value.find(c => c.name === label)
    if (!cat) { drillStack.value.pop(); _isDrilling = false; return }
    filters.value.categoryIds = [cat.id]
    filters.value.seriesIds   = []
    filters.value.modelIds    = []
  } else if (level === 'series') {
    let seriesId = null
    for (const c of categoryTree.value) {
      const s = (c.series || []).find(s => s.code === label)
      if (s) { seriesId = s.id; break }
    }
    if (!seriesId) { drillStack.value.pop(); _isDrilling = false; return }
    filters.value.seriesIds = [seriesId]
    filters.value.modelIds  = []
  }
  nextTick(() => { _isDrilling = false })
}

function drillBack(idx) {
  const snap = drillStack.value[idx]
  _isDrilling = true
  filters.value.categoryIds = snap.savedCategoryIds
  filters.value.seriesIds   = snap.savedSeriesIds
  filters.value.modelIds    = snap.savedModelIds
  if (snap.type === 'dim') {
    filters.value.reasonCategoryIds  = snap.savedReasonCategoryIds
    filters.value.reasonIds          = snap.savedReasonIds
    filters.value.shippingAliasIds   = snap.savedShippingAliasIds
    filters.value.channelNames       = snap.savedChannelNames
    filters.value.provinces          = snap.savedProvinces
    filters.value.cities             = snap.savedCities
    groupBy.value = snap.savedGroupBy
  }
  drillStack.value = drillStack.value.slice(0, idx)
  nextTick(() => { _isDrilling = false })
}

// ── 其他操作 ──────────────────────────────────────

function toggleSection(key) { sections[key] = !sections[key] }

// Tab 可取消（再次点击 = 回到产品视图）
function selectDim(key) { groupBy.value = groupBy.value === key ? null : key }

function onCategoryChange() { filters.value.seriesIds = []; filters.value.modelIds = [] }
function onSeriesChange()   { filters.value.modelIds = [] }
function onReasonCatChange() { filters.value.reasonIds = [] }
function onProvinceChange()  { filters.value.cities = [] }

function resetFilters() {
  drillStack.value = []
  groupBy.value    = null
  Object.assign(filters.value, {
    dateRange:            (() => { const s = new Date(); s.setMonth(s.getMonth() - 1); return [s, new Date()] })(),
    maxDaysSincePurchase: 1825,
    categoryIds: [], seriesIds: [], modelIds: [],
    reasonCategoryIds: [], reasonIds: [], shippingAliasIds: [],
    channelNames: [], provinces: [], cities: [],
  })
}

// 查询按钮：手动触发图表刷新（时间筛选变更后必须通过此按钮）
async function handleQuery() {
  clearTimeout(_chartTimer)
  _chartCache.clear()
  await loadChartData()
}

async function refresh() {
  _chartCache.clear()
  await Promise.all([loadCrossFilterOptions(), loadChartData()])
}

defineExpose({ refresh })
</script>

<template>
  <div class="dashboard-root">

    <!-- ── 左侧筛选面板 ──────────────────────────── -->
    <aside class="filter-panel" :class="{ 'is-collapsed': filterCollapsed }">

      <!-- 查询 + 设置 -->
      <div class="panel-top-btns">
        <button class="btn-query" :disabled="loadingChart" @click="handleQuery">
          {{ loadingChart ? '查询中…' : '查询' }}
        </button>
        <button class="btn-settings" title="分组">
          <el-icon><Setting /></el-icon>分组
        </button>
      </div>

      <!-- ▌时间选择 -->
      <div class="section-group">
        <div class="section-hd" @click="toggleSection('time')">
          <span class="section-title">时间选择</span>
          <el-icon class="section-chevron" :class="{ 'is-closed': !sections.time }"><ArrowDown /></el-icon>
        </div>
        <div class="section-bd" :class="{ 'is-closed': !sections.time }">
          <div class="section-bd-inner">
            <el-date-picker
              v-model="filters.dateRange"
              type="daterange" range-separator="~"
              start-placeholder="开始日期" end-placeholder="结束日期"
              size="default" style="width:100%"
              :shortcuts="DATE_SHORTCUTS"
            />
            <div class="field-row">
              <div class="field-label">售后间隔上限</div>
              <div class="days-input-row">
                <el-input-number
                  v-model="filters.maxDaysSincePurchase"
                  :min="1" :max="9999" :step="1"
                  controls-position="right" placeholder="不限"
                  size="default" style="flex:1"
                />
                <span class="days-unit">天</span>
                <button
                  class="btn-clear-days"
                  :class="{ 'is-active': filters.maxDaysSincePurchase == null }"
                  @click="filters.maxDaysSincePurchase = null"
                >不限</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ▌产品选择 -->
      <div class="section-group">
        <div class="section-hd" @click="toggleSection('product')">
          <span class="section-title">产品选择</span>
          <el-icon class="section-chevron" :class="{ 'is-closed': !sections.product }"><ArrowDown /></el-icon>
        </div>
        <div class="section-bd" :class="{ 'is-closed': !sections.product }">
          <div class="section-bd-inner">
            <div class="field-row">
              <div class="field-label">产品品类</div>
              <el-select v-model="filters.categoryIds" placeholder="全部品类"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%"
                @change="onCategoryChange">
                <el-option v-for="opt in categoryOpts" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </div>
            <div class="field-row">
              <div class="field-label">产品系列</div>
              <el-select v-model="filters.seriesIds" placeholder="全部系列"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%"
                :disabled="!seriesEnabled" @change="onSeriesChange">
                <el-option v-for="opt in seriesOpts" :key="opt.value" :label="opt.label" :value="opt.value">
                  <span class="opt-main">{{ opt.label }}</span>
                  <span v-if="opt.sub" class="opt-sub">{{ opt.sub }}</span>
                </el-option>
              </el-select>
            </div>
            <div class="field-row">
              <div class="field-label">产品型号</div>
              <el-select v-model="filters.modelIds" placeholder="全部型号"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%"
                :disabled="!modelEnabled">
                <el-option v-for="opt in modelOpts" :key="opt.value" :label="opt.label" :value="opt.value">
                  <span class="opt-main">{{ opt.label }}</span>
                  <span v-if="opt.sub" class="opt-sub">{{ opt.sub }}</span>
                </el-option>
              </el-select>
            </div>
          </div>
        </div>
      </div>

      <!-- ▌售后原因选择 -->
      <div class="section-group">
        <div class="section-hd" @click="toggleSection('reason')">
          <span class="section-title">售后原因选择</span>
          <el-icon class="section-chevron" :class="{ 'is-closed': !sections.reason }"><ArrowDown /></el-icon>
        </div>
        <div class="section-bd" :class="{ 'is-closed': !sections.reason }">
          <div class="section-bd-inner">
            <div class="field-row">
              <div class="field-label">原因分类</div>
              <el-select v-model="filters.reasonCategoryIds" placeholder="全部分类"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%"
                :loading="loadingOpts" @change="onReasonCatChange">
                <el-option v-for="opt in reasonCatOpts" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </div>
            <div class="field-row">
              <div class="field-label">具体原因</div>
              <el-select v-model="filters.reasonIds" placeholder="全部原因"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%"
                :disabled="!reasonEnabled" :loading="loadingOpts">
                <el-option v-for="opt in reasonOpts" :key="opt.value" :label="opt.label" :value="opt.value">
                  <span class="opt-main">{{ opt.label }}</span>
                  <span v-if="opt.sub" class="opt-sub">{{ opt.sub }}</span>
                </el-option>
              </el-select>
            </div>
          </div>
        </div>
      </div>

      <!-- ▌发货物料选择 -->
      <div class="section-group">
        <div class="section-hd" @click="toggleSection('shipping')">
          <span class="section-title">发货物料选择</span>
          <el-icon class="section-chevron" :class="{ 'is-closed': !sections.shipping }"><ArrowDown /></el-icon>
        </div>
        <div class="section-bd" :class="{ 'is-closed': !sections.shipping }">
          <div class="section-bd-inner">
            <div class="field-row">
              <div class="field-label">发货物料简称</div>
              <el-select v-model="filters.shippingAliasIds" placeholder="全部发货物料"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%" :loading="loadingOpts">
                <el-option v-for="opt in shippingAliasOpts" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </div>
          </div>
        </div>
      </div>

      <!-- ▌渠道选择 -->
      <div class="section-group">
        <div class="section-hd" @click="toggleSection('channel')">
          <span class="section-title">渠道选择</span>
          <el-icon class="section-chevron" :class="{ 'is-closed': !sections.channel }"><ArrowDown /></el-icon>
        </div>
        <div class="section-bd" :class="{ 'is-closed': !sections.channel }">
          <div class="section-bd-inner">
            <div class="field-row">
              <div class="field-label">渠道</div>
              <el-select v-model="filters.channelNames" placeholder="全部渠道"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%" :loading="loadingOpts">
                <el-option v-for="opt in channelOpts" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </div>
          </div>
        </div>
      </div>

      <!-- ▌地域选择 -->
      <div class="section-group">
        <div class="section-hd" @click="toggleSection('region')">
          <span class="section-title">地域选择</span>
          <el-icon class="section-chevron" :class="{ 'is-closed': !sections.region }"><ArrowDown /></el-icon>
        </div>
        <div class="section-bd" :class="{ 'is-closed': !sections.region }">
          <div class="section-bd-inner">
            <div class="field-row">
              <div class="field-label">省份</div>
              <el-select v-model="filters.provinces" placeholder="全部省份"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%"
                :loading="loadingOpts" @change="onProvinceChange">
                <el-option v-for="opt in provinceOpts" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </div>
            <div class="field-row">
              <div class="field-label">城市</div>
              <el-select v-model="filters.cities" placeholder="全部城市"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%"
                :disabled="!cityEnabled" :loading="loadingOpts">
                <el-option v-for="opt in cityOpts" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </div>
          </div>
        </div>
      </div>

      <button class="btn-reset" @click="resetFilters">重置筛选</button>

    </aside>

    <!-- ── 右侧内容区 ──────────────────────────────── -->
    <div class="content-panel">

      <!-- 顶部工具栏：左=面包屑 / 中=空 / 右=空 -->
      <div class="chart-toolbar">
        <div class="ct-left">
          <button class="btn-collapse" :title="filterCollapsed ? '展开筛选' : '收起筛选'" @click="filterCollapsed = !filterCollapsed">
            <el-icon><ArrowLeft v-if="!filterCollapsed" /><ArrowRight v-else /></el-icon>
          </button>
          <div class="drill-breadcrumb">
            <span :class="drillStack.length ? 'bc-item bc-link' : 'bc-item bc-current'" @click="drillStack.length ? drillBack(0) : null">全部</span>
            <template v-for="(entry, i) in drillStack" :key="i">
              <span class="bc-sep">/</span>
              <span v-if="i < drillStack.length - 1" class="bc-item bc-link" @click="drillBack(i + 1)">{{ entry.label }}</span>
              <span v-else class="bc-item bc-current">{{ entry.label }}</span>
            </template>
          </div>
        </div>
        <div class="ct-center">
          <div class="footer-dims">
            <button
              v-for="dim in DIMS"
              :key="dim.key"
              class="gb-btn"
              :class="{ active: groupBy === dim.key }"
              @click="selectDim(dim.key)"
            >
              <img :src="dim.icon" class="gb-icon" />
              <span class="gb-label">{{ dim.label }}</span>
            </button>
          </div>
        </div>
        <div class="ct-right">
          <el-checkbox v-model="hideNoSales" class="hide-no-sales-check">隐藏当前未销售产品数据</el-checkbox>
          <button class="btn-view-data">查看数据</button>
        </div>
      </div>

      <!-- 图表 -->
      <div v-loading="loadingChart" class="chart-wrap">
        <div v-if="!loadingChart && !chartData?.items?.length" class="chart-empty">暂无数据</div>
        <div ref="chartEl" class="chart-canvas"></div>
      </div>


    </div>

  </div>
</template>

<style scoped>
.dashboard-root {
  flex: 1; min-height: 0;
  display: flex; overflow: hidden;
  font-family: var(--font-family);
  padding: 5px; gap: 4px;
}

/* ── 筛选面板顶部按钮 ──────────────────────────── */
.panel-top-btns { display: flex; gap: 6px; flex-shrink: 0; }
.btn-query {
  flex: 1; height: 36px;
  border: none; border-radius: 8px;
  background: var(--accent); color: #fff;
  font-size: 13px; font-family: var(--font-family);
  cursor: pointer; transition: background 0.15s;
}
.btn-query:hover:not(:disabled) { background: var(--accent-hover); }
.btn-query:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-settings {
  height: 36px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 8px;
  background: var(--bg-card); color: var(--text-muted);
  font-size: 12px; font-family: var(--font-family);
  cursor: pointer; display: flex; align-items: center; gap: 4px;
  transition: all 0.15s; white-space: nowrap;
}
.btn-settings:hover { border-color: var(--accent); color: var(--accent); }

/* ── 筛选面板 ─────────────────────────────────── */
.filter-panel {
  width: 270px; flex-shrink: 0;
  background: transparent;
  overflow-y: auto; overflow-x: hidden;
  padding: 5px;
  display: flex; flex-direction: column; gap: 5px;
  transition: width 0.22s ease, opacity 0.22s ease, padding 0.22s ease;
}
.filter-panel.is-collapsed {
  width: 0; padding: 0; opacity: 0; pointer-events: none;
}
.filter-panel::-webkit-scrollbar { width: 4px; }
.filter-panel::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* ── 区块卡片 ────────────────────────────────── */
.section-group {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 9px; overflow: hidden; flex-shrink: 0;
}
.section-hd {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; cursor: pointer; user-select: none; transition: background 0.15s;
}
.section-hd:hover { background: rgba(196,136,58,0.04); }
.section-hd:hover .section-title { color: var(--accent); }
.section-title { font-size: 12px; font-weight: 600; color: var(--text-primary); letter-spacing: 0.02em; transition: color 0.15s; }
.section-chevron { font-size: 11px; color: var(--text-muted); transition: transform 0.22s ease; flex-shrink: 0; }
.section-chevron.is-closed { transform: rotate(-90deg); }
.section-bd { max-height: 600px; overflow: hidden; transition: max-height 0.22s ease; border-top: 1px solid var(--border); }
.section-bd.is-closed { max-height: 0; border-top: none; }
.section-bd-inner { padding: 12px; display: flex; flex-direction: column; gap: 12px; }

.field-row { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 11px; color: var(--text-muted); letter-spacing: 0.02em; }
.opt-main  { font-size: 12px; color: var(--text-primary); }
.opt-sub   { font-size: 11px; color: var(--text-muted); margin-left: 6px; }

/* ── 间隔天数 ──────────────────────────────────── */
.days-input-row { display: flex; align-items: center; gap: 6px; }
.days-unit { font-size: 12px; color: var(--text-muted); flex-shrink: 0; }
.btn-clear-days {
  padding: 0 10px; height: 32px;
  border: 1px solid var(--border); border-radius: 8px;
  background: transparent; color: var(--text-muted);
  font-size: 12px; font-family: var(--font-family);
  cursor: pointer; transition: all 0.15s; white-space: nowrap; flex-shrink: 0;
}
.btn-clear-days:hover { border-color: var(--accent); color: var(--accent); }
.btn-clear-days.is-active { background: #fff7ed; border-color: var(--accent); color: var(--accent); font-weight: 600; }

/* ── 重置按钮 ──────────────────────────────────── */
.btn-reset {
  width: 100%; padding: 9px;
  border: 1px solid var(--border); border-radius: 8px;
  background: transparent; color: var(--text-muted);
  font-size: 12px; font-family: var(--font-family);
  cursor: pointer; transition: all 0.15s; flex-shrink: 0;
}
.btn-reset:hover { border-color: var(--accent); color: var(--accent); }

/* ── 右侧内容区 ───────────────────────────────── */
.content-panel { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: 5px; overflow: hidden; padding-top: 5px; }

/* 顶部工具栏 */
.chart-toolbar {
  height: 36px;
  flex-shrink: 0;
  display: flex; align-items: center;
}
.ct-left   { flex: 1; display: flex; align-items: center; }
.ct-center { display: flex; align-items: center; gap: 3px; }
.ct-right  { flex: 1; display: flex; align-items: center; justify-content: flex-end; }
.btn-view-data {
  height: 30px; padding: 0 14px;
  border: 1px solid var(--border); border-radius: 8px;
  background: var(--bg-card); color: var(--text-muted);
  font-size: 12px; font-family: var(--font-family);
  cursor: pointer; transition: all 0.15s;
}
.btn-view-data:hover { border-color: var(--accent); color: var(--accent); }
.hide-no-sales-check {
  margin-right: 10px;
  font-size: 12px;
  color: var(--text-muted);
}
:deep(.hide-no-sales-check .el-checkbox__label) {
  font-size: 12px;
  color: var(--text-muted);
  font-family: var(--font-family);
}
:deep(.hide-no-sales-check .el-checkbox__inner) {
  border-radius: 4px;
}

/* 折叠按钮 */
.btn-collapse {
  flex-shrink: 0; width: 24px; height: 24px; margin-right: 6px;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg-card); color: var(--text-muted);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.15s;
}
.btn-collapse:hover { border-color: var(--accent); color: var(--accent); }

/* 面包屑 */
.drill-breadcrumb { display: flex; align-items: center; gap: 4px; font-size: 14px; }
.bc-sep  { color: #b0a090; }
.bc-item { padding: 2px 4px; border-radius: 4px; white-space: nowrap; }
.bc-link { color: #3a7bc8; cursor: pointer; }
.bc-link:hover { text-decoration: underline; background: rgba(58,123,200,0.08); }
.bc-current { color: #3a3028; font-weight: 600; }

/* 图表区 */
.chart-wrap { flex: 1; min-height: 0; background: var(--bg-card); border: 1px solid var(--border); border-radius: 9px; overflow: hidden; position: relative; }
.chart-canvas { width: 100%; height: 100%; }
.chart-empty {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; color: var(--text-muted);
}

/* 底部维度选择 */
.chart-footer {
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between;
  padding: 2px 0;
}
.footer-placeholder { flex: 1; }
.footer-dims { display: flex; gap: 4px; }
.gb-btn {
  display: flex; flex-direction: row; align-items: center; justify-content: center;
  gap: 6px; padding: 6px 18px;
  border: none; background: transparent; border-radius: 10px; cursor: pointer;
  transition: background 0.15s;
}
.gb-btn:hover { background: var(--border); }
.gb-btn.active { background: color-mix(in srgb, #c4883a 12%, transparent); }
.gb-icon  { width: 16px; height: 16px; object-fit: contain; flex-shrink: 0; opacity: 0.6; transition: opacity 0.15s; }
.gb-btn:hover .gb-icon  { opacity: 1; }
.gb-btn.active .gb-icon { opacity: 1; }
.gb-label { font-size: 15px; color: #2c2420; white-space: nowrap; transition: color 0.15s; }
.gb-btn:hover .gb-label { color: #000; }
.gb-btn.active .gb-label { color: #c4883a; font-weight: 500; }

</style>
