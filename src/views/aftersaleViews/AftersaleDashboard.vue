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
import AftersaleCasesDrawer from '@/components/aftersale/AftersaleCasesDrawer.vue'

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
// 原因 Tab 默认进入一级分类视图（reason_category），右击可下钻至具体原因（reason）
const DIMS = [
  { key: 'reason_category', label: '原因', icon: iconReason   },
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
  maxDaysSincePurchase: null, // 售后间隔上限（天），null = 不限
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

const loadingOpts         = ref(false)
const filterCollapsed     = ref(false)
// 无同期发货数据处理模式：all=全显示 | hide=隐藏但不影响占比计算 | exclude=从所有计算中剔除
const noSalesMode         = ref('all')
// 原因维度跳过分类级别，直接进入具体原因视图
const skipReasonCategory  = ref(false)
let   _filterTimer    = null
let   _chartTimer     = null
// 上次图表刷新时的非时间筛选快照（用于判断是否需要自动刷新图表）
let   _lastChartSig   = ''
let   _chartCache  = new Map()       // key: groupBy值('product'/'reason'/...)，value: 接口返回 data

// 图表状态
const groupBy      = ref(null)    // null=产品视图（默认），非null=子维度
const chartData    = ref(null)
const loadingChart = ref(false)
const chartEl      = ref(null)
let   chartInst    = null

// 数据抽屉
const casesDrawer       = ref(false)
const casesDrawerFilter = ref({})
const casesDrawerTitle  = ref('售后数据')

// 产品维度下钻面包屑：[{ label, savedCategoryIds, savedSeriesIds, savedModelIds, savedChartData }]
const drillStack = ref([])
// 防止 drillDown/drillBack 修改 filters 时触发清栈
let   _isDrilling    = false
// 下钻返回时暂存待恢复的图表快照，loadChartData 命中后直接渲染，跳过 API 请求
let   _drillBackData = null

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
  _lastChartSig = _nonTimeSig()
  initChart()  // 先挂载 ResizeObserver，等容器就绪后自动初始化
  await Promise.all([loadStaticOptions(), loadCrossFilterOptions()])
  await loadChartData()
})

onBeforeUnmount(() => {
  chartInst?.dispose()
  chartInst = null
})

// ── Watch ─────────────────────────────────────────

/** 当前非时间筛选的序列化快照（用于判断图表是否需要自动刷新） */
function _nonTimeSig() {
  const f = filters.value
  return JSON.stringify([
    f.categoryIds, f.seriesIds, f.modelIds,
    f.reasonCategoryIds, f.reasonIds, f.shippingAliasIds,
    f.channelNames, f.provinces, f.cities,
  ])
}

// 合并两个 watch：任意筛选 → 联动选项（始终）；非时间筛选 → 图表（自动）
// 两个定时器共用同一个 watch 回调，避免同一次筛选变化并发触发两个独立 watch
watch(filters, () => {
  _chartCache.clear()
  if (!_isDrilling) _drillBackData = null  // 手动筛选时取消待恢复的下钻快照
  clearTimeout(_filterTimer)
  clearTimeout(_chartTimer)
  _filterTimer = setTimeout(() => loadCrossFilterOptions(), 300)
  // 仅非时间筛选变化时自动刷新图表（时间/间隔类需手动点查询）
  const sig = _nonTimeSig()
  if (sig !== _lastChartSig) {
    _lastChartSig = sig
    _chartTimer = setTimeout(() => loadChartData(), 300)
  }
}, { deep: true })

// 产品筛选手动变化时清空下钻栈（drillDown/drillBack 期间用 _isDrilling 跳过）
watch(
  () => [filters.value.categoryIds, filters.value.seriesIds, filters.value.modelIds],
  () => { if (!_isDrilling) drillStack.value = [] },
  { deep: true }
)

// 维度 Tab 切换 → 刷新图表
watch(groupBy, () => {
  if (!_isDrilling) _drillBackData = null  // 手动切 Tab 时取消待恢复的下钻快照
  loadChartData()
})

// 无同期发货模式切换 → 清除缓存并重新请求数据
// exclude 模式涉及后端系列过滤，必须重新请求；hide/all 切换也清缓存保证数据一致
watch(noSalesMode, () => {
  _chartCache.clear()
  loadChartData()
})

