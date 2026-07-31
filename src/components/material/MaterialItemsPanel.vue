<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, watch, onMounted } from 'vue'
import { WarningFilled, Refresh, Search } from '@element-plus/icons-vue'
import http from '@/api/http'
import MaterialCard from './MaterialCard.vue'

// ── 大类定义 ──────────────────────────────────────
// 与后端大类判定服务返回的 categories 数组取值一致。
// 「未分类」不是一个大类，而是「一个大类都没命中」，所以单独走 unclassified 参数。
const CATEGORIES = [
  { key: 'finished', label: '成品',     color: '#c4883a' },
  { key: 'packaged', label: '产成品',   color: '#4a8fc0' },
  { key: 'semi',     label: '半成品',   color: '#9c6fba' },
  { key: 'material', label: '原材料',   color: '#6ab47a' },
  { key: 'useless',  label: '无用物料', color: '#8a7a6a' },
]
const catMap = Object.fromEntries(CATEGORIES.map(c => [c.key, c]))

// ── 数据 ──────────────────────────────────────────
const items    = ref([])
const total    = ref(0)
const loading  = ref(false)
const errorMsg = ref('')

// ── 筛选与分页 ────────────────────────────────────
const activeCat   = ref('')        // '' 全部 / 大类 key / 'unclassified'
const keyword     = ref('')
const showDisabled = ref(false)    // 默认不显示已停用
const page        = ref(1)
const pageSize    = ref(20)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

// ── 物料卡片 ──────────────────────────────────────
const cardCode    = ref('')
const cardVisible = ref(false)

function openCard(row) {
  cardCode.value    = row.code
  cardVisible.value = true
}

// 卡片里保存成功后，把变更回写到列表行，避免整表重新拉一次
function onCardSaved(updated) {
  const row = items.value.find(i => i.code === updated.code)
  if (row) Object.assign(row, updated)
}

// ── 加载列表 ──────────────────────────────────────
async function loadItems() {
  loading.value  = true
  errorMsg.value = ''
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (keyword.value.trim()) params.keyword = keyword.value.trim()
    if (activeCat.value === 'unclassified') params.unclassified = 1
    else if (activeCat.value)              params.category = activeCat.value
    if (!showDisabled.value)               params.is_disabled = 0

    const res = await http.get('/api/material/items', { params })
    if (res.success) {
      items.value = res.data?.items || []
      total.value = res.data?.total ?? 0
    } else {
      errorMsg.value = res.message || '加载失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
  } finally {
    loading.value = false
  }
}

// 筛选变化回到第 1 页再查。关键词单独走搜索按钮/回车，
// 不做 watch 自动请求——8000 多条物料，逐字符触发会打爆请求队列。
watch([activeCat, showDisabled, pageSize], () => {
  page.value = 1
  loadItems()
})
watch(page, loadItems)

function doSearch() {
  page.value = 1
  loadItems()
}

// ── 生命周期 ──────────────────────────────────────
onMounted(loadItems)
</script>

