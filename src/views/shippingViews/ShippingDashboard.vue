<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown, Delete, Setting } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import http from '@/api/http'
import iconBar from '@/assets/icons/btn_bar.png'
import iconLine from '@/assets/icons/btn_line.png'
import iconPie from '@/assets/icons/btn_pie.png'
import iconMap from '@/assets/icons/btn_map.png'
import iconYoy from '@/assets/icons/btn_yoy.png'
import iconMom from '@/assets/icons/btn_mom.png'
import iconProduct from '@/assets/icons/btn_product.png'
import iconChannel from '@/assets/icons/btn_ship.png'
import iconRegion from '@/assets/icons/btn_region.png'
import iconDate from '@/assets/icons/btn_date.png'

// ── 常量 ──────────────────────────────────────────
const FONT = "'Microsoft YaHei UI','Microsoft YaHei','PingFang SC',sans-serif"

const DATE_SHORTCUTS = [
  { text: '从2024年起', value: () => [new Date('2024-01-01'), new Date()] },
  { text: '一年内',   value: () => { const s = new Date(); s.setFullYear(s.getFullYear() - 1); return [s, new Date()] } },
  { text: '半年内',   value: () => { const s = new Date(); s.setMonth(s.getMonth() - 6); return [s, new Date()] } },
  { text: '三个月内', value: () => { const s = new Date(); s.setMonth(s.getMonth() - 3); return [s, new Date()] } },
  { text: '一个月内', value: () => { const s = new Date(); s.setMonth(s.getMonth() - 1); return [s, new Date()] } },
]

const PERIOD_OPTIONS = [
  { label: '月',  value: 'month'    },
  { label: '季度', value: 'quarter' },
  { label: '半年', value: 'halfyear'},
  { label: '年',  value: 'year'     },
]

const PRODUCT_LEVELS = [
  { label: '品类层', value: 'category' },
  { label: '系列层', value: 'series'   },
  { label: '型号层', value: 'model'    },
]
const CHANNEL_LEVELS = [
  { label: '渠道',   value: 'channel'      },
  { label: '渠道商', value: 'channel_code' },
]
const REGION_LEVELS = [
  { label: '省份', value: 'province' },
  { label: '城市', value: 'city'     },
  { label: '县区', value: 'district' },
]

const DIM_DEFAULT_LEVEL = { product: 'category', channel: 'channel', region: 'province' }
const DIM_LABELS = { product: '产品', channel: '渠道', region: '地域' }
const DIM_COLORS = { product: '#c4883a', channel: '#4a8fc0', region: '#6ab47a' }

const METRIC_OPTIONS = [
  { label: '发货数据',   value: 'quantity'        },
  { label: '销退数据',   value: 'return_quantity' },
  { label: '净发货数据', value: 'actual'          },
]

const GROUP_BY_OPTIONS = [
  { label: '产品', value: 'product',  icon: iconProduct },
  { label: '渠道', value: 'channel',  icon: iconChannel },
  { label: '地域', value: 'province', icon: iconRegion  },
  { label: '时间', value: 'date',     icon: iconDate    },
]

// 各聚合维度下允许使用的图表类型和对比模式
const GROUPBY_ALLOWED = {
  product:  { chartTypes: ['bar', 'pie'],  comparisons: [],             default: 'bar' },
  channel:  { chartTypes: ['bar', 'pie'],  comparisons: [],             default: 'bar' },
  province: { chartTypes: ['map', 'bar'],  comparisons: [],             default: 'map' },
  date:     { chartTypes: [],              comparisons: ['yoy', 'mom'], default: null  },
}

// 省份简称 → ECharts GeoJSON 标准全称
const PROVINCE_NAME_MAP = {
  '北京': '北京市',   '天津': '天津市',   '上海': '上海市',   '重庆': '重庆市',
  '河北': '河北省',   '山西': '山西省',   '辽宁': '辽宁省',   '吉林': '吉林省',
  '黑龙江': '黑龙江省', '江苏': '江苏省', '浙江': '浙江省',   '安徽': '安徽省',
  '福建': '福建省',   '江西': '江西省',   '山东': '山东省',   '河南': '河南省',
  '湖北': '湖北省',   '湖南': '湖南省',   '广东': '广东省',   '海南': '海南省',
  '四川': '四川省',   '贵州': '贵州省',   '云南': '云南省',   '陕西': '陕西省',
  '甘肃': '甘肃省',   '青海': '青海省',   '台湾': '台湾省',
  '内蒙古': '内蒙古自治区', '广西': '广西壮族自治区', '西藏': '西藏自治区',
  '宁夏': '宁夏回族自治区', '新疆': '新疆维吾尔自治区',
  '香港': '香港特别行政区', '澳门': '澳门特别行政区',
}

// 省份简称 → 行政区划代码（用于加载省份地图文件）
const PROVINCE_ADCODE = {
  '北京市': '110000', '天津市': '120000', '河北省': '130000', '山西省': '140000',
  '内蒙古自治区': '150000', '辽宁省': '210000', '吉林省': '220000', '黑龙江省': '230000',
  '上海市': '310000', '江苏省': '320000', '浙江省': '330000', '安徽省': '340000',
  '福建省': '350000', '江西省': '360000', '山东省': '370000', '河南省': '410000',
  '湖北省': '420000', '湖南省': '430000', '广东省': '440000', '广西壮族自治区': '450000',
  '海南省': '460000', '重庆市': '500000', '四川省': '510000', '贵州省': '520000',
  '云南省': '530000', '西藏自治区': '540000', '陕西省': '610000', '甘肃省': '620000',
  '青海省': '630000', '宁夏回族自治区': '640000', '新疆维吾尔自治区': '650000',
  '台湾省': '710000', '香港特别行政区': '810000', '澳门特别行政区': '820000',
}

// 通过 Vite glob 懒加载 src/assets/maps/ 下的省份地图 JSON
// 省份地图文件命名规则：{adcode}_full.json，从 DataV 下载
// 下载地址：https://geo.datav.aliyun.com/areas_v3/bound/{adcode}_full.json
const PROVINCE_MAP_MODULES = import.meta.glob('@/assets/maps/*.json')

// 已注册地图缓存
const registeredMaps = new Set()

/** 通过 glob key 中是否包含关键字来查找 loader，规避路径格式差异 */
function findLoader(keyword) {
  const entry = Object.entries(PROVINCE_MAP_MODULES).find(([k]) => k.includes(keyword))
  return entry ? entry[1] : null
}

async function ensureChinaMap() {
  if (registeredMaps.has('china')) return true
  const loader = findLoader('china-map')
  if (!loader) { ElMessage.error('地图数据未找到，请将 china-map.json 放入 src/assets/maps/ 目录'); return false }
  try {
    const mod = await loader()
    echarts.registerMap('china', mod.default)
    registeredMaps.add('china')
    return true
  } catch {
    ElMessage.error('地图数据加载失败')
    return false
  }
}

/** 加载并注册指定行政区划代码的省份地图，返回 mapKey 或 null */
async function ensureProvinceMap(adcode) {
  if (registeredMaps.has(adcode)) return adcode
  const loader = findLoader(`${adcode}_full`)
  if (!loader) return null   // 文件不存在，降级显示全国地图
  try {
    const mod = await loader()
    echarts.registerMap(adcode, mod.default)
    registeredMaps.add(adcode)
    return adcode
  } catch {
    return null
  }
}

/**
 * 根据当前维度和筛选状态决定应该使用哪张地图。
 * 地域维度下筛选了单一省份 → 尝试加载省份地图；否则使用全国地图。
 * 返回最终使用的 mapKey。
 */
async function resolveMapKey() {
  const ok = await ensureChinaMap()
  if (!ok) return null

  // 地域维度下，直接读取筛选中的省份（expandStrSel 处理自定义分组）
  if (groupBy.value === 'province') {
    const provs = expandStrSel(filters.value.provinces)
    if (provs.length === 1) {
      const fullName = PROVINCE_NAME_MAP[provs[0]] ?? provs[0]
      const adcode   = PROVINCE_ADCODE[fullName]
      console.log('[map] province selected:', provs[0], '→', fullName, '→ adcode:', adcode)
      if (adcode) {
        const key = await ensureProvinceMap(adcode)
        console.log('[map] ensureProvinceMap result:', key)
        if (key) return key
      }
    }
  }
  return 'china'
}

// ── 响应式状态 ────────────────────────────────────

const sections = reactive({ time: true, product: true, channel: true, region: true })
const selectedPeriod = ref('month')
const chartType      = ref('bar')    // 图表类型：bar/line/pie/map
const comparisonMode = ref(null)     // 对比模式：null | 'yoy'（同比）| 'mom'（环比）
const groupBy        = ref('product') // 数据聚合维度
const dataMetric     = ref('actual') // 显示指标：quantity/return_quantity/actual

// 当前维度下允许的图表类型 / 对比模式
const allowedChartTypes  = computed(() => GROUPBY_ALLOWED[groupBy.value]?.chartTypes  ?? [])
const allowedComparisons = computed(() => GROUPBY_ALLOWED[groupBy.value]?.comparisons ?? [])

// 根据筛选层级自动推导实际发给后端的 group_by 值
// 产品：品类数≠1 → category；品类=1且系列数≠1 → series；品类=1且系列=1 → model
// 渠道：渠道数≠1 → channel；渠道=1 → channel_code
// 地域：省份数≠1 → province；省份=1且城市数≠1 → city；省份=1且城市=1 → district
// ── 有效筛选 ID 计算（含单候选自动下钻） ──────────────────
// 规则：用户有选择 → 用选择；用户无选择且只有 1 个候选 → 自动视为选中该候选；否则 → 返回空（不过滤）

function effCategoryIds() {
  const sel = expandProdSel(filters.value.categoryIds)
  if (sel.length) return sel
  const opts = categoryOpts.value.filter(o => typeof o.value === 'number')  // 排除分组UUID
  return opts.length === 1 ? [opts[0].value] : []
}

function effSeriesIds() {
  const sel = expandProdSel(filters.value.seriesIds)
  if (sel.length) return sel
  const catIds = effCategoryIds()
  if (catIds.length !== 1) return []
  const cat = categoryTree.value.find(c => c.id === catIds[0])
  if (!cat || !cat.series) return []
  return cat.series.length === 1 ? [cat.series[0].id] : []
}

function effModelIds() {
  const sel = expandProdSel(filters.value.modelIds)
  if (sel.length) return sel
  const serIds = effSeriesIds()
  if (serIds.length !== 1) return []
  const catIds = effCategoryIds()
  const cat = categoryTree.value.find(c => c.id === catIds[0])
  const ser = cat?.series?.find(s => s.id === serIds[0])
  if (!ser || !ser.models) return []
  return ser.models.length === 1 ? [ser.models[0].id] : []
}

function effChannelNames() {
  const sel = expandStrSel(filters.value.channelNames)
  if (sel.length) return sel
  const opts = channelOpts.value
  return opts.length === 1 ? [opts[0].value] : []
}

function effChannelCodes() {
  const sel = expandStrSel(filters.value.channelCodes)
  if (sel.length) return sel
  const names = effChannelNames()
  if (names.length !== 1) return []
  const ch = channelOptions.value.find(c => c.name === names[0])
  if (!ch || !ch.orgs) return []
  return ch.orgs.length === 1 ? [ch.orgs[0].code] : []
}

function effProvinces() {
  const sel = expandStrSel(filters.value.provinces)
  if (sel.length) return sel
  const opts = provinceOpts.value
  return opts.length === 1 ? [opts[0].value] : []
}

function effCities() {
  const sel = expandStrSel(filters.value.cities)
  if (sel.length) return sel
  const provs = effProvinces()
  if (provs.length !== 1) return []
  const prov = provinceOptions.value.find(p => p.name === provs[0])
  if (!prov || !prov.cities) return []
  return prov.cities.length === 1 ? [prov.cities[0].name] : []
}

function effDistricts() {
  const sel = expandStrSel(filters.value.districts)
  if (sel.length) return sel
  const cities = effCities()
  if (cities.length !== 1) return []
  const provs = effProvinces()
  const prov  = provinceOptions.value.find(p => p.name === provs[0])
  const city  = prov?.cities?.find(c => c.name === cities[0])
  if (!city || !city.districts) return []
  return city.districts.length === 1 ? [city.districts[0]] : []
}

