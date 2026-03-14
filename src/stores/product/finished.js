// src/stores/product/finished.js
import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import http from '@/api/http'
import { usePackagedStore } from './packaged'

export const useFinishedStore = defineStore('product/finished', () => {

  // ── 原始全量数据（从后端一次性拉取）──────────────
  const rawItems  = ref([])
  const loading   = ref(false)
  const error     = ref('')

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

  // ── 前端计算：过滤 + 排序 → items ─────────────────
  const items = computed(() => {
    let list = rawItems.value

    // 状态筛选
    if (status.value) {
      list = list.filter(r => r.status === status.value)
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

  // ── 从后端拉取全量数据（初始化时调用一次）────────
  async function load() {
    loading.value = true
    error.value   = ''
    try {
      const res = await http.get('/api/product/finished', {
        params: { page: 1, size: 99999 }
      })
      if (res.success) {
        rawItems.value = res.data.items
      } else {
        error.value = res.message || '加载失败'
      }
    } catch (e) {
      error.value = e.message || '网络错误'
    } finally {
      loading.value = false
    }
  }

  // 保存后重新拉取（使 rawItems 更新，computed 自动刷新）
  async function reload() { await load() }

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
    rawItems.value  = []
    error.value     = ''
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
    rawItems,
    items, total, loading, error,
    filters, status,
    sortField, sortOrder,
    selected, selectedPackaged,
    load, reload, select, resetPage, reset, getSuggestions, getTopSuggestions, setSort,
  }
})