<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { Picture, Search, Close } from '@element-plus/icons-vue'
import { useFinishedStore } from '@/stores/product/finished'
import { ensureTableData } from '@/stores/product'
import FinishedExpandRow from './FinishedExpandRow.vue'

// ── 移动端检测 ─────────────────────────────────────
const isMobile = ref(window.innerWidth <= 768)
function onResize() { isMobile.value = window.innerWidth <= 768 }
onMounted(() => window.addEventListener('resize', onResize))
onBeforeUnmount(() => window.removeEventListener('resize', onResize))

// ── Store ─────────────────────────────────────────
const finishedStore = useFinishedStore()

// ── 本地筛选（独立于表格视图的 store filters）────
const searchText   = ref('')
const filterMarket    = ref('')   // '' | 'domestic' | 'foreign'
const filterLifecycle = ref('')   // '' | 'listed' | 'delisted' | 'unknown'
const filterSeries = ref([])   // 系列名称（多选）
const sortBy       = ref('code') // 'code' | 'listed_yymm'

// 系列选项（从 activeItems 提取，已排除禁用编码规则对应的成品）
const seriesOptions = computed(() => {
  const seen = new Set()
  for (const r of finishedStore.activeItems) {
    if (r.status === 'unrecorded' || r.status === 'ignored') continue
    if (r.series_name) seen.add(r.series_name)
  }
  return [...seen].sort()
})

// ── 筛选选项 ────────────────────────────────────────
const LIFECYCLE_TABS = [
  { key: '',         label: '全部'     },
  { key: 'listed',   label: '已上市'   },
  { key: 'delisted', label: '已退市'   },
  { key: 'unknown',  label: '状态未知' },
]

const MARKET_TABS = [
  { key: '',         label: '全部' },
  { key: 'domestic', label: '内销' },
  { key: 'foreign',  label: '外贸' },
]

