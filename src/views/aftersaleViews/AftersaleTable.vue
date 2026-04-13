<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, watch, onMounted } from 'vue'
import http from '@/api/http.js'

// ── 列定义（动态宽度列） ───────────────────────────
const COL_DEFS = [
  { key: 'order_no',        header: '订单号',       sortBtn: true,  pad: 44, min: 140, max: 260 },
  { key: 'model',           header: '产品',          sortBtn: false, pad: 44, min: 130, max: 220 },
  { key: 'reason_category', header: '一级原因',      sortBtn: false, pad: 44, min: 90,  max: 160 },
  { key: 'reason_name',     header: '二级原因',      sortBtn: false, pad: 44, min: 100, max: 220 },
  { key: 'channel',         header: '渠道',          sortBtn: true,  pad: 44, min: 90,  max: 200 },
  { key: 'province',        header: '省份',          sortBtn: true,  pad: 44, min: 72,  max: 120 },
  { key: 'city',            header: '城市',          sortBtn: false, pad: 44, min: 72,  max: 120 },
  { key: 'district',        header: '县区',          sortBtn: false, pad: 44, min: 72,  max: 120 },
  { key: 'shipping_alias',  header: '发货物料简称',  sortBtn: false, pad: 44, min: 115, max: 180 },
  { key: 'return_alias',    header: '售后物料简称',  sortBtn: false, pad: 44, min: 115, max: 180 },
]
// 固定宽度列（不参与动态计算）
const W_PURCHASE = 100
const W_SHIPPED  = 100
const W_DAYS     = 72

// ── 列宽状态 ──────────────────────────────────────
const colWidths = ref(Object.fromEntries(COL_DEFS.map(d => [d.key, d.min])))

let _canvas = null
function measureText(text, bold = false) {
  if (!_canvas) _canvas = document.createElement('canvas')
  const ctx = _canvas.getContext('2d')
  ctx.font = `${bold ? 'bold ' : ''}12px "Microsoft YaHei UI","Microsoft YaHei",sans-serif`
  return ctx.measureText(String(text ?? '')).width
}

function cellValue(row, key) {
  const r0 = row.reasons?.[0]
  switch (key) {
    case 'order_no':        return row.ecommerce_order_no || ''
    case 'model':           return [(r0?.model_code || ''), (r0?.model_name || '')].filter(Boolean).join(' ')
    case 'reason_category': return r0?.reason_category || ''
    case 'reason_name':     return r0?.reason_name || ''
    case 'channel':         return row.channel_name || ''
    case 'province':        return row.province || ''
    case 'city':            return row.city || ''
    case 'district':        return row.district || ''
    case 'shipping_alias':  return r0?.shipping_alias_name || ''
    case 'return_alias':    return r0?.return_alias_name   || ''
    default:                return ''
  }
}

function calcColWidths() {
  const sample = items.value.slice(0, 100)
  const result = {}
  for (const def of COL_DEFS) {
    // 表头宽 = 粗体标签文字 + 排序按钮（如有）
    let maxW = measureText(def.header, true) + (def.sortBtn ? 26 : 0)
    for (const row of sample) {
      const w = measureText(cellValue(row, def.key))
      if (w > maxW) maxW = w
    }
    result[def.key] = Math.min(def.max, Math.max(def.min, Math.ceil(maxW) + def.pad))
  }
  colWidths.value = result
}

// ── 响应式状态 ────────────────────────────────────
const items    = ref([])
const total    = ref(0)
const page     = ref(1)
const pageSize = ref(50)
const loading  = ref(false)

// 工具栏筛选
const statusFilter = ref('confirmed')
const dateRange    = ref([])

// 列头筛选
const filters = ref({
  search:          '',
  model_code:      '',
  channel:         '',
  province:        '',
  city:            '',
  district:        '',
  reason_category: '',
  reason_name:     '',
  shipping_alias:  '',
  return_alias:    '',
})

