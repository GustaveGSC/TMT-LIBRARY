<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted } from 'vue'
import { WarningFilled, Refresh } from '@element-plus/icons-vue'
import http from '@/api/http'

// ── 大类定义 ──────────────────────────────────────
// 五个大类是固定的，与后端 erp_group_category 的五个布尔列一一对应。
// 成品与产成品**可以同时勾选**：成品只含一个包装时技术人员省略了产成品层，
// 生产数据里确有 276 条编码两者兼具，所以这里不是单选。
const CATEGORIES = [
  { key: 'is_finished', label: '成品',     color: '#c4883a' },
  { key: 'is_packaged', label: '产成品',   color: '#4a8fc0' },
  { key: 'is_semi',     label: '半成品',   color: '#9c6fba' },
  { key: 'is_material', label: '原材料',   color: '#6ab47a' },
  { key: 'is_useless',  label: '无用物料', color: '#8a7a6a' },
]

// ── 数据 ──────────────────────────────────────────
const groups   = ref([])
const loading  = ref(false)
const errorMsg = ref('')

// 每行独立的编辑草稿：{ [group_code]: { is_finished: bool, ... } }
// 不直接改 groups 里的原值，取消时要能还原。
const drafts   = ref({})
const savingId = ref(null)

// ── 筛选 ──────────────────────────────────────────
const keyword     = ref('')
const filterState = ref('')   // '' 全部 / 'unset' 未配置 / 'override' 含前缀例外

const filteredGroups = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return groups.value.filter(g => {
    if (kw && !(`${g.group_code}${g.group_name}`.toLowerCase().includes(kw))) return false
    if (filterState.value === 'unset'    && hasAnyCategory(g)) return false
    if (filterState.value === 'override' && !g.override_count) return false
    return true
  })
})

// 未配置任何大类的分组数，用于提示还剩多少要收口
const unsetCount = computed(() => groups.value.filter(g => !hasAnyCategory(g)).length)

// 有未保存改动的分组，用于顶部提示条与批量操作
const dirtyGroups = computed(() => groups.value.filter(g => isDirty(g)))

// ── 方法 ──────────────────────────────────────────
function hasAnyCategory(g) {
  return CATEGORIES.some(c => g[c.key])
}

// 取某行当前展示用的值：有草稿用草稿，否则用服务端值
function valueOf(g, key) {
  const d = drafts.value[g.group_code]
  return d ? d[key] : !!g[key]
}

function isDirty(g) {
  const d = drafts.value[g.group_code]
  if (!d) return false
  return CATEGORIES.some(c => d[c.key] !== !!g[c.key])
}

function toggle(g, key) {
  if (!drafts.value[g.group_code]) {
    drafts.value[g.group_code] = Object.fromEntries(
      CATEGORIES.map(c => [c.key, !!g[c.key]]),
    )
  }
  const d = drafts.value[g.group_code]
  d[key] = !d[key]
}

function cancelRow(g) {
  delete drafts.value[g.group_code]
}

