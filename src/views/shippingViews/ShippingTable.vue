<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, reactive, computed, watch, onMounted } from 'vue'
import http from '@/api/http'

// ── 可排序字段集合 ─────────────────────────────────
const SORTABLE = new Set([
  'shipped_date', 'quantity', 'return_quantity', 'actual_quantity',
  'finished_code', 'ecommerce_order_no', 'series_code', 'model_code',
])

// ── 响应式状态 ────────────────────────────────────
const loading  = ref(false)
const items    = ref([])
const total    = ref(0)
const page     = ref(1)
const pageSize = ref(50)

// 日期筛选
const dateRange = ref(null)   // [string, string] | null（YYYY-MM-DD）

// 列头文本筛选
const colFilter = reactive({
  ecommerce_order_no: '',
  finished_code:      '',
  finished_name:      '',
  category_name:      '',
  series_code:        '',
  model_code:         '',
  channel_name:       '',
  channel_code:       '',
  channel_org_name:   '',
  province:           '',
  city:               '',
  district:           '',
})

// 排序
const sortField = ref('shipped_date')
const sortOrder = ref('desc')   // 'asc' | 'desc'

// 防抖 timer
let _debounceTimer = null

// ── 方法 ──────────────────────────────────────────
// 构建请求参数（computed 做缓存）
const fetchParams = computed(() => {
  const p = {
    page:       page.value,
    size:       pageSize.value,
    sort_field: sortField.value,
    sort_order: sortOrder.value,
  }
  if (dateRange.value?.[0]) p.date_start = dateRange.value[0]
  if (dateRange.value?.[1]) p.date_end   = dateRange.value[1]
  Object.entries(colFilter).forEach(([k, v]) => { if (v) p[k] = v })
  return p
})

async function fetchData() {
  loading.value = true
  try {
    const res = await http.get('/api/shipping/orders', { params: fetchParams.value })
    if (res.success) {
      items.value = res.data.items
      total.value = res.data.total
    }
  } finally {
    loading.value = false
  }
}

// 筛选变化：重置到第 1 页后防抖查询
function onFilterChange() {
  page.value = 1
  clearTimeout(_debounceTimer)
  _debounceTimer = setTimeout(fetchData, 280)
}

// 排序点击（循环切换 desc → asc → desc）
function sortBy(field) {
  if (!SORTABLE.has(field)) return
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortOrder.value = 'desc'
  }
  page.value = 1
  fetchData()
}

function sortIcon(field) {
  if (sortField.value !== field) return 'none'
  return sortOrder.value
}

function resetFilters() {
  Object.keys(colFilter).forEach(k => { colFilter[k] = '' })
  dateRange.value = null
  sortField.value = 'shipped_date'
  sortOrder.value = 'desc'
  page.value      = 1
  fetchData()
}

// 数字格式化：整数不显示小数，否则保留 1 位
function fmtNum(v) {
  if (v == null) return '—'
  const n = Number(v)
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
}

// 当前页行序号（从 1 开始）
function rowNo(idx) {
  return (page.value - 1) * pageSize.value + idx + 1
}

// ── 生命周期 ──────────────────────────────────────
onMounted(() => fetchData())

// 换页直接查询
watch(page,     () => fetchData())
watch(pageSize, () => { page.value = 1; fetchData() })

// 列头筛选防抖
watch(colFilter, onFilterChange, { deep: true })
// 日期范围立即查询
watch(dateRange, onFilterChange)
</script>

