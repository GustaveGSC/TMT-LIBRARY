<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, watch, onMounted } from 'vue'
import { WarningFilled, Refresh } from '@element-plus/icons-vue'
import http from '@/api/http'
import DataTable from '@/components/common/DataTable.vue'
import MaterialCard from './MaterialCard.vue'

// ── 大类定义 ──────────────────────────────────────
// 与后端大类判定服务返回的 categories 数组取值一致。
// 「未分类」不是一个大类，而是「一个大类都没命中」，走独立的 unclassified 参数。
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
const groups   = ref([])
const loading  = ref(false)
const errorMsg = ref('')

// ── 服务端筛选与排序状态 ───────────────────────────
// 物料 8089 行且接口是服务端分页，对当页做本地筛选排序没有意义
// （要找的行大概率不在当页），所以 DataTable 用 serverMode。
const colFilters = ref({})
const sortBy     = ref('code')
const sortDir    = ref('asc')

// ── 分页 ──────────────────────────────────────────
const page     = ref(1)
const pageSize = ref(50)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

const hasFilter = computed(() =>
  Object.values(colFilters.value).some(v => v != null && String(v).trim() !== ''))
const isSorted = computed(() => sortBy.value !== 'code' || sortDir.value !== 'asc')

// ── 列配置 ────────────────────────────────────────
const columns = computed(() => [
  { prop: 'code',       label: 'ERP 编码', width: 200, fixed: 'left',
    sortable: true, filterable: true, filterType: 'text' },
  { prop: 'name',       label: 'ERP 名称', minWidth: 260,
    sortable: true, filterable: true, filterType: 'text' },
  { prop: 'short_name', label: '短名',     width: 170,
    sortable: true, filterable: true, filterType: 'text' },
  { prop: 'group_code', label: '分组',     width: 190,
    sortable: true, filterable: true,
    filterOptions: groups.value.map(g => ({
      label: `${g.group_code} ${g.group_name}`, value: g.group_code,
    })) },
  { prop: 'categories', label: '大类',     width: 170, filterable: true,
    filterOptions: [
      ...CATEGORIES.map(c => ({ label: c.label, value: c.key })),
      { label: '未分类', value: 'unclassified' },
    ] },
  { prop: 'is_disabled', label: '停用状态', width: 130, filterable: true,
    filterOptions: [{ label: '启用', value: '0' }, { label: '停用', value: '1' }] },
])

// ── 物料卡片 ──────────────────────────────────────
const cardCode    = ref('')
const cardVisible = ref(false)

function openCard(row) {
  cardCode.value    = row.code
  cardVisible.value = true
}

// 卡片保存成功后把变更回写到列表行，避免整表重新拉一次
function onCardSaved(updated) {
  const row = items.value.find(i => i.code === updated.code)
  if (row) Object.assign(row, updated)
}

// ── 加载 ──────────────────────────────────────────
async function loadGroups() {
  try {
    const res = await http.get('/api/material/group-categories')
    if (res.success) groups.value = res.data || []
  } catch { /* 分组候选拿不到不影响主表格 */ }
}