// 筛选下拉候选项（懒加载：第一次展开下拉时才请求）
const filterOptions = ref({
  model_codes:       [],
  channels:          [],
  provinces:         [],
  cities:            [],
  districts:         [],
  reason_categories: [],
  reason_names:      [],
  shipping_aliases:  [],
  return_aliases:    [],
})

// 排序
const currentSortBy    = ref('shipped_date')
const currentSortOrder = ref('desc')

// 展开行
const expandedRows = ref([])

// ── 生命周期 ──────────────────────────────────────
onMounted(() => {
  loadData()
})

// 数据更新后重算列宽
watch(items, (val) => {
  if (val.length > 0) requestAnimationFrame(calcColWidths)
})

// ── 方法 ──────────────────────────────────────────

// 懒加载：第一次展开任意列筛选下拉时触发一次
let _filterOptLoaded = false
async function onFilterDropdownOpen() {
  if (_filterOptLoaded) return
  _filterOptLoaded = true
  const res = await http.get('/api/aftersale/filter-options')
  if (res.success) filterOptions.value = { ...filterOptions.value, ...res.data }
}

// 当前加载批次号，用于取消过期的后台请求
let _loadSeq = 0

async function loadData() {
  loading.value = true
  const seq = ++_loadSeq
  try {
    const f = filters.value
    const params = {
      page:             page.value,
      page_size:        pageSize.value,
      status:           statusFilter.value || undefined,
      date_start:       dateRange.value?.[0] || undefined,
      date_end:         dateRange.value?.[1] || undefined,
      search:           f.search || undefined,
      model_code:       f.model_code || undefined,
      channel_name:     f.channel || undefined,
      province:         f.province || undefined,
      city:             f.city || undefined,
      district:         f.district || undefined,
      reason_category:  f.reason_category || undefined,
      reason_name:      f.reason_name || undefined,
      shipping_alias:   f.shipping_alias || undefined,
      return_alias:     f.return_alias || undefined,
      sort_by:          currentSortBy.value || undefined,
      sort_order:       currentSortOrder.value,
    }

    // 阶段一：拿基础数据（不含 reasons），快速呈现
    const res = await http.get('/api/aftersale/cases', { params })
    if (!res.success || seq !== _loadSeq) return
    items.value = res.data.items.map(r => ({ ...r, reasons: null }))
    total.value = res.data.total
    loading.value = false

    // 阶段二：后台拉 reasons，合并进去
    const ids = res.data.items.map(r => r.id)
    if (!ids.length) return
    const r2 = await http.get('/api/aftersale/cases/reasons', { params: { ids: ids.join(',') } })
    if (!r2.success || seq !== _loadSeq) return
    items.value = items.value.map(row => ({
      ...row,
      reasons: r2.data[String(row.id)] ?? [],
    }))
  } finally {
    if (seq === _loadSeq) loading.value = false
  }
}

function onPageChange(p) { page.value = p; loadData() }
function onSizeChange(s) { pageSize.value = s; page.value = 1; loadData() }
function onToolbarFilterChange() { page.value = 1; loadData() }

let filterTimer = null
function onColFilterChange() {
  clearTimeout(filterTimer)
  filterTimer = setTimeout(() => { page.value = 1; loadData() }, 300)
}

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

function toggleExpand(row) {
  const id = row.id
  const idx = expandedRows.value.indexOf(id)
  if (idx === -1) expandedRows.value.push(id)
  else expandedRows.value.splice(idx, 1)
}

function firstReason(row, field) { return row.reasons?.[0]?.[field] ?? null }
function extraCount(row) { return (row.reasons?.length || 0) - 1 }

function minDaysSincePurchase(row) {
  if (!row.reasons?.length) return null
  const vals = row.reasons.map(r => r.days_since_purchase).filter(v => v != null)
  return vals.length ? Math.min(...vals) : null
}

defineExpose({ refresh: loadData })
</script>