<template>
  <div class="st-root">
    <div class="card">

      <!-- ── 顶栏：日期范围 + 统计 + 重置 ──────── -->
      <div class="card-topbar">
        <div class="topbar-left">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="—"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            size="small"
            value-format="YYYY-MM-DD"
            style="width:240px"
            :clearable="true"
          />
        </div>
        <div class="topbar-right">
          <span class="total-hint">共 {{ total }} 条</span>
          <button class="reset-btn" title="重置筛选和排序" @click="resetFilters">↺ 重置</button>
        </div>
      </div>

      <!-- ── 表格 ─────────────────────────────── -->
      <div class="table-wrap" v-loading="loading" element-loading-background="rgba(255,255,255,0.7)">
        <el-table
          :data="items"
          size="small"
          height="100%"
          border
          scrollbar-always-on
          :tooltip-effect="'light'"
          :show-overflow-tooltip="true"
        >

          <!-- No. -->
          <el-table-column width="52" align="center" fixed="left">
            <template #header>
              <div class="th-top"><span class="th-lbl">No.</span></div>
              <div class="th-fph"></div>
            </template>
            <template #default="{ $index }">
              <span class="row-no">{{ rowNo($index) }}</span>
            </template>
          </el-table-column>

          <!-- 电商订单号（固定左） -->
          <el-table-column resizable width="180" show-overflow-tooltip fixed="left" class-name="col-fixed-left">
            <template #header>
              <div class="th-top">
                <span class="th-lbl">电商订单号</span>
                <button :class="['sort-btn', sortIcon('ecommerce_order_no') !== 'none' ? 'sort-' + sortIcon('ecommerce_order_no') : '']" @click.stop="sortBy('ecommerce_order_no')"></button>
              </div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="colFilter.ecommerce_order_no" class="th-fi" placeholder="筛选..." />
              </div>
            </template>
            <template #default="{ row }">
              <span class="order-no mono">{{ row.ecommerce_order_no || '—' }}</span>
            </template>
          </el-table-column>

          <!-- 成品编码 -->
          <el-table-column resizable width="140" show-overflow-tooltip>
            <template #header>
              <div class="th-top">
                <span class="th-lbl">成品编码</span>
                <button :class="['sort-btn', sortIcon('finished_code') !== 'none' ? 'sort-' + sortIcon('finished_code') : '']" @click.stop="sortBy('finished_code')"></button>
              </div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="colFilter.finished_code" class="th-fi" placeholder="筛选..." />
              </div>
            </template>
            <template #default="{ row }">
              <span class="code-tag">{{ row.finished_code }}</span>
            </template>
          </el-table-column>

          <!-- 成品名称 -->
          <el-table-column resizable width="180" show-overflow-tooltip>
            <template #header>
              <div class="th-top"><span class="th-lbl">成品名称</span></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="colFilter.finished_name" class="th-fi" placeholder="筛选..." />
              </div>
            </template>
            <template #default="{ row }">{{ row.finished_name || '—' }}</template>
          </el-table-column>

          <!-- 品类 -->
          <el-table-column resizable width="120" show-overflow-tooltip>
            <template #header>
              <div class="th-top"><span class="th-lbl">品类</span></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="colFilter.category_name" class="th-fi" placeholder="筛选..." />
              </div>
            </template>
            <template #default="{ row }">{{ row.category_name || '—' }}</template>
          </el-table-column>

          <!-- 型号 -->
          <el-table-column resizable width="120" show-overflow-tooltip>
            <template #header>
              <div class="th-top">
                <span class="th-lbl">型号</span>
                <button :class="['sort-btn', sortIcon('model_code') !== 'none' ? 'sort-' + sortIcon('model_code') : '']" @click.stop="sortBy('model_code')"></button>
              </div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="colFilter.model_code" class="th-fi" placeholder="筛选..." />
              </div>
            </template>
            <template #default="{ row }">
              <span class="dim mono">{{ row.model_code || '—' }}</span>
            </template>
          </el-table-column>

          <!-- 系列 -->
          <el-table-column resizable width="110" show-overflow-tooltip>
            <template #header>
              <div class="th-top">
                <span class="th-lbl">系列</span>
                <button :class="['sort-btn', sortIcon('series_code') !== 'none' ? 'sort-' + sortIcon('series_code') : '']" @click.stop="sortBy('series_code')"></button>
              </div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="colFilter.series_code" class="th-fi" placeholder="筛选..." />
              </div>
            </template>
            <template #default="{ row }">
              <span class="dim mono">{{ row.series_code || '—' }}</span>
            </template>
          </el-table-column>

          <!-- 发货量 -->
          <el-table-column resizable width="88" show-overflow-tooltip align="right">
            <template #header>
              <div class="th-top">
                <span class="th-lbl">发货量</span>
                <button :class="['sort-btn', sortIcon('quantity') !== 'none' ? 'sort-' + sortIcon('quantity') : '']" @click.stop="sortBy('quantity')"></button>
              </div>
              <div class="th-fph"></div>
            </template>
            <template #default="{ row }">
              <span class="num-cell">{{ fmtNum(row.quantity) }}</span>
            </template>
          </el-table-column>

          <!-- 销退量 -->
          <el-table-column resizable width="88" show-overflow-tooltip align="right">
            <template #header>
              <div class="th-top">
                <span class="th-lbl">销退量</span>
                <button :class="['sort-btn', sortIcon('return_quantity') !== 'none' ? 'sort-' + sortIcon('return_quantity') : '']" @click.stop="sortBy('return_quantity')"></button>
              </div>
              <div class="th-fph"></div>
            </template>
            <template #default="{ row }">
              <span class="num-cell" :class="{ 'num-return': row.return_quantity > 0 }">
                {{ fmtNum(row.return_quantity) }}
              </span>
            </template>
          </el-table-column>

          <!-- 净发货 -->
          <el-table-column resizable width="88" show-overflow-tooltip align="right">
            <template #header>
              <div class="th-top">
                <span class="th-lbl">净发货</span>
                <button :class="['sort-btn', sortIcon('actual_quantity') !== 'none' ? 'sort-' + sortIcon('actual_quantity') : '']" @click.stop="sortBy('actual_quantity')"></button>
              </div>
              <div class="th-fph"></div>
            </template>
            <template #default="{ row }">
              <span class="num-cell num-actual">{{ fmtNum(row.actual_quantity) }}</span>
            </template>
          </el-table-column>

          <!-- 发货日期 -->
          <el-table-column resizable width="108" show-overflow-tooltip align="center">
            <template #header>
              <div class="th-top">
                <span class="th-lbl">发货日期</span>
                <button :class="['sort-btn', sortIcon('shipped_date') !== 'none' ? 'sort-' + sortIcon('shipped_date') : '']" @click.stop="sortBy('shipped_date')"></button>
              </div>
              <div class="th-fph"></div>
            </template>
            <template #default="{ row }">
              <span class="dim">{{ row.shipped_date || '—' }}</span>
            </template>
          </el-table-column>

          <!-- 渠道名称 -->
          <el-table-column resizable width="140" show-overflow-tooltip>
            <template #header>
              <div class="th-top"><span class="th-lbl">渠道名称</span></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="colFilter.channel_name" class="th-fi" placeholder="筛选..." />
              </div>
            </template>
            <template #default="{ row }">{{ row.channel_name || '—' }}</template>
          </el-table-column>

          <!-- 渠道商 code -->
          <el-table-column resizable width="120" show-overflow-tooltip>
            <template #header>
              <div class="th-top"><span class="th-lbl">渠道商代码</span></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="colFilter.channel_code" class="th-fi" placeholder="筛选..." />
              </div>
            </template>
            <template #default="{ row }">
              <span class="dim mono">{{ row.channel_code || '—' }}</span>
            </template>
          </el-table-column>

          <!-- 渠道商名称 -->
          <el-table-column resizable width="150" show-overflow-tooltip>
            <template #header>
              <div class="th-top"><span class="th-lbl">渠道商名称</span></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="colFilter.channel_org_name" class="th-fi" placeholder="筛选..." />
              </div>
            </template>
            <template #default="{ row }">
              <span class="dim">{{ row.channel_org_name || '—' }}</span>
            </template>
          </el-table-column>

          <!-- 省份 -->
          <el-table-column resizable width="96" show-overflow-tooltip>
            <template #header>
              <div class="th-top"><span class="th-lbl">省份</span></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="colFilter.province" class="th-fi" placeholder="筛选..." />
              </div>
            </template>
            <template #default="{ row }">
              <span class="dim">{{ row.province || '—' }}</span>
            </template>
          </el-table-column>

          <!-- 城市 -->
          <el-table-column resizable width="96" show-overflow-tooltip>
            <template #header>
              <div class="th-top"><span class="th-lbl">城市</span></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="colFilter.city" class="th-fi" placeholder="筛选..." />
              </div>
            </template>
            <template #default="{ row }">
              <span class="dim">{{ row.city || '—' }}</span>
            </template>
          </el-table-column>

          <!-- 县区 -->
          <el-table-column resizable width="96" show-overflow-tooltip>
            <template #header>
              <div class="th-top"><span class="th-lbl">县区</span></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="colFilter.district" class="th-fi" placeholder="筛选..." />
              </div>
            </template>
            <template #default="{ row }">
              <span class="dim">{{ row.district || '—' }}</span>
            </template>
          </el-table-column>

        </el-table>
      </div>

      <!-- ── 分页器 ─────────────────────────────── -->
      <div class="pg-bar">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          background
        />
      </div>

    </div>
  </div>