// ── 加载分组列表 ──────────────────────────────────
async function loadGroups() {
  loading.value  = true
  errorMsg.value = ''
  try {
    const res = await http.get('/api/material/group-categories')
    if (res.success) {
      groups.value = res.data || []
      drafts.value = {}
    } else {
      errorMsg.value = res.message || '加载失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
  } finally {
    loading.value = false
  }
}

// ── 保存单行 ──────────────────────────────────────
async function saveRow(g) {
  const d = drafts.value[g.group_code]
  if (!d) return
  savingId.value = g.group_code
  errorMsg.value = ''
  try {
    const res = await http.put(
      `/api/material/group-categories/${encodeURIComponent(g.group_code)}`, d,
    )
    if (res.success) {
      // 用服务端返回值回写本行，避免本地状态与库里不一致
      Object.assign(g, res.data || d)
      delete drafts.value[g.group_code]
    } else {
      errorMsg.value = res.message || '保存失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
  } finally {
    savingId.value = null
  }
}

// ── 批量操作 ──────────────────────────────────────
async function saveAll() {
  // 串行保存：单 worker 的服务器，并发 PUT 没有收益
  for (const g of [...dirtyGroups.value]) {
    await saveRow(g)
    if (errorMsg.value) break   // 出错就停下，避免连续失败刷屏
  }
}

function cancelAll() {
  drafts.value = {}
}

// ── 生命周期 ──────────────────────────────────────
onMounted(loadGroups)
</script>

<template>
  <div class="group-category-config">

    <!-- 工具栏 -->
    <div class="toolbar">
      <input v-model="keyword" class="search-input" placeholder="搜索分组编码或名称" />
      <div class="filter-tabs">
        <button class="filter-tab" :class="{ active: filterState === '' }"
                @click="filterState = ''">全部</button>
        <button class="filter-tab" :class="{ active: filterState === 'unset' }"
                @click="filterState = 'unset'">未配置<span v-if="unsetCount"> {{ unsetCount }}</span></button>
        <button class="filter-tab" :class="{ active: filterState === 'override' }"
                @click="filterState = 'override'">含前缀例外</button>
      </div>
      <button class="btn-refresh" title="刷新" :disabled="loading" @click="loadGroups">
        <el-icon :class="{ spinning: loading }"><Refresh /></el-icon>
      </button>
    </div>

    <div class="rules-tip">
      分组默认大类对该分组下<b>未被前缀例外命中</b>的编码生效。未配置的分组，其物料归入「未分类」。
    </div>

    <!-- 有未保存改动时置顶提示，避免只靠行内按钮而被忽略 -->
    <div v-if="dirtyGroups.length" class="dirty-bar">
      <span>有 <b>{{ dirtyGroups.length }}</b> 个分组已修改但未保存</span>
      <div class="dirty-actions">
        <button class="btn-plain" @click="cancelAll">全部放弃</button>
        <button class="btn-save-all" :disabled="savingId !== null" @click="saveAll">全部保存</button>
      </div>
    </div>

    <div v-if="errorMsg" class="error-bar">
      <el-icon><WarningFilled /></el-icon>
      <span>{{ errorMsg }}</span>
    </div>

    <div v-if="loading" class="state-tip">加载中...</div>

    <!-- 分组表格 -->
    <div v-else-if="filteredGroups.length" class="gc-table">
      <div class="gc-head">
        <div class="gc-col col-code">分组编码</div>
        <div class="gc-col col-name">分组名称</div>
        <div class="gc-col col-count">物料数</div>
        <div class="gc-col col-override">前缀例外</div>
        <div class="gc-col col-cats">大类（成品/产成品可同时勾选）</div>
        <div class="gc-col col-actions"></div>
      </div>
      <div class="gc-body">
        <div
          v-for="g in filteredGroups"
          :key="g.group_code"
          class="gc-row"
          :class="{ 'row-unset': !hasAnyCategory(g) && !isDirty(g), 'row-dirty': isDirty(g) }"
        >
          <div class="gc-col col-code"><span class="code-tag">{{ g.group_code }}</span></div>
          <div class="gc-col col-name" :title="g.group_name">{{ g.group_name || '—' }}</div>
          <div class="gc-col col-count">{{ g.material_count ?? '—' }}</div>
          <div class="gc-col col-override">
            <span v-if="g.override_count" class="override-tag" :title="`该分组内有 ${g.override_count} 条被前缀例外规则覆盖`">
              {{ g.override_count }}
            </span>
            <span v-else class="muted">—</span>
          </div>
          <div class="gc-col col-cats">
            <button
              v-for="c in CATEGORIES"
              :key="c.key"
              class="cat-chip"
              :class="{ on: valueOf(g, c.key) }"
              :style="valueOf(g, c.key) ? {
                color: c.color, borderColor: c.color, background: c.color + '18',
              } : {}"
              @click="toggle(g, c.key)"
            >{{ c.label }}</button>
          </div>
          <div class="gc-col col-actions">
            <template v-if="isDirty(g)">
              <button class="btn-row confirm" :disabled="savingId === g.group_code" @click="saveRow(g)">
                {{ savingId === g.group_code ? '保存中' : '保存' }}
              </button>
              <button class="btn-row cancel" @click="cancelRow(g)">取消</button>
            </template>
            <span v-else class="col-actions-hint">—</span>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="state-tip">没有符合条件的分组</div>
  </div>
</template>

<style scoped>
.group-category-config {
  flex: 1 1 0; min-height: 0;
  display: flex; flex-direction: column;
  padding: 4px 0 8px;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ── 工具栏 ───────────────────────────────────── */
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-shrink: 0; }
.search-input {
  width: 200px; height: 30px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg); color: var(--text-primary);
  font-size: 12px; font-family: inherit; outline: none;
  transition: border-color 0.2s;
}
.search-input:focus { border-color: var(--accent); }

.filter-tabs { display: flex; gap: 6px; }
.filter-tab {
  padding: 4px 12px; border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-card); color: var(--text-secondary);
  font-size: 12px; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
}
.filter-tab:hover { border-color: var(--accent); color: var(--accent); }
.filter-tab.active { background: var(--accent-bg); border-color: var(--accent); color: var(--accent); font-weight: 500; }