// 产品层级变化时：若处于"隐藏"模式但已不在系列层级，自动回到"所有数据"
// hide 模式只对系列层级有意义（隐藏本期无销售的系列），切到品类/型号层自动重置
watch(effectiveProductLevel, (newLevel) => {
  if (noSalesMode.value === 'hide' && newLevel !== 'series') {
    noSalesMode.value = 'all'
  }
})

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
    date_start:               start ? formatDate(start) : undefined,
    date_end:                 end   ? formatDate(end)   : undefined,
    max_days_since_purchase:  filters.value.maxDaysSincePurchase ?? undefined,
    category_ids:             filters.value.categoryIds,
    series_ids:               filters.value.seriesIds,
    model_ids:                filters.value.modelIds,
    reason_ids:               filters.value.reasonIds,
    reason_category_ids:      filters.value.reasonCategoryIds,
    shipping_alias_ids:       filters.value.shippingAliasIds,
    channel_names:            filters.value.channelNames,
    provinces:                filters.value.provinces,
    cities:                   filters.value.cities,
    // exclude 模式：后端剔除同期无发货的系列所属工单
    exclude_no_sales_series:  noSalesMode.value === 'exclude',
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

  // 下钻返回：直接使用快照，填充缓存后跳过 API 请求
  if (_drillBackData !== null) {
    _chartCache.set(cacheKey, _drillBackData)
    chartData.value = _drillBackData
    _drillBackData  = null
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
    } else {
      console.error('[Chart] API error:', res.message)
    }
  } catch (err) {
    console.error('[Chart] Request failed:', err)
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

  // reason 和 reason_category 都属于原因维度
  const _dimKeyLabel = groupBy.value === 'reason' ? '原因' : (DIMS.find(d => d.key === groupBy.value)?.label ?? '')
  const dimLabel = groupBy.value ? _dimKeyLabel + '分布' : '产品分布'
  const gby = groupBy.value
  let parts
  if (gby === 'channel')                     parts = [channelDesc(), prodDesc(), reasonDesc(), regionDesc()]
  else if (gby === 'province')              parts = [regionDesc(), prodDesc(), reasonDesc(), channelDesc()]
  else if (gby === 'reason' || gby === 'reason_category') parts = [reasonDesc(), prodDesc(), channelDesc(), regionDesc()]
  else                                       parts = [prodDesc(), reasonDesc(), channelDesc(), regionDesc()]

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

function _createChartInst() {
  if (chartInst) return
  const el = chartEl.value
  if (!el?.offsetWidth || !el?.offsetHeight) return
  chartInst = echarts.init(el, null, { renderer: 'canvas' })
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
}

function initChart() {
  if (!chartEl.value) return
  // 用 ResizeObserver 等容器有实际尺寸后再初始化，避免 ECharts "0 width/height" 警告
  const ro = new ResizeObserver(() => {
    if (chartInst) { chartInst.resize(); return }
    _createChartInst()
  })
  ro.observe(chartEl.value)
  // Safari 保底：ResizeObserver 在 Safari 中可能首次以 0 尺寸触发后不再触发
  requestAnimationFrame(() => _createChartInst())
  setTimeout(() => _createChartInst(), 300)
}

function renderChart() {
  if (!chartInst || !chartData.value) return
  let items = chartData.value.items || []
  // 仅产品视图下过滤"无同期发货"数据（维度视图 sale_ratio 本就全为 null，不适用此逻辑）
  // hide 模式：从图表中隐藏，但占比计算仍基于全量（保留 allItems 传入）
  // exclude 模式：从图表和所有占比计算中完全剔除
  const allItems = items.slice()  // 全量快照（hide 模式下用于占比分母）
  if (noSalesMode.value !== 'all' && groupBy.value === null) {
    items = items.filter(i => i.sale_ratio !== null && i.sale_ratio !== undefined)
  }
  if (!items.length) { chartInst.clear(); return }

  if (groupBy.value === null) {
    // 产品视图：柱状图 + 占比折线 + 累计占比（Pareto）
    // hide 模式：传 allItems 作为占比分母；exclude 模式：传 null（用过滤后数据计算）
    const baseItems = noSalesMode.value === 'hide' ? allItems : null
    chartInst.setOption(buildProductOption(items, baseItems), true)
  } else {
    // 子维度视图：标准柱状图
    chartInst.setOption(buildDimOption(items), true)
  }
}

/** 产品视图图表配置：柱 + 占比折线 + 累计折线，右击可下钻
 * baseItems: hide 模式下传全量数据作为占比分母；null 则用 items 自身 */
function buildProductOption(items, baseItems = null) {
  const names  = items.map(i => i.name)
  const values = items.map(i => i.value)
  // baseItems 非 null 时（hide 模式）：占比分母基于全量；否则基于当前可见 items
  const totalBase = baseItems ?? items
  const total  = totalBase.map(i => i.value).reduce((s, v) => s + v, 0) || 1

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
          formatter: p => p.value === 101 ? '' : `${(+p.value).toFixed(2)}%`,
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
  // reason 和 reason_category 都属于原因维度
  const dimLabel = groupBy.value === 'reason' ? '原因' : (DIMS.find(d => d.key === groupBy.value)?.label ?? '')
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
        const xName = params[0]?.name ?? ''
        let s = `<div style="font-family:${FONT};font-size:13px;min-width:150px">`
        s += `<div style="font-weight:600;margin-bottom:4px;color:#3a3028">${xName}</div>`
        if (bar)   s += ROW(bar.marker,   '件数',    bar.value)
        if (pct)   s += ROW(pct.marker,   '占比',    `${pct.value}%`)
        if (cumul) s += ROW(cumul.marker, '累计占比', `${cumul.value}%`)
        if (hasSaleRatio || shipped > 0 || saleRatio !== null) {
          s += ROW(srMarker, '销售占比', fmtSaleRatio(saleRatio))
        }
        const drillHint = groupBy.value === 'reason_category' ? '右击查看具体原因' : '右击查看产品详情'
        s += `<div style="margin-top:6px;border-top:1px solid #e0d4c0;padding-top:4px;color:#8a7a6a;font-size:11px">${drillHint}</div>`
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
          formatter: p => p.value === 101 ? '' : `${(+p.value).toFixed(2)}%`,
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
    savedChartData:        chartData.value,
  })
  _isDrilling = true
  if (key === 'reason_category') {
    // 一级分类下钻：筛选该分类 → 切换到具体原因视图（reason）
    const group = allReasonGroups.value.find(g => g.category_name === dimName)
    if (group) filters.value.reasonCategoryIds = [group.category_id]
    groupBy.value = 'reason'
  } else if (key === 'reason') {
    // 具体原因下钻：筛选该原因 → 切到产品视图
    let id = null
    for (const g of allReasonGroups.value) {
      const r = (g.reasons || []).find(r => r.name === dimName)
      if (r) { id = r.id; break }
    }
    if (id != null) filters.value.reasonIds = [id]
    groupBy.value = null
  } else if (key === 'shipping_alias') {
    const alias = allShippingAliases.value.find(a => a.name === dimName)
    if (alias) filters.value.shippingAliasIds = [alias.id]
    groupBy.value = null
  } else if (key === 'channel') {
    filters.value.channelNames = [dimName]
    groupBy.value = null
  } else if (key === 'province') {
    filters.value.provinces = [dimName]
    groupBy.value = null
  }
  nextTick(() => { _isDrilling = false })
}

