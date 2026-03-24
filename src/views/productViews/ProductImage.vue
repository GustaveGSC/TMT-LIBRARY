<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted } from 'vue'
import { Picture, Search } from '@element-plus/icons-vue'
import { useFinishedStore } from '@/stores/product/finished'
import { ensureTableData } from '@/stores/product'
import FinishedExpandRow from './FinishedExpandRow.vue'

// ── Store ─────────────────────────────────────────
const finishedStore = useFinishedStore()

// ── 本地筛选（独立于表格视图的 store filters）────
const searchText   = ref('')
const filterMarket = ref('')   // '' | 'domestic' | 'foreign' | 'both'
const filterSeries = ref([])   // 系列名称（多选）
const sortBy       = ref('code') // 'code' | 'listed_yymm'

// 系列选项（从全量数据提取）
const seriesOptions = computed(() => {
  const seen = new Set()
  for (const r of finishedStore.rawItems) {
    if (r.status === 'unrecorded') continue
    if (r.series_name) seen.add(r.series_name)
  }
  return [...seen].sort()
})

// ── 筛选选项 ────────────────────────────────────────
const MARKET_TABS = [
  { key: '',         label: '全部'   },
  { key: 'domestic', label: '内销'   },
  { key: 'foreign',  label: '外贸'   },
  { key: 'both',     label: '内外销' },
]

// ── 过滤后列表（直接读 rawItems，不影响表格视图 filters）
const filteredItems = computed(() => {
  let list = finishedStore.rawItems

  // 始终过滤掉未录入的成品
  list = list.filter(r => r.status !== 'unrecorded')
  if (filterMarket.value) {
    list = list.filter(r => r.market === filterMarket.value)
  }
  if (filterSeries.value.length) {
    list = list.filter(r => filterSeries.value.includes(r.series_name))
  }
  if (searchText.value.trim()) {
    const q = searchText.value.trim().toLowerCase()
    list = list.filter(r =>
      (r.code    || '').toLowerCase().includes(q) ||
      (r.name    || '').toLowerCase().includes(q) ||
      (r.name_en || '').toLowerCase().includes(q)
    )
  }

  if (sortBy.value === 'listed_yymm') {
    list = [...list].sort((a, b) => {
      const av = a.listed_yymm || ''
      const bv = b.listed_yymm || ''
      if (av > bv) return -1
      if (av < bv) return  1
      return 0
    })
  }

  return list
})

// ── 按品类分组 ────────────────────────────────────
const groupedItems = computed(() => {
  const map = new Map()
  for (const r of filteredItems.value) {
    const cat = r.category_name || '未分类'
    if (!map.has(cat)) map.set(cat, [])
    map.get(cat).push(r)
  }
  return Array.from(map, ([category, items]) => ({ category, items }))
})

// ── 折叠状态（存品类名，折叠则隐藏）────────────────
const collapsedCategories = ref(new Set())

function toggleCategory(cat) {
  const s = new Set(collapsedCategories.value)
  s.has(cat) ? s.delete(cat) : s.add(cat)
  collapsedCategories.value = s
}

// ── 详情弹窗 ──────────────────────────────────────
const detailVisible = ref(false)
const selectedRow   = ref(null)

function openDetail(row) {
  selectedRow.value = row
  detailVisible.value = true
}

async function onSaved() {
  const code = selectedRow.value?.code
  await finishedStore.reload()
  // reload 后 rawItems 更新，通过 code 重新匹配最新对象
  if (code) {
    selectedRow.value = finishedStore.rawItems.find(r => r.code === code) || selectedRow.value
  }
}

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  // 如果 store 尚未加载，触发加载（表格页已加载则直接复用）
  if (!finishedStore.loaded) {
    await ensureTableData()
  }
})
</script>

