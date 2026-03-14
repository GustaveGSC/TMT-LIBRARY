<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, reactive, computed, watch, nextTick, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useFinishedStore } from '@/stores/product'
import { usePackagedStore  } from '@/stores/product'
import { CaretBottom, CaretTop } from '@element-plus/icons-vue'
import http from '@/api/http'
import FinishedExpandRow from './FinishedExpandRow.vue'

const finishedStore = useFinishedStore()
const packagedStore = usePackagedStore()

// storeToRefs 保证 sortField/sortOrder/status 响应式可读
const { sortField, sortOrder, status } = storeToRefs(finishedStore)

// ── 状态 tabs ─────────────────────────────────────
const STATUS_TABS = [
  { value: '',           label: '全部'     },
  { value: 'unrecorded', label: '未录入'   },
  { value: 'recorded',   label: '已录入'   },
  { value: 'ignored',    label: '无需录入' },
]

// ── packaged 折叠 ─────────────────────────────────
const packagedCollapsed = ref(false)

// ── 展开行 ────────────────────────────────────────
const expandedCode = ref(null)
const expandedKeys = computed(() => expandedCode.value ? [expandedCode.value] : [])

// ── 销售市场标签映射 ──────────────────────────────
const MARKET_LABELS = { domestic: '内销', foreign: '外贸', both: '内外销' }

// ── 搜索（直接改 filter，computed 自动刷新）──────
const FILTER_FIELDS = [
  'code','name','name_en','category','series_code','series_name','model_code',
  'packaged','gross_weight','net_weight','volume','market','listed_yymm','delisted_yymm'
]
const sugg = reactive({})
FILTER_FIELDS.forEach(f => { sugg[f] = { show: false, list: [] } })

function onFilterInput(field, event) {
  const val = event?.target?.value ?? finishedStore.filters[field]
  sugg[field].list = finishedStore.getSuggestions(field, val)
  sugg[field].show = sugg[field].list.length > 0
}
function onFilterFocus(field) {
  const val = finishedStore.filters[field] || ''
  sugg[field].list = val.trim()
    ? finishedStore.getSuggestions(field, val)
    : finishedStore.getTopSuggestions(field)
  sugg[field].show = sugg[field].list.length > 0
}
function applySugg(field, val) {
  finishedStore.filters[field] = val
  sugg[field].show = false
}
function hideSugg(field) { setTimeout(() => { sugg[field].show = false }, 150) }

// ── 重置筛选和排序 ────────────────────────────────
function resetFilters() {
  Object.keys(finishedStore.filters).forEach(k => { finishedStore.filters[k] = '' })
  finishedStore.setSort('', '')
  FILTER_FIELDS.forEach(f => { sugg[f].show = false })
}

// ── 自定义排序 ────────────────────────────────────
function sortBy(field) {
  if (sortField.value === field) {
    if (sortOrder.value === 'asc')        finishedStore.setSort(field, 'desc')
    else if (sortOrder.value === 'desc')  finishedStore.setSort('', '')
    else                                  finishedStore.setSort(field, 'asc')
  } else {
    finishedStore.setSort(field, 'asc')
  }
}
function sortIcon(field) {
  if (sortField.value !== field) return 'none'
  return sortOrder.value
}

// ── 行展开 ────────────────────────────────────────
function toggleExpand(row) {
  if (expandedCode.value === row.code) {
    expandedCode.value = null
  } else {
    expandedCode.value = row.code
    finishedStore.select(row)
  }
}
function onRowClick(row) { finishedStore.select(row) }

// ── 生命周期 badge ────────────────────────────────
function lc(row) {
  if (row.listed_yymm && row.delisted_yymm) return { label: '已退市', cls: 'lc-out' }
  if (row.listed_yymm)                       return { label: '上市中',  cls: 'lc-on'  }
  return null
}

// ── 行样式 ────────────────────────────────────────
function rowClass({ row }) {
  const c = []
  if (row.status === 'recorded')      c.push('row-recorded')
  if (row.status === 'ignored')       c.push('row-ignored')
  if (row === finishedStore.selected) c.push('row-selected')
  return c.join(' ')
}

// ── 动态列宽 ──────────────────────────────────────
const FONT = '12px "Microsoft YaHei UI", "Microsoft YaHei", sans-serif'
let _canvas = null
function measureText(text) {
  if (!_canvas) _canvas = document.createElement('canvas')
  const ctx = _canvas.getContext('2d')
  ctx.font = FONT
  return ctx.measureText(String(text ?? '')).width
}

