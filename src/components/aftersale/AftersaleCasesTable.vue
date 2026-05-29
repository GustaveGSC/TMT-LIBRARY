<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit, Check, Close, Remove } from '@element-plus/icons-vue'
import Sortable from 'sortablejs'
import http from '@/api/http.js'
import { downloadBlob } from '@/utils/download.js'
import { isElectron } from '@/utils/platform'

// ── Props ──────────────────────────────────────────
const props = defineProps({
  // 外部上下文筛选（来自图表/工具栏，变更时重新加载）
  filter: { type: Object, default: () => ({}) },
  // filter 变更时是否重置列筛选（抽屉场景传 true）
  resetFiltersOnChange: { type: Boolean, default: false },
})

const emit = defineEmits(['update:exportLoading'])

// ── 响应式状态 ────────────────────────────────────
const tableRef    = ref(null)
const items       = ref([])    // 原始 case 数组（带 reasons）
const displayItems = ref([])   // 展平后的展示数组
const total       = ref(0)
const page        = ref(1)
const pageSize    = ref(100)
const loading     = ref(false)
const exportLoading = ref(false)
const saving      = ref(false)
const ignoring    = ref(false)

const PAGE_SIZE_OPTIONS = [20, 50, 100, 200]

// ── 编辑选项 & 行级编辑状态 ─────────────────────
const editOptions   = ref(null)
const editingRowKey = ref(null)
const rowEdits      = ref({
  productCategoryId: null,
  seriesId:          null,
  modelId:           null,
  categoryId:        null,
  reasonId:          null,
  aliasId:           null,
})

// ── 列顺序（可拖拽，持久化到 localStorage） ──────
const DRAGGABLE_COLS = [
  'order_no', 'product_category', 'series', 'model',
  'reason_category', 'reason_name', 'shipping_alias',
  'shipped_date', 'purchase_date', 'days_since_purchase', 'channel', 'province',
  'buyer_remark', 'seller_remark',
]
const STORAGE_KEY = 'cases-table-col-order'

const columnOrder = ref((() => {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
    if (Array.isArray(saved) && DRAGGABLE_COLS.every(k => saved.includes(k)) && saved.length === DRAGGABLE_COLS.length)
      return saved
  } catch {}
  return [...DRAGGABLE_COLS]
})())
watch(columnOrder, val => localStorage.setItem(STORAGE_KEY, JSON.stringify(val)), { deep: true })

// ── SortableJS ────────────────────────────────────
let _sortable = null

function initSort() {
  _sortable?.destroy()
  _sortable = null
  const headerRow = tableRef.value?.$el?.querySelector('.el-table__header-wrapper thead tr')
  if (!headerRow) return
  _sortable = Sortable.create(headerRow, {
    animation: 150,
    filter: '.col-fixed',
    preventOnFilter: false,
    onEnd({ oldIndex, newIndex }) {
      const offset = 2  // expand + 序号
      const from = oldIndex - offset
      const to   = newIndex - offset
      if (from === to || from < 0 || to < 0 || from >= columnOrder.value.length || to >= columnOrder.value.length) return
      const cols = [...columnOrder.value]
      cols.splice(to, 0, cols.splice(from, 1)[0])
      columnOrder.value = cols
    },
  })
}

onMounted(() => {
  loadData()
  loadEditOptions()
  nextTick(initSort)
})
onBeforeUnmount(() => { _sortable?.destroy(); _sortable = null })

// ── 排序状态 ──────────────────────────────────────
const currentSortBy    = ref('shipped_date')
const currentSortOrder = ref('desc')

function sortBy(field) {
  if (currentSortBy.value === field) {
    if (currentSortOrder.value === 'asc') currentSortOrder.value = 'desc'
    else { currentSortBy.value = 'shipped_date'; currentSortOrder.value = 'desc' }
  } else {
    currentSortBy.value    = field
    currentSortOrder.value = 'asc'
  }
  page.value = 1
  loadData()
}

function sortIcon(field) {
  if (currentSortBy.value !== field) return 'none'
  return currentSortOrder.value
}

// ── 列头筛选 ──────────────────────────────────────
const filters = ref({
  product_category: null,
  series:           null,
  model:            null,
  reason_category:  null,
  reason_name:      null,
  shipping_alias:   null,
  channel:          null,
  province:         null,
})

const filterOptions = ref({
  reason_categories: [],
  reason_names:      [],
  channels:          [],
  provinces:         [],
  shipping_aliases:  [],   // {id, name}，仅限 confirmed 工单中出现的简称
  category_ids:      new Set(),  // confirmed 工单涉及的品类 id
  series_ids:        new Set(),  // confirmed 工单涉及的系列 id
  model_ids:         new Set(),  // confirmed 工单涉及的产品 id
})
let _filterOptLoaded = false