.btn-refresh {
  margin-left: auto;
  width: 30px; height: 30px; border-radius: 7px;
  border: 1px solid var(--border);
  background: transparent; color: var(--text-secondary);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.15s;
}
.btn-refresh:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.btn-refresh:disabled { opacity: 0.5; cursor: not-allowed; }
.spinning { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── 说明与状态 ───────────────────────────────── */
.rules-tip {
  flex-shrink: 0;
  font-size: 11px; color: var(--text-secondary);
  margin-bottom: 12px; padding: 8px 12px;
  background: var(--accent-bg);
  border: 1px solid var(--border); border-radius: 7px;
}
.error-bar {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 12px; padding: 8px 12px;
  background: rgba(208,90,60,0.06); border: 1px solid rgba(208,90,60,0.2);
  border-radius: 7px; color: #d05a3c; font-size: 12px;
}
.state-tip { font-size: 13px; color: var(--text-secondary); padding: 24px 0; text-align: center; }

/* ── 表格 ─────────────────────────────────────── */
.gc-table {
  flex: 1 1 auto; min-height: 0;
  display: flex; flex-direction: column;
  border: 1px solid var(--border); border-radius: 10px; overflow: hidden;
}
.gc-body { flex: 1 1 0; min-height: 0; overflow-y: auto; }
.gc-body::-webkit-scrollbar { width: 4px; }
.gc-body::-webkit-scrollbar-track { background: transparent; }
.gc-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.gc-head {
  display: flex; align-items: center; height: 34px;
  background: var(--table-head, #f5f0e8);
  border-bottom: 1px solid var(--border); padding: 0 14px;
  position: sticky; top: 0; z-index: 1;
}
.gc-col { font-size: 12px; color: var(--text-primary); padding-right: 10px; }
.col-code     { width: 96px;  flex-shrink: 0; }
.col-name     { width: 180px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-count    { width: 70px;  flex-shrink: 0; }
.col-override { width: 80px;  flex-shrink: 0; }
.col-cats     { flex: 1; min-width: 0; display: flex; gap: 5px; flex-wrap: wrap; }
.col-actions  { width: 116px; flex-shrink: 0; display: flex; gap: 5px; justify-content: flex-end; padding-right: 0; }
.col-actions-hint { color: var(--text-secondary); }

.gc-row {
  display: flex; align-items: center; min-height: 44px;
  padding: 8px 14px; border-bottom: 1px solid var(--border);
  font-size: 12px; color: var(--text-primary); transition: background 0.15s;
}
.gc-row:last-child { border-bottom: none; }
.gc-row:hover { background: rgba(196,136,58,0.03); }
/* 未配置的行淡淡标出来，便于逐步收口 */
.gc-row.row-unset { background: rgba(208,90,60,0.035); }
/* 有未保存改动的行明显标出，并在左侧加一条竖条 */
.gc-row.row-dirty {
  background: rgba(74,143,192,0.08);
  box-shadow: inset 3px 0 0 #4a8fc0;
}

.code-tag {
  font-family: monospace; font-size: 12px;
  color: var(--accent); background: var(--accent-bg);
  border: 1px solid var(--border); border-radius: 4px; padding: 2px 7px;
}
.override-tag {
  font-size: 11px; color: #9c6fba;
  background: rgba(156,111,186,0.12); border: 1px solid rgba(156,111,186,0.3);
  border-radius: 4px; padding: 2px 7px; cursor: help;
}
.muted { color: var(--text-secondary); }

.cat-chip {
  padding: 3px 10px; border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg); color: var(--text-secondary);
  font-size: 11px; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
}
.cat-chip:hover { border-color: var(--accent); color: var(--accent); }
.cat-chip.on { font-weight: 600; }

.dirty-bar {
  display: flex; align-items: center; gap: 12px;
  flex-shrink: 0; margin-bottom: 10px; padding: 8px 12px;
  background: rgba(74,143,192,0.08);
  border: 1px solid rgba(74,143,192,0.35);
  border-radius: 7px; font-size: 12px; color: var(--text-primary);
}
.dirty-bar b { color: #4a8fc0; font-size: 13px; }
.dirty-actions { margin-left: auto; display: flex; gap: 8px; }
.btn-plain {
  padding: 4px 12px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--bg-card);
  color: var(--text-secondary); font-size: 12px; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
}
.btn-plain:hover { border-color: #d05a3c; color: #d05a3c; }
.btn-save-all {
  padding: 4px 14px; border-radius: 6px; border: none;
  background: #4a8fc0; color: #fff;
  font-size: 12px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
}
.btn-save-all:hover:not(:disabled) { filter: brightness(1.1); }
.btn-save-all:disabled { opacity: 0.5; cursor: not-allowed; }

/* 行内保存/取消：改为文字按钮 —— 原来是纯图标挤在 62px 列里，太容易被忽略 */
.btn-row {
  padding: 3px 11px; border-radius: 5px;
  font-size: 12px; font-family: inherit; font-weight: 600;
  cursor: pointer; transition: all 0.15s; white-space: nowrap;
}
.btn-row:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-row.confirm { border: 1px solid #4a8fc0; background: #4a8fc0; color: #fff; }
.btn-row.confirm:hover:not(:disabled) { filter: brightness(1.1); }
.btn-row.cancel { border: 1px solid rgba(208,90,60,0.45); background: transparent; color: #d05a3c; }
.btn-row.cancel:hover { background: rgba(208,90,60,0.08); border-color: #d05a3c; }

</style>
