<script setup>
// ── 导入 ──────────────────────────────────────────
// 无

/**
 * DataTable — 全局统一样式的数据表格封装（基于 el-table）
 *
 * 目的：项目里散落了近 10 个页面各自手写 :deep(.el-table...) 样式覆盖，
 * 颜色/边框细节不一致（有的写死十六进制、有的干脆没覆盖）。这个组件把
 * themes.css 里已经定义好的 --bg-table-header / --bg-table-hover 等变量
 * 统一接到一处，页面只需要传 columns + data，不用再各自复制一遍表格样式。
 *
 * columns 数组每项：
 *   { prop, label, width, minWidth, align, fixed,
 *     sortable, sortMethod,        // 排序（本地数据用默认 sortable，自定义比较用 sortMethod）
 *     filters, filterMethod,       // 筛选（el-table 原生 filters 数组 + filterMethod）
 *     showOverflowTooltip }        // 默认继承 props.showOverflowTooltip
 *
 * 单元格自定义：#cell-{prop}具名 slot，作用域 { row, $index }
 * 无 prop 的列（比如操作列）：#cell-{label} 或直接用具名 slot，自行传 label 当 key
 */

defineProps({
  data:    { type: Array, default: () => [] },
  columns: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  rowKey:  { type: [String, Function], default: undefined },
  height:  { type: [String, Number], default: undefined },
  maxHeight: { type: [String, Number], default: undefined },
  size:    { type: String, default: 'default' },
  border:  { type: Boolean, default: true },
  stripe:  { type: Boolean, default: false },
  showOverflowTooltip: { type: Boolean, default: true },
  emptyText: { type: String, default: '暂无数据' },
})

defineEmits(['row-click', 'sort-change', 'filter-change'])

function slotKey(col) {
  return col.prop || col.label
}
</script>

<template>
  <div class="app-data-table" :class="{ 'app-data-table--bordered': border }">
    <el-table
      :data="data"
      :row-key="rowKey"
      :height="height"
      :max-height="maxHeight"
      :size="size"
      :border="border"
      :stripe="stripe"
      :show-overflow-tooltip="showOverflowTooltip"
      v-loading="loading"
      @row-click="(row, column, event) => $emit('row-click', { row, column, event })"
      @sort-change="(payload) => $emit('sort-change', payload)"
      @filter-change="(payload) => $emit('filter-change', payload)"
    >
      <el-table-column
        v-for="col in columns"
        :key="slotKey(col)"
        :prop="col.prop"
        :label="col.label"
        :width="col.width"
        :min-width="col.minWidth"
        :align="col.align"
        :fixed="col.fixed"
        :sortable="col.sortable"
        :sort-method="col.sortMethod"
        :filters="col.filters"
        :filter-method="col.filterMethod"
        :show-overflow-tooltip="col.showOverflowTooltip ?? showOverflowTooltip"
      >
        <template #default="scope">
          <slot :name="`cell-${slotKey(col)}`" v-bind="scope">
            {{ col.prop ? (scope.row[col.prop] ?? '—') : '' }}
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

/* ── 统一表头 ─────────────────────────────────────── */
.app-data-table :deep(.el-table__header th.el-table__cell) {
  background: var(--bg-table-header) !important;
  color: var(--text-secondary);
  font-weight: 600;
}
.app-data-table :deep(.el-table__header-wrapper) {
  background: var(--bg-table-header);
}

/* 展开列图标居中——用具体的 expand-column 类，不用 :first-child，
   避免误伤第一列是普通文本列的表格（历史上在 ProductTable.vue 踩过这个坑） */
.app-data-table :deep(.el-table__header th.el-table__cell.el-table__expand-column) {
  position: relative;
}
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