<template>
  <div class="material-items">

    <!-- ── 左侧大类筛选 ──────────────────────────── -->
    <aside class="cat-side">
      <div class="cat-side-title">物料大类</div>
      <button class="cat-item" :class="{ active: activeCat === '' }"
              @click="activeCat = ''">全部</button>
      <button
        v-for="c in CATEGORIES"
        :key="c.key"
        class="cat-item"
        :class="{ active: activeCat === c.key }"
        :style="activeCat === c.key ? { color: c.color, borderColor: c.color, background: c.color + '14' } : {}"
        @click="activeCat = c.key"
      >
        <span class="cat-dot" :style="{ background: c.color }"></span>
        {{ c.label }}
      </button>
      <button class="cat-item cat-unclassified" :class="{ active: activeCat === 'unclassified' }"
              @click="activeCat = 'unclassified'">未分类</button>

      <label class="cat-toggle">
        <input v-model="showDisabled" type="checkbox" />
        <span>显示已停用</span>
      </label>
    </aside>

    <!-- ── 右侧主区 ──────────────────────────────── -->
    <section class="items-main">

      <div class="toolbar">
        <div class="search-wrap">
          <input
            v-model="keyword"
            class="search-input"
            placeholder="搜索 ERP 编码或名称，回车搜索"
            @keyup.enter="doSearch"
          />
          <button class="btn-search" title="搜索" @click="doSearch">
            <el-icon><Search /></el-icon>
          </button>
        </div>
        <span class="total-hint">共 {{ total }} 条</span>
        <button class="btn-refresh" title="刷新" :disabled="loading" @click="loadItems">
          <el-icon :class="{ spinning: loading }"><Refresh /></el-icon>
        </button>
      </div>

      <div v-if="errorMsg" class="error-bar">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ errorMsg }}</span>
      </div>

      <div v-if="loading" class="state-tip">加载中...</div>

      <div v-else-if="items.length" class="mi-table">
        <div class="mi-head">
          <div class="mi-col col-code">ERP 编码</div>
          <div class="mi-col col-name">ERP 名称</div>
          <div class="mi-col col-short">短名</div>
          <div class="mi-col col-group">分组</div>
          <div class="mi-col col-cats">大类</div>
        </div>
        <div class="mi-body">
          <div
            v-for="row in items"
            :key="row.code"
            class="mi-row"
            :class="{ 'row-disabled': row.is_disabled }"
            @click="openCard(row)"
          >
            <div class="mi-col col-code"><span class="code-tag">{{ row.code }}</span></div>
            <div class="mi-col col-name" :title="row.name">{{ row.name }}</div>
            <div class="mi-col col-short" :title="row.short_name || ''">
              <span v-if="row.short_name">{{ row.short_name }}</span>
              <span v-else class="muted">未填</span>
            </div>
            <div class="mi-col col-group" :title="row.group_name">{{ row.group_name || '—' }}</div>
            <div class="mi-col col-cats">
              <span
                v-for="c in (row.categories || [])"
                :key="c"
                class="cat-badge"
                :style="{
                  color: catMap[c]?.color,
                  background: (catMap[c]?.color || '#999') + '18',
                  borderColor: (catMap[c]?.color || '#999') + '40',
                }"
              >{{ catMap[c]?.label || c }}</span>
              <span v-if="!(row.categories || []).length" class="cat-badge badge-none">未分类</span>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="state-tip">没有符合条件的物料</div>

      <!-- 分页 -->
      <div v-if="!loading && total > pageSize" class="pager">
        <button class="pg-btn" :disabled="page <= 1" @click="page--">上一页</button>
        <span class="pg-info">{{ page }} / {{ totalPages }}</span>
        <button class="pg-btn" :disabled="page >= totalPages" @click="page++">下一页</button>
      </div>

    </section>

    <!-- 物料卡片 -->
    <MaterialCard v-model:visible="cardVisible" :code="cardCode" @saved="onCardSaved" />
  </div>
</template>