<template>
  <div class="table-wrap">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-date-picker
        v-model="dateRange"
        type="daterange" size="small" range-separator="~"
        start-placeholder="售后日期起" end-placeholder="售后日期止"
        value-format="YYYY-MM-DD" style="width:230px"
        @change="onToolbarFilterChange"
      />
      <span class="total-hint">共 {{ total }} 条</span>
    </div>

    <!-- 表格：不设宽度，列固定宽，整体可横向滚动 -->
    <div class="table-container">
      <el-table
        v-loading="loading"
        :data="items"
        row-key="id"
        border
        size="small"
        :expand-row-keys="expandedRows.map(String)"
        @row-click="toggleExpand"
      >
        <!-- 展开列 -->
        <el-table-column type="expand" width="30">
          <template #default="{ row }">
            <div class="expand-content">
              <div class="expand-row">
                <span class="expand-label">商家备注</span>
                <span class="expand-val">{{ row.seller_remark || '—' }}</span>
              </div>
              <div class="expand-row">
                <span class="expand-label">买家留言</span>
                <span class="expand-val">{{ row.buyer_remark || '—' }}</span>
              </div>
              <div class="expand-row">
                <span class="expand-label">发货物料</span>
                <div class="products-inline">
                  <span v-if="!row.products?.length" class="empty-val">—</span>
                  <span v-for="p in row.products" :key="p.code" class="prod-tag">
                    {{ p.code }} {{ p.name }} ×{{ p.quantity }}
                  </span>
                </div>
              </div>
            </div>
          </template>
        </el-table-column>

        <!-- 订单号 -->
        <el-table-column :width="colWidths.order_no">
          <template #header>
            <div class="th-top">
              <span class="th-lbl">订单号</span>
              <button :class="['sort-btn', sortIcon('ecommerce_order_no') !== 'none' ? 'sort-' + sortIcon('ecommerce_order_no') : '']" @click.stop="sortBy('ecommerce_order_no')" />
            </div>
            <div class="th-filter-wrap" @click.stop>
              <el-select
                v-model="filters.search" filterable allow-create clearable size="small"
                placeholder="筛选..." class="th-sel" :teleported="true"
                @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange"
              ><el-option v-for="v in []" :key="v" :value="v" :label="v" /></el-select>
            </div>
          </template>
          <template #default="{ row }">{{ row.ecommerce_order_no }}</template>
        </el-table-column>

        <!-- 产品 -->
        <el-table-column :width="colWidths.model">
          <template #header>
            <div class="th-top"><span class="th-lbl">产品</span></div>
            <div class="th-filter-wrap" @click.stop>
              <el-select
                v-model="filters.model_code" filterable clearable size="small"
                placeholder="筛选..." class="th-sel" :teleported="true"
                @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange"
              >
                <el-option v-for="v in filterOptions.model_codes" :key="v" :value="v" :label="v" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">
            <div class="cell-with-badge">
              <span v-if="firstReason(row, 'model_code') || firstReason(row, 'model_name')" class="model-cell">
                <span class="model-code-text">{{ firstReason(row, 'model_code') }}</span>
                <span v-if="firstReason(row, 'model_name')" class="model-name-text">{{ firstReason(row, 'model_name') }}</span>
              </span>
              <span v-else class="empty-val">—</span>
              <span v-if="extraCount(row) > 0" class="multi-badge" :title="`共 ${row.reasons.length} 条售后记录`">+{{ extraCount(row) }}</span>
            </div>
          </template>
        </el-table-column>

        <!-- 一级原因 -->
        <el-table-column :width="colWidths.reason_category">
          <template #header>
            <div class="th-top"><span class="th-lbl">一级原因</span></div>
            <div class="th-filter-wrap" @click.stop>
              <el-select
                v-model="filters.reason_category" filterable clearable size="small"
                placeholder="筛选..." class="th-sel" :teleported="true"
                @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange"
              >
                <el-option v-for="v in filterOptions.reason_categories" :key="v" :value="v" :label="v" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">
            <div class="cell-with-badge">
              <span>{{ firstReason(row, 'reason_category') || '—' }}</span>
              <span v-if="extraCount(row) > 0" class="multi-badge">+{{ extraCount(row) }}</span>
            </div>
          </template>
        </el-table-column>

        <!-- 二级原因 -->
        <el-table-column :width="colWidths.reason_name">
          <template #header>
            <div class="th-top"><span class="th-lbl">二级原因</span></div>
            <div class="th-filter-wrap" @click.stop>
              <el-select
                v-model="filters.reason_name" filterable clearable size="small"
                placeholder="筛选..." class="th-sel" :teleported="true"
                @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange"
              >
                <el-option v-for="v in filterOptions.reason_names" :key="v" :value="v" :label="v" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">
            <div class="cell-with-badge">
              <span>{{ firstReason(row, 'reason_name') || firstReason(row, 'custom_reason') || '—' }}</span>
              <span v-if="extraCount(row) > 0" class="multi-badge">+{{ extraCount(row) }}</span>
            </div>
          </template>
        </el-table-column>

        <!-- 购买日期 -->
        <el-table-column prop="purchase_date" :width="W_PURCHASE">
          <template #header>
            <div class="th-top">
              <span class="th-lbl">购买日期</span>
              <button :class="['sort-btn', sortIcon('purchase_date') !== 'none' ? 'sort-' + sortIcon('purchase_date') : '']" @click.stop="sortBy('purchase_date')" />
            </div>
            <div class="th-fph" />
          </template>
        </el-table-column>

        <!-- 售后日期 -->
        <el-table-column prop="shipped_date" :width="W_SHIPPED">
          <template #header>
            <div class="th-top">
              <span class="th-lbl">售后日期</span>
              <button :class="['sort-btn', sortIcon('shipped_date') !== 'none' ? 'sort-' + sortIcon('shipped_date') : '']" @click.stop="sortBy('shipped_date')" />
            </div>
            <div class="th-fph" />
          </template>
        </el-table-column>

        <!-- 间隔天 -->
        <el-table-column :width="W_DAYS" align="center">
          <template #header>
            <div class="th-top">
              <span class="th-lbl">间隔天</span>
              <button :class="['sort-btn', sortIcon('days_since_purchase') !== 'none' ? 'sort-' + sortIcon('days_since_purchase') : '']" @click.stop="sortBy('days_since_purchase')" />
            </div>
            <div class="th-fph" />
          </template>
          <template #default="{ row }">
            <template v-if="row.reasons">
              <span v-if="minDaysSincePurchase(row) != null">{{ minDaysSincePurchase(row) }}</span>
              <span v-else class="empty-val">—</span>
            </template>
            <span v-else class="empty-val">—</span>
          </template>
        </el-table-column>

        <!-- 渠道 -->
        <el-table-column :width="colWidths.channel">
          <template #header>
            <div class="th-top">
              <span class="th-lbl">渠道</span>
              <button :class="['sort-btn', sortIcon('channel_name') !== 'none' ? 'sort-' + sortIcon('channel_name') : '']" @click.stop="sortBy('channel_name')" />
            </div>
            <div class="th-filter-wrap" @click.stop>
              <el-select
                v-model="filters.channel" filterable clearable size="small"
                placeholder="筛选..." class="th-sel" :teleported="true"
                @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange"
              >
                <el-option v-for="v in filterOptions.channels" :key="v" :value="v" :label="v" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">{{ row.channel_name || '—' }}</template>
        </el-table-column>

        <!-- 省份 -->
        <el-table-column :width="colWidths.province">
          <template #header>
            <div class="th-top">
              <span class="th-lbl">省份</span>
              <button :class="['sort-btn', sortIcon('province') !== 'none' ? 'sort-' + sortIcon('province') : '']" @click.stop="sortBy('province')" />
            </div>
            <div class="th-filter-wrap" @click.stop>
              <el-select
                v-model="filters.province" filterable clearable size="small"
                placeholder="筛选..." class="th-sel" :teleported="true"
                @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange"
              >
                <el-option v-for="v in filterOptions.provinces" :key="v" :value="v" :label="v" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">{{ row.province || '—' }}</template>
        </el-table-column>

        <!-- 城市 -->
        <el-table-column :width="colWidths.city">
          <template #header>
            <div class="th-top"><span class="th-lbl">城市</span></div>
            <div class="th-filter-wrap" @click.stop>
              <el-select
                v-model="filters.city" filterable clearable size="small"
                placeholder="筛选..." class="th-sel" :teleported="true"
                @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange"
              >
                <el-option v-for="v in filterOptions.cities" :key="v" :value="v" :label="v" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">{{ row.city || '—' }}</template>
        </el-table-column>

        <!-- 县区 -->
        <el-table-column :width="colWidths.district">
          <template #header>
            <div class="th-top"><span class="th-lbl">县区</span></div>
            <div class="th-filter-wrap" @click.stop>
              <el-select
                v-model="filters.district" filterable clearable size="small"
                placeholder="筛选..." class="th-sel" :teleported="true"
                @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange"
              >
                <el-option v-for="v in filterOptions.districts" :key="v" :value="v" :label="v" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">{{ row.district || '—' }}</template>
        </el-table-column>

        <!-- 发货物料简称 -->
        <el-table-column :width="colWidths.shipping_alias">
          <template #header>
            <div class="th-top"><span class="th-lbl">发货物料简称</span></div>
            <div class="th-filter-wrap" @click.stop>
              <el-select
                v-model="filters.shipping_alias" filterable clearable size="small"
                placeholder="筛选..." class="th-sel" :teleported="true"
                @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange"
              >
                <el-option v-for="v in filterOptions.shipping_aliases" :key="v.id" :value="v.id" :label="v.name" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">
            <div class="cell-with-badge">
              <span>{{ firstReason(row, 'shipping_alias') || '—' }}</span>
              <span v-if="extraCount(row) > 0" class="multi-badge">+{{ extraCount(row) }}</span>
            </div>
          </template>
        </el-table-column>

        <!-- 售后物料简称 -->
        <el-table-column :width="colWidths.return_alias">
          <template #header>
            <div class="th-top"><span class="th-lbl">售后物料简称</span></div>
            <div class="th-filter-wrap" @click.stop>
              <el-select
                v-model="filters.return_alias" filterable clearable size="small"
                placeholder="筛选..." class="th-sel" :teleported="true"
                @visible-change="onFilterDropdownOpen" @change="onColFilterChange" @clear="onColFilterChange"
              >
                <el-option v-for="v in filterOptions.return_aliases" :key="v.id" :value="v.id" :label="v.name" />
              </el-select>
            </div>
          </template>
          <template #default="{ row }">
            <div class="cell-with-badge">
              <span>{{ firstReason(row, 'return_alias') || '—' }}</span>
              <span v-if="extraCount(row) > 0" class="multi-badge">+{{ extraCount(row) }}</span>
            </div>
          </template>
        </el-table-column>

      </el-table>
    </div>

    <!-- 分页 -->
    <div class="pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        size="small"
        @current-change="onPageChange"
        @size-change="onSizeChange"
      />
    </div>
  </div>
