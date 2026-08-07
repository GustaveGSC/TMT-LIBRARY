<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted } from 'vue'
import { WarningFilled, Refresh, Plus, Delete, Search } from '@element-plus/icons-vue'
import http from '@/api/http'

// ── 数据 ──────────────────────────────────────────
const combos   = ref([])
const loading  = ref(false)
const saving   = ref(false)
const errorMsg = ref('')

// ── 列表筛选 ──────────────────────────────────────
const keyword       = ref('')
const filterCategory = ref('')
const showDisabled  = ref(false)

const categories = computed(() => {
  const set = new Set(combos.value.map(c => (c.category || '').trim()).filter(Boolean))
  return [...set].sort((a, b) => a.localeCompare(b, 'zh'))
})

const visibleCombos = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return combos.value.filter(c => {
    if (!showDisabled.value && c.is_disabled) return false
    if (filterCategory.value && (c.category || '') !== filterCategory.value) return false
    if (kw && !`${c.name}${c.category || ''}`.toLowerCase().includes(kw)) return false
    return true
  })
})

// 按分类分组展示，便于在几十个组合里快速定位
const groupedCombos = computed(() => {
  const map = new Map()
  for (const c of visibleCombos.value) {
    const key = (c.category || '').trim() || '未分类'
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(c)
  }
  return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0], 'zh'))
})

// ── 当前编辑的组合 ────────────────────────────────
// draft 是深拷贝，取消时直接丢弃；不直接改列表里的对象。
const selectedId = ref(null)
const draft      = ref(null)

const selected = computed(() => combos.value.find(c => c.id === selectedId.value) || null)

// 是否有未保存改动：新建（id 为 null）或与服务端值不一致
const isDirty = computed(() => {
  if (!draft.value) return false
  if (draft.value.id == null) return true
  const s = selected.value
  if (!s) return true
  return JSON.stringify(normalize(draft.value)) !== JSON.stringify(normalize(s))
})

// 只比较业务字段，避免服务端返回的展示字段（material_name 等）造成假脏
function normalize(c) {
  return {
    name: (c.name || '').trim(),
    category: (c.category || '').trim(),
    remark: (c.remark || '').trim(),
    is_disabled: !!c.is_disabled,
    items: (c.items || []).map(i => ({
      material_code: i.material_code, quantity: Number(i.quantity) || 0,
    })),
  }
}

function selectCombo(c) {
  if (isDirty.value && !window.confirm('当前组合有未保存的改动，切换将丢弃。继续？')) return
  selectedId.value = c.id
  draft.value = JSON.parse(JSON.stringify({
    id: c.id, name: c.name, category: c.category || '', remark: c.remark || '',
    is_disabled: !!c.is_disabled, sort_order: c.sort_order || 0,
    items: (c.items || []).map(i => ({ ...i })),
  }))
}

function newCombo() {
  if (isDirty.value && !window.confirm('当前组合有未保存的改动，新建将丢弃。继续？')) return
  selectedId.value = null
  draft.value = {
    id: null, name: '', category: '', remark: '',
    is_disabled: false, sort_order: 0, items: [],
  }
}

function discard() {
  if (draft.value?.id != null) selectCombo(selected.value)
  else { draft.value = null; selectedId.value = null }
}

// ── 明细编辑 ──────────────────────────────────────
function removeItem(idx) {
  draft.value.items.splice(idx, 1)
}

function moveItem(idx, delta) {
  const items = draft.value.items
  const to = idx + delta
  if (to < 0 || to >= items.length) return
  const [row] = items.splice(idx, 1)
  items.splice(to, 0, row)
}

// ── 物料选择器 ────────────────────────────────────
const pickerVisible = ref(false)
const pickerKeyword = ref('')
const pickerRows    = ref([])
const pickerLoading = ref(false)