<style scoped>
.material-items {
  display: flex; gap: 14px;
  height: 100%; min-height: 0;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ── 左侧大类 ─────────────────────────────────── */
.cat-side {
  width: 150px; flex-shrink: 0;
  display: flex; flex-direction: column; gap: 4px;
  padding: 12px 10px;
  background: var(--bg-card);
  border: 1px solid var(--border); border-radius: 12px;
  align-self: flex-start;
}
.cat-side-title {
  font-size: 11px; font-weight: 700; color: var(--accent);
  letter-spacing: 0.08em; margin-bottom: 6px; padding-left: 4px;
}
.cat-item {
  display: flex; align-items: center; gap: 7px;
  padding: 6px 10px; border-radius: 7px;
  border: 1px solid transparent;
  background: transparent; color: var(--text-muted);
  font-size: 12px; font-family: inherit; text-align: left;
  cursor: pointer; transition: all 0.15s;
}
.cat-item:hover { background: var(--accent-bg); color: var(--accent); }
.cat-item.active { font-weight: 600; }
.cat-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.cat-unclassified { margin-top: 2px; border-top: 1px solid var(--border); border-radius: 0 0 7px 7px; padding-top: 9px; }

.cat-toggle {
  display: flex; align-items: center; gap: 6px;
  margin-top: 10px; padding: 6px 4px 0;
  border-top: 1px solid var(--border);
  font-size: 11px; color: var(--text-muted); cursor: pointer;
}

/* ── 右侧主区 ─────────────────────────────────── */
.items-main { flex: 1; min-width: 0; display: flex; flex-direction: column; min-height: 0; }

.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.search-wrap { display: flex; gap: 6px; }
.search-input {
  width: 260px; height: 30px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg); color: var(--text-primary);
  font-size: 12px; font-family: inherit; outline: none;
  transition: border-color 0.2s;
}
.search-input:focus { border-color: var(--accent); }
.btn-search, .btn-refresh {
  width: 30px; height: 30px; border-radius: 7px;
  border: 1px solid var(--border);
  background: transparent; color: var(--text-muted);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.15s;
}
.btn-search:hover, .btn-refresh:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.btn-refresh { margin-left: auto; }
.btn-refresh:disabled { opacity: 0.5; cursor: not-allowed; }
.total-hint { font-size: 12px; color: var(--text-muted); }
.spinning { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.error-bar {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 12px; padding: 8px 12px;
  background: rgba(208,90,60,0.06); border: 1px solid rgba(208,90,60,0.2);
  border-radius: 7px; color: #d05a3c; font-size: 12px;
}
.state-tip { font-size: 13px; color: var(--text-muted); padding: 32px 0; text-align: center; }

/* ── 表格 ─────────────────────────────────────── */
.mi-table {
  border: 1px solid var(--border); border-radius: 10px;
  overflow: hidden; display: flex; flex-direction: column; min-height: 0;
}
.mi-body { overflow-y: auto; min-height: 0; }
.mi-body::-webkit-scrollbar { width: 4px; }
.mi-body::-webkit-scrollbar-track { background: transparent; }
.mi-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.mi-head {
  display: flex; align-items: center; height: 34px;
  background: var(--table-head, #f5f0e8);
  border-bottom: 1px solid var(--border); padding: 0 14px;
  position: sticky; top: 0; z-index: 1;
}
.mi-col { font-size: 12px; color: var(--text-muted); padding-right: 10px; }
.col-code  { width: 170px; flex-shrink: 0; }
.col-name  { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-short { width: 150px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-group { width: 130px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-cats  { width: 180px; flex-shrink: 0; display: flex; gap: 4px; flex-wrap: wrap; padding-right: 0; }

.mi-row {
  display: flex; align-items: center; min-height: 42px;
  padding: 7px 14px; border-bottom: 1px solid var(--border);
  font-size: 12px; color: var(--text-primary);
  cursor: pointer; transition: background 0.15s;
}
.mi-row:last-child { border-bottom: none; }
.mi-row:hover { background: rgba(196,136,58,0.04); }
.mi-row.row-disabled { opacity: 0.45; }

.code-tag {
  font-family: monospace; font-size: 11px;
  color: var(--accent); background: var(--accent-bg);
  border: 1px solid var(--border); border-radius: 4px; padding: 2px 6px;
}
.cat-badge {
  font-size: 10px; font-weight: 500;
  border: 1px solid; border-radius: 4px; padding: 1px 6px;
}
.cat-badge.badge-none { color: var(--text-muted); background: var(--bg); border-color: var(--border); }
.muted { color: var(--text-muted); }

/* ── 分页 ─────────────────────────────────────── */
.pager { display: flex; align-items: center; justify-content: center; gap: 12px; padding: 12px 0 4px; }
.pg-btn {
  padding: 4px 14px; border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-card); color: var(--text-muted);
  font-size: 12px; font-family: inherit; cursor: pointer; transition: all 0.15s;
}
.pg-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.pg-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.pg-info { font-size: 12px; color: var(--text-muted); }
</style>
