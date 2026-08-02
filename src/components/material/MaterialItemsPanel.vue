<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, watch, onMounted } from 'vue'
import { WarningFilled, Refresh } from '@element-plus/icons-vue'
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
const groups   = ref([])
const loading  = ref(false)
const errorMsg = ref('')

// ── 筛选（走服务端参数；8089 条是服务端分页，客户端筛选只能筛到当页 20 条，没有意义）──
const filters = ref({
  code: '', name: '', short_name: '',
  group_code: '', category: '', disabled: '',
})

// ── 排序 ──────────────────────────────────────────
const sortBy  = ref('code')
const sortDir = ref('asc')

function toggleSort(prop) {
  if (sortBy.value === prop) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value  = prop
    sortDir.value = 'asc'
  }
}
function sortState(prop) {
  return sortBy.value === prop ? sortDir.value : 'none'
}

// ── 分页 ──────────────────────────────────────────
const page     = ref(1)
const pageSize = ref(50)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

const hasFilter = computed(() =>
  Object.values(filters.value).some(v => String(v || '').trim() !== ''))

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
  } catch { /* 分组下拉拿不到不影响主表格 */ }
}

async function loadItems() {
  loading.value  = true
  errorMsg.value = ''
  try {
    const f = filters.value
    const params = {
      page: page.value, page_size: pageSize.value,
      sort_by: sortBy.value, sort_dir: sortDir.value,
    }
    if (f.code.trim())       params.code       = f.code.trim()
    if (f.name.trim())       params.name       = f.name.trim()
    if (f.short_name.trim()) params.short_name = f.short_name.trim()
    if (f.group_code)        params.group_code = f.group_code
    if (f.category === 'unclassified') params.unclassified = 1
    else if (f.category)               params.category     = f.category
    if (f.disabled !== '')   params.is_disabled = f.disabled

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

// 文本筛选防抖：8089 条物料，逐字符触发会打爆请求队列
let debounceTimer = null
function onTextFilter() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { page.value = 1; loadItems() }, 350)
}

// 下拉筛选与排序是明确的用户动作，立即请求
watch([() => filters.value.group_code, () => filters.value.category,
       () => filters.value.disabled, pageSize], () => {
  page.value = 1
  loadItems()
})
watch([sortBy, sortDir], () => { page.value = 1; loadItems() })
watch(page, loadItems)

function resetAll() {
  filters.value = { code: '', name: '', short_name: '', group_code: '', category: '', disabled: '' }
  sortBy.value  = 'code'
  sortDir.value = 'asc'
  page.value    = 1
  loadItems()
}

// ── 生命周期 ──────────────────────────────────────
onMounted(() => { loadGroups(); loadItems() })
</script>