// 根据有效选择数量推导实际发给后端的 group_by 值
const effectiveGroupBy = computed(() => {
  switch (groupBy.value) {
    case 'product': {
      if (effCategoryIds().length !== 1) return 'category'
      if (effSeriesIds().length   !== 1) return 'series'
      return 'model'
    }
    case 'channel':
      return effChannelNames().length === 1 ? 'channel_code' : 'channel'
    case 'province': {
      if (effProvinces().length !== 1) return 'province'
      // 只有用户显式选定了唯一城市才下钻到县区；
      // effCities() 的自动推导仅用于后端过滤参数，不影响层级判断
      const explicitCities = expandStrSel(filters.value.cities)
      if (explicitCities.length !== 1) return 'city'
      return 'district'
    }
    default:
      return groupBy.value
  }
})

// 筛选条件（各字段可混存"普通值"和"分组UUID"）
const filters = ref({
  dateRange:    (() => { const s = new Date(); s.setMonth(s.getMonth() - 1); return [s, new Date()] })(),
  channelNames: [], channelCodes: [],
  provinces: [], cities: [], districts: [],
  categoryIds: [], seriesIds: [], modelIds: [],
})

// ── 自定义分组（localStorage 持久化） ─────────────

const customGroups   = ref([])
const activeGroupIds = ref([])   // 当前激活的分组 id（仅芯片状态，不写入 filters）
const showGroupMgr   = ref(false)

// 新建分组表单
const newGroup = ref({
  name: '', dimension: 'product', level: 'category',
  parentCategoryId: null, parentSeriesId: null,
  parentChannelName: null,
  parentProvince: null, parentCity: null,
  selectedIds: [],    // 产品维度
  selectedValues: [], // 渠道/地域维度
})

function loadGroupsFromStorage() {
  try {
    const raw = localStorage.getItem('shipping_product_groups')
    customGroups.value = raw ? JSON.parse(raw) : []
  } catch { customGroups.value = [] }
}
function saveGroupsToStorage() {
  localStorage.setItem('shipping_product_groups', JSON.stringify(customGroups.value))
}

// 按维度分组
const productGroups = computed(() => customGroups.value.filter(g => g.dimension === 'product'))
const channelGroups = computed(() => customGroups.value.filter(g => g.dimension === 'channel'))
const regionGroups  = computed(() => customGroups.value.filter(g => g.dimension === 'region'))

// ── 分组辅助函数 ──────────────────────────────────

/** 判断某个值是否为分组 UUID */
function isGroupVal(val) {
  return customGroups.value.some(g => g.id === val)
}

/** 将 filters 中的分组 UUID 展开为产品 ID 数组 */
function expandProdSel(sel) {
  return sel.flatMap(v => {
    const g = customGroups.value.find(x => x.id === v)
    return g ? g.items.map(i => i.id) : [v]
  })
}

/** 将 filters 中的分组 UUID 展开为字符串值数组（渠道/地域） */
function expandStrSel(sel) {
  return sel.flatMap(v => {
    const g = customGroups.value.find(x => x.id === v)
    return g ? g.items.map(i => i.value) : [v]
  })
}

// ── 级联启用条件 ──────────────────────────────────
// 选中的是分组 UUID 时不允许向下钻取（无法确定单一父节点）

const seriesEnabled   = computed(() => filters.value.categoryIds.length === 1  && !isGroupVal(filters.value.categoryIds[0]))
const modelEnabled    = computed(() => filters.value.seriesIds.length === 1    && !isGroupVal(filters.value.seriesIds[0]))
const orgEnabled      = computed(() => filters.value.channelNames.length === 1 && !isGroupVal(filters.value.channelNames[0]))
const cityEnabled     = computed(() => filters.value.provinces.length === 1    && !isGroupVal(filters.value.provinces[0]))
const districtEnabled = computed(() => filters.value.cities.length === 1       && !isGroupVal(filters.value.cities[0]))

// ── 带分组的选项列表 ──────────────────────────────
// 规则：激活的分组出现在候选项中（可供用户选择），其成员同时隐藏

const categoryOpts = computed(() => {
  const active    = productGroups.value.filter(g => g.level === 'category' && activeGroupIds.value.includes(g.id))
  const hidden    = new Set(active.flatMap(g => g.items.map(i => i.id)))
  const activeIds = activeProductIds.value?.categories  // null=未加载→不过滤；[]=无数据→全隐
  return [
    ...categoryTree.value
      .filter(c => !hidden.has(c.id) && (activeIds == null || activeIds.includes(c.id)))
      .map(c => ({ value: c.id, label: c.name })),
    ...active.map(g => ({ value: g.id, label: g.name, sub: g.items.map(i => i.code).join(' + ') })),
  ]
})

const seriesOpts = computed(() => {
  if (!seriesEnabled.value) return []
  const catId     = filters.value.categoryIds[0]
  const cat       = categoryTree.value.find(c => c.id === catId)
  if (!cat) return []
  const active    = productGroups.value.filter(g => g.level === 'series' && activeGroupIds.value.includes(g.id) && g.parent_context?.category_id === catId)
  const hidden    = new Set(active.flatMap(g => g.items.map(i => i.id)))
  const activeIds = activeProductIds.value?.series
  return [
    ...cat.series
      .filter(s => !hidden.has(s.id) && (activeIds == null || activeIds.includes(s.id)))
      .map(s => ({ value: s.id, label: s.code, sub: s.name })),
    ...active.map(g => ({ value: g.id, label: g.name, sub: g.items.map(i => i.code).join(' + ') })),
  ]
})

const modelOpts = computed(() => {
  if (!modelEnabled.value) return []
  const serId     = filters.value.seriesIds[0]
  const cat       = categoryTree.value.find(c => c.id === filters.value.categoryIds[0])
  const ser       = cat?.series.find(s => s.id === serId)
  if (!ser) return []
  const active    = productGroups.value.filter(g => g.level === 'model' && activeGroupIds.value.includes(g.id) && g.parent_context?.series_id === serId)
  const hidden    = new Set(active.flatMap(g => g.items.map(i => i.id)))
  const activeIds = activeProductIds.value?.models
  return [
    ...(ser.models || [])
      .filter(m => !hidden.has(m.id) && (activeIds == null || activeIds.includes(m.id)))
      .map(m => ({ value: m.id, label: m.code, sub: m.name })),
    ...active.map(g => ({ value: g.id, label: g.name, sub: g.items.map(i => i.code).join(' + ') })),
  ]
})

const channelOpts = computed(() => {
  const active = channelGroups.value.filter(g => g.level === 'channel' && activeGroupIds.value.includes(g.id))
  const hidden = new Set(active.flatMap(g => g.items.map(i => i.value)))
  return [
    ...channelOptions.value.filter(c => !hidden.has(c.name)).map(c => ({ value: c.name, label: c.name })),
    ...active.map(g => ({ value: g.id, label: g.name, sub: g.items.map(i => i.label || i.value).join(' + ') })),
  ]
})

const orgOpts = computed(() => {
  if (!orgEnabled.value) return []
  const chName = filters.value.channelNames[0]
  const ch     = channelOptions.value.find(c => c.name === chName)
  if (!ch) return []
  const active = channelGroups.value.filter(g => g.level === 'channel_code' && activeGroupIds.value.includes(g.id) && g.parent_context?.channel_name === chName)
  const hidden = new Set(active.flatMap(g => g.items.map(i => i.value)))
  return [
    ...(ch.orgs || []).filter(o => !hidden.has(o.code)).map(o => ({ value: o.code, label: o.org_name, sub: o.code })),
    ...active.map(g => ({ value: g.id, label: g.name, sub: g.items.map(i => i.value).join(' + ') })),
  ]
})

const provinceOpts = computed(() => {
  const active = regionGroups.value.filter(g => g.level === 'province' && activeGroupIds.value.includes(g.id))
  const hidden = new Set(active.flatMap(g => g.items.map(i => i.value)))
  return [
    ...provinceOptions.value.filter(p => !hidden.has(p.name)).map(p => ({ value: p.name, label: p.name })),
    ...active.map(g => ({ value: g.id, label: g.name, sub: g.items.map(i => i.value).join(' + ') })),
  ]
})

const cityOpts = computed(() => {
  if (!cityEnabled.value) return []
  const provName = filters.value.provinces[0]
  const prov     = provinceOptions.value.find(p => p.name === provName)
  if (!prov) return []
  const active = regionGroups.value.filter(g => g.level === 'city' && activeGroupIds.value.includes(g.id) && g.parent_context?.province === provName)
  const hidden = new Set(active.flatMap(g => g.items.map(i => i.value)))
  return [
    ...(prov.cities || []).filter(c => !hidden.has(c.name)).map(c => ({ value: c.name, label: c.name })),
    ...active.map(g => ({ value: g.id, label: g.name, sub: g.items.map(i => i.value).join(' + ') })),
  ]
})

const districtOpts = computed(() => {
  if (!districtEnabled.value) return []
  const cityName = filters.value.cities[0]
  const prov     = provinceOptions.value.find(p => p.name === filters.value.provinces[0])
  const city     = prov?.cities?.find(c => c.name === cityName)
  if (!city) return []
  const active = regionGroups.value.filter(g => g.level === 'district' && activeGroupIds.value.includes(g.id) && g.parent_context?.city === cityName)
  const hidden = new Set(active.flatMap(g => g.items.map(i => i.value)))
  return [
    ...(city.districts || []).filter(d => !hidden.has(d)).map(d => ({ value: d, label: d })),
    ...active.map(g => ({ value: g.id, label: g.name, sub: g.items.map(i => i.value).join(' + ') })),
  ]
})

// ── 新建分组表单联动 ──────────────────────────────

function onNewGroupDimensionChange() {
  newGroup.value.level = DIM_DEFAULT_LEVEL[newGroup.value.dimension]
  resetNewGroupChildren()
}
function onNewGroupLevelChange()     { resetNewGroupChildren() }
function onNewGroupCategoryChange()  { newGroup.value.parentSeriesId = null; newGroup.value.selectedIds = [] }
function onNewGroupSeriesChange()    { newGroup.value.selectedIds = [] }
function onNewGroupChannelChange()   { newGroup.value.selectedValues = [] }
function onNewGroupProvinceChange()  { newGroup.value.parentCity = null; newGroup.value.selectedValues = [] }
function onNewGroupCityChange()      { newGroup.value.selectedValues = [] }

function resetNewGroupChildren() {
  Object.assign(newGroup.value, {
    parentCategoryId: null, parentSeriesId: null,
    parentChannelName: null, parentProvince: null, parentCity: null,
    selectedIds: [], selectedValues: [],
  })
}

const newGroupLevelOptions = computed(() => {
  if (newGroup.value.dimension === 'product') return PRODUCT_LEVELS
  if (newGroup.value.dimension === 'channel') return CHANNEL_LEVELS
  return REGION_LEVELS
})

const newGroupSeriesOptions = computed(() => {
  const cat = categoryTree.value.find(c => c.id === newGroup.value.parentCategoryId)
  return cat?.series || []
})

const newGroupCityOptions = computed(() => {
  const prov = provinceOptions.value.find(p => p.name === newGroup.value.parentProvince)
  return prov?.cities || []
})

/** 新建分组可选项目列表 */
const newGroupItemOptions = computed(() => {
  const { dimension, level, parentCategoryId, parentSeriesId, parentChannelName, parentProvince, parentCity } = newGroup.value
  if (dimension === 'product') {
    if (level === 'category') return categoryTree.value.map(c => ({ id: c.id, label: c.name }))
    const cat = categoryTree.value.find(c => c.id === parentCategoryId)
    if (level === 'series') return (cat?.series || []).map(s => ({ id: s.id, label: `${s.code}  ${s.name}` }))
    const ser = cat?.series?.find(s => s.id === parentSeriesId)
    return (ser?.models || []).map(m => ({ id: m.id, label: `${m.code}  ${m.name}` }))
  }
  if (dimension === 'channel') {
    if (level === 'channel') return channelOptions.value.map(c => ({ value: c.name, label: c.name }))
    const ch = channelOptions.value.find(c => c.name === parentChannelName)
    return (ch?.orgs || []).map(o => ({ value: o.code, label: `${o.code}  ${o.org_name}` }))
  }
  if (level === 'province') return provinceOptions.value.map(p => ({ value: p.name, label: p.name }))
  const prov = provinceOptions.value.find(p => p.name === parentProvince)
  if (level === 'city') return (prov?.cities || []).map(c => ({ value: c.name, label: c.name }))
  const city = prov?.cities?.find(c => c.name === parentCity)
  return (city?.districts || []).map(d => ({ value: d, label: d }))
})