</template>

<style scoped>
.table-wrap {
  flex: 1; display: flex; flex-direction: column;
  overflow: hidden; padding: 12px 16px;
}

.toolbar {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 10px; flex-wrap: wrap;
}
.total-hint {
  font-size: 12px; color: var(--text-muted); margin-left: auto;
}

/* 容器横向滚动，表格自然撑开 */
.table-container {
  flex: 1; overflow: auto;
}
.table-container::-webkit-scrollbar { width: 4px; height: 4px; }
.table-container::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.table-container::-webkit-scrollbar-track { background: transparent; }

.pagination {
  padding-top: 10px; display: flex; justify-content: flex-end;
}

/* ── 表头 ───────────────────────────────────────── */
.th-top {
  display: flex; align-items: center; justify-content: center; gap: 4px;
  margin-bottom: 5px; white-space: nowrap;
}
.th-lbl {
  font-size: 12px; font-weight: 700; color: var(--text-secondary);
  white-space: nowrap; line-height: 1.3;
}
.sort-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; flex-shrink: 0;
  background: none; border: 1px solid transparent;
  border-radius: 4px; padding: 0; cursor: pointer;
  transition: all 0.15s; position: relative;
}
.sort-btn:hover { background: var(--accent-bg); border-color: var(--border); }
.sort-btn::before, .sort-btn::after {
  content: ''; position: absolute;
  left: 50%; transform: translateX(-50%);
  width: 0; height: 0; border-style: solid;
}
.sort-btn::before { top: 3px; border-width: 0 3px 4px 3px; border-color: transparent transparent var(--border) transparent; }
.sort-btn::after  { bottom: 3px; border-width: 4px 3px 0 3px; border-color: var(--border) transparent transparent transparent; }
.sort-btn.sort-asc::before  { border-color: transparent transparent var(--accent) transparent; }
.sort-btn.sort-asc::after   { border-color: var(--border) transparent transparent transparent; }
.sort-btn.sort-desc::before { border-color: transparent transparent var(--border) transparent; }
.sort-btn.sort-desc::after  { border-color: var(--accent) transparent transparent transparent; }

