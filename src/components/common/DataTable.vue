<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, reactive, computed, watch } from 'vue'

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
 *     filterable,                  // 显示筛选控件；未传 filterOptions 时自动从 data 里取该列去重值
 *     filterType,                  // 'select'(默认，下拉精确匹配) | 'text'(文本框模糊匹配)
 *     filterSuggest,               // 文本筛选时显示候选面板；候选值由 suggestProvider 提供
 *     filterOptions,               // [{ label, value }]，不传则自动生成
 *     filterValue,                 // 自定义取筛选比较值的函数 (row) => any，默认取 row[prop]
 *     formatter,                   // 自定义显示格式 (row) => string，默认原样显示（空值显示"—"）
 *     showOverflowTooltip }
 *
 * 单元格自定义：#cell-{prop} 具名 slot，作用域 { row, $index }
 *
 * serverMode：数据量大到不能整体塞进浏览器时（如物料库 8000+ 行走服务端分页），
 *   本组件不再本地筛选/排序，而是把筛选值与排序状态通过 filter-change / sort-change
 *   抛给调用方去请求服务端。对当前页做本地筛选排序是无意义的——用户要找的行
 *   大概率不在当页。默认 false，既有调用方行为完全不变。
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
  // 服务端筛选排序模式：本组件只负责 UI，不做本地筛选排序
  serverMode: { type: Boolean, default: false },
  // serverMode 下文本筛选的防抖毫秒数，避免逐字符打爆请求队列
  filterDebounce: { type: Number, default: 350 },
  // 候选面板数据源：(prop, keyword) => Promise<string[]>
  // 大数据量下候选值只能由服务端给，不能从当页数据里推。
  suggestProvider: { type: Function, default: null },
})

const emit = defineEmits(['row-click', 'filter-change', 'sort-change'])

// el-table 的 height 是百分比时，必须让本组件根元素也拿到同一高度，
// 否则百分比对着 auto 高度的父元素解析不出来，el-table 会退化成内容高度、
// 撑破容器且无法滚动（height="65vh" 这类视口单位不受影响，所以以前没暴露）。
const rootStyle = computed(() => {
  if (props.height == null || props.height === '') return null
  const h = typeof props.height === 'number' ? `${props.height}px` : props.height
  return { height: h, minHeight: 0 }
})

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

function isTextFilter(col) {
  return col.filterType === 'text'
}

const filterOptionsOf = computed(() => {
  const map = {}
  for (const col of props.columns) {
    // 文本筛选不需要候选项；serverMode 下也无法从当页数据推出完整候选
    if (!col.filterable || isTextFilter(col) || props.serverMode) continue
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
  if (props.serverMode) emit('sort-change', { prop: key, order: next })
}

function defaultCompare(a, b) {
  if (a == null && b == null) return 0
  if (a == null) return -1
  if (b == null) return 1
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b), 'zh')
}

// ── 候选面板 ──────────────────────────────────────
const suggest = reactive({})     // { [key]: { show, list, loading } }
const suggestTimers = {}

function suggestOf(col) {
  const key = slotKey(col)
  if (!suggest[key]) suggest[key] = { show: false, list: [], loading: false }
  return suggest[key]
}

function fetchSuggest(col) {
  if (!props.suggestProvider || !col.filterSuggest) return
  const key = slotKey(col)
  const state = suggestOf(col)
  const q = String(colFilters[key] ?? '').trim()
  clearTimeout(suggestTimers[key])
  if (!q) { state.show = false; state.list = []; return }
  suggestTimers[key] = setTimeout(async () => {
    state.loading = true
    try {
      const list = await props.suggestProvider(col.prop, q)
      state.list = Array.isArray(list) ? list : []
      state.show = state.list.length > 0
    } catch {
      state.list = []
      state.show = false
    } finally {
      state.loading = false
    }
  }, props.filterDebounce)
}

function applySuggest(col, value) {
  const key = slotKey(col)
  colFilters[key] = value
  suggestOf(col).show = false
}

// 延迟隐藏，否则 blur 会先于候选项的点击触发，导致点不中
function hideSuggest(col) {
  setTimeout(() => { suggestOf(col).show = false }, 160)
}

const hasSuggestColumn = computed(() =>
  props.columns.some(c => c.filterable && c.filterType === 'text' && c.filterSuggest))

// ── serverMode：筛选值变化抛给调用方 ────────────────
let filterTimer = null
watch(colFilters, () => {
  if (!props.serverMode) return
  clearTimeout(filterTimer)
  // 文本筛选防抖；下拉是明确动作，立即触发
  const hasText = props.columns.some(c => isTextFilter(c))
  const delay = hasText ? props.filterDebounce : 0
  filterTimer = setTimeout(() => emit('filter-change', { ...colFilters }), delay)
}, { deep: true })

// ── 组合筛选 + 排序后的展示数据 ─────────────────────
const displayData = computed(() => {
  // serverMode 下数据已由服务端筛选、排序、分页，原样呈现
  if (props.serverMode) return props.data
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
  <div
    class="app-data-table"
    :class="{ 'app-data-table--bordered': border, 'app-data-table--suggest': hasSuggestColumn }"
    :style="rootStyle"
  >
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
          <div v-if="col.filterable && col.filterType === 'text'" class="th-txt-wrap" @click.stop>
            <input
              v-model="colFilters[slotKey(col)]"
              class="th-txt"
              placeholder="筛选…"
              @input="fetchSuggest(col)"
              @focus="fetchSuggest(col)"
              @blur="hideSuggest(col)"
            />
            <ul v-if="suggestOf(col).show" class="sg-list">
              <li
                v-for="item in suggestOf(col).list"
                :key="item"
                class="sg-item"
                :title="item"
                @mousedown.prevent="applySuggest(col, item)"
              >{{ item }}</li>
            </ul>
          </div>
          <el-select
            v-else-if="col.filterable"
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
.app-data-table { width: 100%; box-sizing: border-box; }

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
/* 文本筛选框：高度与 .th-sel 下拉保持一致，视觉上同一排 */
.th-txt {
  width: 100%; height: 24px; padding: 0 6px;
  border: 1px solid var(--border); border-radius: 5px;
  background: var(--bg-card); color: var(--text-primary);
  font-size: 11px; font-family: inherit; outline: none;
  transition: border-color 0.15s;
}
.th-txt:focus { border-color: var(--accent); }
.th-txt::placeholder { color: var(--text-muted); }

/* 候选面板 ─ 绝对定位浮在表头下方 */
.th-txt-wrap { position: relative; }
.sg-list {
  position: absolute; top: calc(100% + 2px); left: 0; right: 0; z-index: 9999;
  margin: 0; padding: 4px 0; list-style: none; text-align: left;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.10); max-height: 220px; overflow-y: auto;
}
.sg-list::-webkit-scrollbar { width: 4px; }
.sg-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.sg-item {
  padding: 5px 9px; font-size: 11px; color: var(--text-primary); cursor: pointer;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: background 0.1s;
}
.sg-item:hover { background: var(--accent-bg); color: var(--accent); }

/* 候选面板会被表头单元格的 overflow:hidden 裁掉，只在启用候选的表格上放开，
   避免影响其他调用方（如产品库产成品清单）的表头裁剪行为 */
.app-data-table--suggest :deep(.el-table__header th.el-table__cell .cell) { overflow: visible; }
.app-data-table--suggest :deep(.el-table__header-wrapper) { overflow: visible; }
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