const needParentCategory = computed(() => newGroup.value.dimension === 'product' && ['series','model'].includes(newGroup.value.level))
const needParentSeries   = computed(() => newGroup.value.dimension === 'product' && newGroup.value.level === 'model')
const needParentChannel  = computed(() => newGroup.value.dimension === 'channel' && newGroup.value.level === 'channel_code')
const needParentProvince = computed(() => newGroup.value.dimension === 'region'  && ['city','district'].includes(newGroup.value.level))
const needParentCity     = computed(() => newGroup.value.dimension === 'region'  && newGroup.value.level === 'district')

const itemSelectDisabled = computed(() => {
  const { dimension, level, parentCategoryId, parentSeriesId, parentChannelName, parentProvince, parentCity } = newGroup.value
  if (dimension === 'product') {
    if (level === 'series' && !parentCategoryId) return true
    if (level === 'model'  && !parentSeriesId)   return true
  }
  if (dimension === 'channel' && level === 'channel_code' && !parentChannelName) return true
  if (dimension === 'region') {
    if (level === 'city'     && !parentProvince) return true
    if (level === 'district' && !parentCity)     return true
  }
  return false
})

/** 保存新建分组 */
function saveNewGroup() {
  const { name, dimension, level, parentCategoryId, parentSeriesId, parentChannelName, parentProvince, parentCity, selectedIds, selectedValues } = newGroup.value
  if (!name.trim()) { ElMessage.warning('请输入分组名称'); return }
  if (dimension === 'product' ? selectedIds.length < 2 : selectedValues.length < 2) {
    ElMessage.warning('请至少选择两项'); return
  }

  let items = [], parent_context = null

  if (dimension === 'product') {
    if (level === 'category') {
      items = categoryTree.value.filter(c => selectedIds.includes(c.id)).map(c => ({ id: c.id, code: c.name, name: c.name }))
    } else if (level === 'series') {
      const cat = categoryTree.value.find(c => c.id === parentCategoryId)
      items = (cat?.series || []).filter(s => selectedIds.includes(s.id)).map(s => ({ id: s.id, code: s.code, name: s.name }))
      parent_context = { category_id: cat.id, category_name: cat.name }
    } else {
      const cat = categoryTree.value.find(c => c.id === parentCategoryId)
      const ser = cat?.series?.find(s => s.id === parentSeriesId)
      items = (ser?.models || []).filter(m => selectedIds.includes(m.id)).map(m => ({ id: m.id, code: m.code, name: m.name }))
      parent_context = { category_id: cat.id, category_name: cat.name, series_id: ser.id, series_code: ser.code, series_name: ser.name }
    }
  } else if (dimension === 'channel') {
    if (level === 'channel') {
      items = selectedValues.map(v => ({ value: v, label: v }))
    } else {
      const ch = channelOptions.value.find(c => c.name === parentChannelName)
      items = selectedValues.map(v => {
        const org = ch?.orgs?.find(o => o.code === v)
        return { value: v, label: org ? `${org.code} ${org.org_name}` : v }
      })
      parent_context = { channel_name: parentChannelName }
    }
  } else {
    items = selectedValues.map(v => ({ value: v, label: v }))
    if (level === 'city')     parent_context = { province: parentProvince }
    if (level === 'district') parent_context = { province: parentProvince, city: parentCity }
  }

  customGroups.value.push({ id: crypto.randomUUID(), name: name.trim(), dimension, level, parent_context, items })
  saveGroupsToStorage()

  const dim = newGroup.value.dimension
  newGroup.value = { name: '', dimension: dim, level: DIM_DEFAULT_LEVEL[dim],
    parentCategoryId: null, parentSeriesId: null, parentChannelName: null, parentProvince: null, parentCity: null,
    selectedIds: [], selectedValues: [] }
  ElMessage.success('分组已保存')
}

/** 删除分组，并清除已在筛选条件中使用该分组 UUID 的选项 */
function deleteGroup(id) {
  customGroups.value   = customGroups.value.filter(g => g.id !== id)
  activeGroupIds.value = activeGroupIds.value.filter(v => v !== id)
  _removeGroupFromFilters(id)
  saveGroupsToStorage()
}

/** 判断分组芯片是否激活 */
function isGroupActive(g) {
  return activeGroupIds.value.includes(g.id)
}

/** 点击芯片切换激活状态；取消时同步从 filters 中移除该分组 UUID；实时重渲图表 */
function toggleGroup(g) {
  const idx = activeGroupIds.value.indexOf(g.id)
  if (idx >= 0) {
    activeGroupIds.value.splice(idx, 1)
    _removeGroupFromFilters(g.id)
  } else {
    activeGroupIds.value.push(g.id)
  }
  renderChart()
}

function _removeGroupFromFilters(id) {
  const rm = arr => arr.filter(v => v !== id)
  filters.value.categoryIds  = rm(filters.value.categoryIds)
  filters.value.seriesIds    = rm(filters.value.seriesIds)
  filters.value.modelIds     = rm(filters.value.modelIds)
  filters.value.channelNames = rm(filters.value.channelNames)
  filters.value.channelCodes = rm(filters.value.channelCodes)
  filters.value.provinces    = rm(filters.value.provinces)
  filters.value.cities       = rm(filters.value.cities)
  filters.value.districts    = rm(filters.value.districts)
}

/** 分组描述文字 */
function groupLevelLabel(group) {
  const { dimension: dim, level, parent_context: pc } = group
  if (dim === 'product') {
    if (level === 'category') return '品类'
    if (level === 'series')   return `系列 · ${pc?.category_name || ''}`
    return `型号 · ${pc?.series_code || ''}`
  }
  if (dim === 'channel') return level === 'channel' ? '渠道' : `渠道商 · ${pc?.channel_name || ''}`
  if (level === 'province') return '省份'
  if (level === 'city')     return `城市 · ${pc?.province || ''}`
  return `县区 · ${pc?.city || ''}`
}

// ── 下拉源数据 ────────────────────────────────────
const channelOptions  = ref([])
const provinceOptions = ref([])
const categoryTree    = ref([])
// 当前日期范围内有数据的产品 ID 集合（null=未加载，{}=已加载可能为空）
const activeProductIds = ref(null)

// 图表数据
const summary    = ref({ quantity: 0, return_quantity: 0, actual_quantity: 0 })
const chartItems = ref([])
const loadingOptions = ref(false)
const loadingChart   = ref(false)

// 下钻面包屑：每一项保存右击时的筛选快照和对应的 label
// [{ label: 'A', savedFilters: {...} }, ...]
const drillStack = ref([])

// 允许继续下钻的维度（叶子节点不能再下钻）
const DRILLABLE_LEVELS = new Set(['category', 'series', 'channel', 'province', 'city'])

// ECharts
const chartEl   = ref(null)
let   chartInst = null
let   resizeObs = null

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  loadGroupsFromStorage()
  await loadOptions()       // 先加载选项（categoryTree 等），effectiveGroupBy 依赖它
  await loadChartData()     // 再加载图表，此时 effectiveGroupBy 已能正确推导层级
  initChart()
})
onUnmounted(() => {
  resizeObs?.disconnect()
  if (chartInst) { chartInst.dispose(); chartInst = null }
})

// ── 方法 ──────────────────────────────────────────

function handleQuery() { loadChartData() }
function toggleSection(key) { sections[key] = !sections[key] }

function onCategoryChange() { filters.value.seriesIds = []; filters.value.modelIds = [] }
function onSeriesChange()   { filters.value.modelIds = [] }

function toggleComparison(mode) {
  comparisonMode.value = comparisonMode.value === mode ? null : mode
}

function resetFilters() {
  selectedPeriod.value = 'month'
  activeGroupIds.value = []
  drillStack.value     = []
  filters.value = {
    dateRange:    (() => { const s = new Date(); s.setMonth(s.getMonth() - 1); return [s, new Date()] })(),
    channelNames: [], channelCodes: [],
    provinces: [], cities: [], districts: [],
    categoryIds: [], seriesIds: [], modelIds: [],
  }
}

/** 下钻：右击柱子后进入下一层级，将当前筛选状态压入面包屑栈 */
function drillDown(label) {
  const level = effectiveGroupBy.value
  if (!DRILLABLE_LEVELS.has(level)) return

  // 保存当前所有分类筛选快照（dateRange 不参与下钻，保持不变）
  const savedFilters = {
    categoryIds:  [...filters.value.categoryIds],
    seriesIds:    [...filters.value.seriesIds],
    modelIds:     [...filters.value.modelIds],
    channelNames: [...filters.value.channelNames],
    channelCodes: [...filters.value.channelCodes],
    provinces:    [...filters.value.provinces],
    cities:       [...filters.value.cities],
    districts:    [...filters.value.districts],
  }
  drillStack.value.push({ label, savedFilters })

  // 应用下钻筛选（filter 变更会触发 watch → loadChartData）
  if (level === 'category') {
    const cat = categoryTree.value.find(c => c.name === label)
    if (!cat) { drillStack.value.pop(); return }
    filters.value.categoryIds = [cat.id]
    filters.value.seriesIds   = []
    filters.value.modelIds    = []
  } else if (level === 'series') {
    let seriesId = null
    for (const c of categoryTree.value) {
      const s = (c.series || []).find(s => s.code === label)
      if (s) { seriesId = s.id; break }
    }
    if (!seriesId) { drillStack.value.pop(); return }
    filters.value.seriesIds = [seriesId]
    filters.value.modelIds  = []
  } else if (level === 'channel') {
    filters.value.channelNames = [label]
    filters.value.channelCodes = []
  } else if (level === 'province') {
    filters.value.provinces = [label]
    filters.value.cities    = []
    filters.value.districts = []
  } else if (level === 'city') {
    filters.value.cities    = [label]
    filters.value.districts = []
  }
}

/**
 * 面包屑回退：idx 对应 drillStack 中的位置
 * - idx=0 → 回到下钻前的初始状态
 * - idx=i → 回到第 i 次下钻前保存的状态（即当时的第 i-1 层视图）
 */
function drillBack(idx) {
  const { savedFilters } = drillStack.value[idx]
  Object.assign(filters.value, {
    categoryIds:  savedFilters.categoryIds,
    seriesIds:    savedFilters.seriesIds,
    modelIds:     savedFilters.modelIds,
    channelNames: savedFilters.channelNames,
    channelCodes: savedFilters.channelCodes,
    provinces:    savedFilters.provinces,
    cities:       savedFilters.cities,
    districts:    savedFilters.districts,
  })
  drillStack.value = drillStack.value.slice(0, idx)
}

async function loadOptions() {
  loadingOptions.value = true
  try {
    const [start, end] = filters.value.dateRange || []
    const params = {}
    if (start) params.date_start = formatDate(start)
    if (end)   params.date_end   = formatDate(end)
    const [optRes, treeRes] = await Promise.all([
      http.get('/api/shipping/chart-options', { params }),
      http.get('/api/category/tree'),
    ])
    if (optRes.success) {
      channelOptions.value  = optRes.data.channels
      provinceOptions.value = optRes.data.provinces
      activeProductIds.value = {
        categories: optRes.data.active_category_ids || [],
        series:     optRes.data.active_series_ids   || [],
        models:     optRes.data.active_model_ids    || [],
      }
    }
    if (treeRes.success) { categoryTree.value = treeRes.data }
  } catch { ElMessage.error('加载筛选数据失败') }
  finally  { loadingOptions.value = false }
}

