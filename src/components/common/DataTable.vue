<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, reactive, computed } from 'vue'

/**
 * DataTable — 全局统一样式的数据表格封装（基于 el-table）
 *
 * 目的：项目里散落了近 10 个页面各自手写表格样式/排序/筛选，细节不一致。
 * 这个组件把 AftersaleCasesTable.vue 里已经验证好看的"两行表头"设计
 * （标题+排序按钮 一行，列筛选下拉 一行）抽成通用实现，页面只需要传
 * columns + data，不用再各自实现一套排序/筛选 UI。
 *
 * columns 数组每项：
 *   { prop, label, width, minWidth, align, fixed,
 *     sortable,                    // 本地排序，默认按值大小/字符串比较；数组等特殊值传 sortMethod(a, b)
 *     sortMethod,
 *     filterable,                  // 显示筛选下拉；未传 filterOptions 时自动从 data 里取该列去重值
 *     filterOptions,               // [{ label, value }]，不传则自动生成
 *     filterValue,                 // 自定义取筛选比较值的函数 (row) => any，默认取 row[prop]
 *     formatter,                   // 自定义显示格式 (row) => string，默认原样显示（空值显示"—"）
 *     showOverflowTooltip }
 *
 * 单元格自定义：#cell-{prop} 具名 slot，作用域 { row, $index }
 */

const props = defineProps({
  data:    { type: Array, default: () => [] },
  columns: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  rowKey:  { type: [String, Function], default: undefined },
  height:  { type: [String, Number], default: undefined },
  maxHeight: { type: [String, Number], default: undefined },
  size:    { type: String, default: 'default' },
  border:  { type: Boolean, default: true },
  stripe:  { type: Boolean, default: false },
  resizable: { type: Boolean, default: true },
  showOverflowTooltip: { type: Boolean, default: true },
  emptyText: { type: String, default: '暂无数据' },
})

defineEmits(['row-click'])

function slotKey(col) {
  return col.prop || col.label
}

function formatCell(col, row) {
  const value = row[col.prop]
  if (value == null || value === '') return '—'
  return col.formatter ? col.formatter(row) : value
}

// ── 列筛选 ────────────────────────────────────────
const colFilters = reactive({})

function filterValueOf(col, row) {
  return col.filterValue ? col.filterValue(row) : row[col.prop]
}

const filterOptionsOf = computed(() => {
  const map = {}
  for (const col of props.columns) {
    if (!col.filterable) continue
    if (col.filterOptions) { map[slotKey(col)] = col.filterOptions; continue }
    const seen = new Map()
    for (const row of props.data) {
      const v = filterValueOf(col, row)
      if (v != null && v !== '' && !seen.has(v)) seen.set(v, String(v))
    }
    map[slotKey(col)] = [...seen.entries()].map(([value, label]) => ({ label, value }))
  }
  return map
})

// ── 排序 ──────────────────────────────────────────
const sortState = ref({ prop: null, order: null }) // order: 'asc' | 'desc' | null

function isSortable(col) {
  return !!col.sortable
}
function sortIconClass(col) {
  if (sortState.value.prop !== slotKey(col) || !sortState.value.order) return ''
  return `sort-${sortState.value.order}`
}
function toggleSort(col) {
  if (!isSortable(col)) return
  const key = slotKey(col)
  const orders = ['asc', 'desc', null]
  const cur = sortState.value.prop === key ? sortState.value.order : null
  const next = orders[(orders.indexOf(cur) + 1) % orders.length]
  sortState.value = { prop: key, order: next }
}

function defaultCompare(a, b) {
  if (a == null && b == null) return 0
  if (a == null) return -1
  if (b == null) return 1
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b), 'zh')
}

// ── 组合筛选 + 排序后的展示数据 ─────────────────────
const displayData = computed(() => {
  let rows = props.data
  const activeFilters = props.columns.filter(c => c.filterable && colFilters[slotKey(c)] != null && colFilters[slotKey(c)] !== '')
  if (activeFilters.length) {
    rows = rows.filter(row => activeFilters.every(col => filterValueOf(col, row) === colFilters[slotKey(col)]))
  }
  if (sortState.value.prop && sortState.value.order) {
    const col = props.columns.find(c => slotKey(c) === sortState.value.prop)
    if (col) {
      const cmp = col.sortMethod || ((a, b) => defaultCompare(a[col.prop], b[col.prop]))
      rows = [...rows].sort((a, b) => sortState.value.order === 'asc' ? cmp(a, b) : cmp(b, a))
    }
  }
  return rows
})
</script>