</template>

<style scoped>
/* ── 根容器 ──────────────────────────────────── */
.st-root {
  flex: 1; display: flex; flex-direction: column;
  overflow: hidden; min-height: 0;
  padding: 10px 12px 12px; box-sizing: border-box;
  background: var(--bg);
}

/* ── 卡片 ────────────────────────────────────── */
.card {
  flex: 1; display: flex; flex-direction: column;
  background: var(--bg-card); border-radius: 12px; overflow: hidden;
  border: 1px solid var(--border);
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  min-height: 0;
}

/* ── 顶栏 ────────────────────────────────────── */
.card-topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 14px; flex-shrink: 0;
  border-bottom: 1px solid var(--border);
  background: var(--bg-table-hover);
}
.topbar-left  { display: flex; align-items: center; gap: 8px; }
.topbar-right { display: flex; align-items: center; gap: 10px; }

.total-hint { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.reset-btn {
  padding: 4px 10px; border-radius: 6px; font-size: 12px;
  border: 1px solid var(--border); background: transparent;
  color: var(--text-secondary); cursor: pointer; transition: all 0.15s; font-family: inherit;
}
.reset-btn:hover { background: var(--bg-table-header); color: var(--text-primary); }

/* ── 表格容器 ────────────────────────────────── */
.table-wrap { flex: 1; min-height: 0; overflow: hidden; }

/* ── 分页器 ──────────────────────────────────── */
.pg-bar {
  padding: 6px 12px;
  border-top: 1px solid var(--border);
  display: flex; justify-content: flex-end;
  flex-shrink: 0; background: var(--bg-table-hover);
}

/* ── el-table 覆盖（与 ProductTable 一致）────── */
:deep(.el-table__body-wrapper)::-webkit-scrollbar         { width: 4px; height: 5px; }
:deep(.el-table__body-wrapper)::-webkit-scrollbar-thumb   { background: var(--border); border-radius: 3px; }
:deep(.el-table__body-wrapper)::-webkit-scrollbar-track   { background: transparent; }
:deep(.el-scrollbar__bar.is-horizontal)                   { height: 5px; }
:deep(.el-scrollbar__bar.is-vertical)                     { width: 4px; }
:deep(.el-scrollbar__thumb)                               { background: var(--border); border-radius: 3px; }

:deep(.el-table__header th.el-table__cell) {
  background: var(--bg-table-header) !important;
  padding: 6px 0 4px;
  vertical-align: top;
  position: relative;
}
:deep(.el-table__header th.el-table__cell::after) {
  content: ''; position: absolute;
  right: 0; top: 25%; height: 50%; width: 1px;
  background: var(--border);
}
:deep(.el-table__header th.el-table__cell:last-child::after) { display: none; }
:deep(.el-table__header-wrapper)                { background: var(--bg-table-header); border-bottom: 2px solid var(--border); }
:deep(.el-table__fixed)                         { box-shadow:  4px 0 10px rgba(0,0,0,0.08) !important; }
:deep(.el-table__fixed-right)                   { box-shadow: -4px 0 10px rgba(0,0,0,0.06) !important; }
:deep(.el-table__fixed .el-table__header th.el-table__cell) { background: var(--bg-table-header) !important; }
:deep(.el-table__row td.el-table__cell)         { background: var(--bg-card); }
:deep(.el-table__row:hover td.el-table__cell)   { background: var(--bg-table-hover) !important; }
:deep(.el-table__body-wrapper)                  { background: var(--bg-card); }
:deep(.el-table__row td.el-table__cell .cell)   { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* ── 表头内部元素 ─────────────────────────────── */
.th-top {
  display: flex; align-items: center; justify-content: center; gap: 4px;
  margin-bottom: 5px;
}
.th-lbl {
  font-size: 12px; font-weight: 700; color: var(--text-secondary);
  white-space: nowrap; line-height: 1.3; text-align: center;
}
.th-fph { height: 22px; }   /* 占位，对齐无筛选列 */

.sort-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; flex-shrink: 0;
  background: none; border: 1px solid transparent;
  border-radius: 4px; cursor: pointer; padding: 0; font-size: 10px;
  color: var(--text-muted); transition: all 0.15s;
}
.sort-btn::after           { content: '⇅'; }
.sort-btn:hover            { background: var(--bg-table-header); color: var(--text-secondary); border-color: var(--border); }
.sort-btn.sort-asc::after  { content: '↑'; color: var(--accent); }
.sort-btn.sort-desc::after { content: '↓'; color: var(--accent); }
.sort-btn.sort-asc,
.sort-btn.sort-desc        { border-color: var(--border); background: var(--accent-bg); }

.th-filter-wrap { position: relative; padding: 0 6px; }
.th-fi {
  width: 100%; box-sizing: border-box;
  height: 22px; line-height: 22px;
  font-size: 11px; color: var(--text-primary);
  border: 1px solid var(--border); border-radius: 4px;
  background: var(--bg-card); padding: 0 5px;
  outline: none; font-family: inherit;
  transition: border-color 0.15s;
}
.th-fi:focus       { border-color: var(--accent); }
.th-fi::placeholder { color: var(--text-muted); }

/* ── 单元格内容 ────────────────────────────────── */
.row-no   { font-size: 11px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
.order-no { font-size: 11.5px; color: var(--text-primary); letter-spacing: 0.01em; }
.mono     { font-family: var(--font-mono, 'Microsoft YaHei UI', monospace); }

.code-tag {
  display: inline-block;
  padding: 1px 6px; border-radius: 4px;
  background: var(--accent-bg); color: var(--accent);
  font-size: 11.5px; font-weight: 600; letter-spacing: 0.02em;
  border: 1px solid var(--border);
}
.dim { color: var(--text-secondary); font-size: 12px; }

.num-cell {
  font-variant-numeric: tabular-nums;
  font-size: 12.5px; color: var(--text-primary); font-weight: 600;
}
.num-return { color: #9c6fba; }
.num-actual { color: var(--accent); }

/* el-date-picker 覆盖 */
:deep(.el-date-editor .el-input__wrapper) {
  background: var(--bg-card); border-color: var(--border); border-radius: 7px;
  box-shadow: none !important;
}
:deep(.el-date-editor .el-input__wrapper:hover) { border-color: var(--accent); }
:deep(.el-date-editor .el-input__inner)         { font-size: 12px; }
:deep(.el-date-editor .el-range-separator)      { color: var(--text-muted); font-size: 12px; }
</style>