async function loadChartData() {
  loadingChart.value = true
  try {
    const [start, end] = filters.value.dateRange || []
    const body = {
      group_by:      effectiveGroupBy.value,
      period:        groupBy.value === 'date' ? selectedPeriod.value : undefined,
      date_start:    start ? formatDate(start) : null,
      date_end:      end   ? formatDate(end)   : null,
      // 使用有效筛选函数（含单候选自动下钻逻辑）
      category_ids:  effCategoryIds(),
      series_ids:    effSeriesIds(),
      model_ids:     effModelIds(),
      channel_names: effChannelNames(),
      channel_codes: effChannelCodes(),
      provinces:     effProvinces(),
      cities:        effCities(),
      districts:     effDistricts(),
    }
    const res = await http.post('/api/shipping/chart-data', body)
    if (res.success) {
      summary.value = res.data.summary; chartItems.value = res.data.items; renderChart()
    } else { ElMessage.error(res.message || '图表数据加载失败') }
  } catch { ElMessage.error('图表数据加载失败') }
  finally  { loadingChart.value = false }
}

function formatDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}

// ── ECharts ───────────────────────────────────────
function initChart() {
  if (!chartEl.value) return
  resizeObs = new ResizeObserver(() => {
    if (!chartEl.value?.offsetWidth || !chartEl.value?.offsetHeight) return
    if (!chartInst) {
      chartInst = echarts.init(chartEl.value, null, { renderer: 'canvas' })
      // 右击柱子 → 下钻（自定义分组条目跳过）
      chartInst.on('contextmenu', (params) => {
        params.event?.event?.preventDefault?.()
        if (params.componentType !== 'series' || !['bar', 'pie'].includes(params.seriesType)) return
        const label = params.name
        const isCustomGroup = customGroups.value.some(
          g => activeGroupIds.value.includes(g.id) && g.name === label
        )
        if (!isCustomGroup) drillDown(label)
      })
      renderChart()
    } else {
      chartInst.resize()
    }
  })
  resizeObs.observe(chartEl.value)
}

/**
 * 将激活分组的图表条目合并为单一分组条目，保持后端返回的原始排序。
 * 例：A2、A3 属于分组 A23，则结果为 [..., A23(=A2+A3合计), ...]，A2/A3 原位替换为 A23。
 */
function mergeGroupedItems(items) {
  const curLevel = effectiveGroupBy.value
  // 仅处理层级与当前 groupBy 一致的激活分组
  const activeGroups = customGroups.value.filter(
    g => activeGroupIds.value.includes(g.id) && g.level === curLevel
  )
  if (!activeGroups.length) return items

  // 构建 chart label → group 映射
  // product 分组条目有 code 字段；channel / region 分组条目用 value 字段
  const labelToGroup = new Map()
  for (const g of activeGroups) {
    for (const it of g.items) {
      labelToGroup.set(it.code !== undefined ? it.code : it.value, g)
    }
  }

  const result    = []
  const groupEntry = new Map()  // group.id → 已插入的合并条目引用

  for (const item of items) {
    const g = labelToGroup.get(item.label)
    if (!g) {
      // 非分组成员，原样保留
      result.push({ ...item })
    } else if (groupEntry.has(g.id)) {
      // 同一分组后续成员：累加数量
      const entry = groupEntry.get(g.id)
      entry.quantity        += item.quantity
      entry.return_quantity += item.return_quantity
      entry.actual_quantity += item.actual_quantity
    } else {
      // 分组第一个成员出现时，插入以分组名为 label 的合并条目
      // groupMembers：用于 tooltip 展示分组包含的成员列表
      const groupMembers = g.items.map(it => {
        if (it.code !== undefined) {
          // product 分组：code + name
          return it.name && it.name !== it.code ? `${it.code}  ${it.name}` : it.code
        }
        // channel / region 分组：用 label（已含组织名等信息）
        return it.label ?? it.value
      })
      const entry = {
        label:           g.name,
        quantity:        item.quantity,
        return_quantity: item.return_quantity,
        actual_quantity: item.actual_quantity,
        isGroup:         true,
        groupMembers,
      }
      groupEntry.set(g.id, entry)
      result.push(entry)
    }
  }

  return result
}

async function renderChart() {
  if (!chartInst) return
  const items = mergeGroupedItems(chartItems.value)
  let opt
  if (groupBy.value === 'date') {
    // 时间维度：由对比模式决定图表类型
    opt = comparisonMode.value === 'mom' ? buildMomOption(items) : buildYoyOption(items)
  } else if (chartType.value === 'map') {
    const mapKey = await resolveMapKey()
    if (!mapKey) return
    opt = buildMapOption(items, mapKey)
  } else {
    opt = chartType.value === 'line' ? buildLineOption(items)
        : chartType.value === 'pie'  ? buildPieOption(items)
        : buildBarOption(items)
  }
  chartInst.setOption(opt, { notMerge: true })
}

// 指标 → { field, label, color, areaColor }
const METRIC_MAP = {
  quantity:        { field: 'quantity',        label: '发货量', color: '#4a8fc0', areaColor: 'rgba(74,143,192,0.08)'  },
  return_quantity: { field: 'return_quantity',  label: '销退量', color: '#e07070', areaColor: 'rgba(224,112,112,0.08)' },
  actual:          { field: 'actual_quantity',  label: '净发货', color: '#c4883a', areaColor: 'rgba(196,136,58,0.08)'  },
}

// 动态构建图表标题
// 0项 → 全部×××；1项 → 显示具体名称；多项 → 部分×××
function buildChartTitle(label) {
  // 将单个 ID/值解析为显示名（先查自定义分组，再查数据树）
  function resolveName(v, treeLookup) {
    const g = customGroups.value.find(x => x.id === v)
    if (g) return g.name
    return treeLookup(v) || String(v)
  }

  // 产品描述
  function prodDesc() {
    if (filters.value.modelIds.length > 1)    return '部分型号'
    if (filters.value.modelIds.length === 1)  return resolveName(filters.value.modelIds[0], v => {
      for (const c of categoryTree.value) for (const s of c.series || []) for (const m of s.models || []) if (m.id === v) return m.code
    })
    if (filters.value.seriesIds.length > 1)   return '部分系列'
    if (filters.value.seriesIds.length === 1) return resolveName(filters.value.seriesIds[0], v => {
      for (const c of categoryTree.value) for (const s of c.series || []) if (s.id === v) return s.code
    })
    if (filters.value.categoryIds.length > 1)   return '部分品类'
    if (filters.value.categoryIds.length === 1) return resolveName(filters.value.categoryIds[0], v =>
      categoryTree.value.find(c => c.id === v)?.name
    )
    return '全部品类'
  }

  // 渠道描述
  function channelDesc() {
    const codes = filters.value.channelCodes
    const names = filters.value.channelNames
    if (codes.length > 1 || names.length > 1) return '部分渠道'
    if (codes.length === 1) return resolveName(codes[0], v => v)
    if (names.length === 1) return resolveName(names[0], v => v)
    return '全部渠道'
  }

  // 区域描述
  function regionDesc() {
    const src = filters.value.districts.length ? filters.value.districts
              : filters.value.cities.length    ? filters.value.cities
              : filters.value.provinces
    if (src.length > 1)   return '部分区域'
    if (src.length === 1) return resolveName(src[0], v => v)
    return '全部区域'
  }

  // 当前聚合维度对应的描述放在最前
  let parts
  if (groupBy.value === 'channel') {
    parts = [channelDesc(), prodDesc(), regionDesc()]
  } else if (groupBy.value === 'province') {
    parts = [regionDesc(), prodDesc(), channelDesc()]
  } else {
    parts = [prodDesc(), channelDesc(), regionDesc()]
  }

  return `${parts.join(' - ')}   ${label}分布`
}

// 公共工具区配置
// withZoom=true 时包含区域缩放（仅直角坐标系图表使用）
function makeToolbox(withZoom = false) {
  return {
    right: 16, top: 12,
    feature: {
      ...(withZoom ? { dataZoom: { title: { zoom: '区域缩放', back: '缩放还原' }, yAxisIndex: 'none' } } : {}),
      restore:      { title: '还原' },
      saveAsImage:  { title: '保存图片', pixelRatio: 2 },
    },
    iconStyle:  { borderColor: '#8a7a6a' },
    emphasis:   { iconStyle: { borderColor: '#c4883a', color: '#c4883a' } },
  }
}

// 柱状图：主指标柱 + 占比折线 + 柏拉图累计占比折线
function buildBarOption(items) {
  const { field, label } = METRIC_MAP[dataMetric.value]
  // 切换指标时按当前指标降序排列
  const sorted = [...items].sort((a, b) => (b[field] ?? 0) - (a[field] ?? 0))
  const labels = sorted.map(i => i.label)
  const values = sorted.map(i => i[field])
  // label → name 映射，用于 tooltip 显示（仅 series/model 维度有 name）
  const nameMap = Object.fromEntries(sorted.filter(i => i.name).map(i => [i.label, i.name]))
  // label → groupMembers 映射，用于分组 tooltip 底部展示成员列表
  const groupMembersMap = Object.fromEntries(sorted.filter(i => i.isGroup && i.groupMembers).map(i => [i.label, i.groupMembers]))
  const total  = values.reduce((sum, v) => sum + v, 0)

  // 各项占比（%）
  const pctData = values.map(v => total > 0 ? Math.round(v / total * 1000) / 10 : 0)

  // 柏拉图累计占比（%）
  const cumulData = []
  let running = 0
  for (const v of values) {
    running += v
    cumulData.push(total > 0 ? Math.round(running / total * 1000) / 10 : 0)
  }

  // 销退指标时：计算每项「销退占发货」比例（%）
  const isReturn = dataMetric.value === 'return_quantity'
  const returnRatioData = isReturn
    ? sorted.map(i => {
        const q = i.quantity ?? 0
        const r = i.return_quantity ?? 0
        return q > 0 ? Math.round(r / q * 1000) / 10 : 0
      })
    : []

  const labelOpt = {
    interval: 0, hideOverlap: true,
    rotate: labels.length > 10 ? 30 : 0, color: '#7a5c3a', fontFamily: FONT, fontSize: 13,
  }
  const titleText = buildChartTitle(label)

  return {
    backgroundColor: 'transparent',
    title: {
      text: titleText,
      subtext: (() => {
        const [start, end] = filters.value.dateRange || []
        if (start && end) return `${formatDate(start)}  ~  ${formatDate(end)}`
        if (start) return `${formatDate(start)} 起`
        return '全部时间'
      })(),
      left: 10, top: 16,
      textStyle: { color: '#3a3028', fontFamily: FONT, fontSize: 14, fontWeight: '600' },
      subtextStyle: { color: '#8a7a6a', fontFamily: FONT, fontSize: 12 },
    },
    toolbox: makeToolbox(true),
    legend: {
      top: 76, left: 'center', itemWidth: 18, itemHeight: 12, itemGap: 20,
      textStyle: { color: '#6b5e4e', fontFamily: FONT, fontSize: 13 },
    },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' }, textStyle: { fontFamily: FONT },
      formatter(params) {
        const bar       = params.find(p => p.seriesType === 'bar')
        const pct       = params.find(p => p.seriesName === '占比')
        const cumul     = params.find(p => p.seriesName === '累计占比')
        const retRatio  = params.find(p => p.seriesName === '销退率')
        const code    = params[0]?.name
        const name    = nameMap[code]
        const members = groupMembersMap[code]
        const title = name
          ? `<span style="font-weight:600;color:#3a3028">${code}</span><span style="font-size:12px;color:#8a7a6a;margin-left:6px">${name}</span>`
          : `<span style="font-weight:600;color:#3a3028">${code}</span>`
        const row = (marker, name, val) =>
          `<div style="display:flex;justify-content:space-between;align-items:center;gap:20px;line-height:1.8">` +
          `<span>${marker}${name}</span><span style="font-weight:600">${val}</span></div>`
        let s = `<div style="font-family:${FONT};font-size:14px;min-width:160px">`
        s += `<div style="margin-bottom:4px">${title}</div>`
        if (bar)      s += row(bar.marker,      bar.seriesName,  bar.value)
        if (retRatio) s += row(retRatio.marker, '销退率',        `${retRatio.value}%`)
        if (pct)      s += row(pct.marker,      '占比',          `${pct.value}%`)
        if (cumul)    s += row(cumul.marker,    '累计占比',      `${cumul.value}%`)
        if (members?.length) {
          s += `<div style="margin-top:6px;padding-top:6px;border-top:1px solid #e0d4c0">`
          s += members.map(m => `<div style="color:#3a7bc8;font-size:12px">${m}</div>`).join('')
          s += `</div>`
        }
        // 可继续下钻（非自定义分组）时显示操作提示
        if (!members && DRILLABLE_LEVELS.has(effectiveGroupBy.value)) {
          s += `<div style="margin-top:6px;padding-top:6px;border-top:1px solid #e0d4c0;color:#8a7a6a;font-size:12px">右击柱子查看详情</div>`
        }
        return s + '</div>'
      },
    },
    dataZoom: [
      { type: 'slider', xAxisIndex: 0, bottom: 14, height: 20, borderColor: '#e0d4c0', fillerColor: 'rgba(196,136,58,0.1)', handleStyle: { color: '#c4883a' }, textStyle: { color: '#7a5c3a', fontFamily: FONT, fontSize: 11 } },
      { type: 'inside', xAxisIndex: 0 },
    ],
    grid: { top: 116, left: 60, right: 60, bottom: 82 },
    xAxis: {
      type: 'category', data: labels, axisLabel: labelOpt,
      axisLine: { lineStyle: { color: '#e0d4c0' } }, axisTick: { lineStyle: { color: '#e0d4c0' } },
    },
    yAxis: [
      {
        type: 'value',
        name: '数量（PCS）',
        nameTextStyle: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13, padding: [0, 0, 0, 0] },
        axisLabel: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13 },
        splitLine: { lineStyle: { color: '#f0e8d8' } },
        axisLine: { show: true, lineStyle: { color: '#e0d4c0' } },
        axisTick: { show: true, lineStyle: { color: '#e0d4c0' } },
      },
      {
        type: 'value', min: 0, max: 100,
        name: '百分比',
        nameTextStyle: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13 },
        axisLabel: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13, formatter: '{value}%' },
        splitLine: { show: false },
        axisLine: { show: true, lineStyle: { color: '#e0d4c0' } },
        axisTick: { show: true, lineStyle: { color: '#e0d4c0' } },
      },
    ],
    series: [
      {
        name: label, type: 'bar', data: values, yAxisIndex: 0,
        itemStyle: { color: '#a8cce8', borderRadius: [2, 2, 0, 0] },
        label: { show: true, position: 'top', color: '#2c2420', fontFamily: FONT, fontSize: 14, fontWeight: 'bold', formatter: '{c}' },
      },
      // 销退指标时额外显示「销退率」折线（销退量 / 发货量）
      ...(isReturn ? [{
        name: '销退率', type: 'line', data: returnRatioData, yAxisIndex: 1,
        smooth: true,
        lineStyle: { color: '#9c6fba', width: 2 },
        itemStyle: { color: '#9c6fba' },
        symbol: 'circle', symbolSize: 4,
        label: { show: true, position: 'top', color: '#9c6fba', fontFamily: FONT, fontSize: 13, fontWeight: 'bold', formatter: p => `${p.value}%` },
      }] : []),
      {
        name: '占比', type: 'line', data: pctData, yAxisIndex: 1,
        smooth: true,
        lineStyle: { color: '#e07c00', width: 2 },
        itemStyle: { color: '#e07c00' },
        symbol: 'circle', symbolSize: 4,
        label: { show: true, position: 'top', color: '#e07c00', fontFamily: FONT, fontSize: 13, fontWeight: 'bold', formatter: p => `${p.value}%` },
      },
      {
        name: '累计占比', type: 'line', data: cumulData, yAxisIndex: 1,
        smooth: true,
        lineStyle: { color: '#e05050', width: 1.5, type: 'dashed' },
        itemStyle: { color: '#e05050' },
        symbol: 'circle', symbolSize: 4,
        label: { show: true, position: 'top', color: '#c03030', fontFamily: FONT, fontSize: 13, fontWeight: 'bold', formatter: p => `${p.value}%` },
      },
    ],
  }
}