async function onFilterDropdownOpen() {
  if (_filterOptLoaded) return
  _filterOptLoaded = true
  const res = await http.get('/api/aftersale/filter-options')
  if (res.success) {
    filterOptions.value.reason_categories = res.data.reason_categories || []
    filterOptions.value.reason_names      = res.data.reason_names      || []
    filterOptions.value.channels          = res.data.channels          || []
    filterOptions.value.provinces         = res.data.provinces         || []
    filterOptions.value.shipping_aliases  = res.data.shipping_aliases  || []
    filterOptions.value.category_ids      = new Set(res.data.category_ids || [])
    filterOptions.value.series_ids        = new Set(res.data.series_ids   || [])
    filterOptions.value.model_ids         = new Set(res.data.model_ids    || [])
  }
}

let _filterTimer = null
function onColFilterChange() {
  clearTimeout(_filterTimer)
  _filterTimer = setTimeout(() => { page.value = 1; loadData() }, 300)
}

function getFilterSeriesOpts() {
  if (!editOptions.value) return []
  const sids = filterOptions.value.series_ids
  const pcid = filters.value.product_category
  let list = editOptions.value.series
  if (sids.size) list = list.filter(s => sids.has(s.id))
  if (pcid) list = list.filter(s => Number(s.category_id) === Number(pcid))
  return list
}

function getFilterModelOpts() {
  if (!editOptions.value) return []
  const mids = filterOptions.value.model_ids
  const sid = filters.value.series
  let models
  if (sid) {
    const s = editOptions.value.series.find(s => s.id === Number(sid))
    models = s?.models ?? []
  } else {
    models = editOptions.value.series.flatMap(s => s.models || [])
  }
  if (mids.size) models = models.filter(m => mids.has(m.id))
  return models
}

// ── 监听外部 filter 变更 ──────────────────────────
watch(() => props.filter, () => {
  page.value = 1
  if (props.resetFiltersOnChange) {
    currentSortBy.value    = 'shipped_date'
    currentSortOrder.value = 'desc'
    filters.value = { product_category: null, series: null, model: null, reason_category: null, reason_name: null, shipping_alias: null, channel: null, province: null }
    _filterOptLoaded = false
    filterOptions.value.shipping_aliases = []
    filterOptions.value.category_ids     = new Set()
    filterOptions.value.series_ids       = new Set()
    filterOptions.value.model_ids        = new Set()
  }
  loadData()
}, { deep: true })

// ── 数据构建与加载 ────────────────────────────────
function buildParams() {
  const f  = props.filter
  const cf = filters.value
  return {
    status:                  f.status               || 'confirmed',
    date_start:              f.date_start            || undefined,
    date_end:                f.date_end              || undefined,
    max_days_since_purchase: f.max_days_since_purchase ?? undefined,
    model_ids:           f.model_ids           || undefined,
    series_ids:          f.series_ids          || undefined,
    category_ids:        f.category_ids        || undefined,
    reason_ids:          f.reason_ids          || undefined,
    reason_category_ids: f.reason_category_ids || undefined,
    shipping_alias_ids:  f.shipping_alias_ids  || undefined,
    channel_names:       f.channel_names       || undefined,
    provinces:           f.provinces           || undefined,
    cities:              f.cities              || undefined,
    reason_id:           f.reason_id           || undefined,
    reason_category:     f.reason_category     || undefined,
    reason_name:         f.reason_name         || undefined,
    model_code:          f.model_code          || undefined,
    shipping_alias:      f.shipping_alias      || undefined,
    channel_name:        f.channel_name        || undefined,
    province:            f.province            || undefined,
    city:                f.city                || undefined,
    search:              f.search              || undefined,
    sort_by:             currentSortBy.value,
    sort_order:          currentSortOrder.value,
    ...(cf.product_category ? { category_ids:       String(cf.product_category) } : {}),
    ...(cf.series           ? { series_ids:         String(cf.series) }           : {}),
    ...(cf.model            ? { model_ids:          String(cf.model) }             : {}),
    ...(cf.reason_category  ? { reason_category:    cf.reason_category }           : {}),
    ...(cf.reason_name      ? { reason_name:        cf.reason_name }               : {}),
    ...(cf.shipping_alias   ? { shipping_alias_ids: String(cf.shipping_alias) }    : {}),
    ...(cf.channel          ? { channel_name:       cf.channel }                   : {}),
    ...(cf.province         ? { province:           cf.province }                  : {}),
  }
}

function pickReason(reasons) {
  if (!reasons?.length) return null
  const rid = props.filter.reason_id
  if (rid) { const match = reasons.find(r => r.reason_id === rid); if (match) return match }
  return reasons[0]
}

