<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, reactive, computed, watch, onMounted, onUnmounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown, Delete, Setting, Close } from '@element-plus/icons-vue'
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
const PROVINCE_MAP_MODULES = import.meta.glob('../../assets/maps/*.json')

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

/** 加载并注册全国城市级地图，返回 mapKey 或 null */
async function ensureChinaCityMap() {
  if (registeredMaps.has('china-city')) return 'china-city'
  const loader = findLoader('china-city')
  if (!loader) { ElMessage.error('城市地图数据未找到，请将 china-city.json 放入 src/assets/maps/ 目录'); return null }
  try {
    const mod = await loader()
    echarts.registerMap('china-city', mod.default)
    registeredMaps.add('china-city')
    return 'china-city'
  } catch {
    ElMessage.error('城市地图数据加载失败')
    return null
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

  if (groupBy.value === 'province') {
    // 城市模式：加载全国城市级地图
    if (cityMode.value) {
      const key = await ensureChinaCityMap()
      if (key) return key
    }
    // 筛选了单一省份：加载省份地图
    const provs = expandStrSel(filters.value.provinces)
    if (provs.length === 1) {
      const fullName = PROVINCE_NAME_MAP[provs[0]] ?? provs[0]
      const adcode   = PROVINCE_ADCODE[fullName]
      if (adcode) {
        const key = await ensureProvinceMap(adcode)
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
const cityMode       = ref(false)    // 城市模式：地域维度下直接按城市聚合并显示全国城市地图
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
      if (cityMode.value) return 'city'   // 城市模式：始终按城市聚合
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

// 配置方案（一组激活分组的快照）
const groupPresets    = ref([])   // [{ id, name, groupIds }]
const newPresetName   = ref('')

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
function loadPresetsFromStorage() {
  try {
    const raw = localStorage.getItem('shipping_group_presets')
    groupPresets.value = raw ? JSON.parse(raw) : []
  } catch { groupPresets.value = [] }
}
function savePresetsToStorage() {
  localStorage.setItem('shipping_group_presets', JSON.stringify(groupPresets.value))
}

// 按维度分组
const productGroups = computed(() => customGroups.value.filter(g => g.dimension === 'product'))
const channelGroups = computed(() => customGroups.value.filter(g => g.dimension === 'channel'))
const regionGroups  = computed(() => customGroups.value.filter(g => g.dimension === 'region'))

// 数据库实际发货日期范围文本
const dateRangeText = computed(() => {
  if (!dataDateMin.value || !dataDateMax.value) return ''
  return `当前发货数据范围：${dataDateMin.value}～${dataDateMax.value}`
})

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
  // 城市模式下跨省选城市：展平所有省份的城市列表
  if (level === 'city' && cityMode.value) {
    return provinceOptions.value.flatMap(p => (p.cities || []).map(c => ({ value: c.name, label: `${p.name} / ${c.name}` })))
  }
  const prov = provinceOptions.value.find(p => p.name === parentProvince)
  if (level === 'city') return (prov?.cities || []).map(c => ({ value: c.name, label: c.name }))
  const city = prov?.cities?.find(c => c.name === parentCity)
  return (city?.districts || []).map(d => ({ value: d, label: d }))
})

const needParentCategory = computed(() => newGroup.value.dimension === 'product' && ['series','model'].includes(newGroup.value.level))
const needParentSeries   = computed(() => newGroup.value.dimension === 'product' && newGroup.value.level === 'model')
const needParentChannel  = computed(() => newGroup.value.dimension === 'channel' && newGroup.value.level === 'channel_code')
const needParentProvince = computed(() => newGroup.value.dimension === 'region'  && ['city','district'].includes(newGroup.value.level) && !(newGroup.value.level === 'city' && cityMode.value))
const needParentCity     = computed(() => newGroup.value.dimension === 'region'  && newGroup.value.level === 'district')

const itemSelectDisabled = computed(() => {
  const { dimension, level, parentCategoryId, parentSeriesId, parentChannelName, parentProvince, parentCity } = newGroup.value
  if (dimension === 'product') {
    if (level === 'series' && !parentCategoryId) return true
    if (level === 'model'  && !parentSeriesId)   return true
  }
  if (dimension === 'channel' && level === 'channel_code' && !parentChannelName) return true
  if (dimension === 'region') {
    if (level === 'city'     && !parentProvince && !cityMode.value) return true
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
    if (level === 'city' && !cityMode.value) parent_context = { province: parentProvince }
    if (level === 'district')               parent_context = { province: parentProvince, city: parentCity }
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
  // 同步清理配置方案中对该分组的引用
  groupPresets.value.forEach(p => { p.groupIds = p.groupIds.filter(v => v !== id) })
  savePresetsToStorage()
}

/** 将当前激活的分组保存为配置方案 */
function savePreset() {
  const name = newPresetName.value.trim()
  if (!name) { ElMessage.warning('请输入方案名称'); return }
  if (activeGroupIds.value.length === 0) { ElMessage.warning('当前没有激活的分组'); return }
  groupPresets.value.push({ id: crypto.randomUUID(), name, groupIds: [...activeGroupIds.value] })
  savePresetsToStorage()
  newPresetName.value = ''
  ElMessage.success('配置方案已保存')
}

/** 应用配置方案（批量激活分组，过滤已删除的分组） */
function applyPreset(preset) {
  const validIds = preset.groupIds.filter(id => customGroups.value.some(g => g.id === id))
  activeGroupIds.value = validIds
  renderChart()
  ElMessage.success(`已应用方案「${preset.name}」`)
}

/** 删除配置方案 */
function deletePreset(id) {
  groupPresets.value = groupPresets.value.filter(p => p.id !== id)
  savePresetsToStorage()
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
// 数据库中实际的发货日期范围
const dataDateMin = ref('')
const dataDateMax = ref('')

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
const chartEl      = ref(null)
const chartWrapEl  = ref(null)   // chart-wrap 容器，全屏时用于归还 chartEl
let   chartInst    = null
let   resizeObs    = null
let   lpTimer      = null   // 移动端长按计时器
let   lpActive     = false  // 长按是否仍有效
let   _chartTimer  = null   // 筛选防抖计时器

// ── 全屏 ──────────────────────────────────────────
const isFullscreen = ref(false)
const fsPortrait   = ref(false)  // 进入全屏时是否为竖屏

async function openFullscreen() {
  fsPortrait.value   = window.innerWidth < window.innerHeight
  isFullscreen.value = true
  await nextTick()
  // 把 ECharts canvas 移入全屏容器
  const slot = document.querySelector('.fs-chart-slot')
  if (slot && chartEl.value) slot.appendChild(chartEl.value)
  requestAnimationFrame(() => chartInst?.resize())
  // Android 尝试原生全屏（不锁定朝向，允许用户自由旋转）
  try { await document.documentElement.requestFullscreen?.() } catch {}
}

async function closeFullscreen() {
  // 归还 chartEl 到 chart-wrap（prepend 保持在 map-rank-panel 之前）
  if (chartWrapEl.value && chartEl.value) chartWrapEl.value.prepend(chartEl.value)
  isFullscreen.value = false
  await nextTick()
  requestAnimationFrame(() => chartInst?.resize())
  try { document.fullscreenElement && await document.exitFullscreen?.() } catch {}
}

function onFsKeydown(e) {
  if (e.key === 'Escape' && isFullscreen.value) closeFullscreen()
}

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  loadGroupsFromStorage()
  loadPresetsFromStorage()
  await loadOptions()       // 先加载选项（categoryTree 等），effectiveGroupBy 依赖它
  await loadChartData()     // 再加载图表，此时 effectiveGroupBy 已能正确推导层级
  initChart()
})
onUnmounted(() => {
  resizeObs?.disconnect()
  if (chartInst) { chartInst.dispose(); chartInst = null }
  clearTimeout(lpTimer)
  try { document.fullscreenElement && document.exitFullscreen?.() } catch {}
})

// 移动端适配
const isMobile       = ref(window.innerWidth <= 768)
const filterPanelOpen = ref(false)

function onWindowResize() {
  isMobile.value = window.innerWidth <= 768
  // 全屏中实时跟踪朝向，手机转横屏后取消旋转变换
  if (isFullscreen.value) fsPortrait.value = window.innerWidth < window.innerHeight
}
onMounted(() => {
  window.addEventListener('resize', onWindowResize)
  window.addEventListener('keydown', onFsKeydown)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onWindowResize)
  window.removeEventListener('keydown', onFsKeydown)
})

// iOS Safari 固定定位滚动修复：筛选面板打开时锁定 body 位置
watch(filterPanelOpen, (open) => {
  if (!isMobile.value || window.electronAPI) return
  document.body.style.position = open ? 'fixed' : ''
  document.body.style.width    = open ? '100%' : ''
})

// ── 方法 ──────────────────────────────────────────

function handleQuery() { loadChartData() }
function toggleSection(key) { sections[key] = !sections[key] }

function onCategoryChange() { filters.value.seriesIds = []; filters.value.modelIds = [] }
function onSeriesChange()   { filters.value.modelIds = [] }

function toggleComparison(mode) {
  comparisonMode.value = comparisonMode.value === mode ? null : mode
}

// 移动端维度切换（el-select @change 调用）
function onMobileDimChange(val) {
  if (val !== 'province') cityMode.value = false
  loadChartData()
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

/** 分组下钻：右击激活分组条目，展开分组成员的明细数据 */
function drillDownGroup(group) {
  const savedFilters = {
    categoryIds:   [...filters.value.categoryIds],
    seriesIds:     [...filters.value.seriesIds],
    modelIds:      [...filters.value.modelIds],
    channelNames:  [...filters.value.channelNames],
    channelCodes:  [...filters.value.channelCodes],
    provinces:     [...filters.value.provinces],
    cities:        [...filters.value.cities],
    districts:     [...filters.value.districts],
  }
  const savedActiveGroupIds = [...activeGroupIds.value]
  drillStack.value.push({ label: group.name, savedFilters, savedActiveGroupIds })

  // 下钻后把该分组移出激活列表，否则 mergeGroupedItems 会把成员重新合并回去
  activeGroupIds.value = activeGroupIds.value.filter(id => id !== group.id)

  const level = group.level
  const pc = group.parent_context || {}
  if (level === 'category') {
    filters.value.categoryIds = group.items.map(i => i.id)
    filters.value.seriesIds   = []
    filters.value.modelIds    = []
  } else if (level === 'series') {
    // 保持父品类筛选，effectiveGroupBy 才能推导到 series 层
    if (pc.category_id) filters.value.categoryIds = [pc.category_id]
    filters.value.seriesIds = group.items.map(i => i.id)
    filters.value.modelIds  = []
  } else if (level === 'model') {
    if (pc.category_id) filters.value.categoryIds = [pc.category_id]
    if (pc.series_id)   filters.value.seriesIds   = [pc.series_id]
    filters.value.modelIds = group.items.map(i => i.id)
  } else if (level === 'channel') {
    filters.value.channelNames = group.items.map(i => i.value)
    filters.value.channelCodes = []
  } else if (level === 'channel_code') {
    // 保持父渠道筛选，effectiveGroupBy 才能推导到 channel_code 层
    if (pc.channel_name) filters.value.channelNames = [pc.channel_name]
    filters.value.channelCodes = group.items.map(i => i.value)
  } else if (level === 'province') {
    filters.value.provinces = group.items.map(i => i.value)
    filters.value.cities    = []
    filters.value.districts = []
  } else if (level === 'city') {
    // 跨省分组（city mode）不设 province 筛选；同省分组设父省
    if (pc.province) filters.value.provinces = [pc.province]
    filters.value.cities    = group.items.map(i => i.value)
    filters.value.districts = []
  } else if (level === 'district') {
    if (pc.province) filters.value.provinces = [pc.province]
    if (pc.city)     filters.value.cities    = [pc.city]
    filters.value.districts = group.items.map(i => i.value)
  }
  loadChartData()
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
  const { savedFilters, savedActiveGroupIds } = drillStack.value[idx]
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
  if (savedActiveGroupIds) activeGroupIds.value = savedActiveGroupIds
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
      if (optRes.data.data_date_min) dataDateMin.value = optRes.data.data_date_min
      if (optRes.data.data_date_max) dataDateMax.value = optRes.data.data_date_max
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
function _createChartInst() {
  if (chartInst) return
  const el = chartEl.value
  if (!el?.offsetWidth || !el?.offsetHeight) return
  chartInst = echarts.init(el, null, { renderer: 'canvas' })
  // 桌面端：右键下钻
  chartInst.on('contextmenu', (params) => {
    params.event?.event?.preventDefault?.()
    if (params.componentType !== 'series' || !['bar', 'pie'].includes(params.seriesType)) return
    const label = params.name
    const hitGroup = customGroups.value.find(
      g => activeGroupIds.value.includes(g.id) && g.name === label
    )
    if (hitGroup) drillDownGroup(hitGroup)
    else drillDown(label)
  })
  // 移动端：长按 1s 下钻（触屏无右键）
  chartInst.on('mousedown', (params) => {
    if (!isMobile.value) return
    if (params.componentType !== 'series' || !['bar', 'pie'].includes(params.seriesType)) return
    const label = params.name
    lpActive = true
    lpTimer  = setTimeout(() => {
      if (!lpActive) return
      lpActive = false
      const hitGroup = customGroups.value.find(
        g => activeGroupIds.value.includes(g.id) && g.name === label
      )
      if (hitGroup) drillDownGroup(hitGroup)
      else drillDown(label)
    }, 1000)
  })
  chartInst.on('mouseup',    () => { clearTimeout(lpTimer); lpActive = false })
  chartInst.on('mousemove',  () => { clearTimeout(lpTimer); lpActive = false })
  chartInst.on('globalout',  () => { clearTimeout(lpTimer); lpActive = false })
  renderChart()
}

function initChart() {
  if (!chartEl.value) return
  resizeObs = new ResizeObserver(() => {
    if (chartInst) { chartInst.resize(); return }
    _createChartInst()
  })
  resizeObs.observe(chartEl.value)
  // Safari 保底：ResizeObserver 在 Safari 中可能首次以 0 尺寸触发后不再触发
  requestAnimationFrame(() => _createChartInst())
  setTimeout(() => _createChartInst(), 300)
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
  let opt
  if (groupBy.value === 'date') {
    const items = mergeGroupedItems(chartItems.value)
    opt = comparisonMode.value === 'mom' ? buildMomOption(items) : buildYoyOption(items)
  } else if (chartType.value === 'map') {
    // 地图模式：传原始 items，由 buildMapOption 内部处理分组着色
    const mapKey = await resolveMapKey()
    if (!mapKey) return
    opt = buildMapOption(chartItems.value, mapKey)
  } else {
    const items = mergeGroupedItems(chartItems.value)
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
// 手机端不显示工具区（操作空间不足）
function makeToolbox(withZoom = false) {
  if (isMobile.value) return { feature: {} }
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
          s += `<div style="margin-top:6px;padding-top:6px;border-top:1px solid #e0d4c0;color:#8a7a6a;font-size:12px">${isMobile.value ? '长按柱子查看详情' : '右击柱子查看详情'}</div>`
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
        labelLayout: { hideOverlap: true },
      },
      // 销退指标时额外显示「销退率」折线（销退量 / 发货量）
      ...(isReturn ? [{
        name: '销退率', type: 'line', data: returnRatioData, yAxisIndex: 1,
        smooth: true,
        lineStyle: { color: '#9c6fba', width: 2 },
        itemStyle: { color: '#9c6fba' },
        symbol: 'circle', symbolSize: 4,
        label: { show: true, position: 'top', color: '#9c6fba', fontFamily: FONT, fontSize: 13, fontWeight: 'bold', formatter: p => `${p.value}%` },
        labelLayout: { hideOverlap: true },
      }] : []),
      {
        name: '占比', type: 'line', data: pctData, yAxisIndex: 1,
        smooth: true,
        lineStyle: { color: '#e07c00', width: 2 },
        itemStyle: { color: '#e07c00' },
        symbol: 'circle', symbolSize: 4,
        label: { show: true, position: 'top', color: '#e07c00', fontFamily: FONT, fontSize: 13, fontWeight: 'bold', formatter: p => `${p.value}%` },
        labelLayout: { hideOverlap: true },
      },
      {
        name: '累计占比', type: 'line', data: cumulData, yAxisIndex: 1,
        smooth: true,
        lineStyle: { color: '#e05050', width: 1.5, type: 'dashed' },
        itemStyle: { color: '#e05050' },
        symbol: 'circle', symbolSize: 4,
        label: { show: true, position: 'top', color: '#c03030', fontFamily: FONT, fontSize: 13, fontWeight: 'bold', formatter: p => `${p.value}%` },
        labelLayout: { hideOverlap: true },
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
// 上图：每个期号（月/季）一条折线，X 轴 = 年份跨度（"24→25" 等）
// 下图：各年数量柱状，X 轴 = 期号
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

  const years = [...yearMap.keys()].sort()

  const YEAR_COLORS = ['#c4883a', '#4a8fc0', '#6ab47a', '#9c6fba', '#e07070', '#f0a030', '#50c0c0']

  // 柱状系列（下图）：每年一组，绑定 xAxisIndex:1
  const barSeries = years.map((yr, idx) => {
    const clr  = YEAR_COLORS[idx % YEAR_COLORS.length]
    const data = periodOrder.map(k => yearMap.get(yr)?.get(k) ?? 0)
    return {
      name: `${yr}年`,
      type: 'bar',
      xAxisIndex: 1,
      yAxisIndex: 1,   // yAxis[1] → gridIndex:1（下图）
      data,
      itemStyle: { color: clr, borderRadius: [2, 2, 0, 0] },
      label: {
        show: true, position: 'top', color: clr,
        fontFamily: FONT, fontSize: 12, fontWeight: 'bold', formatter: '{c}',
      },
    }
  })

  const titleText = `${buildChartTitle(label)} · 同比`
  const subtextStr = (() => {
    const [start, end] = filters.value.dateRange || []
    if (start && end) return `${formatDate(start)}  ~  ${formatDate(end)}`
    if (start) return `${formatDate(start)} 起`
    return '全部时间'
  })()

  // 只有 1 年：纯柱状单图
  if (years.length < 2) {
    return {
      backgroundColor: 'transparent',
      title: {
        text: titleText, subtext: subtextStr,
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
      },
      grid: { top: 116, left: 60, right: 30, bottom: 50 },
      xAxis: {
        type: 'category', data: xLabels,
        axisLabel: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13 },
        axisLine: { lineStyle: { color: '#e0d4c0' } },
        axisTick: { lineStyle: { color: '#e0d4c0' } },
      },
      yAxis: [{
        type: 'value', name: '数量（PCS）',
        nameTextStyle: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13 },
        axisLabel: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13 },
        splitLine: { lineStyle: { color: '#f0e8d8' } },
        axisLine: { show: true, lineStyle: { color: '#e0d4c0' } },
        axisTick: { show: true, lineStyle: { color: '#e0d4c0' } },
      }],
      series: barSeries.map(s => ({ ...s, xAxisIndex: 0, yAxisIndex: 0 })),
    }
  }

  // 2+ 年：上下双图布局
  // 上图：每年一条折线，X 轴 = 期号（与下图对齐），Y 轴 = 相对基准年的增长率
  // 基准年（最早年）增长率固定为 0，其他年份与基准年对比
  // 同比增长率：每年与上一年对比
  // series name 格式 "2025 vs 2024"，颜色与柱状图年份对齐
  // 面积图：平滑折线 + 半透明面积填充，正增长暖色、负增长冷色通过 visualMap 区分
  const rateSeries = years.slice(1).map((yr, idx) => {
    const prevYr   = years[idx]
    const colorIdx = idx + 1
    const clr = YEAR_COLORS[colorIdx % YEAR_COLORS.length]
    const rateData = periodOrder.map(k => {
      const prev = yearMap.get(prevYr)?.get(k) ?? 0
      const val  = yearMap.get(yr)?.get(k) ?? 0
      if (prev === 0) return null
      return Math.round((val - prev) / prev * 1000) / 10
    })
    return {
      name: `${yr}年`,
      type: 'line',
      xAxisIndex: 0,
      yAxisIndex: 0,
      data: rateData,
      smooth: true,
      connectNulls: false,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { color: clr, width: 2 },
      itemStyle: { color: clr },
      areaStyle: { color: clr, opacity: 0.15 },
      label: { show: false },
      emphasis: {
        label: {
          show: true, position: 'top',
          fontFamily: FONT, fontSize: 11, fontWeight: '600', color: clr,
          formatter: p => {
            if (p.value == null) return ''
            return p.value > 0 ? `▲${p.value}%` : p.value < 0 ? `▼${Math.abs(p.value)}%` : '0%'
          },
        },
      },
    }
  })

  // 只有一条增长率折线时，直接在图上显示数据标签（增长红色，下降蓝色，持平灰色）
  if (rateSeries.length === 1) {
    rateSeries[0].label = {
      show: true, position: 'top',
      fontFamily: FONT, fontSize: 11, fontWeight: '600',
      formatter: p => {
        if (p.value == null) return ''
        if (p.value > 0) return `{pos|▲${p.value}%}`
        if (p.value < 0) return `{neg|▼${Math.abs(p.value)}%}`
        return `{zero|0%}`
      },
      rich: {
        pos:  { color: '#d05a3c', fontFamily: FONT, fontSize: 11, fontWeight: '600' },
        neg:  { color: '#4a8fc0', fontFamily: FONT, fontSize: 11, fontWeight: '600' },
        zero: { color: '#8a7a6a', fontFamily: FONT, fontSize: 11, fontWeight: '600' },
      },
    }
  }

  return {
    backgroundColor: 'transparent',
    title: {
      text: titleText, subtext: subtextStr,
      left: 10, top: 16,
      textStyle:    { color: '#3a3028', fontFamily: FONT, fontSize: 14, fontWeight: '600' },
      subtextStyle: { color: '#8a7a6a', fontFamily: FONT, fontSize: 12 },
    },
    toolbox: makeToolbox(true),
    legend: {
      // 只显示年份项，排除 lollipop 茎系列（__stem__前缀）
      data: years.map(yr => `${yr}年`),
      top: 76, left: 'center', itemWidth: 18, itemHeight: 12, itemGap: 20,
      textStyle: { color: '#6b5e4e', fontFamily: FONT, fontSize: 13 },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      textStyle: { fontFamily: FONT },
      formatter(params) {
        const xLabel = params[0]?.name

        // 过滤茎系列，按年份合并数量（bar）和增长率（scatter）
        const yearMap2 = {}  // "2025年" → { marker, quantity, rate }
        for (const p of params) {
          if (p.seriesName.startsWith('__stem__')) continue
          const name = p.seriesName
          if (!yearMap2[name]) yearMap2[name] = { marker: p.marker }
          if (p.seriesType === 'bar')     yearMap2[name].quantity = p.value
          if (p.seriesType === 'line')    yearMap2[name].rate     = p.value
        }
        const sortedYears = Object.keys(yearMap2).sort()

        const cell = (val, align = 'right') =>
          `<td style="padding:1px 0 1px 14px;font-weight:600;text-align:${align};white-space:nowrap">${val}</td>`
        const rateStr = v => v == null ? '—' : v > 0 ? `▲${v}%` : v < 0 ? `▼${Math.abs(v)}%` : '0%'

        let s = `<div style="font-family:${FONT};font-size:13px">`
        s += `<div style="font-weight:600;color:#3a3028;font-size:14px;margin-bottom:6px">${xLabel}</div>`
        s += `<table style="border-collapse:collapse;width:100%">`

        // 表头
        s += `<tr style="color:#8a7a6a;font-size:12px;border-bottom:1px solid #e8dfd0">`
        s += `<th style="padding:0 0 4px;font-weight:400;text-align:left"></th>`
        s += `<th style="padding:0 0 4px 14px;font-weight:400;text-align:right">数量（PCS）</th>`
        s += `<th style="padding:0 0 4px 14px;font-weight:400;text-align:right">同比增长率</th>`
        s += `</tr>`

        // 数据行
        for (const yr of sortedYears) {
          const d = yearMap2[yr]
          const rateColor = d.rate == null ? '#8a7a6a' : d.rate > 0 ? '#e07070' : d.rate < 0 ? '#4a8fc0' : '#8a7a6a'
          s += `<tr style="line-height:1.9">`
          s += `<td style="white-space:nowrap">${d.marker}${yr}</td>`
          s += cell(d.quantity != null ? d.quantity : '—')
          s += `<td style="padding:1px 0 1px 14px;font-weight:600;text-align:right;color:${rateColor};white-space:nowrap">${rateStr(d.rate)}</td>`
          s += `</tr>`
        }

        s += `</table></div>`
        return s
      },
    },
    // 联动两图的 axisPointer，hover 任一图时两图同步高亮同一月份
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { top: 116, left: 60, right: 30, bottom: '68%' },  // [0] 上图：增长率
      { top: '37%', left: 60, right: 30, bottom: 50 },   // [1] 下图：数量
    ],
    xAxis: [
      {
        // [0] 上图 X 轴：与下图相同期号，隐藏标签（上下对齐）
        gridIndex: 0, type: 'category', data: xLabels,
        axisLabel: { show: false },
        axisTick:  { show: false },
        axisLine:  { lineStyle: { color: '#e0d4c0' } },
        splitLine: { show: false },
      },
      {
        // [1] 下图 X 轴：显示期号标签
        gridIndex: 1, type: 'category', data: xLabels,
        axisLabel: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13 },
        axisLine:  { lineStyle: { color: '#e0d4c0' } },
        axisTick:  { lineStyle: { color: '#e0d4c0' } },
      },
    ],
    yAxis: [
      {
        // [0] 上图增长率轴（gridIndex: 0）
        gridIndex: 0, type: 'value', name: '同比增长率',
        nameTextStyle: { color: '#7a5c3a', fontFamily: FONT, fontSize: 12 },
        axisLabel: { color: '#7a5c3a', fontFamily: FONT, fontSize: 12, formatter: '{value}%' },
        splitLine: { lineStyle: { color: '#f0e8d8' } },
        axisLine: { show: true, lineStyle: { color: '#e0d4c0' } },
        axisTick: { show: true, lineStyle: { color: '#e0d4c0' } },
      },
      {
        // [1] 下图数量轴（gridIndex: 1）
        gridIndex: 1, type: 'value', name: '数量（PCS）',
        nameTextStyle: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13 },
        axisLabel: { color: '#7a5c3a', fontFamily: FONT, fontSize: 13 },
        splitLine: { lineStyle: { color: '#f0e8d8' } },
        axisLine: { show: true, lineStyle: { color: '#e0d4c0' } },
        axisTick: { show: true, lineStyle: { color: '#e0d4c0' } },
      },
    ],
    series: [...rateSeries, ...barSeries],
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
  const isChina    = mapKey === 'china'
  const isCityMode = mapKey === 'china-city'

  // city 模式下，计算激活分组的城市归属与合计值
  const activeCityGroups = isCityMode
    ? customGroups.value.filter(g => activeGroupIds.value.includes(g.id) && g.level === 'city')
    : []
  // 城市原始 label → { groupName, groupTotal, selfField }
  const cityToGroup = new Map()
  for (const g of activeCityGroups) {
    const groupTotal = g.items.reduce((sum, it) => {
      const found = items.find(i => i.label === it.value)
      return sum + (found ? (found[field] ?? 0) : 0)
    }, 0)
    for (const it of g.items) {
      cityToGroup.set(it.value, { groupName: g.name, groupTotal })
    }
  }

  // 构建 data：分组成员共享分组合计值（→ 同色），非分组成员用自身值
  const data = items.map(i => {
    const mapName = isChina ? (PROVINCE_NAME_MAP[i.label] ?? i.label) : i.label
    const gInfo   = cityToGroup.get(i.label)
    return {
      name:         mapName,
      value:        gInfo ? gInfo.groupTotal : (i[field] ?? 0),
      originalName: i.label,
      selfValue:    i[field] ?? 0,
      groupName:    gInfo ? gInfo.groupName  : null,
      groupTotal:   gInfo ? gInfo.groupTotal : null,
    }
  })
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
        const d = params.data
        const W = `font-family:${FONT};font-size:13px;min-width:150px`
        const ROW = `display:flex;justify-content:space-between;align-items:center;gap:20px;line-height:1.8`
        if (d?.groupName) {
          // 分组成员：显示分组合计 + 本城市自身值
          return `<div style="${W}">` +
            `<div style="font-weight:600;margin-bottom:2px;color:#c4883a">${d.groupName}</div>` +
            `<div style="${ROW};margin-bottom:2px"><span>${label}合计</span><span style="font-weight:600">${d.groupTotal}</span></div>` +
            `<div style="border-top:1px solid #e0d4c0;margin:4px 0"></div>` +
            `<div style="color:#6b5e4e;margin-bottom:2px">${d.originalName}</div>` +
            `<div style="${ROW}"><span>${label}</span><span style="font-weight:600">${d.selfValue}</span></div>` +
            `</div>`
        }
        const name = d?.originalName ?? params.name
        return `<div style="${W}">` +
          `<div style="font-weight:600;margin-bottom:4px">${name}</div>` +
          `<div style="${ROW}"><span>${label}</span><span style="font-weight:600">${params.value}</span></div>` +
          `</div>`
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
      label: { show: mapKey !== 'china-city', fontFamily: FONT, fontSize: 11, color: '#3a3028' },
      emphasis:  { label: { show: mapKey !== 'china-city', fontFamily: FONT, fontSize: 12, fontWeight: 'bold' }, itemStyle: { areaColor: '#e09050' } },
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
// 产品/渠道/地域筛选变化 → 防抖 300ms 后刷新图表
watch(
  () => [
    filters.value.categoryIds, filters.value.seriesIds,  filters.value.modelIds,
    filters.value.channelNames, filters.value.channelCodes,
    filters.value.provinces,   filters.value.cities,     filters.value.districts,
  ],
  () => {
    clearTimeout(_chartTimer)
    _chartTimer = setTimeout(() => loadChartData(), 300)
  },
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

    <!-- 移动端遮罩：点击关闭筛选面板 -->
    <transition name="fade">
      <div v-if="isMobile && filterPanelOpen" class="filter-backdrop" @click="filterPanelOpen = false" />
    </transition>

    <!-- ── 左侧筛选面板 ──────────────────────────── -->
    <aside class="filter-panel" :class="{ 'is-open': filterPanelOpen }">
      <!-- 移动端关闭按钮 -->
      <button v-if="isMobile" class="filter-close-btn" @click="filterPanelOpen = false">
        <el-icon><Close /></el-icon>
        关闭筛选
      </button>

      <!-- 查询 + 分组管理 -->
      <div class="panel-top-btns">
        <button class="btn-query" @click="handleQuery(); filterPanelOpen = false" :disabled="loadingChart">
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

      <!-- ▌配置方案面板 -->
      <div v-if="groupPresets.length > 0" class="section-group preset-panel">
        <div class="preset-panel-hd">
          <span class="section-title">配置方案</span>
          <button
            v-if="activeGroupIds.length > 0"
            class="btn-clear-groups"
            @click="activeGroupIds = []; renderChart()"
            title="取消所有激活分组"
          >清除分组</button>
        </div>
        <div class="preset-panel-bd">
          <button
            v-for="p in groupPresets"
            :key="p.id"
            class="preset-chip"
            @click="applyPreset(p)"
            :title="`应用方案「${p.name}」`"
          >{{ p.name }}</button>
        </div>
      </div>

    </aside>

    <!-- ── 右侧内容区 ──────────────────────────────── -->
    <div class="content-panel">

      <!-- 顶部：图表类型图标 + 竖线 + 同比/环比 | 最右侧：数据指标选择 -->
      <div class="chart-toolbar">
        <!-- 左侧：面包屑（有下钻时显示），无下钻时占位保证中间居中 -->
        <div class="ct-left">
          <!-- 移动端：筛选按钮 + 维度选择 + 城市模式 -->
          <template v-if="isMobile">
            <button class="ct-filter-btn" @click="filterPanelOpen = true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="15" height="15">
                <path d="M3 6h18M6 12h12M9 18h6"/>
              </svg>
              筛选
            </button>
            <el-select
              v-model="groupBy"
              size="small"
              class="mobile-dim-select"
              @change="onMobileDimChange"
            >
              <el-option v-for="opt in GROUP_BY_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
            <el-switch
              v-if="groupBy === 'province'"
              v-model="cityMode"
              size="small"
              active-text="城市"
              active-color="#c4883a"
              class="mobile-city-switch"
              @change="loadChartData()"
            />
          </template>
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

        <!-- 右侧：数据指标选择 + 全屏按钮 -->
        <div class="ct-right">
          <el-select v-model="dataMetric" :size="isMobile ? 'small' : 'default'" class="metric-select">
            <el-option v-for="m in METRIC_OPTIONS" :key="m.value" :label="m.label" :value="m.value" />
          </el-select>
          <button class="ct-btn ct-fs-btn" :title="isFullscreen ? '退出全屏' : '全屏查看'" @click="isFullscreen ? closeFullscreen() : openFullscreen()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="20" height="20">
              <template v-if="!isFullscreen">
                <path d="M8 3H5a2 2 0 00-2 2v3M21 8V5a2 2 0 00-2-2h-3M16 21h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/>
              </template>
              <template v-else>
                <path d="M8 3v3a2 2 0 01-2 2H3M21 8h-3a2 2 0 01-2-2V3M3 16h3a2 2 0 012 2v3M16 21v-3a2 2 0 012-2h3"/>
              </template>
            </svg>
          </button>
        </div>
      </div>

      <!-- 中间：图表 -->
      <div ref="chartWrapEl" v-loading="loadingChart" class="chart-wrap" :class="{ 'chart-wrap--with-table': showMapTable }" @contextmenu.prevent>
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

      <!-- 底部：类别选择（移动端已移入 toolbar，桌面端保留） -->
      <div v-if="!isMobile" class="chart-footer">
        <div class="footer-placeholder">
          <div v-if="groupBy === 'province'" class="footer-city-mode">
            <el-switch v-model="cityMode" size="small" active-text="城市模式" active-color="#c4883a" @change="loadChartData()" />
          </div>
        </div>
        <div class="footer-dims">
          <button v-for="opt in GROUP_BY_OPTIONS" :key="opt.value"
            class="gb-btn" :class="{ active: groupBy === opt.value }"
            @click="if (opt.value !== 'province') cityMode = false; groupBy = opt.value; loadChartData()">
            <img :src="opt.icon" width="28" height="28" :alt="opt.label" />
            <span class="gb-label">{{ opt.label }}</span>
          </button>
        </div>
        <div v-if="!isMobile" class="footer-date-range">{{ dateRangeText }}</div>
      </div>

    </div>

    <!-- ── 分组管理弹窗 ──────────────────────────────── -->
    <el-dialog v-model="showGroupMgr" title="管理自定义分组" width="520px" :close-on-click-modal="false">

      <!-- 配置方案：仅保存操作，列表在面板外部显示 -->
      <div class="mgr-divider">保存配置方案</div>
      <div class="mgr-preset-save">
        <el-input v-model="newPresetName" placeholder="输入方案名称" size="default" style="flex:1" @keyup.enter="savePreset" />
        <button class="btn-save-group" @click="savePreset">保存当前激活分组</button>
      </div>

      <!-- 现有方案列表（支持删除） -->
      <div v-if="groupPresets.length > 0" class="mgr-preset-list" style="margin-top:10px">
        <div v-for="p in groupPresets" :key="p.id" class="mgr-preset-item">
          <div class="mgr-preset-info">
            <span class="mgr-preset-name">{{ p.name }}</span>
            <span class="mgr-preset-meta">{{ p.groupIds.length }} 个分组</span>
          </div>
          <button class="mgr-del-btn" @click="deletePreset(p.id)" title="删除方案">
            <el-icon><Delete /></el-icon>
          </button>
        </div>
      </div>

      <!-- 现有分组列表 -->
      <div class="mgr-divider" style="margin-top:16px">分组列表</div>
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

    <!-- ── 全屏覆盖层（Teleport 到 body，避免 stacking context 干扰） ── -->
  <teleport to="body">
    <div v-if="isFullscreen" class="fs-overlay" :class="{ 'fs-portrait': fsPortrait }">

      <!-- 全屏工具栏：面包屑 + 维度选择 + 关闭 -->
      <div class="fs-toolbar">
        <div class="fs-toolbar-left">
          <!-- 维度选择 -->
          <el-select v-model="groupBy" size="small" class="mobile-dim-select" @change="onMobileDimChange">
            <el-option v-for="opt in GROUP_BY_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
          <!-- 城市模式（地域维度时显示） -->
          <el-switch
            v-if="groupBy === 'province'"
            v-model="cityMode"
            size="small"
            active-text="城市"
            active-color="#c4883a"
            class="mobile-city-switch"
            @change="loadChartData()"
          />
          <!-- 下钻面包屑（维度选择右侧） -->
          <div v-if="drillStack.length" class="drill-breadcrumb">
            <span class="bc-item bc-link" @click="drillBack(0)">index</span>
            <template v-for="(entry, i) in drillStack" :key="i">
              <span class="bc-sep">/</span>
              <span v-if="i < drillStack.length - 1" class="bc-item bc-link" @click="drillBack(i + 1)">{{ entry.label }}</span>
              <span v-else class="bc-item bc-current">{{ entry.label }}</span>
            </template>
          </div>
        </div>
        <button class="fs-close-btn" title="退出全屏" @click="closeFullscreen">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
            <path d="M8 3v3a2 2 0 01-2 2H3M21 8h-3a2 2 0 01-2-2V3M3 16h3a2 2 0 012 2v3M16 21v-3a2 2 0 012-2h3"/>
          </svg>
        </button>
      </div>

      <!-- 图表容器：chartEl 将通过 JS 移入此处 -->
      <div class="fs-chart-slot"></div>

    </div>
  </teleport>

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
.metric-select { width: 150px; }
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
  display: flex; align-items: center; justify-content: space-between;
  padding: 2px 0;
}
.footer-placeholder { flex: 1; display: flex; align-items: center; padding-left: 8px; }
.footer-city-mode { display: flex; align-items: center; }
.footer-dims { display: flex; gap: 4px; }
.footer-date-range {
  flex: 1; display: flex; align-items: center; justify-content: flex-end;
  font-size: 14px; color: #c0392b; white-space: nowrap; padding-right: 4px;
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
.preset-panel { padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }
.preset-panel-hd { display: flex; align-items: center; justify-content: space-between; }
.preset-panel-bd { display: flex; flex-wrap: wrap; gap: 5px; }
.btn-clear-groups {
  height: 22px; padding: 0 8px;
  border: 1px solid var(--border); border-radius: 5px;
  background: transparent; color: var(--text-muted);
  font-size: 11px; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
}
.btn-clear-groups:hover { border-color: #d05a3c; color: #d05a3c; }
.preset-chip {
  height: 26px; padding: 0 11px;
  border: 1px solid var(--accent); border-radius: 13px;
  background: rgba(196,136,58,0.08); color: var(--accent);
  font-size: 12px; font-family: inherit;
  cursor: pointer; transition: all 0.15s; white-space: nowrap;
}
.preset-chip:hover { background: var(--accent); color: #fff; }
.mgr-preset-list { min-height: 32px; margin-bottom: 4px; }
.mgr-preset-item { display: flex; align-items: center; justify-content: space-between; padding: 7px 0; border-bottom: 1px solid var(--border); }
.mgr-preset-item:last-child { border-bottom: none; }
.mgr-preset-info { display: flex; align-items: baseline; gap: 8px; min-width: 0; flex: 1; }
.mgr-preset-name { font-size: 13px; color: var(--text-primary); font-weight: 500; }
.mgr-preset-meta { font-size: 11px; color: var(--text-muted); }
.mgr-preset-actions { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.mgr-apply-btn {
  height: 26px; padding: 0 10px;
  border: 1px solid var(--accent); border-radius: 6px;
  background: transparent; color: var(--accent);
  font-size: 12px; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
}
.mgr-apply-btn:hover { background: var(--accent); color: #fff; }
.mgr-preset-save { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
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

/* ── 移动端适配（≤768px） ─────────────────────── */
@media (max-width: 768px) {

  /* ── 筛选遮罩 ── */
  .filter-backdrop {
    position: fixed; inset: 0; z-index: 199;
    background: rgba(0,0,0,0.35);
  }

  /* ── 筛选面板：左侧抽屉 ── */
  .filter-panel {
    position: fixed; z-index: 200;
    left: 0; top: 0; bottom: 0;
    width: 82%; max-width: 320px;
    transform: translateX(-100%);
    transition: transform 0.28s ease;
    background: var(--bg);
    box-shadow: 4px 0 24px rgba(0,0,0,0.14);
    overflow-y: auto; overflow-x: hidden;
    -webkit-overflow-scrolling: touch;
    overscroll-behavior: contain;
    padding: 0 10px 24px; /* 左右留 10px 边距 */
  }
  .filter-panel.is-open { transform: translateX(0); }

  /* 关闭按钮横向出血到面板边缘 */
  .filter-close-btn { margin: 0 -10px; width: calc(100% + 20px); }

  /* ── 面板关闭按钮 ── */
  .filter-close-btn {
    width: 100%;
    display: flex; align-items: center; gap: 6px;
    padding: 14px 16px 10px;
    border: none; background: transparent;
    color: var(--text-muted); font-size: 13px; font-family: inherit;
    cursor: pointer;
    border-bottom: 1px solid var(--border);
    margin-bottom: 5px;
  }

  /* ── content-panel：toolbar(auto) + chart(1fr)，footer 已移除 ── */
  .content-panel {
    display: grid;
    grid-template-rows: auto 1fr;
    grid-template-columns: 1fr;
    gap: 6px;
    overflow: hidden;
    min-height: 0;
  }
  .chart-wrap { min-height: 0; }

  /* ── 工具栏：两行布局（第一行筛选+指标，第二行图表类型） ── */
  .chart-toolbar {
    flex-wrap: wrap;
    padding: 2px 0 4px;
    row-gap: 6px;
    column-gap: 4px;
    align-items: center;
  }
  .ct-left   { order: 1; flex: 1 0 auto; min-width: 0; }
  .ct-right  { order: 2; flex: 0 0 auto; }
  .ct-center { order: 3; flex: 0 0 100%; display: flex; justify-content: center; }

  /* ── 工具栏内按钮：统一高度 26px ── */
  .ct-filter-btn {
    display: inline-flex; align-items: center; gap: 4px;
    height: 26px; padding: 0 8px;
    border: 1px solid var(--border); border-radius: 7px;
    background: var(--bg-card); color: var(--text-muted);
    font-size: 12px; font-family: inherit; cursor: pointer;
    transition: all 0.15s; white-space: nowrap; flex-shrink: 0;
  }
  .ct-filter-btn:active { border-color: var(--accent); color: var(--accent); }
  /* 图表类型图标行同比缩小 */
  .ct-btn { height: 26px; padding: 0 3px; }
  .ct-btn img { width: 20px; height: 20px; }
  .ct-btn--labeled { padding: 0 5px; }
  .ct-label { display: none; }
  /* metric-select 统一为 26px 高、12px 字（mobile 已切为 size="small"） */
  .metric-select { width: 105px; }
  :deep(.metric-select .el-input__wrapper) { height: 26px; padding: 0 8px; }
  :deep(.metric-select .el-input__inner)   { height: 26px; line-height: 26px; font-size: 12px; }

  /* ── 移动端维度选择 el-select ── */
  .mobile-dim-select { width: 68px; flex-shrink: 0; }
  :deep(.mobile-dim-select .el-input__wrapper) { height: 26px; padding: 0 6px; }
  :deep(.mobile-dim-select .el-input__inner)   { height: 26px; line-height: 26px; font-size: 12px; }
  .mobile-city-switch { flex-shrink: 0; }
  :deep(.mobile-city-switch .el-switch__label) { font-size: 11px; }
}

/* ── 横屏手机：最大化图表高度 ── */
@media (orientation: landscape) and (max-height: 600px) {
  /* 筛选面板收窄 */
  .filter-panel { width: 55%; max-width: 260px; }

  /* 工具栏强制单行（覆盖竖屏两行设置） */
  .chart-toolbar { flex-wrap: nowrap; padding: 1px 0; row-gap: 0; column-gap: 0; }
  .ct-left   { order: 0; flex: 1; min-width: 0; }
  .ct-center { order: 0; flex: 0 0 auto; width: auto; display: flex; padding: 0; }
  .ct-right  { order: 0; flex: 0 0 auto; }
}

/* ── 遮罩动画 ── */
.fade-enter-active, .fade-leave-active { transition: opacity 0.22s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* ── 全屏按钮（嵌入 ct-right，风格与 ct-btn 一致） ── */
.ct-fs-btn { margin-left: 4px; }

/* ── 全屏覆盖层 ── */
.fs-overlay {
  position: fixed;
  inset: 0;
  z-index: 900;
  background: var(--bg);
  display: flex;
  flex-direction: column;
}

/* 竖屏时旋转 90° 以横屏展示；手机转横后 fsPortrait=false，此规则移除，overlay 恢复 inset:0 */
.fs-overlay.fs-portrait {
  width: 100dvh;
  height: 100dvw;
  top: calc((100dvh - 100dvw) / 2);
  left: calc((100dvw - 100dvh) / 2);
  transform: rotate(90deg);
  transform-origin: center center;
}

/* 全屏内工具栏 */
.fs-toolbar {
  flex-shrink: 0;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px;
  background: rgba(255,255,255,0.65);
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(12px);
  gap: 8px;
}
.fs-toolbar-left {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}

/* 图表容器：撑满覆盖层剩余空间 */
.fs-chart-slot {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

/* ECharts canvas 在全屏容器内撑满 */
.fs-chart-slot :deep(.chart-canvas) {
  width: 100% !important;
  height: 100% !important;
}

/* 退出全屏按钮（在 toolbar 右侧） */
.fs-close-btn {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.fs-close-btn:hover { border-color: var(--accent); color: var(--accent); }
</style>
