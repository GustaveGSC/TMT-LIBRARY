// src/stores/product/finished.js
import { defineStore } from 'pinia'
import { ref, reactive, computed, watch } from 'vue'
import http from '@/api/http'
import { usePackagedStore } from './packaged'

export const useFinishedStore = defineStore('product/finished', () => {

  // ── 原始全量数据（从后端分批拉取）──────────────
  const rawItems   = ref([])
  const loading    = ref(false)   // 首批加载中
  const loadingMore = ref(false)  // 后台继续加载中
  const loaded     = ref(false)
  const error      = ref('')
  let   _loadGen   = 0            // 防止过期批次写入

  // ── 禁用编码前缀（从编码规则接口同步）───────────
  // 仅保存 finished 类型被禁用的前缀，用于全局过滤
  const disabledPrefixes = ref([])   // string[]

  // ── 分页 ──────────────────────────────────────────
  const currentPage = ref(1)
  const pageSize    = ref(50)

  // ── 搜索（每列独立）──────────────────────────────
  const filters = reactive({
    global:       '',   // 顶部全局搜索（匹配 code / name / name_en）
    code:         '',
    name:         '',
    name_en:      '',
    category:     '',
    series_code:  '',
    series_name:  '',
    model_code:   '',
    packaged:     '',
    gross_weight: '',
    net_weight:   '',
    volume:       '',
    listed_yymm:  '',
    delisted_yymm:'',
    market:       '',
  })

  // ── 状态筛选 ───────────────────────────────────────
  const status = ref('')

  // ── 生命周期筛选 ────────────────────────────────────
  // '' = 全部  'listed' = 已上市  'delisted' = 已退市  'unknown' = 状态未知
  const lifecycle = ref('')

  // ── 排序 ──────────────────────────────────────────
  const sortField = ref('')
  const sortOrder = ref('')   // 'asc' | 'desc' | ''

  // ── 选中行 & 关联产成品 ────────────────────────────
  const selected         = ref(null)
  const selectedPackaged = ref([])

  // ── 字段取值映射（搜索 & 排序共用）──────────────
  const FIELD_GETTER = {
    code:               r => r.code,
    name:               r => r.name,
    name_en:            r => r.name_en,
    category:           r => r.category_name,
    series_code:        r => r.series_code,
    series_name:        r => r.series_name,
    model_code:         r => r.model_code,
    packaged:           r => (r.packaged_list || []).join(' '),
    gross_weight:       r => r.total_gross_weight != null ? String(r.total_gross_weight) : '',
    net_weight:         r => r.total_net_weight   != null ? String(r.total_net_weight)   : '',
    volume:             r => r.total_volume        != null ? String(r.total_volume)        : '',
    listed_yymm:        r => r.listed_yymm   || '',
    delisted_yymm:      r => r.delisted_yymm || '',
    market:             r => r.market        || '',
    total_volume:       r => r.total_volume,
    total_gross_weight: r => r.total_gross_weight,
    total_net_weight:   r => r.total_net_weight,
  }

  // ── 排除禁用编码规则对应的成品 ─────────────────────
  // activeItems：rawItems 中去掉编码前缀被禁用的成品
  const activeItems = computed(() => {
    const prefixes = disabledPrefixes.value
    if (!prefixes.length) return rawItems.value
    return rawItems.value.filter(r =>
      !prefixes.some(p => (r.code || '').startsWith(p))
    )
  })

  // ── 前端计算：过滤 + 排序 → items ─────────────────
  const items = computed(() => {
    let list = activeItems.value

    // 状态筛选
    if (status.value) {
      list = list.filter(r => r.status === status.value)
    }

    // 生命周期筛选
    if (lifecycle.value === 'listed') {
      list = list.filter(r => r.listed_yymm && !r.delisted_yymm)
    } else if (lifecycle.value === 'delisted') {
      list = list.filter(r => r.listed_yymm && r.delisted_yymm)
    } else if (lifecycle.value === 'unknown') {
      list = list.filter(r => !r.listed_yymm)
    }

    // 每列搜索
    for (const [field, val] of Object.entries(filters)) {
      if (!val || !val.trim()) continue
      if (field === 'global') continue  // global 单独处理
      const v = val.trim().toLowerCase()
      const getter = FIELD_GETTER[field]
      if (getter) list = list.filter(r => (getter(r) || '').toLowerCase().includes(v))
    }

    // 全局搜索（匹配 code / name / name_en，OR 逻辑）
    if (filters.global?.trim()) {
      const v = filters.global.trim().toLowerCase()
      list = list.filter(r =>
        (r.code    || '').toLowerCase().includes(v) ||
        (r.name    || '').toLowerCase().includes(v) ||
        (r.name_en || '').toLowerCase().includes(v)
      )
    }

    // 排序
    if (sortField.value && sortOrder.value) {
      const getter = FIELD_GETTER[sortField.value] || (r => r[sortField.value])
      const dir    = sortOrder.value === 'asc' ? 1 : -1
      list = [...list].sort((a, b) => {
        const av = getter(a) ?? ''
        const bv = getter(b) ?? ''
        if (av < bv) return -1 * dir
        if (av > bv) return  1 * dir
        return 0
      })
    }

    return list
  })

  const total = computed(() => items.value.length)

  // 当前页数据（切片）
  const pagedItems = computed(() => {
    const start = (currentPage.value - 1) * pageSize.value
    return items.value.slice(start, start + pageSize.value)
  })

  // 过滤/排序条件变化时重置到第一页
  watch(
    [() => ({ ...filters }), status, lifecycle, sortField, sortOrder],
    () => { currentPage.value = 1 },
    { deep: true }
  )

  // ── 从后端分批拉取数据 ────────────────────────────
  // 第一批（200条）加载完立即 resolve，其余后台继续加载
  const BATCH_SIZE = 200

  // 拉取编码规则，提取 finished 类型被禁用的前缀
  async function loadDisabledPrefixes() {
    try {
      const res = await http.get('/api/erp-code-rules/')
      if (res.success) {
        disabledPrefixes.value = (res.data || [])
          .filter(r => r.type === 'finished' && r.is_disabled)
          .map(r => r.prefix)
      }
    } catch (_) { /* 失败时不影响主流程 */ }
  }

  async function load() {
    const gen = ++_loadGen   // 每次 load 递增，旧批次发现 gen 变化后自动停止
    loading.value    = true
    loadingMore.value = false
    error.value      = ''
    rawItems.value   = []

    // 同步加载禁用前缀（与成品数据并行，失败不阻塞）
    loadDisabledPrefixes()

    try {
      // 第一批：快速拿到首屏数据
      const res = await http.get('/api/product/finished', {
        params: { page: 1, size: BATCH_SIZE }
      })
      if (gen !== _loadGen) return   // 已被新的 load() 取代
      if (!res.success) {
        error.value = res.message || '加载失败'
        return
      }
      rawItems.value = res.data.items
      loaded.value   = true
      loading.value  = false

      // 若还有更多，后台继续分批拉取
      const serverTotal = res.data.total
      if (rawItems.value.length < serverTotal) {
        _loadRemaining(gen, serverTotal)
      }
    } catch (e) {
      if (gen !== _loadGen) return
      error.value = e.message || '网络错误'
    } finally {
      if (gen === _loadGen) loading.value = false
    }
  }

  async function _loadRemaining(gen, total) {
    loadingMore.value = true
    try {
      const totalPages = Math.ceil(total / BATCH_SIZE)
      for (let page = 2; page <= totalPages; page++) {
        if (gen !== _loadGen) return   // 已被新 load() 取代，放弃
        const r = await http.get('/api/product/finished', {
          params: { page, size: BATCH_SIZE }
        })
        if (gen !== _loadGen) return
        if (!r.success) break
        rawItems.value = [...rawItems.value, ...r.data.items]
      }
    } finally {
      if (gen === _loadGen) loadingMore.value = false
    }
  }

  // 保存后重新拉取（rawItems 更新后 computed 自动刷新）
  async function reload() { await load() }

  // ── 局部刷新单行（保存后调用，不触发全量重载，不重置页码）────────
  async function refreshItem(code) {
    try {
      // 用 code 精确搜索（LIKE '%code%'，size=20 足以覆盖同前缀短码）
      const res = await http.get('/api/product/finished', {
        params: { page: 1, size: 20, search_field: 'code', search_value: code }
      })
      if (!res.success) return
      // 从结果中找到完全匹配的行
      const updated = res.data.items.find(i => i.code === code)
      if (!updated) return
      const idx = rawItems.value.findIndex(i => i.code === code)
      if (idx >= 0) {
        // 原地替换，Vue 响应式会检测到变化，computed 自动刷新
        rawItems.value = [
          ...rawItems.value.slice(0, idx),
          updated,
          ...rawItems.value.slice(idx + 1),
        ]
      }
    } catch (e) {
      console.error('[refreshItem] 失败', e)
    }
  }

  // ── 搜索候选（从 rawItems 本地匹配，最多20条）────
  function getSuggestions(field, val) {
    if (!val || !val.trim()) return []
    const v      = val.trim().toLowerCase()
    const getter = FIELD_GETTER[field]
    if (!getter) return []
    const seen = new Set()
    const result = []
    for (const row of rawItems.value) {
      const cell = (getter(row) || '').toLowerCase()
      if (cell.includes(v) && !seen.has(cell)) {
        seen.add(cell)
        result.push(getter(row))
        if (result.length >= 20) break
      }
    }
    return result
  }

  // focus 时展示前20条不重复值
  function getTopSuggestions(field) {
    const getter = FIELD_GETTER[field]
    if (!getter) return []
    const seen = new Set()
    const result = []
    for (const row of rawItems.value) {
      const cell = getter(row)
      if (cell && !seen.has(cell)) {
        seen.add(cell)
        result.push(cell)
        if (result.length >= 20) break
      }
    }
    return result
  }

  // ── 选中行 ────────────────────────────────────────
  function select(row) {
    selected.value = row
    if (!row) { selectedPackaged.value = []; return }
    const packagedStore = usePackagedStore()
    selectedPackaged.value = packagedStore.getByCodeList(row.packaged_list || [])
  }

  // ── 重置（离开产品库时调用）──────────────────────
  function reset() {
    _loadGen++              // 令后台批次失效
    rawItems.value   = []
    loaded.value     = false
    loadingMore.value = false
    error.value      = ''
    status.value    = ''
    sortField.value = ''
    sortOrder.value = ''
    selected.value          = null
    selectedPackaged.value  = []
    Object.keys(filters).forEach(k => { filters[k] = '' })
  }

  // ── 设置排序（组件通过此方法修改，避免直接赋值破坏响应式）
  function setSort(field, order) {
    sortField.value = field
    sortOrder.value = order
  }

  // resetPage 保留接口兼容（全量模式下无实际作用）
  function resetPage() {}

  return {
    rawItems, activeItems,
    items, pagedItems, total, currentPage, pageSize,
    loading, loadingMore, loaded, error,
    filters, status, lifecycle,
    sortField, sortOrder,
    selected, selectedPackaged,
    load, reload, refreshItem, select, resetPage, reset, getSuggestions, getTopSuggestions, setSort,
    disabledPrefixes, reloadDisabledPrefixes: loadDisabledPrefixes,
  }
})