function flattenItems(caseRows) {
  return caseRows.map((row, idx) => {
    const r = pickReason(row.reasons)
    return {
      _caseId:            row.id,
      _key:               `${row.id}-${r?.id ?? 0}`,
      _rowIndex:          idx,
      _caseReasonId:      r?.id                    ?? null,
      _modelId:           r?.model_id              ?? null,
      _seriesId:          r?.series_id             ?? null,
      _productCategoryId: r?.product_category_id   ?? null,
      _reasonId:          r?.reason_id             ?? null,
      _categoryId:        r?.reason_category_id    ?? null,
      _aliasId:           r?.shipping_alias_id     ?? null,
      ecommerce_order_no: row.ecommerce_order_no,
      shipped_date:       row.shipped_date,
      channel_name:       row.channel_name,
      province:           row.province,
      buyer_remark:       row.buyer_remark,
      seller_remark:      row.seller_remark,
      products:           row.products || [],
      product_category_name: r?.product_category_name ?? null,
      series_code:        r?.series_code           ?? null,
      series_name:        r?.series_name           ?? null,
      model_code:         r?.model_code            ?? null,
      model_name:         r?.model_name            ?? null,
      reason_category:    r?.reason_category       ?? null,
      reason_name:        r?.reason_name           ?? null,
      shipping_alias_name: r?.shipping_alias_name  ?? null,
      purchase_date:      r?.purchase_date         ?? null,
      days_since_purchase: r?.days_since_purchase  ?? null,
      _reasonsLoaded:     row.reasons !== null,
    }
  })
}

let _seq = 0

async function loadData() {
  loading.value = true
  const seq = ++_seq
  try {
    const params = { ...buildParams(), page: page.value, page_size: pageSize.value }
    const res = await http.get('/api/aftersale/cases', { params })
    if (!res.success || seq !== _seq) return
    items.value        = res.data.items.map(r => ({ ...r, reasons: null }))
    displayItems.value = flattenItems(items.value)
    total.value        = res.data.total
    loading.value      = false

    const ids = res.data.items.map(r => r.id)
    if (!ids.length) return
    const r2 = await http.get('/api/aftersale/cases/reasons', { params: { ids: ids.join(',') } })
    if (!r2.success || seq !== _seq) return
    items.value = items.value.map(row => ({ ...row, reasons: r2.data[String(row.id)] ?? [] }))
    displayItems.value = flattenItems(items.value)
  } finally {
    if (seq === _seq) loading.value = false
  }
}

async function loadEditOptions() {
  if (editOptions.value) return
  const res = await http.get('/api/aftersale/case-edit-options')
  if (res.success) editOptions.value = res.data
}

// ── 行级编辑方法 ──────────────────────────────────
function startRowEdit(row) {
  if (!row._reasonsLoaded) return
  editingRowKey.value = row._key
  rowEdits.value = {
    productCategoryId: row._productCategoryId,
    seriesId:          row._seriesId,
    modelId:           row._modelId,
    categoryId:        row._categoryId,
    reasonId:          row._reasonId,
    aliasId:           row._aliasId,
  }
}

function cancelRowEdit() { editingRowKey.value = null }

function onEditProductCategory(val) {
  rowEdits.value.productCategoryId = val
  rowEdits.value.seriesId = null; rowEdits.value.modelId = null
}

function onEditSeries(val) {
  rowEdits.value.seriesId = val; rowEdits.value.modelId = null
  if (val && editOptions.value) {
    const s = editOptions.value.series.find(s => s.id === val)
    rowEdits.value.productCategoryId = s?.category_id != null ? Number(s.category_id) : null
  } else if (!val) { rowEdits.value.productCategoryId = null }
}

function onEditModel(val) {
  rowEdits.value.modelId = val
  if (val && editOptions.value) {
    for (const s of editOptions.value.series) {
      if (s.models.some(m => m.id === val)) {
        rowEdits.value.seriesId = s.id
        rowEdits.value.productCategoryId = s.category_id != null ? Number(s.category_id) : null
        break
      }
    }
  } else if (!val) { rowEdits.value.seriesId = null; rowEdits.value.productCategoryId = null }
}

function onEditCategory(val) { rowEdits.value.categoryId = val; rowEdits.value.reasonId = null }

function onEditReason(val) {
  rowEdits.value.reasonId = val
  if (val && editOptions.value) {
    for (const g of editOptions.value.reasons) {
      if (g.reasons.some(r => r.id === val)) { rowEdits.value.categoryId = g.category_id; break }
    }
  } else if (!val) { rowEdits.value.categoryId = null }
}

function getEditSeries() {
  if (!editOptions.value) return []
  const pcid = rowEdits.value.productCategoryId
  if (pcid) return editOptions.value.series.filter(s => Number(s.category_id) === Number(pcid))
  return editOptions.value.series
}

function getEditModels() {
  if (!editOptions.value) return []
  const sid = rowEdits.value.seriesId
  if (sid) { const s = editOptions.value.series.find(s => s.id === sid); return s?.models ?? [] }
  return editOptions.value.series.flatMap(s => s.models)
}

function getEditReasons() {
  if (!editOptions.value) return []
  const cid = rowEdits.value.categoryId
  if (cid) { const g = editOptions.value.reasons.find(g => g.category_id === cid); return g?.reasons ?? [] }
  return editOptions.value.reasons.flatMap(g => g.reasons)
}