async function searchMaterials() {
  const kw = pickerKeyword.value.trim()
  if (!kw) { pickerRows.value = []; return }
  pickerLoading.value = true
  try {
    // 复用物料清单接口。这里不限定大类：分组默认大类目前一条都没配，
    // 8091 条里有 3354 条「未分类」，若默认只显示原材料会大量选不到。
    const res = await http.get('/api/material/items', {
      params: { page: 1, page_size: 30, keyword: kw, is_disabled: '0' },
    })
    pickerRows.value = res.success ? (res.data?.items || []) : []
  } catch {
    pickerRows.value = []
  } finally {
    pickerLoading.value = false
  }
}

function addMaterial(row) {
  const items = draft.value.items
  if (items.some(i => i.material_code === row.code)) {
    errorMsg.value = `「${row.code}」已在明细中`
    return
  }
  errorMsg.value = ''
  items.push({
    material_code: row.code, quantity: 1,
    material_name: row.name, short_name: row.short_name,
    group_name: row.group_name, is_missing: false,
  })
}

// ── 加载与保存 ────────────────────────────────────
async function loadCombos() {
  loading.value  = true
  errorMsg.value = ''
  try {
    const res = await http.get('/api/material/combos')
    if (res.success) {
      combos.value = res.data?.items || res.data || []
      // 保持当前选中项（若仍存在）
      if (selectedId.value != null) {
        const still = combos.value.find(c => c.id === selectedId.value)
        if (still) selectCombo(still)
        else { draft.value = null; selectedId.value = null }
      }
    } else {
      errorMsg.value = res.message || '加载失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
  } finally {
    loading.value = false
  }
}

async function save() {
  const d = draft.value
  if (!d) return
  if (!d.name.trim()) { errorMsg.value = '组合名称不能为空'; return }
  const bad = d.items.find(i => !(Number(i.quantity) > 0 && Number.isInteger(Number(i.quantity))))
  if (bad) { errorMsg.value = `「${bad.material_code}」的数量必须是正整数`; return }

  saving.value   = true
  errorMsg.value = ''
  try {
    const payload = {
      name: d.name.trim(), category: d.category.trim() || null,
      remark: d.remark.trim() || null, is_disabled: !!d.is_disabled,
      sort_order: d.sort_order || 0,
      items: d.items.map((i, idx) => ({
        material_code: i.material_code, quantity: Number(i.quantity), sort_order: idx,
      })),
    }
    const res = d.id == null
      ? await http.post('/api/material/combos', payload)
      : await http.put(`/api/material/combos/${d.id}`, payload)
    if (res.success) {
      selectedId.value = res.data?.id ?? d.id
      await loadCombos()
    } else {
      errorMsg.value = res.message || '保存失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
  } finally {
    saving.value = false
  }
}

async function remove() {
  const d = draft.value
  if (!d?.id) return
  if (!window.confirm(`确认删除组合「${d.name}」？其明细会一并删除。`)) return
  saving.value = true
  try {
    const res = await http.delete(`/api/material/combos/${d.id}`)
    if (res.success) {
      draft.value = null; selectedId.value = null
      await loadCombos()
    } else {
      errorMsg.value = res.message || '删除失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
  } finally {
    saving.value = false
  }
}

// ── 生命周期 ──────────────────────────────────────
onMounted(loadCombos)
</script>

<template>
  <div class="combo-panel">

    <!-- ── 左：组合列表 ──────────────────────────── -->
    <aside class="combo-side">
      <div class="side-head">
        <input v-model="keyword" class="side-search" placeholder="搜索组合名称" />
        <button class="btn-refresh" title="刷新" :disabled="loading" @click="loadCombos">
          <el-icon :class="{ spinning: loading }"><Refresh /></el-icon>
        </button>
      </div>

      <div class="side-filters">
        <select v-model="filterCategory" class="side-select">
          <option value="">全部分类</option>
          <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
        </select>
        <label class="side-check">
          <input v-model="showDisabled" type="checkbox" />
          <span>含停用</span>
        </label>
      </div>

      <button class="btn-new" @click="newCombo">
        <el-icon><Plus /></el-icon><span>新建组合</span>
      </button>

      <div class="side-list">
        <div v-if="loading" class="state-tip">加载中...</div>
        <div v-else-if="!groupedCombos.length" class="state-tip">暂无组合</div>
        <template v-else>
          <div v-for="[cat, list] in groupedCombos" :key="cat" class="side-group">
            <div class="side-group-label">{{ cat }}<span class="cnt">{{ list.length }}</span></div>
            <button
              v-for="c in list"
              :key="c.id"
              class="side-item"
              :class="{ active: c.id === selectedId, off: c.is_disabled }"
              @click="selectCombo(c)"
            >
              <span class="si-name">{{ c.name }}</span>
              <span class="si-cnt">{{ (c.items || []).length }} 项</span>
            </button>
          </div>
        </template>
      </div>
    </aside>

    <!-- ── 右：明细编辑 ──────────────────────────── -->
    <section class="combo-main">
      <div v-if="errorMsg" class="error-bar">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ errorMsg }}</span>
      </div>

      <div v-if="!draft" class="state-tip big">
        从左侧选择一个组合，或点击「新建组合」
      </div>

      <template v-else>
        <!-- 未保存提示条 -->
        <div v-if="isDirty" class="dirty-bar">
          <span>{{ draft.id == null ? '新建的组合尚未保存' : '当前组合有未保存的改动' }}</span>
          <div class="dirty-actions">
            <button class="btn-plain" @click="discard">放弃</button>
            <button class="btn-save" :disabled="saving" @click="save">
              {{ saving ? '保存中…' : '保存' }}
            </button>
          </div>
        </div>

        <!-- 组合属性 -->
        <div class="combo-head">
          <div class="ch-row">
            <label>名称</label>
            <input v-model="draft.name" class="ch-input" placeholder="如：领航员桌腿维修包" />
            <label class="ml">分类</label>
            <input v-model="draft.category" class="ch-input short" placeholder="如：桌腿" list="combo-cats" />
            <datalist id="combo-cats">
              <option v-for="c in categories" :key="c" :value="c" />
            </datalist>
          </div>
          <div class="ch-row">
            <label>备注</label>
            <input v-model="draft.remark" class="ch-input" placeholder="可选" />
            <label class="ch-check ml">
              <input v-model="draft.is_disabled" type="checkbox" />
              <span>停用</span>
            </label>
            <button v-if="draft.id != null" class="btn-del" :disabled="saving" @click="remove">
              <el-icon><Delete /></el-icon><span>删除组合</span>
            </button>
          </div>
        </div>

        <!-- 明细 -->
        <div class="items-head">
          <span class="ih-title">明细 <b>{{ draft.items.length }}</b> 项</span>
          <button class="btn-add-item" @click="pickerVisible = true">
            <el-icon><Plus /></el-icon><span>添加物料</span>
          </button>
        </div>

        <div class="items-table">
          <div class="it-head">
            <div class="it-col col-idx">#</div>
            <div class="it-col col-code">ERP 编码</div>
            <div class="it-col col-name">物料名称 / 简称</div>
            <div class="it-col col-qty">数量</div>
            <div class="it-col col-act"></div>
          </div>
          <div class="it-body">
            <div v-if="!draft.items.length" class="state-tip">还没有明细，点击「添加物料」</div>
            <div
              v-for="(it, idx) in draft.items"
              :key="it.material_code"
              class="it-row"
              :class="{ missing: it.is_missing }"
            >
              <div class="it-col col-idx">{{ idx + 1 }}</div>
              <div class="it-col col-code"><span class="code-tag">{{ it.material_code }}</span></div>
              <div class="it-col col-name">
                <template v-if="it.is_missing">
                  <span class="miss-tag">物料已不存在</span>
                </template>
                <template v-else>
                  <div class="nm-main">{{ it.short_name || it.material_name || '—' }}</div>
                  <div v-if="it.short_name && it.material_name" class="nm-sub">{{ it.material_name }}</div>
                </template>
              </div>
              <div class="it-col col-qty">
                <input v-model.number="it.quantity" class="qty-input" type="number" min="1" step="1" />
              </div>
              <div class="it-col col-act">
                <button class="mini" title="上移" @click="moveItem(idx, -1)">↑</button>
                <button class="mini" title="下移" @click="moveItem(idx, 1)">↓</button>
                <button class="mini danger" title="移除" @click="removeItem(idx)">✕</button>
              </div>
            </div>
          </div>
        </div>
      </template>
    </section>

    <!-- ── 物料选择器 ────────────────────────────── -->
    <el-dialog v-model="pickerVisible" title="添加物料" width="720" align-center append-to-body>
      <div class="picker">
        <div class="pk-search">
          <input
            v-model="pickerKeyword"
            class="pk-input"
            placeholder="按 ERP 编码或名称搜索，回车查询"
            @keyup.enter="searchMaterials"
          />
          <button class="btn-save" @click="searchMaterials">
            <el-icon><Search /></el-icon><span>搜索</span>
          </button>
        </div>
        <div class="pk-hint">
          未限定物料大类——分组默认大类尚未配置，8,091 条里有 3,354 条「未分类」，
          限定后会大量选不到。
        </div>
        <div v-if="pickerLoading" class="state-tip">搜索中...</div>
        <div v-else-if="!pickerRows.length" class="state-tip">输入关键词后回车搜索</div>
        <div v-else class="pk-list">
          <div v-for="r in pickerRows" :key="r.code" class="pk-row">
            <span class="code-tag">{{ r.code }}</span>
            <span class="pk-name" :title="r.name">{{ r.short_name || r.name }}</span>
            <span class="pk-group">{{ r.group_name || '' }}</span>
            <button class="btn-save mini-btn" @click="addMaterial(r)">添加</button>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.combo-panel {
  flex: 1 1 0; min-height: 0;
  display: flex; gap: 14px;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  color: var(--text-primary);
}

/* ── 左侧列表 ─────────────────────────────────── */
.combo-side {
  width: 260px; flex-shrink: 0;
  display: flex; flex-direction: column; gap: 8px; min-height: 0;
  padding: 10px; background: var(--bg-card);
  border: 1px solid var(--border); border-radius: 10px;
}
.side-head { display: flex; gap: 6px; flex-shrink: 0; }
.side-search {
  flex: 1; min-width: 0; height: 28px; padding: 0 8px;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg); color: var(--text-primary);
  font-size: 12px; font-family: inherit; outline: none;
}
.side-search:focus { border-color: var(--accent); }
.side-filters { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.side-select {
  flex: 1; min-width: 0; height: 26px; padding: 0 6px;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg); color: var(--text-primary);
  font-size: 12px; font-family: inherit; cursor: pointer; outline: none;
}
.side-check, .ch-check {
  display: flex; align-items: center; gap: 4px;
  font-size: 12px; color: var(--text-primary); cursor: pointer; white-space: nowrap;
}
.side-check input, .ch-check input { margin: 0; cursor: pointer; }