// 折线图：按当前指标显示单条系列
function buildLineOption(items) {
  const { field, label, color, areaColor } = METRIC_MAP[dataMetric.value]
  const labels = items.map(i => i.label)
  const labelOpt = {
    rotate: labels.length > 10 ? 30 : 0, color: '#7a5c3a', fontFamily: FONT, fontSize: 11,
    interval: labels.length > 20 ? Math.floor(labels.length / 20) : 0,
  }
  return {
    backgroundColor: 'transparent',
    toolbox: makeToolbox(true),
    tooltip: { trigger: 'axis', textStyle: { fontFamily: FONT } },
    grid: { top: 48, left: 52, right: 16, bottom: 44 },
    xAxis: { type: 'category', data: labels, axisLabel: labelOpt, axisLine: { lineStyle: { color: '#e0d4c0' } }, axisTick: { lineStyle: { color: '#e0d4c0' } } },
    yAxis: { type: 'value', axisLabel: { color: '#7a5c3a', fontFamily: FONT, fontSize: 11 }, splitLine: { lineStyle: { color: '#f0e8d8' } } },
    series: [
      { name: label, type: 'line', smooth: true, data: items.map(i => i[field]), lineStyle: { color }, itemStyle: { color }, areaStyle: { color: areaColor } },
    ],
  }
}

// 同比（YoY）：将日期序列按年拆分，各年同期数据并排对比
function buildYoyOption(items) {
  const { field, label } = METRIC_MAP[dataMetric.value]
  const period = selectedPeriod.value

  // 解析后端 label 为 { year, periodKey, periodLabel }
  function parseLabel(raw) {
    if (period === 'year') {
      return { year: raw, periodKey: raw, periodLabel: raw }
    }
    const dashIdx = raw.indexOf('-')
    const yr  = raw.slice(0, dashIdx)     // '2024'
    const seg = raw.slice(dashIdx + 1)    // 'Q1' | 'H1' | '03'
    if (period === 'quarter') {
      return { year: yr, periodKey: seg, periodLabel: seg }
    }
    if (period === 'halfyear') {
      return { year: yr, periodKey: seg, periodLabel: seg === 'H1' ? '上半年' : '下半年' }
    }
    // month: '03' → '3月'
    return { year: yr, periodKey: seg, periodLabel: `${parseInt(seg)}月` }
  }

  // 生成完整的期号序列（X 轴固定展示完整一年，缺失数据填 0）
  // year 粒度则由数据自身决定 X 轴
  const FULL_PERIODS = {
    month:    ['01','02','03','04','05','06','07','08','09','10','11','12'],
    quarter:  ['Q1','Q2','Q3','Q4'],
    halfyear: ['H1','H2'],
    year:     null,   // 年粒度无固定序列
  }
  const PERIOD_LABELS = {
    month:    ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'],
    quarter:  ['Q1','Q2','Q3','Q4'],
    halfyear: ['上半年','下半年'],
    year:     null,
  }

  // 收集所有年份和数据
  const yearMap = new Map()   // year → Map<periodKey, value>

  for (const item of items) {
    const { year, periodKey } = parseLabel(item.label)
    if (!yearMap.has(year)) yearMap.set(year, new Map())
    yearMap.get(year).set(periodKey, item[field] || 0)
  }

  // 确定 X 轴期号序列
  let periodOrder, xLabels
  if (FULL_PERIODS[period]) {
    // 固定完整序列
    periodOrder = FULL_PERIODS[period]
    xLabels     = PERIOD_LABELS[period]
  } else {
    // year 粒度：按出现年份升序
    periodOrder = [...yearMap.keys()].sort()
    xLabels     = periodOrder
  }

  const years   = [...yearMap.keys()].sort()

  const YEAR_COLORS = ['#c4883a', '#4a8fc0', '#6ab47a', '#9c6fba', '#e07070', '#f0a030', '#50c0c0']

  const series = years.map((yr, idx) => {
    const clr  = YEAR_COLORS[idx % YEAR_COLORS.length]
    // 缺失期号填 0（确保每年序列长度与 X 轴一致）
    const data = periodOrder.map(k => yearMap.get(yr)?.get(k) ?? 0)
    return {
      name: `${yr}年`,
      type: 'bar',
      data,
      itemStyle: { color: clr, borderRadius: [2, 2, 0, 0] },
      label: {
        show: true, position: 'top', color: clr,
        fontFamily: FONT, fontSize: 12, fontWeight: 'bold', formatter: '{c}',
      },
    }
  })

  const titleText = `${buildChartTitle(label)} · 同比`
  return {
    backgroundColor: 'transparent',
    title: {
      text: titleText,
      subtext: (() => {
        const [start, end] = filters.value.dateRange || []
        if (start && end) return `${formatDate(start)}  ~  ${formatDate(end)}`
        if (start) return `${formatDate(start)} 起`
        return '全部时间'
      })(),
      left: 10, top: 16,
      textStyle:    { color: '#3a3028', fontFamily: FONT, fontSize: 14, fontWeight: '600' },
      subtextStyle: { color: '#8a7a6a', fontFamily: FONT, fontSize: 12 },
    },
    toolbox: makeToolbox(true),
    legend: {
      top: 76, left: 'center', itemWidth: 18, itemHeight: 12, itemGap: 20,
      textStyle: { color: '#6b5e4e', fontFamily: FONT, fontSize: 13 },
    },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' }, textStyle: { fontFamily: FONT },
      formatter(params) {
        const periodLabel = params[0]?.name
        const row = (marker, name, val) =>
          `<div style="display:flex;justify-content:space-between;align-items:center;gap:20px;line-height:1.8">` +
          `<span>${marker}${name}</span><span style="font-weight:600">${val ?? '-'}</span></div>`
        let s = `<div style="font-family:${FONT};font-size:14px;min-width:160px">`
        s += `<div style="margin-bottom:4px;font-weight:600;color:#3a3028">${periodLabel}</div>`
        for (const p of params) {
          if (p.value != null) s += row(p.marker, p.seriesName, p.value)
        }
        return s + '</div>'
      },
    },
    grid: { top: 116, left: 60, right: 30, bottom: 50 },
    xAxis: {
      type: 'category', data: xLabels,
      axisLabel: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13 },
      axisLine: { lineStyle: { color: '#e0d4c0' } },
      axisTick: { lineStyle: { color: '#e0d4c0' } },
    },
    yAxis: {
      type: 'value', name: '数量（PCS）',
      nameTextStyle: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13 },
      axisLabel: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13 },
      splitLine: { lineStyle: { color: '#f0e8d8' } },
      axisLine: { show: true, lineStyle: { color: '#e0d4c0' } },
      axisTick: { show: true, lineStyle: { color: '#e0d4c0' } },
    },
    series,
  }
}