async function confirmRowEdit(row) {
  const { productCategoryId, seriesId, modelId } = rowEdits.value
  if (productCategoryId && !seriesId) { ElMessage.error('已选品类，请继续选择系列'); return }
  if (seriesId && !modelId)           { ElMessage.error('已选系列，请继续选择产品型号'); return }
  if (!row._caseReasonId) { editingRowKey.value = null; return }

  const patch = {}
  if (rowEdits.value.modelId  !== row._modelId)  patch.model_id          = rowEdits.value.modelId
  if (rowEdits.value.reasonId !== row._reasonId) patch.reason_id         = rowEdits.value.reasonId
  if (rowEdits.value.aliasId  !== row._aliasId)  patch.shipping_alias_id = rowEdits.value.aliasId
  if (!Object.keys(patch).length) { editingRowKey.value = null; return }

  saving.value = true
  try {
    const res = await http.patch(`/api/aftersale/case-reasons/${row._caseReasonId}`, patch)
    if (!res.success) { ElMessage.error(res.message || '保存失败'); return }

    if ('model_id' in patch) {
      let foundModel = null, foundSeries = null, foundCategory = null
      if (rowEdits.value.modelId && editOptions.value) {
        for (const s of editOptions.value.series) {
          const m = s.models.find(m => m.id === rowEdits.value.modelId)
          if (m) { foundModel = m; foundSeries = s; foundCategory = editOptions.value.product_categories?.find(c => c.id === s.category_id) ?? null; break }
        }
      }
      row.model_code            = foundModel?.model_code ?? null
      row.model_name            = foundModel?.name       ?? null
      row.series_code           = foundSeries?.code      ?? null
      row.series_name           = foundSeries?.name      ?? null
      row.product_category_name = foundCategory?.name    ?? null
      row._modelId              = rowEdits.value.modelId ?? null
      row._seriesId             = foundSeries?.id        ?? null
      row._productCategoryId    = foundCategory?.id      ?? null
    }
    if ('reason_id' in patch) {
      let foundReason = null, foundGroup = null
      if (rowEdits.value.reasonId && editOptions.value) {
        for (const g of editOptions.value.reasons) {
          const r = g.reasons.find(r => r.id === rowEdits.value.reasonId)
          if (r) { foundReason = r; foundGroup = g; break }
        }
      }
      row.reason_name     = foundReason?.name         ?? null
      row.reason_category = foundGroup?.category_name ?? null
      row._reasonId       = rowEdits.value.reasonId   ?? null
      row._categoryId     = foundGroup?.category_id   ?? null
    }
    if ('shipping_alias_id' in patch) {
      const alias = editOptions.value?.aliases.find(a => a.id === rowEdits.value.aliasId)
      row.shipping_alias_name = alias?.name ?? null
      row._aliasId = rowEdits.value.aliasId ?? null
    }
    editingRowKey.value = null
    ElMessage.success('已保存')
  } finally {
    saving.value = false
  }
}