async function loadItems() {
  loading.value  = true
  errorMsg.value = ''
  try {
    const f = colFilters.value
    const params = {
      page: page.value, page_size: pageSize.value,
      sort_by: sortBy.value, sort_dir: sortDir.value,
    }
    const txt = (v) => (v == null ? '' : String(v).trim())
    if (txt(f.code))       params.code       = txt(f.code)
    if (txt(f.name))       params.name       = txt(f.name)
    if (txt(f.short_name)) params.short_name = txt(f.short_name)
    if (f.group_code)      params.group_code = f.group_code
    if (f.categories === 'unclassified') params.unclassified = 1
    else if (f.categories)               params.category     = f.categories
    if (txt(f.is_disabled)) params.is_disabled = f.is_disabled

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

// ── DataTable 事件（serverMode）─────────────────────
function onFilterChange(next) {
  colFilters.value = next
  page.value = 1
  loadItems()
}

function onSortChange({ prop, order }) {
  // order 为 null 表示第三次点击取消排序，回落到默认的编码升序
  sortBy.value  = order ? prop : 'code'
  sortDir.value = order || 'asc'
  page.value = 1
  loadItems()
}

watch([pageSize], () => { page.value = 1; loadItems() })
watch(page, loadItems)

// ── 生命周期 ──────────────────────────────────────
onMounted(() => { loadGroups(); loadItems() })
</script>

<template>
  <div class="material-items">

    <!-- ── 工具条 ────────────────────────────────── -->
    <div class="toolbar">
      <span class="total-hint">共 <b>{{ total }}</b> 条</span>
      <span class="tip">点击 ERP 编码查看物料卡片</span>
      <div class="tb-right">
        <select v-model.number="pageSize" class="tb-select">
          <option :value="20">20 条/页</option>
          <option :value="50">50 条/页</option>
          <option :value="100">100 条/页</option>
        </select>
        <button class="btn-icon" title="刷新" :disabled="loading" @click="loadItems">
          <el-icon :class="{ spinning: loading }"><Refresh /></el-icon>
        </button>
      </div>
    </div>

    <div v-if="errorMsg" class="error-bar">
      <el-icon><WarningFilled /></el-icon>
      <span>{{ errorMsg }}</span>
    </div>

    <!-- ── 表格（复用全站统一的 DataTable，服务端筛选排序）── -->
    <div class="table-wrap">
      <DataTable
        :data="items"
        :columns="columns"
        :loading="loading"
        server-mode
        size="small"
        height="100%"
        row-key="code"
        empty-text="没有符合条件的物料"
        @filter-change="onFilterChange"
        @sort-change="onSortChange"
      >
        <!-- ERP 编码：点击打开物料卡片 -->
        <template #cell-code="{ row }">
          <span class="code-link" title="点击查看物料卡片" @click.stop="openCard(row)">{{ row.code }}</span>
        </template>

        <template #cell-short_name="{ row }">
          <span v-if="row.short_name">{{ row.short_name }}</span>
          <span v-else class="cell-empty">未填</span>
        </template>

        <template #cell-group_code="{ row }">
          {{ row.group_code }} · {{ row.group_name || '—' }}
        </template>

        <template #cell-categories="{ row }">
          <span
            v-for="c in (row.categories || [])"
            :key="c"
            class="cat-badge"
            :style="{
              color: catMap[c]?.color,
              background: (catMap[c]?.color || '#8a7a6a') + '1a',
              borderColor: (catMap[c]?.color || '#8a7a6a') + '55',
            }"
          >{{ catMap[c]?.label || c }}</span>
          <span v-if="!(row.categories || []).length" class="cat-badge badge-none">未分类</span>
        </template>

        <!-- 停用状态：is_disabled 是最终生效值；is_disabled_override 是人工设定值
             （null = 跟随 ERP 默认判定）。两者结合才能区分「默认停用」与「人工覆盖」。 -->
        <template #cell-is_disabled="{ row }">
          <span v-if="row.is_disabled" class="st-badge st-off">停用</span>
          <span v-else class="st-badge st-on">启用</span>
          <span v-if="row.is_disabled_override !== null && row.is_disabled_override !== undefined"
                class="st-manual" title="人工覆盖，未跟随 ERP 默认">人工</span>
        </template>
      </DataTable>
    </div>

    <!-- ── 分页 ──────────────────────────────────── -->
    <div class="pager">
      <button class="pg-btn" :disabled="page <= 1 || loading" @click="page--">上一页</button>
      <span class="pg-info">{{ page }} / {{ totalPages }}</span>
      <button class="pg-btn" :disabled="page >= totalPages || loading" @click="page++">下一页</button>
      <span v-if="hasFilter || isSorted" class="pg-note">（筛选/排序由服务端执行，跨全部 {{ total }} 条生效）</span>
    </div>

    <!-- 物料卡片（dialog） -->
    <MaterialCard v-model:visible="cardVisible" :code="cardCode" @saved="onCardSaved" />
  </div>
</template>

<style scoped>
.material-items {
  display: flex; flex-direction: column;
  height: 100%; min-height: 0;
}

/* ── 工具条 ───────────────────────────────────── */
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; flex-shrink: 0; }
.total-hint { font-size: 12px; color: var(--text-secondary); }
.total-hint b { color: var(--text-primary); font-size: 13px; }
.tip { font-size: 11px; color: var(--text-secondary); }
.tb-right { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.tb-select {
  height: 28px; padding: 0 6px;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg-card); color: var(--text-primary);
  font-size: 12px; font-family: inherit; cursor: pointer; outline: none;
}
.btn-icon {
  width: 28px; height: 28px; border-radius: 6px;
  border: 1px solid var(--border);
  background: transparent; color: var(--text-secondary);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.15s;
}
.btn-icon:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.btn-icon:disabled { opacity: 0.5; cursor: not-allowed; }
.spinning { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.error-bar {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 10px; padding: 8px 12px;
  background: rgba(208,90,60,0.06); border: 1px solid rgba(208,90,60,0.2);
  border-radius: 7px; color: #d05a3c; font-size: 12px; flex-shrink: 0;
}

/* ── 表格 ─────────────────────────────────────── */
.table-wrap { flex: 1; min-height: 0; }

.code-link {
  font-family: monospace; font-size: 11px; font-weight: 600;
  color: var(--accent); cursor: pointer;
  border-bottom: 1px dashed var(--accent);
}
.code-link:hover { color: var(--accent-hover); }
.cell-empty { color: var(--text-muted); }

.cat-badge {
  display: inline-block; margin-right: 3px;
  font-size: 10px; font-weight: 500;
  border: 1px solid; border-radius: 4px; padding: 1px 6px;
}
.cat-badge.badge-none { color: var(--text-secondary); background: var(--bg-table-header); border-color: var(--border); }

.st-badge {
  font-size: 10px; font-weight: 600;
  border: 1px solid; border-radius: 4px; padding: 1px 7px;
}
.st-badge.st-on  { color: #4a8f6a; background: rgba(74,143,106,0.12); border-color: rgba(74,143,106,0.4); }
.st-badge.st-off { color: #d05a3c; background: rgba(208,90,60,0.1);  border-color: rgba(208,90,60,0.35); }
.st-manual {
  margin-left: 4px; font-size: 10px;
  color: #9c6fba; background: rgba(156,111,186,0.12);
  border: 1px solid rgba(156,111,186,0.3); border-radius: 4px; padding: 1px 5px;
  cursor: help;
}

/* ── 分页 ─────────────────────────────────────── */
.pager {
  display: flex; align-items: center; justify-content: center; gap: 12px;
  padding: 10px 0 2px; flex-shrink: 0;
}
.pg-btn {
  padding: 4px 14px; border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-card); color: var(--text-primary);
  font-size: 12px; font-family: inherit; cursor: pointer; transition: all 0.15s;
}
.pg-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.pg-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.pg-info { font-size: 12px; color: var(--text-primary); }
.pg-note { font-size: 11px; color: var(--text-secondary); }
</style>