// 环比（MoM）：按时间顺序显示柱状数据，叠加环比增长率折线
function buildMomOption(items) {
  const { field, label } = METRIC_MAP[dataMetric.value]
  const labels = items.map(i => i.label)
  const values = items.map(i => i[field] || 0)

  // 计算环比增长率（%）
  const momData = values.map((v, i) => {
    if (i === 0 || values[i - 1] === 0) return null
    return Math.round((v - values[i - 1]) / values[i - 1] * 1000) / 10
  })

  const titleText = `${buildChartTitle(label)} · 环比`
  return {
    backgroundColor: 'transparent',
    title: {
      text: titleText,
      subtext: (() => {
        const [start, end] = filters.value.dateRange || []
        if (start && end) return `${formatDate(start)}  ~  ${formatDate(end)}`
        if (start) return `${formatDate(start)} 起`
        return '全部时间'
      })(),
      left: 10, top: 16,
      textStyle:    { color: '#3a3028', fontFamily: FONT, fontSize: 14, fontWeight: '600' },
      subtextStyle: { color: '#8a7a6a', fontFamily: FONT, fontSize: 12 },
    },
    toolbox: makeToolbox(true),
    legend: {
      top: 76, left: 'center', itemWidth: 18, itemHeight: 12, itemGap: 20,
      textStyle: { color: '#6b5e4e', fontFamily: FONT, fontSize: 13 },
    },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' }, textStyle: { fontFamily: FONT },
      formatter(params) {
        const periodLabel = params[0]?.name
        const row = (marker, name, val) =>
          `<div style="display:flex;justify-content:space-between;align-items:center;gap:20px;line-height:1.8">` +
          `<span>${marker}${name}</span><span style="font-weight:600">${val ?? '-'}</span></div>`
        let s = `<div style="font-family:${FONT};font-size:14px;min-width:160px">`
        s += `<div style="margin-bottom:4px;font-weight:600;color:#3a3028">${periodLabel}</div>`
        for (const p of params) {
          if (p.value == null) continue
          const display = p.seriesName === '环比增长率' ? `${p.value}%` : p.value
          s += row(p.marker, p.seriesName, display)
        }
        return s + '</div>'
      },
    },
    dataZoom: [
      { type: 'slider', xAxisIndex: 0, bottom: 14, height: 20, borderColor: '#e0d4c0', fillerColor: 'rgba(196,136,58,0.1)', handleStyle: { color: '#c4883a' }, textStyle: { color: '#7a5c3a', fontFamily: FONT, fontSize: 11 } },
      { type: 'inside', xAxisIndex: 0 },
    ],
    grid: { top: 116, left: 60, right: 60, bottom: 82 },
    xAxis: {
      type: 'category', data: labels,
      axisLabel: { rotate: labels.length > 10 ? 30 : 0, color: '#7a5c3a', fontFamily: FONT, fontSize: 13, interval: labels.length > 20 ? Math.floor(labels.length / 20) : 0 },
      axisLine: { lineStyle: { color: '#e0d4c0' } },
      axisTick: { lineStyle: { color: '#e0d4c0' } },
    },
    yAxis: [
      {
        type: 'value', name: '数量（PCS）',
        nameTextStyle: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13 },
        axisLabel: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13 },
        splitLine: { lineStyle: { color: '#f0e8d8' } },
        axisLine: { show: true, lineStyle: { color: '#e0d4c0' } },
        axisTick: { show: true, lineStyle: { color: '#e0d4c0' } },
      },
      {
        type: 'value', name: '环比增长率',
        nameTextStyle: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13 },
        axisLabel: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13, formatter: '{value}%' },
        splitLine: { show: false },
        axisLine: { show: true, lineStyle: { color: '#e0d4c0' } },
        axisTick: { show: true, lineStyle: { color: '#e0d4c0' } },
      },
    ],
    series: [
      {
        name: label, type: 'bar', data: values, yAxisIndex: 0,
        itemStyle: { color: '#a8cce8', borderRadius: [2, 2, 0, 0] },
        label: { show: true, position: 'top', color: '#2c2420', fontFamily: FONT, fontSize: 14, fontWeight: 'bold', formatter: '{c}' },
      },
      {
        name: '环比增长率', type: 'line', data: momData, yAxisIndex: 1,
        smooth: true, connectNulls: false,
        lineStyle: { color: '#e07c00', width: 2 },
        itemStyle: { color: '#e07c00' },
        symbol: 'circle', symbolSize: 5,
        label: { show: true, position: 'top', color: '#e07c00', fontFamily: FONT, fontSize: 12, fontWeight: 'bold', formatter: p => p.value != null ? `${p.value}%` : '' },
      },
    ],
  }
}

// 饼图（donut）：按当前指标显示分布
function buildPieOption(items) {
  const { field, label } = METRIC_MAP[dataMetric.value]
  const nameMap         = Object.fromEntries(items.filter(i => i.name).map(i => [i.label, i.name]))
  const groupMembersMap = Object.fromEntries(items.filter(i => i.isGroup && i.groupMembers).map(i => [i.label, i.groupMembers]))
  const total = items.reduce((s, i) => s + (i[field] || 0), 0)
  const data  = items.filter(i => i[field] > 0).map(i => ({ name: i.label, value: i[field] }))

  const titleText = buildChartTitle(label)

  return {
    backgroundColor: 'transparent',
    title: {
      text: titleText,
      subtext: (() => {
        const [start, end] = filters.value.dateRange || []
        if (start && end) return `${formatDate(start)}  ~  ${formatDate(end)}`
        if (start) return `${formatDate(start)} 起`
        return '全部时间'
      })(),
      left: 10, top: 16,
      textStyle:    { color: '#3a3028', fontFamily: FONT, fontSize: 14, fontWeight: '600' },
      subtextStyle: { color: '#8a7a6a', fontFamily: FONT, fontSize: 12 },
    },
    toolbox: makeToolbox(false),
    tooltip: {
      trigger: 'item',
      textStyle: { fontFamily: FONT },
      formatter(params) {
        const code    = params.name
        const name    = nameMap[code]
        const members = groupMembersMap[code]
        const pct     = total > 0 ? Math.round(params.value / total * 1000) / 10 : 0
        const titleEl = name
          ? `<span style="font-weight:600;color:#3a3028">${code}</span><span style="font-size:12px;color:#8a7a6a;margin-left:6px">${name}</span>`
          : `<span style="font-weight:600;color:#3a3028">${code}</span>`
        const row = (marker, name, val) =>
          `<div style="display:flex;justify-content:space-between;align-items:center;gap:20px;line-height:1.8">` +
          `<span>${marker}${name}</span><span style="font-weight:600">${val}</span></div>`
        let s = `<div style="font-family:${FONT};font-size:14px;min-width:160px">`
        s += `<div style="margin-bottom:4px">${titleEl}</div>`
        s += row(params.marker, params.seriesName, `${params.value}（${pct}%）`)
        if (members?.length) {
          s += `<div style="margin-top:6px;padding-top:6px;border-top:1px solid #e0d4c0">`
          s += members.map(m => `<div style="color:#3a7bc8;font-size:12px">${m}</div>`).join('')
          s += `</div>`
        }
        if (!members && DRILLABLE_LEVELS.has(effectiveGroupBy.value)) {
          s += `<div style="margin-top:6px;padding-top:6px;border-top:1px solid #e0d4c0;color:#8a7a6a;font-size:12px">右击扇区查看详情</div>`
        }
        return s + '</div>'
      },
    },
    legend: {
      orient: 'vertical', right: 40, top: 'middle',
      textStyle: { color: '#6b5e4e', fontFamily: FONT, fontSize: 14 },
      type: 'scroll',
      itemWidth: 16, itemHeight: 12, itemGap: 14,
      pageButtonItemGap: 6,
      pageIconSize: 12,
      pageTextStyle: { color: '#8a7a6a', fontFamily: FONT, fontSize: 12 },
    },
    series: [{
      name: label, type: 'pie', radius: ['36%', '62%'],
      // 右侧图例占位，饼图左移
      center: ['50%', '54%'],
      data,
      label: {
        show: true,
        position: 'outside',
        formatter: '{a|{a}}{abg|}\n{hr|}\n  {b|{b}：}{c}  {per|{d}%}  ',
        backgroundColor: '#fff',
        borderColor: '#e0d4c0',
        borderWidth: 1,
        borderRadius: 6,
        rich: {
          a:   { color: '#8a7a6a', lineHeight: 22, align: 'center', fontFamily: FONT, fontSize: 11 },
          hr:  { borderColor: '#e0d4c0', width: '100%', borderWidth: 1, height: 0 },
          b:   { color: '#3a3028', fontSize: 13, fontWeight: 'bold', lineHeight: 30, fontFamily: FONT },
          per: { color: '#fff', backgroundColor: '#c4883a', padding: [3, 5], borderRadius: 4, fontSize: 11, fontFamily: FONT },
        },
      },
      labelLine: { show: true, length: 10, length2: 14, smooth: true },
      emphasis: {
        itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,0.15)' },
      },
      itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
    }],
  }
}

// 地图：全国地图或省份地图
// mapKey='china' → 全国，需要将省份简称转换为 GeoJSON 标准全称
// mapKey=adcode  → 省份地图，城市名称直接使用 DB 中的值
function buildMapOption(items, mapKey = 'china') {
  const { field, label } = METRIC_MAP[dataMetric.value]
  const titleText = buildChartTitle(label)
  const isChina = mapKey === 'china'
  const data = items.map(i => ({
    name:  isChina ? (PROVINCE_NAME_MAP[i.label] ?? i.label) : i.label,
    value: i[field] ?? 0,
    originalName: i.label,
  }))
  const maxVal = Math.max(...data.map(d => d.value), 1)

  return {
    backgroundColor: 'transparent',
    title: {
      text: titleText,
      subtext: (() => {
        const [start, end] = filters.value.dateRange || []
        if (start && end) return `${formatDate(start)}  ~  ${formatDate(end)}`
        if (start) return `${formatDate(start)} 起`
        return '全部时间'
      })(),
      left: 10, top: 16,
      textStyle:    { color: '#3a3028', fontFamily: FONT, fontSize: 14, fontWeight: '600' },
      subtextStyle: { color: '#8a7a6a', fontFamily: FONT, fontSize: 12 },
    },
    toolbox: makeToolbox(false),
    tooltip: {
      trigger: 'item',
      textStyle: { fontFamily: FONT, fontSize: 13 },
      formatter(params) {
        if (params.value == null || isNaN(params.value)) return `${params.name}：暂无数据`
        const name = params.data?.originalName ?? params.name
        return `<div style="font-family:${FONT};font-size:13px;min-width:140px">` +
          `<div style="font-weight:600;margin-bottom:4px">${name}</div>` +
          `<div style="display:flex;justify-content:space-between;align-items:center;gap:20px;line-height:1.8">` +
          `<span>${label}</span><span style="font-weight:600">${params.value}</span></div></div>`
      },
    },
    visualMap: {
      min: 0, max: maxVal,
      left: 16, bottom: 40,
      text: ['多', '少'],
      calculable: true,
      inRange: { color: ['#fef3e0', '#e8a855', '#c4883a'] },
      textStyle: { color: '#6b5e4e', fontFamily: FONT, fontSize: 12 },
    },
    series: [{
      name: label, type: 'map', map: mapKey,
      roam: true,
      data,
      label: { show: true, fontFamily: FONT, fontSize: 11, color: '#3a3028' },
      emphasis:  { label: { show: true, fontFamily: FONT, fontSize: 12, fontWeight: 'bold' }, itemStyle: { areaColor: '#e09050' } },
      select:    { disabled: true },
      itemStyle: { areaColor: '#f5f0e8', borderColor: '#d4c4a8', borderWidth: 0.8 },
    }],
  }
}

// 地图右侧 Top10 表格：地域维度且图表为地图时显示
const showMapTable = computed(() => groupBy.value === 'province' && chartType.value === 'map')

// 按当前指标降序取前 10 条（过滤 0 值）
const mapTopItems = computed(() => {
  if (!showMapTable.value) return []
  const { field } = METRIC_MAP[dataMetric.value]
  return [...chartItems.value]
    .filter(i => (i[field] ?? 0) > 0)
    .sort((a, b) => (b[field] ?? 0) - (a[field] ?? 0))
    .slice(0, 10)
})

// 图表类型切换：仅重渲，不重新请求数据
watch(chartType,       () => renderChart())
watch(dataMetric,      () => renderChart())
// 对比模式切换（同比/环比）→ 仅重渲
watch(comparisonMode,  () => { if (groupBy.value === 'date') renderChart() })
// 时间粒度切换（在时间维度下）→ 重新请求数据
watch(selectedPeriod,  () => { if (groupBy.value === 'date') loadChartData() })
// 产品/渠道/地域筛选变化 → 自动刷新图表
watch(
  () => [
    filters.value.categoryIds, filters.value.seriesIds,  filters.value.modelIds,
    filters.value.channelNames, filters.value.channelCodes,
    filters.value.provinces,   filters.value.cities,     filters.value.districts,
  ],
  () => loadChartData(),
  { deep: true }
)
// 日期变化 → 重新加载筛选候选（图表需点击查询才更新）
watch(() => filters.value.dateRange, () => loadOptions(), { deep: true })
// groupBy 切换时，自动重置不合法的图表类型 / 对比模式；地域维度默认使用地图
watch(groupBy, () => {
  const allowed  = allowedChartTypes.value
  const defType  = GROUPBY_ALLOWED[groupBy.value]?.default ?? null
  if (!allowed.includes(chartType.value)) {
    chartType.value = defType
  } else if (defType && defType !== chartType.value) {
    chartType.value = defType
  }
  if (comparisonMode.value && !allowedComparisons.value.includes(comparisonMode.value)) {
    comparisonMode.value = null
  }
  // 切换到时间维度时，默认激活同比
  if (groupBy.value === 'date' && !comparisonMode.value) {
    comparisonMode.value = 'yoy'
  }
})
</script>