<template>
  <div class="app-data-table" :class="{ 'app-data-table--bordered': border }">
    <el-table
      :data="displayData"
      :row-key="rowKey"
      :height="height"
      :max-height="maxHeight"
      :size="size"
      :border="border"
      :stripe="stripe"
      :show-overflow-tooltip="showOverflowTooltip"
      v-loading="loading"
      @row-click="(row, column, event) => $emit('row-click', { row, column, event })"
    >
      <el-table-column
        v-for="col in columns"
        :key="slotKey(col)"
        :prop="col.prop"
        :width="col.width"
        :min-width="col.minWidth"
        :align="col.align"
        :fixed="col.fixed"
        :resizable="resizable"
        :show-overflow-tooltip="col.showOverflowTooltip ?? showOverflowTooltip"
      >
        <template #header>
          <div class="th-top" :class="{ 'th-top--plain': !isSortable(col) }">
            <span class="th-lbl">{{ col.label }}</span>
            <button
              v-if="isSortable(col)"
              :class="['sort-btn', sortIconClass(col)]"
              @click.stop="toggleSort(col)"
            />
          </div>
          <el-select
            v-if="col.filterable"
            v-model="colFilters[slotKey(col)]"
            filterable clearable size="small" placeholder="筛选…" class="th-sel" :teleported="true"
          >
            <el-option v-for="opt in filterOptionsOf[slotKey(col)]" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </template>
        <template #default="scope">
          <slot :name="`cell-${slotKey(col)}`" v-bind="scope">
            {{ col.prop ? formatCell(col, scope.row) : '' }}
          </slot>
        </template>
      </el-table-column>

      <template #empty>
        <slot name="empty">
          <div class="app-data-table-empty">{{ emptyText }}</div>
        </slot>
      </template>
    </el-table>
  </div>
</template>

<style scoped>
.app-data-table { width: 100%; }

/* ── 两行表头：标题+排序 / 筛选下拉 ────────────────── */
.th-top { display: flex; align-items: center; justify-content: center; gap: 4px; white-space: nowrap; }
.th-top:not(.th-top--plain) { margin-bottom: 5px; }
.th-lbl { font-size: 12px; font-weight: 700; color: var(--text-secondary); white-space: nowrap; line-height: 1.3; }
.sort-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; flex-shrink: 0;
  background: none; border: 1px solid transparent; border-radius: 4px; padding: 0; cursor: pointer;
  transition: all 0.15s; position: relative;
}
.sort-btn:hover { background: rgba(196,136,58,0.08); border-color: var(--border); }
.sort-btn::before, .sort-btn::after { content: ''; position: absolute; left: 50%; transform: translateX(-50%); width: 0; height: 0; border-style: solid; }
.sort-btn::before { top: 3px;    border-width: 0 3px 4px 3px; border-color: transparent transparent var(--border) transparent; }
.sort-btn::after  { bottom: 3px; border-width: 4px 3px 0 3px; border-color: var(--border) transparent transparent transparent; }
.sort-btn.sort-asc::before  { border-color: transparent transparent var(--accent) transparent; }
.sort-btn.sort-desc::after  { border-color: var(--accent) transparent transparent transparent; }

.th-sel { width: 100%; }
.app-data-table :deep(.th-sel .el-input__wrapper) { padding: 0 6px; height: 24px; border-radius: 5px; box-shadow: 0 0 0 1px var(--border) inset; }
.app-data-table :deep(.th-sel .el-input__wrapper:hover), .app-data-table :deep(.th-sel .el-input__wrapper.is-focus) { box-shadow: 0 0 0 1px var(--accent) inset; }
.app-data-table :deep(.th-sel .el-input__inner) { font-size: 11px; height: 22px; line-height: 22px; }
.app-data-table :deep(.th-sel .el-input__suffix) { height: 22px; }

/* ── 统一表头背景 ─────────────────────────────────── */
.app-data-table :deep(.el-table__header th.el-table__cell) {
  background: var(--bg-table-header) !important;
  vertical-align: top;
  padding: 6px 4px;
}
.app-data-table :deep(.el-table__header-wrapper) { background: var(--bg-table-header); }

/* 展开列图标居中——用具体的 expand-column 类，不用 :first-child，
   避免误伤第一列是普通文本列的表格（历史上在 ProductTable.vue 踩过这个坑） */
.app-data-table :deep(.el-table__header th.el-table__cell.el-table__expand-column) { position: relative; }
.app-data-table :deep(.el-table__header th.el-table__cell.el-table__expand-column .cell) {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  padding: 0; overflow: visible;
}

/* ── 统一行 hover / 背景 ──────────────────────────── */
.app-data-table :deep(.el-table__row td.el-table__cell) { background: var(--bg-card); }
.app-data-table :deep(.el-table__row:hover td.el-table__cell) { background: var(--bg-table-hover) !important; }
.app-data-table :deep(.el-table__expanded-cell) { background: var(--bg-table-hover) !important; }

/* ── 滚动条 ───────────────────────────────────────── */
.app-data-table :deep(.el-table__body-wrapper)::-webkit-scrollbar { width: 4px; height: 5px; }
.app-data-table :deep(.el-table__body-wrapper)::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
.app-data-table :deep(.el-table__body-wrapper)::-webkit-scrollbar-track { background: transparent; }

/* ── 空状态 ───────────────────────────────────────── */
.app-data-table-empty {
  padding: 32px 0;
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
}
</style>