const COL_DEFS = [
  { key: 'code',               header: '成品编码',        pad: 48, min: 120, max: 240 },
  { key: 'name',               header: '成品名称（中文）', pad: 48, min: 120, max: 300 },
  { key: 'name_en',            header: '成品名称（英文）', pad: 48, min: 120, max: 280 },
  { key: 'category_name',      header: '成品品类',         pad: 40, min: 120, max: 200 },
  { key: 'series_code',        header: '系列编码',         pad: 40, min: 120, max: 180 },
  { key: 'series_name',        header: '系列名称',         pad: 40, min: 120, max: 200 },
  { key: 'model_code',         header: '型号编码',         pad: 40, min: 120, max: 220 },
  { key: 'packaged_list',      header: '产成品清单',       pad: 48, min: 120, max: 300 },
  { key: 'total_gross_weight', header: '毛重 (kg)',        pad: 36, min: 120, max: 160 },
  { key: 'total_net_weight',   header: '净重 (kg)',        pad: 36, min: 120, max: 160 },
  { key: 'total_volume',       header: '体积 (m³)',        pad: 36, min: 120, max: 160 },
  { key: 'market',             header: '销售市场',         pad: 32, min: 100, max: 120 },
  { key: 'listed_yymm',        header: '上市年月',         pad: 36, min: 120, max: 160 },
  { key: 'delisted_yymm',      header: '下市年月',         pad: 36, min: 120, max: 160 },
  { key: '_lifecycle',         header: '生命周期',         pad: 32, min: 120, max: 140 },
]

const colWidths = reactive({})

function calcColWidths() {
  const items = finishedStore.rawItems
  if (!items?.length) return
  for (const def of COL_DEFS) {
    let maxW = measureText(def.header) * 1.1
    for (const row of items) {
      let val = ''
      if (def.key === 'packaged_list') {
        val = (row.packaged_list || []).join(', ')
      } else if (def.key === '_lifecycle') {
        val = row.listed_yymm ? (row.delisted_yymm ? '已退市' : '上市中') : ''
      } else if (def.key === 'market') {
        val = MARKET_LABELS[row.market] || ''
      } else {
        val = row[def.key] ?? ''
      }
      const w = measureText(val)
      if (w > maxW) maxW = w
    }
    colWidths[def.key] = Math.min(Math.max(Math.ceil(maxW) + def.pad, def.min), def.max)
  }
}

watch(
  () => finishedStore.rawItems?.length ?? 0,
  (len) => { if (len > 0) nextTick(() => calcColWidths()) }
)
onMounted(() => {
  if (finishedStore.rawItems.length > 0) nextTick(() => calcColWidths())
})
</script>