// ── 过滤后列表（基于 activeItems，已排除禁用编码规则对应的成品）
const filteredItems = computed(() => {
  let list = finishedStore.activeItems

  // 始终过滤掉未录入和无需录入的成品
  list = list.filter(r => r.status !== 'unrecorded' && r.status !== 'ignored')
  if (filterLifecycle.value === 'listed') {
    list = list.filter(r => r.listed_yymm && !r.delisted_yymm)
  } else if (filterLifecycle.value === 'delisted') {
    list = list.filter(r => r.listed_yymm && r.delisted_yymm)
  } else if (filterLifecycle.value === 'unknown') {
    list = list.filter(r => !r.listed_yymm)
  }
  if (filterMarket.value) {
    // 'both' 的产品同时属于内销和外贸
    list = list.filter(r => r.market === filterMarket.value || r.market === 'both')
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

// ── 详情弹窗 / 抽屉 ───────────────────────────────
const detailVisible  = ref(false)
const drawerVisible  = ref(false)
const selectedRow    = ref(null)

const MARKET_LABELS = { domestic: '内销', foreign: '外贸', both: '内销 + 外贸' }

// iOS Safari：body { overflow:hidden } 会阻断 position:fixed 内部的触摸滚动
// 抽屉打开时将 body 改为 position:fixed，关闭后还原，让 el-drawer 内部可正常滚动
watch(drawerVisible, (visible) => {
  if (window.electronAPI) return // Electron 不需要
  if (visible) {
    document.body.style.position = 'fixed'
    document.body.style.width = '100%'
  } else {
    document.body.style.position = ''
    document.body.style.width = ''
  }
})

function openDetail(row) {
  selectedRow.value = row
  if (isMobile.value) {
    drawerVisible.value = true
  } else {
    detailVisible.value = true
  }
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

      <!-- 生命周期筛选 -->
      <div class="filter-tabs">
        <button
          v-for="tab in LIFECYCLE_TABS"
          :key="tab.key"
          class="filter-tab"
          :class="{ active: filterLifecycle === tab.key }"
          @click="filterLifecycle = tab.key"
        >{{ tab.label }}</button>
      </div>

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

    <!-- ── 详情弹窗（桌面端）──────────────────────────── -->
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

    <!-- ── 详情抽屉（手机端）──────────────────────────── -->
    <el-drawer
      v-model="drawerVisible"
      direction="btt"
      size="88%"
      :with-header="false"
      :close-on-click-modal="true"
      class="mobile-drawer"
      @closed="selectedRow = null"
    >
      <div v-if="selectedRow" class="drawer-content">
        <!-- 顶部把手 -->
        <div class="drawer-handle-bar">
          <div class="drawer-handle"></div>
        </div>

        <!-- 图片（关闭按钮悬浮在图片右上角）-->
        <div class="drawer-img-wrap">
          <img v-if="selectedRow.cover_image" :src="selectedRow.cover_image" class="drawer-img" :alt="selectedRow.code" />
          <div v-else class="drawer-img-empty">
            <el-icon class="drawer-img-empty-icon"><Picture /></el-icon>
            <span>暂无图片</span>
          </div>
          <!-- 关闭按钮：悬浮在图片右上角，避免与把手重叠 -->
          <button class="drawer-close" @click="drawerVisible = false">
            <el-icon><Close /></el-icon>
          </button>
          <!-- 底部渐变过渡 -->
          <div class="drawer-img-fade"></div>
        </div>

        <!-- 基本信息 -->
        <div class="drawer-body">

          <!-- 名称卡片 -->
          <div class="drawer-info-card">
            <div class="drawer-code">{{ selectedRow.code }}</div>
            <div class="drawer-name">{{ selectedRow.name || '—' }}</div>
            <div v-if="selectedRow.name_en" class="drawer-name-en">{{ selectedRow.name_en }}</div>
            <!-- 标签行 -->
            <div class="drawer-tags">
              <span v-if="selectedRow.listed_yymm && !selectedRow.delisted_yymm" class="d-tag d-tag-listed">已上市</span>
              <span v-else-if="selectedRow.delisted_yymm" class="d-tag d-tag-delisted">已退市</span>
              <span v-else class="d-tag d-tag-unknown">状态未知</span>
              <span v-if="selectedRow.market" class="d-tag d-tag-market">{{ MARKET_LABELS[selectedRow.market] || selectedRow.market }}</span>
              <span v-for="tag in (selectedRow.tags || [])" :key="tag.name" class="d-tag" :style="{ background: tag.color + '22', color: tag.color, borderColor: tag.color + '44' }">{{ tag.name }}</span>
            </div>
          </div>

          <!-- 字段列表卡片 -->
          <div class="drawer-fields-card">
            <div class="drawer-fields-title">产品参数</div>
            <div class="drawer-fields">
              <div v-if="selectedRow.category_name" class="drawer-field">
                <span class="df-label">品类</span>
                <span class="df-value">{{ selectedRow.category_name }}</span>
              </div>
              <div v-if="selectedRow.series_name" class="drawer-field">
                <span class="df-label">系列</span>
                <span class="df-value">{{ selectedRow.series_name }}</span>
              </div>
              <div v-if="selectedRow.model_code" class="drawer-field">
                <span class="df-label">型号</span>
                <span class="df-value mono">{{ selectedRow.model_code }}</span>
              </div>
              <div v-if="selectedRow.listed_yymm" class="drawer-field">
                <span class="df-label">上市年月</span>
                <span class="df-value">{{ selectedRow.listed_yymm }}</span>
              </div>
              <div v-if="selectedRow.delisted_yymm" class="drawer-field">
                <span class="df-label">退市年月</span>
                <span class="df-value">{{ selectedRow.delisted_yymm }}</span>
              </div>
              <div v-if="selectedRow.total_gross_weight" class="drawer-field">
                <span class="df-label">毛重</span>
                <span class="df-value">{{ selectedRow.total_gross_weight }} kg</span>
              </div>
              <div v-if="selectedRow.total_net_weight" class="drawer-field">
                <span class="df-label">净重</span>
                <span class="df-value">{{ selectedRow.total_net_weight }} kg</span>
              </div>
              <div v-if="selectedRow.total_volume" class="drawer-field">
                <span class="df-label">体积</span>
                <span class="df-value">{{ selectedRow.total_volume }} m³</span>
              </div>
            </div>
          </div>

        </div>
      </div>
    </el-drawer>

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

/* ── 卡片网格：移动端 2 列 ────────────────────── */
@media (max-width: 768px) {
  .image-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
    padding: 4px 12px 14px;
  }
  /* 工具栏：搜索框独占第一行，筛选项横向滚动第二行 */
  .img-toolbar {
    flex-wrap: wrap;
    overflow-x: visible;
    padding: 8px 12px 6px;
    gap: 6px;
  }
  .search-box {
    flex: 1 1 100%;   /* 第一行独占全宽 */
    min-width: 0;
    order: -1;
  }
  :deep(.series-select) {
    width: 130px;     /* 缩小系列筛选 */
  }
  .img-count { display: none; }
  .cat-header { margin: 8px 12px 0; }
}

/* ── 详情弹窗（桌面端）──────────────────────── */
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

/* ── 手机端抽屉 ───────────────────────────────── */
:deep(.mobile-drawer .el-drawer) {
  border-radius: 20px 20px 0 0;
  overflow: visible !important; /* 覆盖 Element Plus 自带的 overflow:hidden */
}
:deep(.mobile-drawer .el-drawer__body) {
  padding: 0;
  overflow-y: scroll !important;   /* el-drawer__body 作为唯一滚动容器 */
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
  height: 100%;
}

.drawer-content {
  display: flex;
  flex-direction: column;
  min-height: 100%;                /* 允许内容超过抽屉高度以触发滚动 */
  background: var(--bg);
  border-radius: 20px 20px 0 0;   /* 补回圆角（父级不再 overflow:hidden） */
}

.drawer-handle-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 10px 16px 6px;
  flex-shrink: 0;
}
.drawer-handle {
  width: 36px; height: 4px;
  background: var(--border);
  border-radius: 2px;
}
/* 关闭按钮：悬浮在图片右上角 */
.drawer-close {
  position: absolute; right: 10px; top: 10px;
  width: 30px; height: 30px;
  border: none; border-radius: 50%;
  background: rgba(0,0,0,0.32);
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 14px;
  z-index: 5;
}

.drawer-img-wrap {
  width: calc(100% - 32px);
  margin: 0 16px;
  aspect-ratio: 1 / 1;
  max-height: 42vh;
  flex-shrink: 0;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  position: relative;
}
.drawer-img {
  width: 100%; height: 100%;
  object-fit: cover; display: block;
}
/* 图片底部渐变，与 drawer-body 背景色衔接 */
.drawer-img-fade {
  position: absolute; bottom: 0; left: 0; right: 0;
  height: 48px;
  background: linear-gradient(to bottom, transparent, var(--bg));
  pointer-events: none;
}
.drawer-img-empty {
  width: 100%; height: 100%;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 8px; color: var(--text-muted);
}
.drawer-img-empty-icon { font-size: 40px; color: var(--border); }

.drawer-body {
  flex: none;                      /* 自然高度，父容器负责滚动 */
  padding: 12px 16px 32px;
  display: flex; flex-direction: column; gap: 10px;
}

/* ── 名称信息卡 ───────────────────── */
.drawer-info-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px 16px 12px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}
.drawer-code {
  font-size: 11px; color: var(--accent);
  font-family: 'Microsoft YaHei UI', monospace;
  letter-spacing: 0.06em; margin-bottom: 5px;
  background: rgba(196,136,58,0.08);
  display: inline-block; padding: 2px 8px;
  border-radius: 6px; border: 1px solid rgba(196,136,58,0.2);
}
.drawer-name {
  font-size: 18px; font-weight: 700;
  color: var(--text-primary); line-height: 1.4;
  margin: 6px 0 3px;
}
.drawer-name-en {
  font-size: 12px; color: var(--text-muted);
  margin-bottom: 10px;
}
.drawer-tags {
  display: flex; flex-wrap: wrap; gap: 5px;
  margin-top: 8px;
}
.d-tag {
  font-size: 11px; padding: 3px 9px;
  border-radius: 20px; border: 1px solid;
  font-weight: 500;
}
.d-tag-listed   { background: #edfbf0; color: #2d9b55; border-color: #a8e4bc; }
.d-tag-delisted { background: #f5f0e8; color: #8a7a6a; border-color: #d4c8b8; }
.d-tag-unknown  { background: #f0f4ff; color: #6a7cc0; border-color: #c0caec; }
.d-tag-market   { background: var(--bg-card); color: var(--text-muted); border-color: var(--border); }

/* ── 参数卡片 ───────────────────────── */
.drawer-fields-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}
.drawer-fields-title {
  font-size: 11px; font-weight: 700;
  color: var(--text-muted); letter-spacing: 0.08em;
  padding: 10px 16px 8px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
}
.drawer-fields {
  display: flex; flex-direction: column; gap: 0;
}
.drawer-field {
  display: flex; align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  transition: background 0.12s;
}
.drawer-field:last-child { border-bottom: none; }
.drawer-field:active { background: var(--bg); }
.df-label {
  width: 70px; flex-shrink: 0;
  font-size: 12px; color: var(--text-muted);
  font-weight: 500;
}
.df-value {
  flex: 1; font-size: 13px; color: var(--text-primary);
  font-weight: 500;
}
.df-value.mono { font-family: 'Microsoft YaHei UI', monospace; }

/* ── 手机横屏：左右布局，右侧信息独立滚动 ── */
@media (orientation: landscape) and (max-height: 600px) {
  /* el-drawer__body 保持 scroll 容器（不能再设 overflow:hidden，否则 iOS 滚动失效）
     drawer-content 精确填满高度，body 本身不滚动，只有右侧 drawer-body 滚动 */
  .drawer-content {
    flex-direction: row;
    align-items: stretch;
    height: 100%;
    min-height: unset;  /* 覆盖竖屏的 min-height:100% */
    border-radius: 0;
  }
  /* 横屏隐藏把手条 */
  .drawer-handle-bar { display: none; }
  /* 图片占左侧，圆角卡片，固定不动 */
  .drawer-img-wrap {
    width: 42%;
    height: calc(100% - 24px);
    margin: 12px 0 12px 12px;
    aspect-ratio: unset;
    max-height: none;
    flex-shrink: 0;
    border-radius: 12px;
    border: 1px solid var(--border);
  }
  /* 右侧信息：height:100% 显式约束高度（row 布局下 flex:1 只控制宽度），
     内容超高时 overflow-y:scroll 生效 */
  .drawer-body {
    flex: 1;
    height: 100%;
    box-sizing: border-box;
    overflow-y: scroll;
    -webkit-overflow-scrolling: touch;
    overscroll-behavior: contain;
    padding: 10px 12px 12px;
    gap: 8px;
  }
  .drawer-name { font-size: 15px; }
  .drawer-info-card { padding: 10px 12px; border-radius: 10px; }
  .drawer-fields-card { border-radius: 10px; }
  .drawer-img-fade { display: none; }
}
</style>