// ── 产品视图下钻 ───────────────────────────────────

function drillDown(label) {
  const level = effectiveProductLevel.value
  if (level === 'model') return

  // 保存当前 filter 快照与图表数据快照（用于返回时直接恢复，跳过 API 请求）
  drillStack.value.push({
    label,
    savedCategoryIds: [...filters.value.categoryIds],
    savedSeriesIds:   [...filters.value.seriesIds],
    savedModelIds:    [...filters.value.modelIds],
    savedChartData:   chartData.value,
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
    // 必须在当前已选品类范围内查找，避免跨品类同名系列拿到错误 id
    const selectedCatIds = new Set(filters.value.categoryIds)
    for (const c of categoryTree.value) {
      if (selectedCatIds.size > 0 && !selectedCatIds.has(c.id)) continue
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
  _isDrilling    = true
  _drillBackData = snap.savedChartData ?? null  // 暂存快照，loadChartData 命中后跳过 API 请求
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
  } else {
    // 产品下钻返回：强制回到产品视图（快照是产品数据，维度视图须同步重置）
    groupBy.value = null
  }
  drillStack.value = drillStack.value.slice(0, idx)
  nextTick(() => { _isDrilling = false })
}

// ── 其他操作 ──────────────────────────────────────

function toggleSection(key) { sections[key] = !sections[key] }

// Tab 可取消（再次点击 = 回到产品视图）
// 原因 Tab：reason_category 和 reason 都属于原因维度，均视为激活态；再次点击回到产品视图
// skipReasonCategory 勾选时：原因 Tab 直接进入具体原因（reason）视图，跳过分类层级
function selectDim(key) {
  if (key === 'reason_category') {
    if (groupBy.value === 'reason_category' || groupBy.value === 'reason') {
      groupBy.value = null
    } else {
      groupBy.value = skipReasonCategory.value ? 'reason' : 'reason_category'
    }
  } else {
    groupBy.value = groupBy.value === key ? null : key
  }
}

function onCategoryChange() { filters.value.seriesIds = []; filters.value.modelIds = [] }
function onSeriesChange()   { filters.value.modelIds = [] }
function onReasonCatChange() { filters.value.reasonIds = [] }
function onProvinceChange()  { filters.value.cities = [] }

function resetFilters() {
  drillStack.value = []
  groupBy.value    = null
  Object.assign(filters.value, {
    dateRange:            (() => { const s = new Date(); s.setMonth(s.getMonth() - 1); return [s, new Date()] })(),
    maxDaysSincePurchase: null,
    categoryIds: [], seriesIds: [], modelIds: [],
    reasonCategoryIds: [], reasonIds: [], shippingAliasIds: [],
    channelNames: [], provinces: [], cities: [],
  })
}

// ── 数据抽屉 ──────────────────────────────────────

/** 右上角「查看数据」按钮：将当前图表所有筛选条件完整传递给 cases 列表 */
function openCasesDrawer() {
  const [start, end] = filters.value.dateRange || []
  const csv = arr => arr.length ? arr.join(',') : undefined
  casesDrawerFilter.value = {
    date_start:               start ? formatDate(start) : undefined,
    date_end:                 end   ? formatDate(end)   : undefined,
    max_days_since_purchase:  filters.value.maxDaysSincePurchase ?? undefined,
    model_ids:                csv(filters.value.modelIds),
    series_ids:               csv(filters.value.seriesIds),
    category_ids:             csv(filters.value.categoryIds),
    reason_ids:               csv(filters.value.reasonIds),
    reason_category_ids:      csv(filters.value.reasonCategoryIds),
    shipping_alias_ids:       csv(filters.value.shippingAliasIds),
    channel_names:            csv(filters.value.channelNames),
    provinces:                csv(filters.value.provinces),
    cities:                   csv(filters.value.cities),
  }
  casesDrawerTitle.value = buildDrawerTitle()
  casesDrawer.value = true
}

/** 根据当前筛选状态构建抽屉标题 */
function buildDrawerTitle() {
  const parts = []
  // 产品：型号 > 系列 > 品类
  if (filters.value.modelIds.length === 1) {
    outer: for (const c of categoryTree.value) for (const s of c.series || []) {
      const m = (s.models || []).find(m => m.id === filters.value.modelIds[0])
      if (m) { parts.push(m.model_code); break outer }
    }
  } else if (filters.value.modelIds.length > 1) {
    parts.push('多个型号')
  } else if (filters.value.seriesIds.length === 1) {
    for (const c of categoryTree.value) {
      const s = (c.series || []).find(s => s.id === filters.value.seriesIds[0])
      if (s) { parts.push(s.code); break }
    }
  } else if (filters.value.seriesIds.length > 1) {
    parts.push('多个系列')
  } else if (filters.value.categoryIds.length === 1) {
    const cat = categoryTree.value.find(c => c.id === filters.value.categoryIds[0])
    if (cat) parts.push(cat.name)
  } else if (filters.value.categoryIds.length > 1) {
    parts.push('多个品类')
  }
  // 原因：具体原因 > 原因分类
  if (filters.value.reasonIds.length === 1) {
    for (const g of allReasonGroups.value) {
      const r = (g.reasons || []).find(r => r.id === filters.value.reasonIds[0])
      if (r) { parts.push(r.name); break }
    }
  } else if (filters.value.reasonIds.length > 1) {
    parts.push('多个原因')
  } else if (filters.value.reasonCategoryIds.length === 1) {
    const grp = allReasonGroups.value.find(g => g.category_id === filters.value.reasonCategoryIds[0])
    if (grp) parts.push(grp.category_name)
  } else if (filters.value.reasonCategoryIds.length > 1) {
    parts.push('多个原因分类')
  }
  // 发货物料
  if (filters.value.shippingAliasIds.length === 1) {
    const a = allShippingAliases.value.find(a => a.id === filters.value.shippingAliasIds[0])
    if (a) parts.push(a.name)
  } else if (filters.value.shippingAliasIds.length > 1) {
    parts.push('多个物料')
  }
  // 渠道
  if (filters.value.channelNames.length === 1) parts.push(filters.value.channelNames[0])
  else if (filters.value.channelNames.length > 1) parts.push('多个渠道')
  // 地域
  const regionSrc = filters.value.cities.length ? filters.value.cities : filters.value.provinces
  if (regionSrc.length === 1) parts.push(regionSrc[0])
  else if (regionSrc.length > 1) parts.push('多个区域')
  // 日期
  const [start, end] = filters.value.dateRange || []
  const dateStr = start && end ? `${formatDate(start)} ~ ${formatDate(end)}` : ''
  const desc = parts.join(' · ')
  if (desc && dateStr) return `售后数据 · ${desc} · ${dateStr}`
  if (desc) return `售后数据 · ${desc}`
  if (dateStr) return `售后数据 · ${dateStr}`
  return '售后数据'
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
              :class="{ active: groupBy === dim.key || (dim.key === 'reason_category' && groupBy === 'reason') }"
              @click="selectDim(dim.key)"
            >
              <img :src="dim.icon" class="gb-icon" />
              <span class="gb-label">{{ dim.label }}</span>
            </button>
          </div>
        </div>
        <div class="ct-right">
          <button class="btn-view-data" @click="openCasesDrawer">查看数据</button>
        </div>
      </div>

      <!-- 图表 -->
      <div v-loading="loadingChart" class="chart-wrap">
        <div v-if="!loadingChart && !chartData?.items?.length" class="chart-empty">暂无数据</div>
        <div ref="chartEl" class="chart-canvas"></div>
      </div>

      <!-- 图表底部控制栏 -->
      <div class="chart-bottom-bar">
        <div class="cbb-left">
          <el-checkbox v-model="skipReasonCategory" class="chart-ctrl-check">跳过原因分类</el-checkbox>
        </div>
        <div class="cbb-right">
          <el-radio-group v-model="noSalesMode" class="no-sales-radio">
            <el-radio value="all">所有数据</el-radio>
            <el-radio value="hide" :disabled="groupBy !== null || effectiveProductLevel !== 'series'">隐藏当前未销售产品数据</el-radio>
            <el-radio value="exclude">不记录当前未销售产品数据</el-radio>
          </el-radio-group>
        </div>
      </div>

    </div>

    <!-- 数据抽屉 -->
    <AftersaleCasesDrawer
      v-model="casesDrawer"
      :filter="casesDrawerFilter"
      :title="casesDrawerTitle"
    />

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

/* 图表底部控制栏 */
.chart-bottom-bar {
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between;
  padding: 4px 6px;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 9px;
}
.cbb-left  { display: flex; align-items: center; }
.cbb-right { display: flex; align-items: center; }

.chart-ctrl-check { font-size: 12px; }
:deep(.chart-ctrl-check .el-checkbox__label) {
  font-size: 12px; color: var(--text-muted); font-family: var(--font-family);
}
:deep(.chart-ctrl-check .el-checkbox__inner) { border-radius: 4px; }

.no-sales-radio { display: flex; align-items: center; gap: 4px; }
:deep(.no-sales-radio .el-radio__label) {
  font-size: 12px; color: var(--text-muted); font-family: var(--font-family); padding-left: 5px;
}
:deep(.no-sales-radio .el-radio) { margin-right: 4px; height: auto; }
:deep(.no-sales-radio .el-radio.is-checked .el-radio__label) { color: var(--accent); }
:deep(.no-sales-radio .el-radio__input.is-checked .el-radio__inner) {
  background: var(--accent); border-color: var(--accent);
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