<template>
  <div class="pt-root">

    <!-- ══ 成品卡片 ═══════════════════════════════ -->
    <div class="card finished-card">

      <!-- 卡片顶栏 -->
      <div class="card-topbar">
        <div class="status-tabs">
          <button v-for="t in STATUS_TABS" :key="t.value"
            class="tab-btn" :class="{ active: status === t.value }"
            @click="status = t.value"
          >{{ t.label }}</button>
        </div>
        <span class="total-hint">共 {{ finishedStore.total }} 条</span>
      </div>

      <div v-if="finishedStore.error" class="error-bar">{{ finishedStore.error }}</div>

      <!-- 表格 -->
      <div class="table-wrap">
        <el-table
          :data="finishedStore.items"
          :row-class-name="rowClass"
          v-loading="finishedStore.loading"
          size="small"
          height="100%"
          border
          :row-key="r => r.code"
          :expand-row-keys="expandedKeys"
          @row-click="onRowClick"
          :tooltip-effect="'light'"
          :show-overflow-tooltip="true"
          scrollbar-always-on
        >
          <!-- 展开列 -->
          <el-table-column type="expand" width="36" fixed="left">
            <template #header>
              <button class="reset-btn" @click.stop="resetFilters" title="重置筛选和排序">↺</button>
            </template>
            <template #default="{ row }">
              <FinishedExpandRow :row="row" @saved="finishedStore.load()" />
            </template>
          </el-table-column>

          <!-- ── 成品编码（冻结）── -->
          <el-table-column resizable :width="colWidths['code'] || 140" show-overflow-tooltip fixed="left" class-name="col-fixed-left">
            <template #header>
              <div class="th-top"><span class="th-lbl">成品编码</span><button :class="['sort-btn', sortIcon('code') !== 'none' ? 'sort-' + sortIcon('code') : '']" @click.stop="sortBy('code')"></button></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="finishedStore.filters.code" class="th-fi" placeholder="筛选..." @input="onFilterInput('code', $event)" @blur="hideSugg('code')" @focus="onFilterFocus('code')"/>
                <ul v-if="sugg.code.show" class="sg-list"><li v-for="s in sugg.code.list" :key="s" class="sg-item" @mousedown="applySugg('code',s)">{{ s }}</li></ul>
              </div>
            </template>
            <template #default="{ row }">
              <span class="code-tag" :class="{'code-on': expandedCode === row.code}" @click.stop="toggleExpand(row)">{{ row.code }}</span>
            </template>
          </el-table-column>

          <!-- ── 中文名称 ── -->
          <el-table-column resizable :width="colWidths['name'] || 160" show-overflow-tooltip>
            <template #header>
              <div class="th-top"><span class="th-lbl">成品名称（中文）</span><button :class="['sort-btn', sortIcon('name') !== 'none' ? 'sort-' + sortIcon('name') : '']" @click.stop="sortBy('name')"></button></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="finishedStore.filters.name" class="th-fi" placeholder="筛选..." @input="onFilterInput('name', $event)" @blur="hideSugg('name')" @focus="onFilterFocus('name')"/>
                <ul v-if="sugg.name.show" class="sg-list"><li v-for="s in sugg.name.list" :key="s" class="sg-item" @mousedown="applySugg('name',s)">{{ s }}</li></ul>
              </div>
            </template>
            <template #default="{ row }"><span>{{ row.name || '—' }}</span></template>
          </el-table-column>

          <!-- ── 英文名称 ── -->
          <el-table-column resizable :width="colWidths['name_en'] || 140" show-overflow-tooltip>
            <template #header>
              <div class="th-top"><span class="th-lbl">成品名称（英文）</span><button :class="['sort-btn', sortIcon('name_en') !== 'none' ? 'sort-' + sortIcon('name_en') : '']" @click.stop="sortBy('name_en')"></button></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="finishedStore.filters.name_en" class="th-fi" placeholder="筛选..." @input="onFilterInput('name_en', $event)" @blur="hideSugg('name_en')" @focus="onFilterFocus('name_en')"/>
                <ul v-if="sugg.name_en.show" class="sg-list"><li v-for="s in sugg.name_en.list" :key="s" class="sg-item" @mousedown="applySugg('name_en',s)">{{ s }}</li></ul>
              </div>
            </template>
            <template #default="{ row }"><span class="dim">{{ row.name_en || '—' }}</span></template>
          </el-table-column>

          <!-- ── 品类 ── -->
          <el-table-column resizable :width="colWidths['category_name'] || 120" show-overflow-tooltip>
            <template #header>
              <div class="th-top"><span class="th-lbl">成品品类</span><button :class="['sort-btn', sortIcon('category') !== 'none' ? 'sort-' + sortIcon('category') : '']" @click.stop="sortBy('category')"></button></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="finishedStore.filters.category" class="th-fi" placeholder="筛选..." @input="onFilterInput('category', $event)" @blur="hideSugg('category')" @focus="onFilterFocus('category')"/>
                <ul v-if="sugg.category.show" class="sg-list"><li v-for="s in sugg.category.list" :key="s" class="sg-item" @mousedown="applySugg('category',s)">{{ s }}</li></ul>
              </div>
            </template>
            <template #default="{ row }">{{ row.category_name || '—' }}</template>
          </el-table-column>

          <!-- ── 系列编码 ── -->
          <el-table-column resizable :width="colWidths['series_code'] || 120" show-overflow-tooltip>
            <template #header>
              <div class="th-top"><span class="th-lbl">系列编码</span><button :class="['sort-btn', sortIcon('series_code') !== 'none' ? 'sort-' + sortIcon('series_code') : '']" @click.stop="sortBy('series_code')"></button></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="finishedStore.filters.series_code" class="th-fi" placeholder="筛选..." @input="onFilterInput('series_code', $event)" @blur="hideSugg('series_code')" @focus="onFilterFocus('series_code')"/>
                <ul v-if="sugg.series_code.show" class="sg-list"><li v-for="s in sugg.series_code.list" :key="s" class="sg-item" @mousedown="applySugg('series_code',s)">{{ s }}</li></ul>
              </div>
            </template>
            <template #default="{ row }"><span class="dim mono">{{ row.series_code || '—' }}</span></template>
          </el-table-column>

          <!-- ── 系列名称 ── -->
          <el-table-column resizable :width="colWidths['series_name'] || 120" show-overflow-tooltip>
            <template #header>
              <div class="th-top"><span class="th-lbl">系列名称</span><button :class="['sort-btn', sortIcon('series_name') !== 'none' ? 'sort-' + sortIcon('series_name') : '']" @click.stop="sortBy('series_name')"></button></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="finishedStore.filters.series_name" class="th-fi" placeholder="筛选..." @input="onFilterInput('series_name', $event)" @blur="hideSugg('series_name')" @focus="onFilterFocus('series_name')"/>
                <ul v-if="sugg.series_name.show" class="sg-list"><li v-for="s in sugg.series_name.list" :key="s" class="sg-item" @mousedown="applySugg('series_name',s)">{{ s }}</li></ul>
              </div>
            </template>
            <template #default="{ row }">{{ row.series_name || '—' }}</template>
          </el-table-column>

          <!-- ── 型号编码 ── -->
          <el-table-column resizable :width="colWidths['model_code'] || 120" show-overflow-tooltip>
            <template #header>
              <div class="th-top"><span class="th-lbl">型号编码</span><button :class="['sort-btn', sortIcon('model_code') !== 'none' ? 'sort-' + sortIcon('model_code') : '']" @click.stop="sortBy('model_code')"></button></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="finishedStore.filters.model_code" class="th-fi" placeholder="筛选..." @input="onFilterInput('model_code', $event)" @blur="hideSugg('model_code')" @focus="onFilterFocus('model_code')"/>
                <ul v-if="sugg.model_code.show" class="sg-list"><li v-for="s in sugg.model_code.list" :key="s" class="sg-item" @mousedown="applySugg('model_code',s)">{{ s }}</li></ul>
              </div>
            </template>
            <template #default="{ row }"><span class="dim mono">{{ row.model_code || '—' }}</span></template>
          </el-table-column>

          <!-- ── 产成品清单 ── -->
          <el-table-column resizable :width="colWidths['packaged_list'] || 160" show-overflow-tooltip>
            <template #header>
              <div class="th-top"><span class="th-lbl">产成品清单</span></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="finishedStore.filters.packaged" class="th-fi" placeholder="筛选..." @input="onFilterInput('packaged', $event)" @blur="hideSugg('packaged')" @focus="onFilterFocus('packaged')"/>
                <ul v-if="sugg.packaged.show" class="sg-list"><li v-for="s in sugg.packaged.list" :key="s" class="sg-item" @mousedown="applySugg('packaged',s)">{{ s }}</li></ul>
              </div>
            </template>
            <template #default="{ row }">
              <span v-for="c in (row.packaged_list || [])" :key="c" class="pk-tag">{{ c }}</span>
              <span v-if="!row.packaged_list?.length" class="dim">—</span>
            </template>
          </el-table-column>

          <!-- ── 毛重 ── -->
          <el-table-column resizable :width="colWidths['total_gross_weight'] || 120" show-overflow-tooltip align="right">
            <template #header>
              <div class="th-top"><span class="th-lbl">毛重 (kg)</span><button :class="['sort-btn', sortIcon('total_gross_weight') !== 'none' ? 'sort-' + sortIcon('total_gross_weight') : '']" @click.stop="sortBy('total_gross_weight')"></button></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="finishedStore.filters.gross_weight" class="th-fi" placeholder="筛选..." @input="onFilterInput('gross_weight', $event)" @blur="hideSugg('gross_weight')" @focus="onFilterFocus('gross_weight')"/>
                <ul v-if="sugg.gross_weight.show" class="sg-list"><li v-for="s in sugg.gross_weight.list" :key="s" class="sg-item" @mousedown="applySugg('gross_weight',s)">{{ s }}</li></ul>
              </div>
            </template>
            <template #default="{ row }"><span class="dim">{{ row.total_gross_weight ?? '—' }}</span></template>
          </el-table-column>

          <!-- ── 净重 ── -->
          <el-table-column resizable :width="colWidths['total_net_weight'] || 120" show-overflow-tooltip align="right">
            <template #header>
              <div class="th-top"><span class="th-lbl">净重 (kg)</span><button :class="['sort-btn', sortIcon('total_net_weight') !== 'none' ? 'sort-' + sortIcon('total_net_weight') : '']" @click.stop="sortBy('total_net_weight')"></button></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="finishedStore.filters.net_weight" class="th-fi" placeholder="筛选..." @input="onFilterInput('net_weight', $event)" @blur="hideSugg('net_weight')" @focus="onFilterFocus('net_weight')"/>
                <ul v-if="sugg.net_weight.show" class="sg-list"><li v-for="s in sugg.net_weight.list" :key="s" class="sg-item" @mousedown="applySugg('net_weight',s)">{{ s }}</li></ul>
              </div>
            </template>
            <template #default="{ row }"><span class="dim">{{ row.total_net_weight ?? '—' }}</span></template>
          </el-table-column>

          <!-- ── 体积 ── -->
          <el-table-column resizable :width="colWidths['total_volume'] || 120" show-overflow-tooltip align="right">
            <template #header>
              <div class="th-top"><span class="th-lbl">体积 (m³)</span><button :class="['sort-btn', sortIcon('total_volume') !== 'none' ? 'sort-' + sortIcon('total_volume') : '']" @click.stop="sortBy('total_volume')"></button></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="finishedStore.filters.volume" class="th-fi" placeholder="筛选..." @input="onFilterInput('volume', $event)" @blur="hideSugg('volume')" @focus="onFilterFocus('volume')"/>
                <ul v-if="sugg.volume.show" class="sg-list"><li v-for="s in sugg.volume.list" :key="s" class="sg-item" @mousedown="applySugg('volume',s)">{{ s }}</li></ul>
              </div>
            </template>
            <template #default="{ row }"><span class="dim">{{ row.total_volume ?? '—' }}</span></template>
          </el-table-column>

          <!-- ── 销售市场 ── -->
          <el-table-column resizable :width="colWidths['market'] || 100" show-overflow-tooltip align="center">
            <template #header>
              <div class="th-top"><span class="th-lbl">销售市场</span><button :class="['sort-btn', sortIcon('market') !== 'none' ? 'sort-' + sortIcon('market') : '']" @click.stop="sortBy('market')"></button></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="finishedStore.filters.market" class="th-fi" placeholder="筛选..." @input="onFilterInput('market', $event)" @blur="hideSugg('market')" @focus="onFilterFocus('market')"/>
                <ul v-if="sugg.market.show" class="sg-list"><li v-for="s in sugg.market.list" :key="s" class="sg-item" @mousedown="applySugg('market',s)">{{ s }}</li></ul>
              </div>
            </template>
            <template #default="{ row }"><span class="dim">{{ MARKET_LABELS[row.market] || '—' }}</span></template>
          </el-table-column>

          <!-- ── 上市年月 ── -->
          <el-table-column resizable :width="colWidths['listed_yymm'] || 120" show-overflow-tooltip align="center">
            <template #header>
              <div class="th-top"><span class="th-lbl">上市年月</span><button :class="['sort-btn', sortIcon('listed_yymm') !== 'none' ? 'sort-' + sortIcon('listed_yymm') : '']" @click.stop="sortBy('listed_yymm')"></button></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="finishedStore.filters.listed_yymm" class="th-fi" placeholder="筛选..." @input="onFilterInput('listed_yymm', $event)" @blur="hideSugg('listed_yymm')" @focus="onFilterFocus('listed_yymm')"/>
                <ul v-if="sugg.listed_yymm.show" class="sg-list"><li v-for="s in sugg.listed_yymm.list" :key="s" class="sg-item" @mousedown="applySugg('listed_yymm',s)">{{ s }}</li></ul>
              </div>
            </template>
            <template #default="{ row }"><span class="dim">{{ row.listed_yymm || '—' }}</span></template>
          </el-table-column>

          <!-- ── 下市年月 ── -->
          <el-table-column resizable :width="colWidths['delisted_yymm'] || 120" show-overflow-tooltip align="center">
            <template #header>
              <div class="th-top"><span class="th-lbl">下市年月</span><button :class="['sort-btn', sortIcon('delisted_yymm') !== 'none' ? 'sort-' + sortIcon('delisted_yymm') : '']" @click.stop="sortBy('delisted_yymm')"></button></div>
              <div class="th-filter-wrap" @click.stop>
                <input v-model="finishedStore.filters.delisted_yymm" class="th-fi" placeholder="筛选..." @input="onFilterInput('delisted_yymm', $event)" @blur="hideSugg('delisted_yymm')" @focus="onFilterFocus('delisted_yymm')"/>
                <ul v-if="sugg.delisted_yymm.show" class="sg-list"><li v-for="s in sugg.delisted_yymm.list" :key="s" class="sg-item" @mousedown="applySugg('delisted_yymm',s)">{{ s }}</li></ul>
              </div>
            </template>
            <template #default="{ row }"><span class="dim">{{ row.delisted_yymm || '—' }}</span></template>
          </el-table-column>

          <!-- ── 生命周期 ── -->
          <el-table-column resizable :width="colWidths['_lifecycle'] || 120" show-overflow-tooltip align="center">
            <template #header>
              <div class="th-top"><span class="th-lbl">生命周期</span></div>
              <div class="th-fph"></div>
            </template>
            <template #default="{ row }">
              <template v-if="lc(row)">
                <span class="lc-badge" :class="lc(row).cls">{{ lc(row).label }}</span>
              </template>
              <span v-else class="dim">—</span>
            </template>
          </el-table-column>

          <!-- ── 状态 ── -->
          <el-table-column resizable width="52" show-overflow-tooltip align="center" fixed="right">
            <template #header>
              <div class="th-top"><span class="th-lbl">状态</span></div>
              <div class="th-fph"></div>
            </template>
            <template #default="{ row }">
              <span class="dot" :class="`dot-${row.status}`" :title="{unrecorded:'未录入',recorded:'已录入',ignored:'无需录入'}[row.status]"></span>
            </template>
          </el-table-column>

        </el-table>
      </div>
    </div>

    <!-- ══ 包装清单卡片 ════════════════════════════ -->
    <div class="card packaged-card" :class="{ collapsed: packagedCollapsed }">
      <div class="pk-hd" @click="packagedCollapsed = !packagedCollapsed">
        <span class="pk-hd-title">包装清单</span>
        <span v-if="finishedStore.selected" class="pk-hd-code">· {{ finishedStore.selected.code }}</span>
        <span v-if="!finishedStore.selected && !packagedCollapsed" class="pk-hd-hint">点击成品行查看关联包装</span>
        <el-icon class="pk-toggle"><CaretBottom v-if="!packagedCollapsed"/><CaretTop v-else/></el-icon>
      </div>
      <div v-show="!packagedCollapsed" class="pk-body">
        <template v-if="!finishedStore.selected">
          <div class="pk-empty">请先选择一行成品</div>
        </template>
        <el-table v-else :data="finishedStore.selectedPackaged" size="small" height="100%">
          <el-table-column prop="code"         label="产成品编码"    min-width="148">
            <template #default="{ row }"><span class="pk-code-tag">{{ row.code }}</span></template>
          </el-table-column>
          <el-table-column prop="name"         label="产成品名称"    min-width="140"/>
          <el-table-column prop="length"       label="包装长度 (mm)" min-width="110" align="right"><template #default="{ row }"><span class="dim">{{ row.length ?? '—' }}</span></template></el-table-column>
          <el-table-column prop="width"        label="包装宽度 (mm)" min-width="110" align="right"><template #default="{ row }"><span class="dim">{{ row.width ?? '—' }}</span></template></el-table-column>
          <el-table-column prop="height"       label="包装高度 (mm)" min-width="110" align="right"><template #default="{ row }"><span class="dim">{{ row.height ?? '—' }}</span></template></el-table-column>
          <el-table-column prop="volume"       label="包装体积 (m³)" min-width="110" align="right"><template #default="{ row }"><span class="dim">{{ row.volume ?? '—' }}</span></template></el-table-column>
          <el-table-column prop="gross_weight" label="毛重 (kg)"     min-width="86"  align="right"><template #default="{ row }"><span class="dim">{{ row.gross_weight ?? '—' }}</span></template></el-table-column>
          <el-table-column prop="net_weight"   label="净重 (kg)"     min-width="86"  align="right"><template #default="{ row }"><span class="dim">{{ row.net_weight ?? '—' }}</span></template></el-table-column>
        </el-table>
      </div>
    </div><!-- /packaged-card -->

  </div><!-- /pt-root -->