<template>
  <div class="material-items">

    <!-- ── 工具条 ────────────────────────────────── -->
    <div class="toolbar">
      <span class="total-hint">共 <b>{{ total }}</b> 条</span>
      <button v-if="hasFilter || sortBy !== 'code' || sortDir !== 'asc'"
              class="btn-plain" @click="resetAll">重置筛选与排序</button>
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

    <!-- ── 表格 ──────────────────────────────────── -->
    <div class="table-wrap">
      <el-table
        :data="items"
        v-loading="loading"
        size="small"
        height="100%"
        border
        :row-key="r => r.code"
        :tooltip-effect="'light'"
        :show-overflow-tooltip="true"
        scrollbar-always-on
      >
        <!-- ERP 编码：点击打开物料卡片 -->
        <el-table-column resizable width="200" fixed="left" class-name="col-fixed-left">
          <template #header>
            <div class="th-top">
              <span class="th-lbl">ERP 编码</span>
              <button :class="['sort-btn', 'sort-' + sortState('code')]" @click.stop="toggleSort('code')"></button>
            </div>
            <div class="th-filter-wrap" @click.stop>
              <input v-model="filters.code" class="th-fi" placeholder="筛选..." @input="onTextFilter" />
            </div>
          </template>
          <template #default="{ row }">
            <span class="code-link" title="点击查看物料卡片" @click.stop="openCard(row)">{{ row.code }}</span>
          </template>
        </el-table-column>

        <!-- ERP 名称 -->
        <el-table-column resizable min-width="260">
          <template #header>
            <div class="th-top">
              <span class="th-lbl">ERP 名称</span>
              <button :class="['sort-btn', 'sort-' + sortState('name')]" @click.stop="toggleSort('name')"></button>
            </div>
            <div class="th-filter-wrap" @click.stop>
              <input v-model="filters.name" class="th-fi" placeholder="筛选..." @input="onTextFilter" />
            </div>
          </template>
          <template #default="{ row }">{{ row.name }}</template>
        </el-table-column>

        <!-- 短名 -->
        <el-table-column resizable width="170">
          <template #header>
            <div class="th-top">
              <span class="th-lbl">短名</span>
              <button :class="['sort-btn', 'sort-' + sortState('short_name')]" @click.stop="toggleSort('short_name')"></button>
            </div>
            <div class="th-filter-wrap" @click.stop>
              <input v-model="filters.short_name" class="th-fi" placeholder="筛选..." @input="onTextFilter" />
            </div>
          </template>
          <template #default="{ row }">
            <span v-if="row.short_name">{{ row.short_name }}</span>
            <span v-else class="cell-empty">未填</span>
          </template>
        </el-table-column>

        <!-- 分组 -->
        <el-table-column resizable width="180">
          <template #header>
            <div class="th-top">
              <span class="th-lbl">分组</span>
              <button :class="['sort-btn', 'sort-' + sortState('group_code')]" @click.stop="toggleSort('group_code')"></button>
            </div>
            <div class="th-filter-wrap" @click.stop>
              <select v-model="filters.group_code" class="th-fs">
                <option value="">全部</option>
                <option v-for="g in groups" :key="g.group_code" :value="g.group_code">
                  {{ g.group_code }} {{ g.group_name }}
                </option>
              </select>
            </div>
          </template>
          <template #default="{ row }">{{ row.group_code }} · {{ row.group_name || '—' }}</template>
        </el-table-column>

        <!-- 大类 -->
        <el-table-column resizable width="170">
          <template #header>
            <div class="th-top"><span class="th-lbl">大类</span></div>
            <div class="th-filter-wrap" @click.stop>
              <select v-model="filters.category" class="th-fs">
                <option value="">全部</option>
                <option v-for="c in CATEGORIES" :key="c.key" :value="c.key">{{ c.label }}</option>
                <option value="unclassified">未分类</option>
              </select>
            </div>
          </template>
          <template #default="{ row }">
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
        </el-table-column>

        <!-- 停用状态 -->
        <el-table-column resizable width="130">
          <template #header>
            <div class="th-top"><span class="th-lbl">停用状态</span></div>
            <div class="th-filter-wrap" @click.stop>
              <select v-model="filters.disabled" class="th-fs">
                <option value="">全部</option>
                <option value="0">启用</option>
                <option value="1">停用</option>
              </select>
            </div>
          </template>
          <template #default="{ row }">
            <!-- is_disabled 是最终生效值；is_disabled_override 是人工设定值（null=跟随 ERP 默认）。
                 两者结合才能区分「ERP 默认停用」与「人工强制停用/启用」。 -->
            <span v-if="row.is_disabled" class="st-badge st-off">停用</span>
            <span v-else class="st-badge st-on">启用</span>
            <span v-if="row.is_disabled_override !== null && row.is_disabled_override !== undefined"
                  class="st-manual" title="人工覆盖，未跟随 ERP 默认">人工</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ── 分页 ──────────────────────────────────── -->
    <div class="pager">
      <button class="pg-btn" :disabled="page <= 1 || loading" @click="page--">上一页</button>
      <span class="pg-info">{{ page }} / {{ totalPages }}</span>
      <button class="pg-btn" :disabled="page >= totalPages || loading" @click="page++">下一页</button>
    </div>

    <!-- 物料卡片（dialog） -->
    <MaterialCard v-model:visible="cardVisible" :code="cardCode" @saved="onCardSaved" />
  </div>
</template>