<template>
  <div class="product-image">

    <!-- ── 工具栏 ──────────────────────────────────── -->
    <div class="img-toolbar">
      <!-- 搜索框 -->
      <div class="search-box">
        <el-icon class="search-icon"><Search /></el-icon>
        <input
          v-model="searchText"
          class="search-input"
          placeholder="搜索品号 / 中文名 / 英文名"
          type="text"
        />
      </div>

      <!-- 系列筛选 -->
      <el-select
        v-model="filterSeries"
        multiple
        filterable
        collapse-tags
        collapse-tags-tooltip
        placeholder="筛选系列"
        clearable
        class="series-select"
      >
        <el-option v-for="s in seriesOptions" :key="s" :label="s" :value="s" />
      </el-select>

      <!-- 市场筛选 -->
      <div class="filter-tabs">
        <button
          v-for="tab in MARKET_TABS"
          :key="tab.key"
          class="filter-tab"
          :class="{ active: filterMarket === tab.key }"
          @click="filterMarket = tab.key"
        >{{ tab.label }}</button>
      </div>

      <!-- 排序 -->
      <div class="sort-group">
        <button
          class="sort-btn"
          :class="{ active: sortBy === 'code' }"
          @click="sortBy = 'code'"
          title="按品号排序"
        >品号</button>
        <button
          class="sort-btn"
          :class="{ active: sortBy === 'listed_yymm' }"
          @click="sortBy = 'listed_yymm'"
          title="按上市年月排序（最新优先）"
        >上市时间</button>
      </div>

      <!-- 数量 -->
      <span class="img-count">{{ filteredItems.length }} 个成品</span>
    </div>

    <!-- ── 加载中 ─────────────────────────────────── -->
    <div v-if="finishedStore.loading" class="img-loading">
      <div class="loading-spinner"></div>
      <span>加载中…</span>
    </div>

    <!-- ── 图片网格（按品类分组）─────────────────────── -->
    <div v-else class="grid-scroll">

      <!-- 空状态 -->
      <div v-if="!groupedItems.length" class="empty-state">
        <el-icon class="empty-icon"><Picture /></el-icon>
        <div class="empty-text">{{ finishedStore.loaded ? '没有匹配的成品' : '暂无数据' }}</div>
        <div v-if="searchText || filterMarket || filterSeries.length" class="empty-hint">尝试清除筛选条件</div>
      </div>

      <!-- 品类分组 -->
      <div v-for="group in groupedItems" :key="group.category" class="cat-section">

        <!-- 分组标题 -->
        <div
          class="cat-header"
          :class="{ expanded: !collapsedCategories.has(group.category) }"
          @click="toggleCategory(group.category)"
        >
          <span class="cat-arrow" :class="{ collapsed: collapsedCategories.has(group.category) }">▾</span>
          <span class="cat-name">{{ group.category }}</span>
          <span class="cat-count">{{ group.items.length }} 个</span>
        </div>

        <!-- 卡片网格 -->
        <div v-show="!collapsedCategories.has(group.category)" class="image-grid">
          <div
            v-for="row in group.items"
            :key="row.code"
            class="image-card"
            @click="openDetail(row)"
          >
            <!-- 图片区 -->
            <div class="img-area">
              <img v-if="row.cover_image" :src="row.cover_image" class="img-actual" :alt="row.code" />
              <div v-else class="img-placeholder">
                <el-icon class="img-ph-icon"><Picture /></el-icon>
                <span class="img-ph-text">暂无图片</span>
              </div>
              <div class="img-hover-mask">
                <span class="img-hover-text">查看详情</span>
              </div>
            </div>
            <!-- 信息区 -->
            <div class="img-info">
              <div class="img-code">{{ row.code }}</div>
              <div class="img-name">{{ row.name || '—' }}</div>
            </div>
          </div>
        </div>

      </div>
    </div><!-- /.grid-scroll -->

    <!-- ── 详情弹窗 ─────────────────────────────────── -->
    <el-dialog
      v-model="detailVisible"
      width="1198"
      :show-header="false"
      :show-close="false"
      :close-on-click-modal="true"
      class="detail-dialog"
      @closed="selectedRow = null"
    >
      <div class="detail-body">
        <FinishedExpandRow
          v-if="selectedRow"
          :row="selectedRow"
          :plain="true"
          :on-close="() => detailVisible = false"
          @saved="onSaved"
        />
      </div>
    </el-dialog>

  </div>