</template>

<style scoped>
/* ── 根容器 ──────────────────────────────────── */
.pt-root {
  flex: 1; display: flex; flex-direction: column;
  overflow: hidden; min-height: 0;
  padding: 10px 12px 12px; gap: 10px; box-sizing: border-box;
  background: #ede8dc;
}

/* ── 通用卡片 ────────────────────────────────── */
.card {
  display: flex; flex-direction: column;
  background: #fff; border-radius: 12px; overflow: hidden;
  border: 1px solid #e0d4c0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

/* ── 成品卡片 ────────────────────────────────── */
.finished-card { flex: 8; min-height: 0; }

.card-topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 14px; flex-shrink: 0;
  border-bottom: 1px solid #f0e8dc;
  background: #faf7f2;
}
.status-tabs { display: flex; gap: 3px; }
.tab-btn {
  padding: 4px 14px; border-radius: 6px; font-size: 12px;
  border: 1px solid transparent; background: transparent;
  color: #6b5e4e; cursor: pointer; transition: all 0.15s; font-family: inherit;
}
.tab-btn:hover  { background: #f0e8dc; color: #3a3028; }
.tab-btn.active { background: #fff7ed; color: #c4883a; border-color: rgba(196,136,58,0.35); font-weight: 600; }
.total-hint { font-size: 12px; color: #8a7a6a; }
.error-bar  { padding: 6px 14px; font-size: 12px; color: #d05a3c; background: #fff5f3; border-bottom: 1px solid #ffd6cc; flex-shrink: 0; }

.table-wrap { flex: 1; min-height: 0; overflow: hidden; }

/* el-table 滚动条 */
:deep(.el-table__body-wrapper)::-webkit-scrollbar         { width: 4px; height: 5px; }
:deep(.el-table__body-wrapper)::-webkit-scrollbar-thumb   { background: #d0c4b0; border-radius: 3px; }
:deep(.el-table__body-wrapper)::-webkit-scrollbar-track   { background: transparent; }
:deep(.el-scrollbar__bar.is-horizontal)                    { height: 5px; }
:deep(.el-scrollbar__bar.is-vertical)                      { width: 4px; }
:deep(.el-scrollbar__thumb)                                { background: #d0c4b0; border-radius: 3px; }

/* el-table 覆盖 */
:deep(.el-table__header th.el-table__cell) {
  background: #f5f0e8 !important;
  padding: 6px 0 4px;
  vertical-align: top;
  position: relative;
}
:deep(.el-table__header th.el-table__cell::after) {
  content: ''; position: absolute;
  right: 0; top: 25%; height: 50%; width: 1px;
  background: #ccc0aa;
}
:deep(.el-table__header th.el-table__cell:last-child::after) { display: none; }
:deep(.el-table__header-wrapper) { background: #f5f0e8; border-bottom: 2px solid #e0d4c0; }
:deep(.el-table__fixed)       { box-shadow:  4px 0 10px rgba(0,0,0,0.08) !important; }
:deep(.el-table__fixed-right) { box-shadow: -4px 0 10px rgba(0,0,0,0.06) !important; }
:deep(.el-table__fixed .el-table__header th.el-table__cell) { background: #f5f0e8 !important; }
:deep(.el-table__header th.el-table__cell:first-child) { position: relative; }
:deep(.el-table__header th.el-table__cell:first-child .cell) {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  padding: 0; overflow: visible;
}
:deep(.el-table__row td.el-table__cell .cell) {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
:deep(.el-table__row td.el-table__cell)       { background: #fff; }
:deep(.el-table__row:hover td.el-table__cell) { background: #faf7f2 !important; }
:deep(.el-table__expanded-cell)               { background: #faf7f2 !important; padding: 0 !important; }
:deep(.el-table__body-wrapper)                { background: #fff; }

/* 行着色 */
:deep(.row-recorded td.el-table__cell)       { background: #f2fbf3 !important; }
:deep(.row-ignored  td.el-table__cell)       { background: #fffcf0 !important; }
:deep(.row-selected td.el-table__cell)       { background: #fff7ed !important; }
:deep(.row-recorded:hover td.el-table__cell) { background: #e8f8ea !important; }
:deep(.row-ignored:hover  td.el-table__cell) { background: #fff6dc !important; }
:deep(.row-selected:hover td.el-table__cell) { background: #feefd8 !important; }

/* ── 表头 ────────────────────────────────────── */
.th-top {
  display: flex; align-items: center; justify-content: center; gap: 4px;
  margin-bottom: 5px;
}
.th-lbl {
  font-size: 12px; font-weight: 700; color: #4a3f32;
  white-space: nowrap; line-height: 1.3; text-align: center;
}
.sort-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; flex-shrink: 0;
  background: none; border: 1px solid transparent;
  border-radius: 4px; padding: 0; cursor: pointer;
  transition: all 0.15s; position: relative;
}
.sort-btn:hover { background: rgba(196,136,58,0.08); border-color: rgba(196,136,58,0.2); }
.sort-btn::before, .sort-btn::after {
  content: ''; position: absolute;
  left: 50%; transform: translateX(-50%);
  width: 0; height: 0; border-style: solid;
}
.sort-btn::before { top: 3px; border-width: 0 3px 4px 3px; border-color: transparent transparent #ccc transparent; }
.sort-btn::after  { bottom: 3px; border-width: 4px 3px 0 3px; border-color: #ccc transparent transparent transparent; }
.sort-btn.sort-asc::before  { border-color: transparent transparent #c4883a transparent; }
.sort-btn.sort-asc::after   { border-color: #ddd transparent transparent transparent; }
.sort-btn.sort-desc::before { border-color: transparent transparent #ddd transparent; }
.sort-btn.sort-desc::after  { border-color: #c4883a transparent transparent transparent; }

.th-filter-wrap { position: relative; }
.th-fi {
  width: 100%; height: 23px; padding: 0 6px; box-sizing: border-box;
  border: 1px solid #ddd5c4; border-radius: 5px;
  background: #fff; color: #3a3028; font-size: 11px;
  outline: none; transition: border-color 0.2s; font-family: inherit;
}
.th-fi:focus { border-color: #c4883a; box-shadow: 0 0 0 2px rgba(196,136,58,0.10); }
.th-fi::placeholder { color: #c0a888; }
.th-fph { height: 23px; }

.sg-list {
  position: absolute; top: calc(100% + 2px); left: 0; right: 0; z-index: 9999;
  margin: 0; padding: 4px 0; list-style: none;
  background: #fff; border: 1px solid #e0d4c0; border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.10); max-height: 200px; overflow-y: auto;
}
.sg-list::-webkit-scrollbar { width: 4px; }
.sg-list::-webkit-scrollbar-thumb { background: #e0d4c0; border-radius: 2px; }
.sg-item {
  padding: 5px 10px; font-size: 12px; color: #3a3028; cursor: pointer;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: background 0.1s;
}
.sg-item:hover { background: #fff7ed; color: #c4883a; }

/* ── 单元格 ──────────────────────────────────── */
.code-tag {
  display: inline-block; font-size: 12px; color: #c4883a;
  border-radius: 4px; padding: 2px 7px; cursor: pointer;
  border: 1px solid transparent; transition: all 0.15s;
  font-family: 'Microsoft YaHei UI','Microsoft YaHei',monospace;
}
.code-tag:hover { background: #fff7ed; border-color: #f5d6a8; }
.code-on        { background: #fff7ed; border-color: #c4883a; font-weight: 700; }
.dim  { color: #999; font-size: 12px; }
.mono { font-family: 'Microsoft YaHei UI','Microsoft YaHei',monospace; }
.pk-tag {
  display: inline-block; font-size: 11px; color: #3a7bc8;
  background: #edf4ff; border: 1px solid #c5d9f5;
  border-radius: 3px; padding: 1px 5px; margin-right: 3px;
  font-family: 'Microsoft YaHei UI','Microsoft YaHei',monospace;
}
.lc-badge {
  display: inline-block; font-size: 11px; font-weight: 600;
  padding: 2px 7px; border-radius: 3px; border: 1px solid;
}
.lc-on  { color: #389e0d; background: #f6ffed; border-color: #b7eb8f; }
.lc-out { color: #cf1322; background: #fff1f0; border-color: #ffa39e; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
.dot-recorded   { background: #52c41a; }
.dot-ignored    { background: #faad14; }
.dot-unrecorded { background: #d9d9d9; }

/* ── 包装清单卡片 ────────────────────────────── */
.packaged-card { flex: 2; min-height: 0; transition: flex 0.25s ease; }
.packaged-card.collapsed { flex: 0 0 40px; min-height: 40px; }

.pk-hd {
  display: flex; align-items: center; gap: 8px;
  padding: 0 16px; height: 40px; flex-shrink: 0;
  cursor: pointer; user-select: none;
  background: #f5f0e8; border-bottom: 1px solid #e0d4c0;
  transition: background 0.15s;
}
.pk-hd:hover { background: #ede5d8; }
.packaged-card.collapsed .pk-hd { border-bottom: none; border-radius: 0 0 12px 12px; }
.pk-hd-title { font-size: 12px; font-weight: 700; color: #4a3f32; }
.pk-hd-code  { color: #c4883a; font-size: 12px; font-weight: 500; }
.pk-hd-hint  { font-size: 11px; color: #b09070; }
.pk-toggle   { margin-left: auto; color: #8a7a6a; font-size: 13px; }

.pk-body { flex: 1; min-height: 0; overflow: hidden; }
.pk-empty {
  height: 100%; display: flex; align-items: center; justify-content: center;
  font-size: 13px; color: #b0a090;
}
:deep(.pk-body .el-table__header th.el-table__cell) { background: #f8f4ec !important; text-align: center; }
:deep(.pk-body .el-table__header .cell) { justify-content: center; }

/* 重置按钮 */
.reset-btn {
  display: flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: 6px;
  border: 1.5px solid #c4883a; background: #fff7ed;
  color: #c4883a; font-size: 15px; cursor: pointer;
  transition: all 0.15s; font-family: inherit; margin: 0 auto; line-height: 1;
}
.reset-btn:hover { background: #c4883a; color: #fff; box-shadow: 0 2px 6px rgba(196,136,58,0.35); }

/* Tooltip */
:deep(.el-popper.is-light) { border: 1px solid #e0d4c0 !important; box-shadow: 0 4px 12px rgba(0,0,0,0.10) !important; }
:deep(.el-popper.is-light .el-popper__arrow::before) { border-color: #e0d4c0 !important; }
:global(.el-tooltip__popper.is-light) { font-size: 12px; color: #2c2420; background: #fff !important; }

.pk-code-tag {
  font-size: 11px; color: #3a7bc8; background: #edf4ff;
  border: 1px solid #c5d9f5; border-radius: 3px; padding: 1px 5px;
  font-family: 'Microsoft YaHei UI','Microsoft YaHei',monospace;
}
</style>