.btn-new {
  display: flex; align-items: center; justify-content: center; gap: 5px;
  height: 30px; flex-shrink: 0;
  border: 1px dashed var(--accent); border-radius: 7px;
  background: var(--accent-bg); color: var(--accent);
  font-size: 12px; font-weight: 600; font-family: inherit; cursor: pointer;
  transition: all 0.15s;
}
.btn-new:hover { background: var(--accent); color: #fff; border-style: solid; }

.side-list { flex: 1 1 0; min-height: 0; overflow-y: auto; }
.side-list::-webkit-scrollbar { width: 4px; }
.side-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.side-group { margin-bottom: 8px; }
.side-group-label {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; font-weight: 700; color: var(--accent);
  letter-spacing: 0.06em; padding: 4px 2px;
}
.side-group-label .cnt {
  font-weight: 400; color: var(--text-secondary);
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 8px; padding: 0 5px;
}
.side-item {
  display: flex; align-items: center; gap: 6px; width: 100%;
  padding: 6px 8px; margin-bottom: 2px;
  border: 1px solid transparent; border-radius: 6px;
  background: transparent; color: var(--text-primary);
  font-size: 12px; font-family: inherit; text-align: left; cursor: pointer;
  transition: all 0.15s;
}
.side-item:hover { background: var(--bg-table-hover); }
.side-item.active { background: var(--accent-bg); border-color: var(--accent); font-weight: 600; }
.side-item.off { opacity: 0.5; }
.si-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.si-cnt { font-size: 11px; color: var(--text-secondary); flex-shrink: 0; }

/* ── 右侧主区 ─────────────────────────────────── */
.combo-main { flex: 1; min-width: 0; display: flex; flex-direction: column; min-height: 0; }

.error-bar {
  display: flex; align-items: center; gap: 8px; flex-shrink: 0;
  margin-bottom: 10px; padding: 8px 12px;
  background: rgba(208,90,60,0.06); border: 1px solid rgba(208,90,60,0.2);
  border-radius: 7px; color: #d05a3c; font-size: 12px;
}
.state-tip { font-size: 13px; color: var(--text-secondary); padding: 20px 0; text-align: center; }
.state-tip.big { padding: 60px 0; }

.dirty-bar {
  display: flex; align-items: center; gap: 12px; flex-shrink: 0;
  margin-bottom: 10px; padding: 8px 12px;
  background: rgba(74,143,192,0.08); border: 1px solid rgba(74,143,192,0.35);
  border-radius: 7px; font-size: 12px;
}
.dirty-actions { margin-left: auto; display: flex; gap: 8px; }
.btn-plain {
  padding: 4px 12px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--bg-card);
  color: var(--text-secondary); font-size: 12px; font-family: inherit; cursor: pointer;
}
.btn-plain:hover { border-color: #d05a3c; color: #d05a3c; }
.btn-save {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 14px; border-radius: 6px; border: none;
  background: #4a8fc0; color: #fff;
  font-size: 12px; font-weight: 600; font-family: inherit; cursor: pointer;
}
.btn-save:hover:not(:disabled) { filter: brightness(1.1); }
.btn-save:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── 组合属性 ─────────────────────────────────── */
.combo-head {
  flex-shrink: 0; margin-bottom: 10px; padding: 12px;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
}
.ch-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.ch-row:last-child { margin-bottom: 0; }
.ch-row label { font-size: 12px; color: var(--text-secondary); white-space: nowrap; }
.ch-row label.ml { margin-left: 8px; }
.ch-input {
  flex: 1; min-width: 0; height: 28px; padding: 0 8px;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg); color: var(--text-primary);
  font-size: 12px; font-family: inherit; outline: none;
}
.ch-input:focus { border-color: var(--accent); }
.ch-input.short { flex: 0 0 160px; }
.btn-del {
  display: inline-flex; align-items: center; gap: 4px; margin-left: auto;
  padding: 4px 12px; border-radius: 6px;
  border: 1px solid rgba(208,90,60,0.45); background: transparent;
  color: #d05a3c; font-size: 12px; font-family: inherit; cursor: pointer;
}
.btn-del:hover:not(:disabled) { background: rgba(208,90,60,0.08); border-color: #d05a3c; }
.btn-del:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── 明细 ─────────────────────────────────────── */
.items-head { display: flex; align-items: center; margin-bottom: 8px; flex-shrink: 0; }
.ih-title { font-size: 12px; color: var(--text-secondary); }
.ih-title b { color: var(--text-primary); font-size: 13px; }
.btn-add-item {
  display: inline-flex; align-items: center; gap: 4px; margin-left: auto;
  padding: 4px 12px; border-radius: 6px;
  border: 1px solid var(--accent); background: var(--accent-bg);
  color: var(--accent); font-size: 12px; font-weight: 600;
  font-family: inherit; cursor: pointer;
}
.btn-add-item:hover { background: var(--accent); color: #fff; }

.items-table {
  flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column;
  border: 1px solid var(--border); border-radius: 10px; overflow: hidden;
}
.it-head {
  display: flex; align-items: center; height: 32px; flex-shrink: 0;
  background: var(--bg-table-header); border-bottom: 1px solid var(--border);
  padding: 0 12px;
}
.it-body { flex: 1 1 0; min-height: 0; overflow-y: auto; }
.it-body::-webkit-scrollbar { width: 4px; }
.it-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.it-col { font-size: 12px; color: var(--text-primary); padding-right: 10px; }
.col-idx  { width: 34px;  flex-shrink: 0; color: var(--text-secondary); }
.col-code { width: 180px; flex-shrink: 0; }
.col-name { flex: 1; min-width: 0; }
.col-qty  { width: 90px;  flex-shrink: 0; }
.col-act  { width: 96px;  flex-shrink: 0; display: flex; gap: 4px; justify-content: flex-end; padding-right: 0; }

.it-row {
  display: flex; align-items: center; min-height: 44px;
  padding: 6px 12px; border-bottom: 1px solid var(--border);
}
.it-row:last-child { border-bottom: none; }
.it-row:hover { background: var(--bg-table-hover); }
.it-row.missing { background: rgba(208,90,60,0.07); }

.code-tag {
  font-family: 'Microsoft YaHei UI', monospace; font-size: 11px; font-weight: 600;
  color: var(--text-primary); background: var(--accent-bg);
  border: 1px solid var(--border); border-radius: 4px; padding: 2px 6px;
}
.nm-main { font-size: 12px; }
.nm-sub {
  font-size: 11px; color: var(--text-secondary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.miss-tag {
  font-size: 11px; color: #d05a3c;
  background: rgba(208,90,60,0.12); border: 1px solid rgba(208,90,60,0.35);
  border-radius: 4px; padding: 1px 7px;
}
.qty-input {
  width: 68px; height: 26px; padding: 0 6px;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg); color: var(--text-primary);
  font-size: 12px; font-family: inherit; outline: none;
}
.qty-input:focus { border-color: var(--accent); }
.mini {
  width: 26px; height: 26px; border-radius: 5px;
  border: 1px solid var(--border); background: transparent;
  color: var(--text-primary); font-size: 12px; cursor: pointer; transition: all 0.15s;
}
.mini:hover { border-color: var(--accent); color: var(--accent); }
.mini.danger:hover { border-color: #d05a3c; color: #d05a3c; background: rgba(208,90,60,0.08); }

.btn-refresh {
  width: 28px; height: 28px; flex-shrink: 0; border-radius: 6px;
  border: 1px solid var(--border); background: transparent;
  color: var(--text-secondary);
  display: flex; align-items: center; justify-content: center; cursor: pointer;
}
.btn-refresh:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.spinning { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── 物料选择器 ───────────────────────────────── */
.picker { font-size: 12px; color: var(--text-primary); }
.pk-search { display: flex; gap: 8px; margin-bottom: 8px; }
.pk-input {
  flex: 1; height: 30px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg); color: var(--text-primary);
  font-size: 12px; font-family: inherit; outline: none;
}
.pk-input:focus { border-color: var(--accent); }
.pk-hint {
  font-size: 11px; color: var(--text-secondary);
  background: var(--accent-bg); border: 1px solid var(--border);
  border-radius: 6px; padding: 6px 10px; margin-bottom: 8px;
}
.pk-list { max-height: 380px; overflow-y: auto; }
.pk-list::-webkit-scrollbar { width: 4px; }
.pk-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.pk-row {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 4px; border-bottom: 1px solid var(--border);
}
.pk-row:last-child { border-bottom: none; }
.pk-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pk-group { width: 130px; flex-shrink: 0; color: var(--text-secondary); font-size: 11px; }
.mini-btn { padding: 3px 12px; }
</style>