<template>
  <div class="dashboard-root">

    <!-- ── 左侧筛选面板 ──────────────────────────── -->
    <aside class="filter-panel">

      <!-- 查询 + 分组管理 -->
      <div class="panel-top-btns">
        <button class="btn-query" @click="handleQuery" :disabled="loadingChart">
          {{ loadingChart ? '查询中…' : '查询' }}
        </button>
        <button class="btn-group-mgr" @click="showGroupMgr = true" title="管理自定义分组">
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
            <el-date-picker v-model="filters.dateRange" type="daterange" range-separator="~"
              start-placeholder="开始日期" end-placeholder="结束日期"
              size="default" style="width:100%" :shortcuts="DATE_SHORTCUTS" />
            <el-segmented v-model="selectedPeriod" :options="PERIOD_OPTIONS" size="default" block />
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
            <!-- 产品分组芯片 -->
            <div v-if="productGroups.length > 0" class="group-chips-row">
              <span v-for="g in productGroups" :key="g.id"
                class="group-chip" :class="{ 'is-active': isGroupActive(g) }"
                :title="groupLevelLabel(g) + '：' + g.items.map(i => i.code || i.label || i.value).join('、')"
                @click="toggleGroup(g)">
                {{ g.name }}
              </span>
            </div>
            <div class="field-row">
              <div class="field-label">产品品类</div>
              <el-select v-model="filters.categoryIds" placeholder="全部品类"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%"
                :loading="loadingOptions" @change="onCategoryChange">
                <el-option v-for="opt in categoryOpts" :key="String(opt.value)"
                  :label="opt.label" :value="opt.value">
                  <span class="opt-main">{{ opt.label }}</span>
                  <span v-if="opt.sub" class="opt-sub">{{ opt.sub }}</span>
                </el-option>
              </el-select>
            </div>
            <div class="field-row">
              <div class="field-label">产品系列</div>
              <el-select v-model="filters.seriesIds" placeholder="全部系列"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%"
                :disabled="!seriesEnabled" @change="onSeriesChange">
                <el-option v-for="opt in seriesOpts" :key="String(opt.value)"
                  :label="opt.label" :value="opt.value">
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
                <el-option v-for="opt in modelOpts" :key="String(opt.value)"
                  :label="opt.label" :value="opt.value">
                  <span class="opt-main">{{ opt.label }}</span>
                  <span v-if="opt.sub" class="opt-sub">{{ opt.sub }}</span>
                </el-option>
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
            <!-- 渠道分组芯片 -->
            <div v-if="channelGroups.length > 0" class="group-chips-row">
              <span v-for="g in channelGroups" :key="g.id"
                class="group-chip" :class="{ 'is-active': isGroupActive(g) }"
                :title="groupLevelLabel(g) + '：' + g.items.map(i => i.label || i.value).join('、')"
                @click="toggleGroup(g)">
                {{ g.name }}
              </span>
            </div>
            <div class="field-row">
              <div class="field-label">渠道</div>
              <el-select v-model="filters.channelNames" placeholder="全部渠道"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%"
                @change="filters.channelCodes = []">
                <el-option v-for="opt in channelOpts" :key="String(opt.value)"
                  :label="opt.label" :value="opt.value">
                  <span class="opt-main">{{ opt.label }}</span>
                </el-option>
              </el-select>
            </div>
            <div class="field-row">
              <div class="field-label">渠道商</div>
              <el-select v-model="filters.channelCodes" placeholder="全部渠道商"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%"
                :disabled="!orgEnabled">
                <el-option v-for="opt in orgOpts" :key="String(opt.value)"
                  :label="opt.label" :value="opt.value">
                  <span class="opt-main">{{ opt.label }}</span>
                  <span v-if="opt.sub" class="opt-sub">{{ opt.sub }}</span>
                </el-option>
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
            <!-- 地域分组芯片 -->
            <div v-if="regionGroups.length > 0" class="group-chips-row">
              <span v-for="g in regionGroups" :key="g.id"
                class="group-chip" :class="{ 'is-active': isGroupActive(g) }"
                :title="groupLevelLabel(g) + '：' + g.items.map(i => i.value).join('、')"
                @click="toggleGroup(g)">
                {{ g.name }}
              </span>
            </div>
            <div class="field-row">
              <div class="field-label">省份</div>
              <el-select v-model="filters.provinces" placeholder="全部省份"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%"
                @change="filters.cities = []; filters.districts = []">
                <el-option v-for="opt in provinceOpts" :key="String(opt.value)"
                  :label="opt.label" :value="opt.value">
                  <span class="opt-main">{{ opt.label }}</span>
                </el-option>
              </el-select>
            </div>
            <div class="field-row">
              <div class="field-label">城市</div>
              <el-select v-model="filters.cities" placeholder="全部城市"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%"
                :disabled="!cityEnabled"
                @change="filters.districts = []">
                <el-option v-for="opt in cityOpts" :key="String(opt.value)"
                  :label="opt.label" :value="opt.value">
                  <span class="opt-main">{{ opt.label }}</span>
                </el-option>
              </el-select>
            </div>
            <div class="field-row">
              <div class="field-label">县区</div>
              <el-select v-model="filters.districts" placeholder="全部县区"
                multiple filterable collapse-tags collapse-tags-tooltip
                clearable size="default" style="width:100%"
                :disabled="!districtEnabled">
                <el-option v-for="opt in districtOpts" :key="String(opt.value)"
                  :label="opt.label" :value="opt.value">
                  <span class="opt-main">{{ opt.label }}</span>
                  <span v-if="opt.sub" class="opt-sub">{{ opt.sub }}</span>
                </el-option>
              </el-select>
            </div>
          </div>
        </div>
      </div>

      <button class="btn-reset" @click="resetFilters">重置筛选</button>

    </aside>

    <!-- ── 右侧内容区 ──────────────────────────────── -->
    <div class="content-panel">

      <!-- 顶部：图表类型图标 + 竖线 + 同比/环比 | 最右侧：数据指标选择 -->
      <div class="chart-toolbar">
        <!-- 左侧：面包屑（有下钻时显示），无下钻时占位保证中间居中 -->
        <div class="ct-left">
          <div v-if="drillStack.length" class="drill-breadcrumb">
            <span class="bc-item bc-link" @click="drillBack(0)">index</span>
            <template v-for="(entry, i) in drillStack" :key="i">
              <span class="bc-sep">/</span>
              <span
                v-if="i < drillStack.length - 1"
                class="bc-item bc-link"
                @click="drillBack(i + 1)"
              >{{ entry.label }}</span>
              <span v-else class="bc-item bc-current">{{ entry.label }}</span>
            </template>
          </div>
        </div>

        <!-- 中间：图表类型 + 同比/环比 -->
        <div class="ct-center">
          <!-- 柱状 -->
          <button class="ct-btn" :class="{ active: chartType === 'bar', disabled: !allowedChartTypes.includes('bar') }"
            :disabled="!allowedChartTypes.includes('bar')" title="柱状图" @click="chartType = 'bar'">
            <img :src="iconBar" width="28" height="28" alt="柱状图" />
          </button>
          <!-- 折线 -->
          <button class="ct-btn" :class="{ active: chartType === 'line', disabled: !allowedChartTypes.includes('line') }"
            :disabled="!allowedChartTypes.includes('line')" title="折线图" @click="chartType = 'line'">
            <img :src="iconLine" width="28" height="28" alt="折线图" />
          </button>
          <!-- 饼图 -->
          <button class="ct-btn" :class="{ active: chartType === 'pie', disabled: !allowedChartTypes.includes('pie') }"
            :disabled="!allowedChartTypes.includes('pie')" title="饼图" @click="chartType = 'pie'">
            <img :src="iconPie" width="28" height="28" alt="饼图" />
          </button>
          <!-- 地图 -->
          <button class="ct-btn" :class="{ active: chartType === 'map', disabled: !allowedChartTypes.includes('map') }"
            :disabled="!allowedChartTypes.includes('map')" title="地图" @click="chartType = 'map'">
            <img :src="iconMap" width="28" height="28" alt="地图" />
          </button>

          <span class="ct-divider"></span>

          <!-- 同比 -->
          <button class="ct-btn ct-btn--labeled" :class="{ active: comparisonMode === 'yoy', disabled: !allowedComparisons.includes('yoy') }"
            :disabled="!allowedComparisons.includes('yoy')" @click="toggleComparison('yoy')">
            <img :src="iconYoy" width="28" height="28" alt="同比" />
            <span class="ct-label">同比</span>
          </button>
          <!-- 环比 -->
          <button class="ct-btn ct-btn--labeled" :class="{ active: comparisonMode === 'mom', disabled: !allowedComparisons.includes('mom') }"
            :disabled="!allowedComparisons.includes('mom')" @click="toggleComparison('mom')">
            <img :src="iconMom" width="28" height="28" alt="环比" />
            <span class="ct-label">环比</span>
          </button>
        </div>

        <!-- 右侧：数据指标选择 -->
        <div class="ct-right">
          <el-select v-model="dataMetric" size="default" class="metric-select" style="width: 150px">
            <el-option v-for="m in METRIC_OPTIONS" :key="m.value" :label="m.label" :value="m.value" />
          </el-select>
        </div>
      </div>

      <!-- 中间：图表 -->
      <div v-loading="loadingChart" class="chart-wrap" :class="{ 'chart-wrap--with-table': showMapTable }" @contextmenu.prevent>
        <div ref="chartEl" class="chart-canvas"></div>

        <!-- 地域维度地图：右侧 Top10 排行表 -->
        <div v-if="showMapTable" class="map-rank-panel">
          <div class="map-rank-title">{{ METRIC_MAP[dataMetric].label }} Top 10</div>
          <div class="map-rank-list">
            <div v-for="(item, idx) in mapTopItems" :key="item.label" class="map-rank-row">
              <span class="map-rank-no" :class="{ 'top3': idx < 3 }">{{ idx + 1 }}</span>
              <span class="map-rank-name">{{ item.label }}</span>
              <span class="map-rank-val">{{ item[METRIC_MAP[dataMetric].field] }}</span>
            </div>
            <div v-if="mapTopItems.length === 0" class="map-rank-empty">暂无数据</div>
          </div>
        </div>
      </div>

      <!-- 底部：类别选择 -->
      <div class="chart-footer">
        <button v-for="opt in GROUP_BY_OPTIONS" :key="opt.value"
          class="gb-btn" :class="{ active: groupBy === opt.value }"
          @click="groupBy = opt.value; loadChartData()">
          <img :src="opt.icon" width="28" height="28" :alt="opt.label" />
          <span class="gb-label">{{ opt.label }}</span>
        </button>
      </div>

    </div>

    <!-- ── 分组管理弹窗 ──────────────────────────────── -->
    <el-dialog v-model="showGroupMgr" title="管理自定义分组" width="520px" :close-on-click-modal="false">

      <!-- 现有分组列表 -->
      <div class="mgr-group-list">
        <div v-if="customGroups.length === 0" class="mgr-empty">暂无分组，在下方新建</div>
        <div v-for="g in customGroups" :key="g.id" class="mgr-group-item">
          <div class="mgr-group-info">
            <div class="mgr-group-name-row">
              <span class="mgr-dim-tag" :style="{ background: DIM_COLORS[g.dimension]+'22', color: DIM_COLORS[g.dimension] }">
                {{ DIM_LABELS[g.dimension] }}
              </span>
              <span class="mgr-group-name">{{ g.name }}</span>
            </div>
            <span class="mgr-group-meta">
              {{ groupLevelLabel(g) }} · {{ g.items.map(i => i.code || i.label || i.value).join('、') }}
            </span>
          </div>
          <button class="mgr-del-btn" @click="deleteGroup(g.id)" title="删除">
            <el-icon><Delete /></el-icon>
          </button>
        </div>
      </div>

      <!-- 新建分组表单 -->
      <div class="mgr-divider">新建分组</div>
      <div class="mgr-form">

        <div class="mgr-field">
          <div class="mgr-label">分组名称</div>
          <el-input v-model="newGroup.name" placeholder="如：华东三省、北欧家具" size="default" />
        </div>

        <div class="mgr-field">
          <div class="mgr-label">分组维度</div>
          <el-radio-group v-model="newGroup.dimension" @change="onNewGroupDimensionChange">
            <el-radio-button value="product">产品</el-radio-button>
            <el-radio-button value="channel">渠道</el-radio-button>
            <el-radio-button value="region">地域</el-radio-button>
          </el-radio-group>
        </div>

        <div class="mgr-field">
          <div class="mgr-label">分组层级</div>
          <el-radio-group v-model="newGroup.level" @change="onNewGroupLevelChange">
            <el-radio-button v-for="opt in newGroupLevelOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </el-radio-button>
          </el-radio-group>
        </div>

        <div v-if="needParentCategory" class="mgr-field">
          <div class="mgr-label">所属品类</div>
          <el-select v-model="newGroup.parentCategoryId" placeholder="选择品类"
            filterable clearable size="default" style="width:100%" @change="onNewGroupCategoryChange">
            <el-option v-for="c in categoryTree" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </div>

        <div v-if="needParentSeries" class="mgr-field">
          <div class="mgr-label">所属系列</div>
          <el-select v-model="newGroup.parentSeriesId" placeholder="选择系列"
            filterable clearable size="default" style="width:100%"
            :disabled="!newGroup.parentCategoryId" @change="onNewGroupSeriesChange">
            <el-option v-for="s in newGroupSeriesOptions" :key="s.id" :label="s.code" :value="s.id">
              <span class="opt-main">{{ s.code }}</span><span class="opt-sub">{{ s.name }}</span>
            </el-option>
          </el-select>
        </div>

        <div v-if="needParentChannel" class="mgr-field">
          <div class="mgr-label">所属渠道</div>
          <el-select v-model="newGroup.parentChannelName" placeholder="选择渠道"
            filterable clearable size="default" style="width:100%" @change="onNewGroupChannelChange">
            <el-option v-for="c in channelOptions" :key="c.name" :label="c.name" :value="c.name" />
          </el-select>
        </div>

        <div v-if="needParentProvince" class="mgr-field">
          <div class="mgr-label">所属省份</div>
          <el-select v-model="newGroup.parentProvince" placeholder="选择省份"
            filterable clearable size="default" style="width:100%" @change="onNewGroupProvinceChange">
            <el-option v-for="p in provinceOptions" :key="p.name" :label="p.name" :value="p.name" />
          </el-select>
        </div>

        <div v-if="needParentCity" class="mgr-field">
          <div class="mgr-label">所属城市</div>
          <el-select v-model="newGroup.parentCity" placeholder="选择城市"
            filterable clearable size="default" style="width:100%"
            :disabled="!newGroup.parentProvince" @change="onNewGroupCityChange">
            <el-option v-for="c in newGroupCityOptions" :key="c.name" :label="c.name" :value="c.name" />
          </el-select>
        </div>

        <div class="mgr-field">
          <div class="mgr-label">
            {{ { category:'选择品类', series:'选择系列', model:'选择型号',
                 channel:'选择渠道', channel_code:'选择渠道商',
                 province:'选择省份', city:'选择城市', district:'选择县区' }[newGroup.level] }}
            <span class="mgr-label-hint">（至少选 2 项）</span>
          </div>
          <el-select v-if="newGroup.dimension === 'product'"
            v-model="newGroup.selectedIds"
            placeholder="请选择" multiple filterable collapse-tags collapse-tags-tooltip
            clearable size="default" style="width:100%" :disabled="itemSelectDisabled">
            <el-option v-for="item in newGroupItemOptions" :key="item.id" :label="item.label" :value="item.id" />
          </el-select>
          <el-select v-else
            v-model="newGroup.selectedValues"
            placeholder="请选择" multiple filterable collapse-tags collapse-tags-tooltip
            clearable size="default" style="width:100%" :disabled="itemSelectDisabled">
            <el-option v-for="item in newGroupItemOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </div>

        <div class="mgr-actions">
          <button class="btn-save-group" @click="saveNewGroup">保存分组</button>
        </div>
      </div>
    </el-dialog>

  </div>