</template>

<style scoped>
/* ── 容器 ─────────────────────────────────────── */
.product-image {
  flex: 1; overflow: hidden;
  display: flex; flex-direction: column;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'PingFang SC', sans-serif;
}

/* ── 工具栏 ───────────────────────────────────── */
.img-toolbar {
  display: flex; align-items: center; gap: 10px; flex-wrap: nowrap; overflow-x: auto;
  padding: 10px 20px;
  background: rgba(255,255,255,0.7);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.search-box {
  display: flex; align-items: center; gap: 7px;
  padding: 5px 12px;
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 10px; min-width: 220px;
  transition: border-color 0.15s;
}
.search-box:focus-within { border-color: var(--accent); }
.search-icon { color: var(--text-muted); font-size: 13px; flex-shrink: 0; }
.search-input {
  flex: 1; border: none; outline: none;
  background: transparent; font-size: 13px;
  color: var(--text-primary); font-family: inherit;
}
.search-input::placeholder { color: var(--text-muted); }

:deep(.series-select) {
  width: 250px; flex-shrink: 0;
}
:deep(.series-select .el-input__wrapper) {
  border-radius: 10px;
  font-size: 12px;
}

.filter-tabs {
  display: flex; gap: 2px;
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 10px; padding: 3px;
}
.filter-tab {
  padding: 4px 10px; border: none; border-radius: 7px;
  background: transparent; color: var(--text-muted);
  font-size: 12px; font-family: inherit;
  cursor: pointer; transition: all 0.15s; white-space: nowrap;
}
.filter-tab:hover { color: var(--text-primary); }
.filter-tab.active {
  background: var(--accent); color: #fff; font-weight: 500;
}

.sort-group {
  display: flex; gap: 2px;
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 10px; padding: 3px;
}
.sort-btn {
  padding: 4px 10px; border: none; border-radius: 7px;
  background: transparent; color: var(--text-muted);
  font-size: 12px; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
}
.sort-btn:hover { color: var(--text-primary); }
.sort-btn.active { background: var(--bg-card); color: var(--accent); font-weight: 500; border: 1px solid var(--border); }

.img-count {
  margin-left: auto; font-size: 12px; color: var(--text-muted);
  flex-shrink: 0;
}

/* ── 加载状态 ─────────────────────────────────── */
.img-loading {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px; color: var(--text-muted); font-size: 13px;
}
.loading-spinner {
  width: 28px; height: 28px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── 图片网格 ─────────────────────────────────── */
/* 滚动容器：flex 子项，负责上下滚动 */
.grid-scroll {
  flex: 1; min-height: 0; overflow-y: auto;
}
.grid-scroll::-webkit-scrollbar { width: 4px; }
.grid-scroll::-webkit-scrollbar-track { background: transparent; }
.grid-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* ── 品类分组 ─────────────────────────────────── */
.cat-section { padding: 0; }

.cat-header {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 20px;
  margin: 8px 20px 0;
  border-radius: 8px;
  cursor: pointer; user-select: none;
  background: var(--bg-card);
  border: 1px solid var(--border);
  transition: all 0.15s;
}
.cat-header.expanded {
  background: var(--accent);
  border-color: var(--accent);
}
.cat-header.expanded .cat-name  { color: #fff; }
.cat-header.expanded .cat-count { color: rgba(255,255,255,0.75); }
.cat-header.expanded .cat-arrow { color: rgba(255,255,255,0.85); }
.cat-header:not(.expanded):hover { border-color: var(--accent); }
.cat-header:not(.expanded):hover .cat-name { color: var(--accent); }

.cat-arrow {
  font-size: 14px; color: var(--text-muted);
  transition: transform 0.2s, color 0.15s;
  display: inline-block;
}
.cat-arrow.collapsed { transform: rotate(-90deg); }

.cat-name {
  font-size: 13px; font-weight: 600; color: var(--text-primary);
  transition: color 0.15s; flex: 1;
}
.cat-count {
  font-size: 11px; color: var(--text-muted);
}

/* grid 布局：自然高度，不参与 flex 分配 */
.image-grid {
  padding: 4px 20px 16px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 14px;
}

/* ── 卡片 ─────────────────────────────────────── */
.image-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 12px; overflow: hidden;
  cursor: pointer; transition: all 0.2s;
}
.image-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 28px var(--shadow);
  border-color: var(--accent);
}

/* 图片区：padding-top: 100% 撑起正方形容器，子元素绝对定位填满 */
.img-area {
  position: relative;
  width: 100%;
  padding-top: 100%;
  border-bottom: 1px solid var(--border);
  overflow: hidden;
}
.img-actual {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  object-fit: cover; display: block;
  transition: transform 0.25s;
}
.image-card:hover .img-actual { transform: scale(1.04); }

.img-placeholder {
  position: absolute; inset: 0;
  background: var(--bg);
  display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 8px;
}
.img-ph-icon { font-size: 32px; color: var(--border); }
.img-ph-text { font-size: 11px; color: var(--text-muted); }

/* 悬停遮罩 */
.img-hover-mask {
  position: absolute; inset: 0;
  background: rgba(0,0,0,0);
  display: flex; align-items: center; justify-content: center;
  transition: background 0.2s;
  pointer-events: none;
}
.img-hover-text {
  font-size: 13px; color: #fff; font-weight: 500;
  opacity: 0; transition: opacity 0.2s;
  text-shadow: 0 1px 4px rgba(0,0,0,0.5);
}
.image-card:hover .img-hover-mask { background: rgba(0,0,0,0.18); }
.image-card:hover .img-hover-text { opacity: 1; }

/* 信息区 */
.img-info { padding: 10px 12px 12px; }
.img-code {
  font-family: 'Microsoft YaHei UI', monospace;
  font-size: 11px; color: var(--accent);
  margin-bottom: 4px; letter-spacing: 0.02em;
}
.img-name {
  font-size: 13px; font-weight: 500; color: var(--text-primary);
  line-height: 1.4; word-break: break-all;
}
.img-name-en {
  font-size: 11px; color: var(--text-secondary);
  margin-bottom: 8px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  min-height: 16px;
}

.img-footer {
  display: flex; align-items: center; gap: 5px; flex-wrap: wrap;
  margin-bottom: 6px;
}
.img-badge {
  font-size: 11px; padding: 2px 7px; border-radius: 20px;
  white-space: nowrap;
}
.status-badge { font-weight: 500; }
.market-badge {
  background: var(--bg); color: var(--text-muted);
  border: 1px solid var(--border);
}

.img-tags {
  display: flex; flex-wrap: wrap; gap: 4px;
}
.img-tag {
  font-size: 11px; padding: 2px 7px; border-radius: 20px;
  border: 1px solid; white-space: nowrap;
}
.img-tag-more {
  font-size: 11px; color: var(--text-muted);
  align-self: center;
}

/* ── 空状态 ───────────────────────────────────── */
.empty-state {
  grid-column: 1 / -1;
  display: flex; flex-direction: column;
  align-items: center; padding: 80px 0; gap: 10px;
}
.empty-icon { font-size: 40px; color: var(--border); }
.empty-text { font-size: 14px; color: var(--text-muted); }
.empty-hint { font-size: 12px; color: var(--text-muted); opacity: 0.7; }

/* ── 详情弹窗 ─────────────────────────────────── */
:deep(.detail-dialog),
:deep(.detail-dialog .el-dialog) {
  --el-dialog-padding-primary: 0;
  padding: 0;
  border: none;
  border-radius: 10px;
  overflow: hidden;
}
:deep(.detail-dialog .el-dialog__body) {
  padding: 0;
  margin: 0;
}
.detail-body {
  max-height: 90vh;
  overflow-y: auto;
  overflow-x: hidden;
}
.detail-body::-webkit-scrollbar { width: 4px; }
.detail-body::-webkit-scrollbar-track { background: transparent; }
.detail-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
</style>