<style scoped>
.material-items {
  display: flex; flex-direction: column;
  height: 100%; min-height: 0;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ── 工具条 ───────────────────────────────────── */
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; flex-shrink: 0; }
.total-hint { font-size: 12px; color: var(--text-secondary, #6b5e4e); }
.total-hint b { color: var(--text-primary); font-size: 13px; }
.tb-right { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.tb-select {
  height: 28px; padding: 0 6px;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg-card); color: var(--text-primary);
  font-size: 12px; font-family: inherit; cursor: pointer; outline: none;
}
.btn-plain {
  padding: 4px 12px; border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-card); color: var(--text-secondary, #6b5e4e);
  font-size: 12px; font-family: inherit; cursor: pointer; transition: all 0.15s;
}
.btn-plain:hover { border-color: var(--accent); color: var(--accent); }
.btn-icon {
  width: 28px; height: 28px; border-radius: 6px;
  border: 1px solid var(--border);
  background: transparent; color: var(--text-secondary, #6b5e4e);
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

/* 表头：标签 + 排序按钮 + 筛选输入，与产品库表格一致 */
.th-top { display: flex; align-items: center; justify-content: space-between; gap: 4px; }
.th-lbl { font-size: 12px; font-weight: 600; color: var(--text-primary); }
.sort-btn {
  width: 14px; height: 14px; flex-shrink: 0;
  border: none; background: transparent; cursor: pointer;
  position: relative; opacity: 0.35; transition: opacity 0.15s;
}
.sort-btn:hover { opacity: 0.8; }
.sort-btn::before {
  content: '⇅'; font-size: 11px; color: var(--text-primary);
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
}
.sort-btn.sort-asc  { opacity: 1; }
.sort-btn.sort-desc { opacity: 1; }
.sort-btn.sort-asc::before  { content: '↑'; color: var(--accent); font-weight: 700; }
.sort-btn.sort-desc::before { content: '↓'; color: var(--accent); font-weight: 700; }

.th-filter-wrap { margin-top: 3px; }
.th-fi, .th-fs {
  width: 100%; height: 22px; padding: 0 5px;
  border: 1px solid var(--border); border-radius: 4px;
  background: #fff; color: #2c2420;
  font-size: 11px; font-family: inherit; outline: none;
  transition: border-color 0.15s;
}
.th-fi:focus, .th-fs:focus { border-color: var(--accent); }
.th-fs { cursor: pointer; }

/* 单元格内容 */
.code-link {
  font-family: monospace; font-size: 11px;
  color: var(--accent); cursor: pointer;
  border-bottom: 1px dashed var(--accent);
}
.code-link:hover { color: var(--accent-hover, #e09050); }
.cell-empty { color: #a89a8a; }

.cat-badge {
  display: inline-block; margin-right: 3px;
  font-size: 10px; font-weight: 500;
  border: 1px solid; border-radius: 4px; padding: 1px 6px;
}
.cat-badge.badge-none { color: #8a7a6a; background: #f5f0e8; border-color: var(--border); }

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
</style>

<!-- 非 scoped：el-table 的内部结构由组件渲染，scoped 选择器匹配不到。
     用祖先类名 .material-items 限定作用域，避免影响其他页面的表格。
     表格正文文字统一用主文字色（深黑褐），不用 Element 默认的浅灰。 -->
<style>
.material-items .el-table {
  --el-table-border-color: var(--border);
  --el-table-header-bg-color: #f5f0e8;
  --el-table-row-hover-bg-color: #faf7f2;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}
.material-items .el-table th.el-table__cell {
  background: #f5f0e8 !important;
  color: #2c2420;
  padding: 5px 0;
  vertical-align: top;
}
.material-items .el-table td.el-table__cell {
  color: #2c2420;
  padding: 6px 0;
}
.material-items .el-table .cell {
  color: #2c2420;
  font-size: 12px;
  line-height: 1.5;
}
.material-items .el-table__body tr:hover > td.el-table__cell { background: #faf7f2; }
.material-items .el-table__inner-wrapper::before { display: none; }
.material-items .el-table ::-webkit-scrollbar { width: 6px; height: 6px; }
.material-items .el-table ::-webkit-scrollbar-track { background: transparent; }
.material-items .el-table ::-webkit-scrollbar-thumb { background: #d8cbb6; border-radius: 3px; }
</style>