async function ignoreCase(row) {
  try {
    await ElMessageBox.confirm(
      `确认忽略订单「${row.ecommerce_order_no}」？忽略后该订单不再出现在待处理列表中。`,
      '忽略工单',
      { confirmButtonText: '忽略', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }
  ignoring.value = true
  try {
    const res = await http.post(`/api/aftersale/cases/${row.ecommerce_order_no}/ignore`)
    if (!res.success) { ElMessage.error(res.message || '操作失败'); return }
    ElMessage.success('已忽略')
    const idx = displayItems.value.findIndex(r => r._key === row._key)
    if (idx >= 0) displayItems.value.splice(idx, 1)
    total.value = Math.max(0, total.value - 1)
  } finally {
    ignoring.value = false
  }
}

// ── 导出 ──────────────────────────────────────────
async function exportData() {
  exportLoading.value = true
  emit('update:exportLoading', true)
  try {
    const today    = new Date().toISOString().slice(0, 10).replace(/-/g, '')
    const filename = `售后数据_${today}.xlsx`
    const res = await http.get('/api/aftersale/cases/export', {
      params:       buildParams(),
      responseType: 'arraybuffer',
    })
    if (isElectron) {
      const save = await window.electronAPI.showSaveDialog({
        defaultPath: filename,
        filters: [{ name: 'Excel', extensions: ['xlsx'] }],
      })
      if (save?.canceled || !save?.filePath) return
      await window.electronAPI.saveFile(save.filePath, res)
    } else {
      downloadBlob(res, filename)
    }
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败，请重试')
  } finally {
    exportLoading.value = false
    emit('update:exportLoading', false)
  }
}

defineExpose({ total, exportLoading, exportData, initSort, refresh: loadData })
</script>

<template>
  <div class="cases-table-wrap">
    <!-- 表格 -->
    <el-table
      ref="tableRef"
      v-loading="loading"
      :data="displayItems"
      size="small"
      border
      :row-key="row => row._key"
      class="cases-table"
    >
      <!-- 固定列：展开行 -->
      <el-table-column type="expand" width="32" label-class-name="col-fixed">
        <template #default="{ row }">
          <div class="expand-products">
            <template v-if="row.products?.length">
              <el-tag v-for="p in row.products" :key="p.code" size="small" class="product-tag">
                {{ p.name }} × {{ p.quantity }}
              </el-tag>
            </template>
            <span v-else class="no-products">暂无发货记录</span>
          </div>
        </template>
      </el-table-column>

      <!-- 固定列：序号 -->
      <el-table-column label="序号" width="52" resizable label-class-name="col-fixed">
        <template #default="{ $index }">
          {{ (page - 1) * pageSize + $index + 1 }}
        </template>
      </el-table-column>

      <!-- 可拖动列 -->
      <template v-for="colKey in columnOrder" :key="colKey">

        <!-- 订单号 -->
        <el-table-column v-if="colKey === 'order_no'" min-width="150" resizable show-overflow-tooltip>
          <template #header>
            <div class="th-top">
              <span class="th-lbl">订单号</span>
              <button :class="['sort-btn', sortIcon('ecommerce_order_no') !== 'none' ? 'sort-' + sortIcon('ecommerce_order_no') : '']" @click.stop="sortBy('ecommerce_order_no')" />
            </div>
            <div class="th-fph" />
          </template>
          <template #default="{ row }">{{ row.ecommerce_order_no }}</template>
        </el-table-column>

        <!-- 产品品类 -->
        <el-table-column v-else-if="colKey === 'product_category'" min-width="100" resizable>
          <template #header>
            <div class="th-top">
              <span class="th-lbl">产品品类</span>
              <button :class="['sort-btn', sortIcon('product_category_name') !== 'none' ? 'sort-' + sortIcon('product_category_name') : '']" @click.stop="sortBy('product_category_name')" />
            </div>
            <div class="th-filter-wrap" @click.stop>
              <el-select v-model="filters.product_category" filterable clearable size="small" placeholder="筛选…" class="th-sel" :teleported="true" @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange">
                <el-option v-for="c in (editOptions?.product_categories ?? []).filter(c => !filterOptions.category_ids.size || filterOptions.category_ids.has(c.id))" :key="c.id" :value="c.id" :label="c.name" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">
            <span v-if="!row._reasonsLoaded" class="loading-cell">…</span>
            <template v-else-if="editingRowKey === row._key">
              <el-select :model-value="rowEdits.productCategoryId" size="small" filterable clearable placeholder="选择品类" style="width:100%" @change="onEditProductCategory">
                <el-option v-for="c in editOptions?.product_categories ?? []" :key="c.id" :value="c.id" :label="c.name" />
              </el-select>
            </template>
            <template v-else>{{ row.product_category_name || '—' }}</template>
          </template>
        </el-table-column>

        <!-- 系列 -->
        <el-table-column v-else-if="colKey === 'series'" min-width="120" resizable>
          <template #header>
            <div class="th-top">
              <span class="th-lbl">系列</span>
              <button :class="['sort-btn', sortIcon('series_code') !== 'none' ? 'sort-' + sortIcon('series_code') : '']" @click.stop="sortBy('series_code')" />
            </div>
            <div class="th-filter-wrap" @click.stop>
              <el-select v-model="filters.series" filterable clearable size="small" placeholder="筛选…" class="th-sel" :teleported="true" @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange">
                <el-option v-for="s in getFilterSeriesOpts()" :key="s.id" :value="s.id" :label="`${s.code} ${s.name}`" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">
            <span v-if="!row._reasonsLoaded" class="loading-cell">…</span>
            <template v-else-if="editingRowKey === row._key">
              <el-select :model-value="rowEdits.seriesId" size="small" filterable clearable placeholder="选择系列" style="width:100%" @change="onEditSeries">
                <el-option v-for="s in getEditSeries()" :key="s.id" :value="s.id" :label="`${s.code} ${s.name}`" />
              </el-select>
            </template>
            <template v-else>
              <span v-if="row.series_code || row.series_name">{{ row.series_code }}<span class="name-hint"> {{ row.series_name }}</span></span>
              <span v-else class="text-muted">—</span>
            </template>
          </template>
        </el-table-column>

        <!-- 产品 -->
        <el-table-column v-else-if="colKey === 'model'" min-width="150" resizable>
          <template #header>
            <div class="th-top">
              <span class="th-lbl">产品</span>
              <button :class="['sort-btn', sortIcon('model_code') !== 'none' ? 'sort-' + sortIcon('model_code') : '']" @click.stop="sortBy('model_code')" />
            </div>
            <div class="th-filter-wrap" @click.stop>
              <el-select v-model="filters.model" filterable clearable size="small" placeholder="筛选…" class="th-sel" :teleported="true" @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange">
                <el-option v-for="m in getFilterModelOpts()" :key="m.id" :value="m.id" :label="m.model_code" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">
            <span v-if="!row._reasonsLoaded" class="loading-cell">…</span>
            <template v-else-if="editingRowKey === row._key">
              <el-select :model-value="rowEdits.modelId" size="small" filterable clearable placeholder="选择产品" style="width:100%" @change="onEditModel">
                <el-option v-for="m in getEditModels()" :key="m.id" :value="m.id" :label="m.model_code">
                  <span>{{ m.model_code }}</span><span class="option-hint">{{ m.name }}</span>
                </el-option>
              </el-select>
            </template>
            <template v-else>{{ row.model_code || '—' }}<span class="name-hint">{{ row.model_name }}</span></template>
          </template>
        </el-table-column>

        <!-- 原因分类 -->
        <el-table-column v-else-if="colKey === 'reason_category'" min-width="100" resizable>
          <template #header>
            <div class="th-top">
              <span class="th-lbl">原因分类</span>
              <button :class="['sort-btn', sortIcon('reason_category') !== 'none' ? 'sort-' + sortIcon('reason_category') : '']" @click.stop="sortBy('reason_category')" />
            </div>
            <div class="th-filter-wrap" @click.stop>
              <el-select v-model="filters.reason_category" filterable clearable size="small" placeholder="筛选…" class="th-sel" :teleported="true" @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange">
                <el-option v-for="v in filterOptions.reason_categories" :key="v" :value="v" :label="v" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">
            <span v-if="!row._reasonsLoaded" class="loading-cell">…</span>
            <template v-else-if="editingRowKey === row._key">
              <el-select :model-value="rowEdits.categoryId" size="small" filterable clearable placeholder="选择分类" style="width:100%" @change="onEditCategory">
                <el-option v-for="g in editOptions?.reasons ?? []" :key="g.category_id" :value="g.category_id" :label="g.category_name" />
              </el-select>
            </template>
            <template v-else>{{ row.reason_category || '—' }}</template>
          </template>
        </el-table-column>

        <!-- 具体原因 -->
        <el-table-column v-else-if="colKey === 'reason_name'" min-width="120" resizable>
          <template #header>
            <div class="th-top">
              <span class="th-lbl">具体原因</span>
              <button :class="['sort-btn', sortIcon('reason_name') !== 'none' ? 'sort-' + sortIcon('reason_name') : '']" @click.stop="sortBy('reason_name')" />
            </div>
            <div class="th-filter-wrap" @click.stop>
              <el-select v-model="filters.reason_name" filterable clearable size="small" placeholder="筛选…" class="th-sel" :teleported="true" @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange">
                <el-option v-for="v in filterOptions.reason_names" :key="v" :value="v" :label="v" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">
            <span v-if="!row._reasonsLoaded" class="loading-cell">…</span>
            <template v-else-if="editingRowKey === row._key">
              <el-select :model-value="rowEdits.reasonId" size="small" filterable clearable placeholder="选择原因" style="width:100%" @change="onEditReason">
                <el-option v-for="r in getEditReasons()" :key="r.id" :value="r.id" :label="r.name" />
              </el-select>
            </template>
            <template v-else>{{ row.reason_name || '—' }}</template>
          </template>
        </el-table-column>

        <!-- 发货简称 -->
        <el-table-column v-else-if="colKey === 'shipping_alias'" min-width="110" resizable>
          <template #header>
            <div class="th-top">
              <span class="th-lbl">发货简称</span>
              <button :class="['sort-btn', sortIcon('shipping_alias_name') !== 'none' ? 'sort-' + sortIcon('shipping_alias_name') : '']" @click.stop="sortBy('shipping_alias_name')" />
            </div>
            <div class="th-filter-wrap" @click.stop>
              <el-select v-model="filters.shipping_alias" filterable clearable size="small" placeholder="筛选…" class="th-sel" :teleported="true" @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange">
                <el-option v-for="a in filterOptions.shipping_aliases" :key="a.id" :value="a.id" :label="a.name" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">
            <span v-if="!row._reasonsLoaded" class="loading-cell">…</span>
            <template v-else-if="editingRowKey === row._key">
              <el-select :model-value="rowEdits.aliasId" size="small" filterable clearable placeholder="选择简称" style="width:100%" @change="val => rowEdits.aliasId = val">
                <el-option v-for="a in editOptions?.aliases ?? []" :key="a.id" :value="a.id" :label="a.name" />
              </el-select>
            </template>
            <template v-else>{{ row.shipping_alias_name || '—' }}</template>
          </template>
        </el-table-column>

        <!-- 售后日期 -->
        <el-table-column v-else-if="colKey === 'shipped_date'" prop="shipped_date" width="100" resizable>
          <template #header>
            <div class="th-top">
              <span class="th-lbl">售后日期</span>
              <button :class="['sort-btn', sortIcon('shipped_date') !== 'none' ? 'sort-' + sortIcon('shipped_date') : '']" @click.stop="sortBy('shipped_date')" />
            </div>
            <div class="th-fph" />
          </template>
        </el-table-column>

        <!-- 购买日期 -->
        <el-table-column v-else-if="colKey === 'purchase_date'" width="100" resizable>
          <template #header>
            <div class="th-top">
              <span class="th-lbl">购买日期</span>
              <button :class="['sort-btn', sortIcon('purchase_date') !== 'none' ? 'sort-' + sortIcon('purchase_date') : '']" @click.stop="sortBy('purchase_date')" />
            </div>
            <div class="th-fph" />
          </template>
          <template #default="{ row }">
            <span v-if="!row._reasonsLoaded" class="loading-cell">…</span>
            <span v-else>{{ row.purchase_date || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 售后间隔 -->
        <el-table-column v-else-if="colKey === 'days_since_purchase'" width="88" resizable align="center">
          <template #header>
            <div class="th-top">
              <span class="th-lbl">售后间隔</span>
              <button :class="['sort-btn', sortIcon('days_since_purchase') !== 'none' ? 'sort-' + sortIcon('days_since_purchase') : '']" @click.stop="sortBy('days_since_purchase')" />
            </div>
            <div class="th-fph" />
          </template>
          <template #default="{ row }">
            <span v-if="!row._reasonsLoaded" class="loading-cell">…</span>
            <span v-else-if="row.days_since_purchase != null">{{ row.days_since_purchase }}天</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>

        <!-- 渠道 -->
        <el-table-column v-else-if="colKey === 'channel'" min-width="90" resizable>
          <template #header>
            <div class="th-top">
              <span class="th-lbl">渠道</span>
              <button :class="['sort-btn', sortIcon('channel_name') !== 'none' ? 'sort-' + sortIcon('channel_name') : '']" @click.stop="sortBy('channel_name')" />
            </div>
            <div class="th-filter-wrap" @click.stop>
              <el-select v-model="filters.channel" filterable clearable size="small" placeholder="筛选…" class="th-sel" :teleported="true" @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange">
                <el-option v-for="v in filterOptions.channels" :key="v" :value="v" :label="v" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">{{ row.channel_name || '—' }}</template>
        </el-table-column>

        <!-- 省份 -->
        <el-table-column v-else-if="colKey === 'province'" width="76" resizable>
          <template #header>
            <div class="th-top">
              <span class="th-lbl">省份</span>
              <button :class="['sort-btn', sortIcon('province') !== 'none' ? 'sort-' + sortIcon('province') : '']" @click.stop="sortBy('province')" />
            </div>
            <div class="th-filter-wrap" @click.stop>
              <el-select v-model="filters.province" filterable clearable size="small" placeholder="筛选…" class="th-sel" :teleported="true" @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange">
                <el-option v-for="v in filterOptions.provinces" :key="v" :value="v" :label="v" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">{{ row.province || '—' }}</template>
        </el-table-column>

        <!-- 买家留言 -->
        <el-table-column v-else-if="colKey === 'buyer_remark'" min-width="160" resizable show-overflow-tooltip>
          <template #header>
            <div class="th-top">
              <span class="th-lbl">买家留言</span>
              <button :class="['sort-btn', sortIcon('buyer_remark') !== 'none' ? 'sort-' + sortIcon('buyer_remark') : '']" @click.stop="sortBy('buyer_remark')" />
            </div>
            <div class="th-fph" />
          </template>
          <template #default="{ row }">
            <span class="remark-cell">{{ row.buyer_remark || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 商家备注 -->
        <el-table-column v-else-if="colKey === 'seller_remark'" min-width="160" resizable show-overflow-tooltip>
          <template #header>
            <div class="th-top">
              <span class="th-lbl">商家备注</span>
              <button :class="['sort-btn', sortIcon('seller_remark') !== 'none' ? 'sort-' + sortIcon('seller_remark') : '']" @click.stop="sortBy('seller_remark')" />
            </div>
            <div class="th-fph" />
          </template>
          <template #default="{ row }">
            <span class="remark-cell">{{ row.seller_remark || '—' }}</span>
          </template>
        </el-table-column>

      </template>

      <!-- 固定列：操作 -->
      <el-table-column label="操作" width="108" fixed="right" label-class-name="col-fixed">
        <template #default="{ row }">
          <span v-if="!row._reasonsLoaded" />
          <template v-else-if="editingRowKey === row._key">
            <el-button :icon="Check" size="small" type="primary" circle :loading="saving" class="btn-action" @click="confirmRowEdit(row)" />
            <el-button :icon="Close" size="small" circle class="btn-action" @click="cancelRowEdit" />
          </template>
          <template v-else>
            <el-button :icon="Edit" size="small" circle class="btn-action btn-edit" :disabled="!!editingRowKey || ignoring" @click="startRowEdit(row)" />
            <el-button :icon="Remove" size="small" circle class="btn-action btn-ignore" :disabled="!!editingRowKey || ignoring" title="忽略此订单" @click="ignoreCase(row)" />
          </template>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部：条/页 + 翻页 -->
    <div class="table-footer">
      <div class="footer-left">
        <select v-model="pageSize" class="page-size-select">
          <option v-for="n in PAGE_SIZE_OPTIONS" :key="n" :value="n">{{ n }}条/页</option>
        </select>
        <span class="footer-info">共 {{ total }} 条</span>
      </div>
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        small
        background
        @current-change="loadData"
      />
    </div>
  </div>
</template>

<style scoped>
.cases-table-wrap {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* 表格 */
.cases-table {
  flex: 1;
  overflow: auto;
  font-size: 12px;
}
:deep(.el-table__header th) { background: #f5f0e8 !important; color: var(--text-secondary); font-weight: 600; font-size: 12px; }
:deep(.el-table__header th:not(.col-fixed)) { cursor: grab; }
:deep(.el-table__header th:not(.col-fixed):active) { cursor: grabbing; }
:deep(.el-table__header th .cell) { white-space: nowrap; overflow: visible; text-overflow: clip; padding: 4px 8px; }
:deep(.sortable-ghost th), :deep(.sortable-ghost td) { background: #fdf3e3 !important; opacity: 0.6; }
:deep(.el-table__row:hover > td) { background: #faf7f2 !important; }
:deep(.el-table__column-resize-proxy) { border-color: var(--accent) !important; }
:deep(.el-table__row td .cell) { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* ── 两行列头 ─────────────────────────────────────── */
.th-top { display: flex; align-items: center; justify-content: center; gap: 4px; margin-bottom: 5px; white-space: nowrap; }
.th-lbl { font-size: 12px; font-weight: 700; color: var(--text-secondary); white-space: nowrap; line-height: 1.3; }
.sort-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; flex-shrink: 0;
  background: none; border: 1px solid transparent; border-radius: 4px; padding: 0; cursor: pointer; transition: all 0.15s; position: relative;
}
.sort-btn:hover { background: #fdf3e3; border-color: var(--border); }
.sort-btn::before, .sort-btn::after { content: ''; position: absolute; left: 50%; transform: translateX(-50%); width: 0; height: 0; border-style: solid; }
.sort-btn::before { top: 3px;    border-width: 0 3px 4px 3px; border-color: transparent transparent var(--border) transparent; }
.sort-btn::after  { bottom: 3px; border-width: 4px 3px 0 3px; border-color: var(--border) transparent transparent transparent; }
.sort-btn.sort-asc::before  { border-color: transparent transparent var(--accent) transparent; }
.sort-btn.sort-asc::after   { border-color: var(--border) transparent transparent transparent; }
.sort-btn.sort-desc::before { border-color: transparent transparent var(--border) transparent; }
.sort-btn.sort-desc::after  { border-color: var(--accent) transparent transparent transparent; }

.th-filter-wrap { position: relative; }
.th-sel { width: 100%; }
:deep(.th-sel .el-input__wrapper) { padding: 0 6px; height: 24px; border-radius: 5px; box-shadow: 0 0 0 1px var(--border) inset; }
:deep(.th-sel .el-input__wrapper:hover), :deep(.th-sel .el-input__wrapper.is-focus) { box-shadow: 0 0 0 1px var(--accent) inset; }
:deep(.th-sel .el-input__inner) { font-size: 11px; height: 22px; line-height: 22px; }
:deep(.th-sel .el-input__suffix) { height: 22px; }
.th-fph { height: 24px; }

.loading-cell { color: var(--text-muted); font-style: italic; }
.name-hint   { color: var(--text-muted); font-size: 11px; margin-left: 4px; }
.text-muted  { color: var(--text-muted); }
.remark-cell { color: var(--text-secondary); }
.option-hint { color: var(--text-muted); font-size: 11px; margin-left: 6px; }

.btn-action  { margin: 0 2px !important; }
.btn-edit    { color: var(--text-muted) !important; border-color: var(--border) !important; }
.btn-edit:hover   { color: var(--accent) !important; border-color: var(--accent) !important; }
.btn-ignore  { color: var(--text-muted) !important; border-color: var(--border) !important; }
.btn-ignore:hover { color: #d05a3c !important; border-color: #f0c0c0 !important; }

/* 展开行 */
.expand-products { padding: 6px 16px 6px 40px; background: #faf7f2; display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.product-tag { background: var(--bg-card); border-color: var(--border); color: var(--text-secondary); font-family: var(--font-family); }
.no-products { color: var(--text-muted); font-style: italic; font-size: 12px; }

/* 底部栏 */
.table-footer { flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; padding: 8px 4px 4px; border-top: 1px solid var(--border); }
.footer-left  { display: flex; align-items: center; gap: 10px; }
.page-size-select {
  font-size: 12px; border: 1px solid var(--border); border-radius: 6px;
  padding: 2px 6px; background: var(--bg-card); color: var(--text-secondary);
  cursor: pointer; outline: none;
}
.page-size-select:focus { border-color: var(--accent); }
.footer-info { font-size: 12px; color: var(--text-muted); }
</style>
