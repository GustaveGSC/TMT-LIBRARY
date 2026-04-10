<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted, computed } from 'vue'
import { WarningFilled, Plus, Delete, Edit, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import http from '@/api/http'
import { useFinishedStore } from '@/stores/product/finished'

// ── Store ─────────────────────────────────────────
const finishedStore = useFinishedStore()

// ── 类型配置 ──────────────────────────────────────
const TYPE_OPTIONS = [
  { value: 'finished',  label: '成品',   color: '#c4883a' },
  { value: 'packaged',  label: '产成品', color: '#4a8fc0' },
  { value: 'semi',      label: '半成品', color: '#9c6fba' },
  { value: 'material',  label: '物料',   color: '#6ab47a' },
]
const typeMap = Object.fromEntries(TYPE_OPTIONS.map(t => [t.value, t]))

// ── 数据 ──────────────────────────────────────────
const rules    = ref([])
const loading  = ref(false)
const errorMsg = ref('')

// ── 筛选 ──────────────────────────────────────────
const filterType = ref('')

const filteredRules = computed(() => {
  const list = filterType.value
    ? rules.value.filter(r => r.type === filterType.value)
    : rules.value
  // 按说明排序（无说明的排到最后）
  return [...list].sort((a, b) => {
    const da = a.description || ''
    const db = b.description || ''
    if (!da && !db) return 0
    if (!da) return 1
    if (!db) return -1
    return da.localeCompare(db, 'zh-CN')
  })
})

// ── 新增/编辑表单 ──────────────────────────────────
const showForm   = ref(false)
const isEditing  = ref(false)
const formData   = ref({ id: null, prefix: '', type: 'finished', description: '' })
const formError  = ref('')
const submitting = ref(false)

// ── 加载规则列表 ──────────────────────────────────
async function loadRules() {
  loading.value  = true
  errorMsg.value = ''
  try {
    const res = await http.get('/api/erp-code-rules/')
    if (res.success) {
      rules.value = res.data
    } else {
      errorMsg.value = res.message || '加载失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
  } finally {
    loading.value = false
  }
}

// ── 打开新增表单 ──────────────────────────────────
function openCreate() {
  isEditing.value = false
  formData.value  = { id: null, prefix: '', type: 'finished', description: '' }
  formError.value = ''
  showForm.value  = true
}

// ── 打开编辑表单 ──────────────────────────────────
function openEdit(rule) {
  isEditing.value = true
  formData.value  = { id: rule.id, prefix: rule.prefix, type: rule.type, description: rule.description || '' }
  formError.value = ''
  showForm.value  = true
}

// ── 提交表单 ──────────────────────────────────────
async function handleSubmit() {
  formError.value = ''
  if (!formData.value.prefix.trim()) {
    formError.value = '前缀不能为空'
    return
  }
  submitting.value = true
  try {
    const payload = {
      prefix:      formData.value.prefix.trim(),
      type:        formData.value.type,
      description: formData.value.description.trim() || null,
    }
    const res = isEditing.value
      ? await http.put(`/api/erp-code-rules/${formData.value.id}`, payload)
      : await http.post('/api/erp-code-rules/', payload)

    if (res.success) {
      showForm.value = false
      await loadRules()
    } else {
      formError.value = res.message || '操作失败'
    }
  } catch (e) {
    formError.value = e.message || '网络错误'
  } finally {
    submitting.value = false
  }
}

// ── 禁用/启用规则 ────────────────────────────────────
const togglingId = ref(null)

async function handleToggleDisabled(rule) {
  togglingId.value = rule.id
  try {
    const res = await http.patch(`/api/erp-code-rules/${rule.id}/toggle-disabled`)
    if (res.success) {
      // 本地更新行状态
      rule.is_disabled = res.data.is_disabled
      // 通知 store 刷新禁用前缀，表格/图片/图表视图立即生效
      finishedStore.reloadDisabledPrefixes()
    } else {
      errorMsg.value = res.message || '操作失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
  } finally {
    togglingId.value = null
  }
}

// ── 删除规则 ──────────────────────────────────────
const deletingId = ref(null)

async function handleDelete(rule) {
  deletingId.value = rule.id
  try {
    const res = await http.delete(`/api/erp-code-rules/${rule.id}`)
    if (res.success) {
      await loadRules()
    } else {
      errorMsg.value = res.message || '删除失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
  } finally {
    deletingId.value = null
  }
}

// ── 生命周期 ──────────────────────────────────────
onMounted(loadRules)
</script>

<template>
  <div class="product-rules">

    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="filter-tabs">
        <button
          class="filter-tab"
          :class="{ active: filterType === '' }"
          @click="filterType = ''"
        >全部</button>
        <button
          v-for="t in TYPE_OPTIONS"
          :key="t.value"
          class="filter-tab"
          :class="{ active: filterType === t.value }"
          :style="filterType === t.value ? { color: t.color, borderColor: t.color, background: t.color + '12' } : {}"
          @click="filterType = t.value"
        >{{ t.label }}</button>
      </div>
      <button class="btn-add" @click="openCreate">
        <el-icon><Plus /></el-icon>
        <span>新增规则</span>
      </button>
    </div>

    <!-- 说明文字 -->
    <div class="rules-tip">
      同一前缀可同时对应多个类型。
    </div>

    <!-- 错误提示 -->
    <div v-if="errorMsg" class="error-bar">
      <el-icon><WarningFilled /></el-icon>
      <span>{{ errorMsg }}</span>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="state-tip">加载中...</div>

    <!-- 规则表格 -->
    <div v-else-if="filteredRules.length" class="rules-table">
      <div class="rt-head">
        <div class="rt-col col-prefix">前缀</div>
        <div class="rt-col col-type">类型</div>
        <div class="rt-col col-desc">说明</div>
        <div class="rt-col col-actions"></div>
      </div>
      <div class="rules-table-body">
        <div
          v-for="rule in filteredRules"
          :key="rule.id"
          class="rt-row"
          :class="{ 'row-disabled': rule.is_disabled }"
        >
          <div class="rt-col col-prefix">
            <span class="prefix-tag" :class="{ 'prefix-disabled': rule.is_disabled }">{{ rule.prefix }}</span>
          </div>
          <div class="rt-col col-type">
            <span
              class="type-badge"
              :style="rule.is_disabled ? {} : {
                color:       typeMap[rule.type]?.color,
                background:  typeMap[rule.type]?.color + '18',
                borderColor: typeMap[rule.type]?.color + '40',
              }"
              :class="{ 'badge-disabled': rule.is_disabled }"
            >{{ rule.type_label }}</span>
          </div>
          <div class="rt-col col-desc">{{ rule.description || '—' }}</div>
          <div class="rt-col col-actions">
            <button
              class="btn-icon"
              :class="rule.is_disabled ? 'btn-enable' : 'btn-disable'"
              :title="rule.is_disabled ? '启用' : '禁用'"
              :disabled="togglingId === rule.id"
              @click="handleToggleDisabled(rule)"
            >
              <el-icon><VideoPlay v-if="rule.is_disabled" /><VideoPause v-else /></el-icon>
            </button>
            <button class="btn-icon" title="编辑" @click="openEdit(rule)">
              <el-icon><Edit /></el-icon>
            </button>
            <button
              class="btn-icon danger"
              title="删除"
              :disabled="deletingId === rule.id"
              @click="handleDelete(rule)"
            >
              <el-icon><Delete /></el-icon>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else class="state-tip">暂无规则，点击「新增规则」开始配置</div>

    <!-- 新增/编辑表单 -->
    <div v-if="showForm" class="form-card">
      <div class="form-title">{{ isEditing ? '编辑规则' : '新增规则' }}</div>

      <div class="form-row">
        <label class="form-label">前缀 <span class="required">*</span></label>
        <input
          v-model="formData.prefix"
          class="form-input"
          placeholder="如 1101 或 1101LH01"
          @keyup.enter="handleSubmit"
        />
      </div>

      <div class="form-row">
        <label class="form-label">类型 <span class="required">*</span></label>
        <div class="type-selector">
          <button
            v-for="t in TYPE_OPTIONS"
            :key="t.value"
            class="type-option"
            :class="{ selected: formData.type === t.value }"
            :style="formData.type === t.value ? {
              color:       t.color,
              background:  t.color + '18',
              borderColor: t.color,
            } : {}"
            @click="formData.type = t.value"
          >{{ t.label }}</button>
        </div>
      </div>

      <div class="form-row">
        <label class="form-label">说明</label>
        <input
          v-model="formData.description"
          class="form-input"
          placeholder="可选，备注说明"
        />
      </div>

      <div v-if="formError" class="form-error">{{ formError }}</div>

      <div class="form-actions">
        <button class="btn btn-secondary" @click="showForm = false">取消</button>
        <button class="btn btn-primary" :disabled="submitting" @click="handleSubmit">
          {{ submitting ? '提交中...' : (isEditing ? '保存' : '新增') }}
        </button>
      </div>
    </div>

  </div>
</template>

<style scoped>
.product-rules {
  padding: 4px 0 8px;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ── 工具栏 ───────────────────────────────────── */
.toolbar {
  display: flex; align-items: center;
  justify-content: space-between; margin-bottom: 10px;
}
.filter-tabs { display: flex; gap: 6px; }
.filter-tab {
  padding: 4px 12px; border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-card); color: var(--text-muted);
  font-size: 12px; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
}
.filter-tab:hover { border-color: var(--accent); color: var(--accent); }
.filter-tab.active { background: var(--accent-bg); border-color: var(--accent); color: var(--accent); font-weight: 500; }

.btn-add {
  display: flex; align-items: center; gap: 5px;
  padding: 5px 14px; border-radius: 7px;
  background: var(--accent); color: #fff;
  border: none; font-size: 12px; font-family: inherit;
  cursor: pointer; transition: all 0.2s;
}
.btn-add:hover { filter: brightness(1.1); }

/* ── 说明 ─────────────────────────────────────── */
.rules-tip {
  font-size: 11px; color: var(--text-muted);
  margin-bottom: 14px; padding: 8px 12px;
  background: var(--accent-bg);
  border: 1px solid var(--border); border-radius: 7px;
}

/* ── 状态提示 ─────────────────────────────────── */
.error-bar {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 12px; padding: 8px 12px;
  background: rgba(208,90,60,0.06); border: 1px solid rgba(208,90,60,0.2);
  border-radius: 7px; color: #d05a3c; font-size: 12px;
}
.state-tip { font-size: 13px; color: var(--text-muted); padding: 24px 0; text-align: center; }

/* ── 规则表格 ─────────────────────────────────── */
.rules-table {
  border: 1px solid var(--border);
  border-radius: 10px; overflow: hidden; margin-bottom: 16px;
}
.rules-table::-webkit-scrollbar { width: 4px; }
.rules-table::-webkit-scrollbar-track { background: transparent; }
.rules-table::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.rules-table-body {
  max-height: 220px; overflow-y: auto;
}
.rules-table-body::-webkit-scrollbar { width: 4px; }
.rules-table-body::-webkit-scrollbar-track { background: transparent; }
.rules-table-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.rt-head {
  display: flex; align-items: center; height: 34px;
  background: rgba(255,255,255,0.95);
  border-bottom: 1px solid var(--border); padding: 0 14px;
  position: sticky; top: 0; z-index: 1;
}
.rt-col {
  font-size: 12px; color: var(--text-muted);
  padding-right: 10px;
}
.col-prefix  { width: 140px; flex-shrink: 0; }
.col-type    { width: 80px;  flex-shrink: 0; }
.col-desc    { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-actions { width: 94px;  flex-shrink: 0; display: flex; gap: 4px; justify-content: flex-end; padding-right: 0; }

.rt-row {
  display: flex; align-items: center; min-height: 44px;
  padding: 8px 14px; border-bottom: 1px solid var(--border);
  font-size: 12px; color: var(--text-primary); transition: background 0.15s;
}
.rt-row:last-child { border-bottom: none; }
.rt-row:hover { background: rgba(196,136,58,0.03); }

.prefix-tag {
  font-family: monospace; font-size: 12px;
  color: var(--accent); background: var(--accent-bg);
  border: 1px solid var(--border); border-radius: 4px; padding: 2px 7px;
}
.type-badge {
  font-size: 11px; font-weight: 500;
  border: 1px solid; border-radius: 4px; padding: 2px 8px;
}
.btn-icon {
  width: 26px; height: 26px; border-radius: 5px;
  border: 1px solid var(--border);
  background: transparent; color: var(--text-muted);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.15s; font-size: 13px;
}
.btn-icon:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-bg); }
.btn-icon.danger:hover { border-color: #d05a3c; color: #d05a3c; background: rgba(208,90,60,0.06); }
.btn-icon.btn-disable:hover { border-color: #e09050; color: #e09050; background: rgba(196,136,58,0.06); }
.btn-icon.btn-enable:hover  { border-color: #4a8fc0; color: #4a8fc0; background: rgba(74,143,192,0.06); }
.btn-icon:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── 禁用行样式 ───────────────────────────────────── */
.rt-row.row-disabled { opacity: 0.45; }
.prefix-tag.prefix-disabled { text-decoration: line-through; }
.type-badge.badge-disabled {
  color: var(--text-muted);
  background: var(--bg);
  border-color: var(--border);
  border: 1px solid;
}

/* ── 表单卡片 ─────────────────────────────────── */
.form-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px;
}
.form-title { font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 16px; }
.form-row { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 14px; }
.form-label {
  width: 48px; flex-shrink: 0;
  font-size: 12px; color: var(--text-muted);
  padding-top: 7px; text-align: right;
}
.required { color: #d05a3c; }
.form-input {
  flex: 1; height: 32px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg); color: var(--text-primary);
  font-size: 13px; font-family: inherit;
  outline: none; transition: border-color 0.2s;
}
.form-input:focus { border-color: var(--accent); }
.type-selector { display: flex; gap: 6px; flex-wrap: wrap; padding-top: 2px; }
.type-option {
  padding: 4px 14px; border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg); color: var(--text-muted);
  font-size: 12px; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
}
.type-option:hover { border-color: var(--accent); color: var(--accent); }
.type-option.selected { font-weight: 500; }
.form-error { font-size: 12px; color: #d05a3c; margin-bottom: 12px; padding-left: 60px; }
.form-actions { display: flex; gap: 8px; justify-content: flex-end; padding-top: 4px; }
.btn {
  padding: 6px 18px; border-radius: 7px;
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.2s; border: none;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { background: var(--bg); border: 1px solid var(--border); color: var(--text-muted); }
.btn-secondary:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover:not(:disabled) { filter: brightness(1.1); }
</style>