</template>

<style scoped>
.dashboard-root {
  flex: 1; min-height: 0;
  display: flex; overflow: hidden;
  font-family: var(--font-family);
  padding: 5px; gap: 4px;
}

/* ── 筛选面板 ─────────────────────────────────── */
.filter-panel {
  width: 280px; flex-shrink: 0;
  background: transparent;
  overflow-y: auto; overflow-x: hidden;
  padding: 5px;
  display: flex; flex-direction: column; gap: 5px;
}

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
.btn-group-mgr {
  height: 36px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 8px;
  background: var(--bg-card); color: var(--text-muted);
  font-size: 12px; font-family: var(--font-family);
  cursor: pointer; display: flex; align-items: center; gap: 4px;
  transition: all 0.15s; white-space: nowrap;
}
.btn-group-mgr:hover { border-color: var(--accent); color: var(--accent); }

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

.btn-reset {
  width: 100%; padding: 9px;
  border: 1px solid var(--border); border-radius: 8px;
  background: transparent; color: var(--text-muted);
  font-size: 12px; font-family: var(--font-family);
  cursor: pointer; transition: all 0.15s; flex-shrink: 0;
}
.btn-reset:hover { border-color: var(--accent); color: var(--accent); }

/* ── 下拉选项 ──────────────────────────────────── */
.opt-main  { font-size: 12px; color: var(--text-primary); }
.opt-sub   { font-size: 11px; color: var(--text-muted); margin-left: 6px; }

/* ── 右侧内容区 ───────────────────────────────── */
.content-panel { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: 8px; overflow: hidden; }

/* 顶部工具栏：无卡片，三段式（左占位 | 中居中 | 右指标） */
.chart-toolbar {
  flex-shrink: 0;
  display: flex; align-items: center;
  padding: 2px 0;
}
.ct-left   { flex: 1; display: flex; align-items: center; }
.ct-center { display: flex; align-items: center; gap: 3px; }
.ct-right  { flex: 1; display: flex; align-items: center; justify-content: flex-end; }

/* 下钻面包屑 */
.drill-breadcrumb { display: flex; align-items: center; gap: 4px; font-size: 14px; }
.bc-sep  { color: #b0a090; }
.bc-item { padding: 2px 4px; border-radius: 4px; white-space: nowrap; }
.bc-link { color: #3a7bc8; cursor: pointer; }
.bc-link:hover { text-decoration: underline; background: rgba(58,123,200,0.08); }
.bc-current { color: #3a3028; font-weight: 600; }
:deep(.metric-select .el-input__wrapper) { height: 32px; }
:deep(.metric-select .el-input__inner) { height: 32px; line-height: 32px; }
.ct-btn {
  height: 36px; padding: 0 6px; border: none; background: transparent;
  border-radius: 8px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.15s;
}
.ct-btn--labeled { gap: 4px; padding: 0 10px; }
.ct-btn img { opacity: 0.55; transition: opacity 0.15s; }
.ct-btn:hover:not(:disabled) { background: var(--border); }
.ct-btn:hover:not(:disabled) img { opacity: 0.8; }
.ct-btn.active { background: color-mix(in srgb, #c4883a 12%, transparent); }
.ct-btn.active img { opacity: 1; }
.ct-btn.disabled { opacity: 0.25; cursor: not-allowed; }
.ct-label { font-size: 15px; color: #2c2420; transition: color 0.15s; white-space: nowrap; }
.ct-btn:hover .ct-label { color: #000; }
.ct-btn.active .ct-label { color: #c4883a; font-weight: 500; }
.ct-divider { width: 1px; height: 20px; background: var(--border); margin: 0 4px; }

/* 图表区 */
.chart-wrap { flex: 1; min-height: 0; background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; position: relative; }
.chart-wrap--with-table { display: flex; }
.chart-canvas { width: 100%; height: 100%; }
.chart-wrap--with-table .chart-canvas { flex: 1; min-width: 0; width: auto; }

/* 地图 Top10 侧边表格 */
.map-rank-panel {
  width: 190px; flex-shrink: 0;
  border-left: 1px solid var(--border);
  display: flex; flex-direction: column;
  padding: 12px 0;
  background: var(--bg-card);
}
.map-rank-title {
  font-size: 12px; font-weight: 600; color: var(--text-secondary);
  padding: 0 14px 8px; border-bottom: 1px solid var(--border);
  letter-spacing: 0.5px;
}
.map-rank-list { flex: 1; overflow-y: auto; padding: 4px 0; }
.map-rank-row {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 14px;
  font-size: 12px; color: var(--text-primary);
  transition: background 0.12s;
}
.map-rank-row:hover { background: var(--bg-page); }
.map-rank-no {
  width: 18px; height: 18px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 600; flex-shrink: 0;
  background: var(--border); color: var(--text-muted);
}
.map-rank-no.top3 { background: var(--accent); color: #fff; }
.map-rank-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.map-rank-val { font-weight: 600; color: var(--accent); font-variant-numeric: tabular-nums; }
.map-rank-empty { padding: 20px 14px; color: var(--text-muted); font-size: 12px; text-align: center; }

/* 底部类别选择 */
.chart-footer {
  flex-shrink: 0;
  display: flex; justify-content: center; gap: 4px;
  padding: 2px 0;
}
.gb-btn {
  display: flex; flex-direction: row; align-items: center; justify-content: center;
  gap: 6px; padding: 6px 14px;
  border: none; background: transparent; border-radius: 10px; cursor: pointer;
  transition: background 0.15s;
}
.gb-btn img { opacity: 0.55; transition: opacity 0.15s; }
.gb-btn:hover { background: var(--border); }
.gb-btn:hover img { opacity: 0.8; }
.gb-btn.active { background: color-mix(in srgb, #c4883a 12%, transparent); }
.gb-btn.active img { opacity: 1; }
.gb-label { font-size: 15px; color: #2c2420; white-space: nowrap; transition: color 0.15s; }
.gb-btn:hover .gb-label { color: #000; }
.gb-btn.active .gb-label { color: #c4883a; font-weight: 500; }

:deep(.el-date-editor--daterange) { width: 100% !important; }

/* ── 分组芯片行 ──────────────────────────────── */
.group-chips-row { display: flex; flex-wrap: wrap; gap: 5px; }
.group-chip {
  padding: 3px 9px; border-radius: 20px;
  border: 1px solid var(--border);
  font-size: 11px; cursor: pointer;
  background: var(--bg-card); color: var(--text-muted);
  transition: all 0.15s; user-select: none;
}
.group-chip:hover { border-color: var(--accent); color: var(--accent); }
.group-chip.is-active { background: var(--accent); border-color: var(--accent); color: #fff; }

/* ── 分组管理弹窗 ─────────────────────────────── */
.mgr-group-list { min-height: 32px; margin-bottom: 4px; }
.mgr-empty { font-size: 12px; color: var(--text-muted); text-align: center; padding: 12px 0; }
.mgr-group-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border); }
.mgr-group-item:last-child { border-bottom: none; }
.mgr-group-info { display: flex; flex-direction: column; gap: 3px; min-width: 0; flex: 1; }
.mgr-group-name-row { display: flex; align-items: center; gap: 6px; }
.mgr-dim-tag { font-size: 10px; padding: 1px 6px; border-radius: 10px; font-weight: 500; flex-shrink: 0; }
.mgr-group-name { font-size: 13px; color: var(--text-primary); font-weight: 500; }
.mgr-group-meta { font-size: 11px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 420px; }
.mgr-del-btn {
  flex-shrink: 0; width: 28px; height: 28px;
  border: none; background: transparent; color: var(--text-muted);
  cursor: pointer; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s; font-size: 14px;
}
.mgr-del-btn:hover { background: #fee; color: #d05a3c; }
.mgr-divider { font-size: 12px; font-weight: 600; color: var(--text-secondary); padding: 14px 0 8px; border-top: 1px solid var(--border); margin-top: 8px; letter-spacing: 0.02em; }
.mgr-form { display: flex; flex-direction: column; gap: 12px; }
.mgr-field { display: flex; flex-direction: column; gap: 6px; }
.mgr-label { font-size: 11px; color: var(--text-muted); }
.mgr-label-hint { font-size: 10px; color: var(--text-muted); opacity: 0.7; margin-left: 4px; }
.mgr-actions { display: flex; justify-content: flex-end; padding-top: 4px; }
.btn-save-group {
  padding: 8px 20px; border: none; border-radius: 8px;
  background: var(--accent); color: #fff;
  font-size: 13px; font-family: var(--font-family);
  cursor: pointer; transition: background 0.15s;
}
.btn-save-group:hover { background: var(--accent-hover); }
</style>