.th-filter-wrap { position: relative; }
.th-sel { width: 100%; }
:deep(.th-sel .el-input__wrapper) {
  padding: 0 6px; height: 24px; border-radius: 5px;
  box-shadow: 0 0 0 1px var(--border) inset;
}
:deep(.th-sel .el-input__wrapper:hover),
:deep(.th-sel .el-input__wrapper.is-focus) { box-shadow: 0 0 0 1px var(--accent) inset; }
:deep(.th-sel .el-input__inner) { font-size: 11px; height: 22px; line-height: 22px; }
:deep(.th-sel .el-input__suffix) { height: 22px; }
/* 无筛选列的占位 */
.th-fph { height: 24px; }

/* 表头单元格不截断 */
:deep(.el-table__header th .cell) {
  white-space: nowrap; overflow: visible; text-overflow: clip; padding: 6px 8px;
}

/* ── 单元格 ─────────────────────────────────────── */
.model-cell { display: inline-flex; flex-direction: column; gap: 1px; }
.model-code-text { font-size: 12px; font-weight: 600; color: var(--text-primary); }
.model-name-text { font-size: 11px; color: var(--text-muted); }

.cell-with-badge { display: flex; align-items: center; gap: 4px; }
.multi-badge {
  flex-shrink: 0; padding: 0 5px;
  background: #f0ece4; border: 1px solid var(--border);
  border-radius: 8px; font-size: 10px; color: var(--text-muted); line-height: 16px;
}
.empty-val { color: var(--text-muted); }

/* ── 展开行 ─────────────────────────────────────── */
.expand-content {
  padding: 10px 20px 12px 40px;
  background: #faf7f2; border-top: 1px solid var(--border);
}
.expand-row {
  display: flex; gap: 12px; margin-bottom: 8px;
  font-size: 12px; line-height: 1.6;
}
.expand-label {
  width: 68px; flex-shrink: 0;
  font-weight: 600; color: var(--text-muted);
}
.expand-val { color: var(--text-primary); }
.products-inline { display: flex; flex-wrap: wrap; gap: 4px; }
.prod-tag {
  padding: 2px 8px; background: #f5f0e8;
  border: 1px solid var(--border); border-radius: 4px;
  font-size: 11px; color: var(--text-primary);
}
</style>
