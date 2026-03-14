<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import { Plus, Delete, Edit } from '@element-plus/icons-vue'
import http from '@/api/http'

// ── 标签列表 ──────────────────────────────────────
const labels  = ref([])
const loading = ref(false)
const error   = ref('')

// ── 表单 ──────────────────────────────────────────
const formMode    = ref('')   // 'create' | 'edit' | ''
const editingItem = ref(null)
const formName    = ref('')
const formColor   = ref('#c4883a')
const formError   = ref('')
const submitting  = ref(false)

// 预设颜色
const PRESET_COLORS = [
  '#c4883a', '#4a8fc0', '#9c6fba', '#6ab47a',
  '#d05a3c', '#3a7bc8', '#e6a817', '#5c7a5c',
]

// ── 生命周期 ──────────────────────────────────────
onMounted(loadLabels)

// ── 加载标签 ──────────────────────────────────────
async function loadLabels() {
  loading.value = true
  error.value   = ''
  try {
    const res = await http.get('/api/product/tags/')
    if (res.success) labels.value = res.data
    else error.value = res.message || '加载失败'
  } catch (e) {
    error.value = e.message || '网络错误'
  } finally {
    loading.value = false
  }
}

// ── 打开新增表单 ──────────────────────────────────
function openCreate() {
  formMode.value    = 'create'
  editingItem.value = null
  formName.value    = ''
  formColor.value   = '#c4883a'
  formError.value   = ''
}

// ── 打开编辑表单 ──────────────────────────────────
function openEdit(item) {
  formMode.value    = 'edit'
  editingItem.value = item
  formName.value    = item.name
  formColor.value   = item.color || '#c4883a'
  formError.value   = ''
}

// ── 取消 ──────────────────────────────────────────
function handleCancel() {
  formMode.value    = ''
  editingItem.value = null
  formError.value   = ''
}

// ── 提交 ──────────────────────────────────────────
async function handleSubmit() {
  const name = formName.value.trim()
  if (!name) { formError.value = '名称不能为空'; return }
  submitting.value = true
  formError.value  = ''
  try {
    let res
    if (formMode.value === 'create') {
      res = await http.post('/api/product/tags/', { name, color: formColor.value })
    } else {
      res = await http.put(`/api/product/tags/${editingItem.value.id}`, { name, color: formColor.value })
    }
    if (res.success) {
      formMode.value = ''
      await loadLabels()
    } else {
      formError.value = res.message || '操作失败'
    }
  } catch (e) {
    formError.value = e.message || '网络错误'
  } finally {
    submitting.value = false
  }
}

// ── 删除 ──────────────────────────────────────────
const deletingId = ref(null)
async function handleDelete(item) {
  deletingId.value = item.id
  try {
    const res = await http.delete(`/api/product/tags/${item.id}`)
    if (res.success) await loadLabels()
    else error.value = res.message || '删除失败'
  } catch (e) {
    error.value = e.message || '网络错误'
  } finally {
    deletingId.value = null
  }
}
</script>

<template>
  <div class="product-label">

    <div v-if="error" class="error-bar">{{ error }}</div>

    <div class="layout">

      <!-- ── 左侧标签列表 ──────────────────────── -->
      <div class="list-panel">
        <div class="panel-header">
          <span class="panel-title">标签列表</span>
          <button class="btn-add" @click="openCreate">
            <el-icon><Plus /></el-icon>
          </button>
        </div>

        <div v-if="loading" class="panel-state">加载中...</div>
        <div v-else-if="!labels.length" class="panel-state">暂无标签，点击 + 新增</div>

        <div v-else class="list-body">
          <div
            v-for="item in labels" :key="item.id"
            class="label-row"
            :class="{ active: editingItem?.id === item.id }"
            @click="openEdit(item)"
          >
            <span class="label-dot" :style="{ background: item.color || '#c4883a' }"></span>
            <span class="label-name">{{ item.name }}</span>
            <div class="label-actions">
              <button class="btn-node" @click.stop="openEdit(item)">
                <el-icon><Edit /></el-icon>
              </button>
              <button
                class="btn-node danger"
                :disabled="deletingId === item.id"
                @click.stop="handleDelete(item)"
              >
                <el-icon><Delete /></el-icon>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- ── 右侧表单 ───────────────────────────── -->
      <div class="edit-panel">
        <div v-if="!formMode" class="edit-empty">
          <span class="empty-hint">选择标签编辑，或点击 + 新增</span>
        </div>

        <div v-else class="edit-form">
          <div class="form-title">{{ formMode === 'create' ? '新增标签' : '编辑标签' }}</div>

          <!-- 名称 -->
          <div class="form-row">
            <label class="form-label">名称 <span class="required">*</span></label>
            <input
              v-model="formName"
              class="form-input"
              placeholder="输入标签名称"
              @keyup.enter="handleSubmit"
            />
          </div>

          <!-- 颜色 -->
          <div class="form-row">
            <label class="form-label">颜色</label>
            <div class="color-picker">
              <span
                v-for="c in PRESET_COLORS" :key="c"
                class="color-dot"
                :class="{ selected: formColor === c }"
                :style="{ background: c }"
                @click="formColor = c"
              ></span>
              <input type="color" v-model="formColor" class="color-custom" title="自定义颜色" />
            </div>
          </div>

          <!-- 预览 -->
          <div class="form-row">
            <label class="form-label">预览</label>
            <span class="label-preview" :style="{ background: formColor + '20', color: formColor, borderColor: formColor + '60' }">
              {{ formName || '标签名称' }}
            </span>
          </div>

          <div v-if="formError" class="form-error">{{ formError }}</div>

          <div class="form-actions">
            <button class="btn btn-secondary" @click="handleCancel">取消</button>
            <button class="btn btn-primary" :disabled="submitting" @click="handleSubmit">
              {{ submitting ? '提交中...' : (formMode === 'create' ? '新增' : '保存') }}
            </button>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.product-label {
  height: 100%;
}
.error-bar {
  margin-bottom: 10px; padding: 8px 12px;
  background: rgba(208,90,60,0.06); border: 1px solid rgba(208,90,60,0.2);
  border-radius: 7px; color: #d05a3c; font-size: 12px;
}

/* ── 布局 ─────────────────────────────────────── */
.layout {
  display: flex; gap: 12px;
  height: 340px;
}

/* ── 左侧列表 ─────────────────────────────────── */
.list-panel {
  width: 220px; flex-shrink: 0;
  border: 1px solid var(--border); border-radius: 10px;
  display: flex; flex-direction: column; overflow: hidden;
}
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.8); flex-shrink: 0;
}
.panel-title { font-size: 12px; font-weight: 600; color: #5a4e42; }
.btn-add {
  width: 22px; height: 22px; border-radius: 5px;
  border: 1px solid var(--border); background: transparent;
  color: var(--text-muted); display: flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 12px; transition: all 0.15s;
}
.btn-add:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-bg); }

.panel-state {
  padding: 24px; text-align: center;
  font-size: 12px; color: var(--text-muted);
}
.list-body {
  flex: 1; overflow-y: auto; padding: 4px 0;
}
.list-body::-webkit-scrollbar { width: 4px; }
.list-body::-webkit-scrollbar-track { background: transparent; }
.list-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.label-row {
  display: flex; align-items: center; gap: 8px;
  padding: 0 10px; height: 36px;
  cursor: pointer; transition: background 0.15s;
}
.label-row:hover  { background: rgba(196,136,58,0.05); }
.label-row.active { background: var(--accent-bg); }
.label-dot {
  width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}
.label-name {
  flex: 1; font-size: 12px; color: #3a3028;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.label-actions {
  display: none; gap: 2px;
}
.label-row:hover .label-actions { display: flex; }

.btn-node {
  width: 20px; height: 20px; border-radius: 4px;
  border: none; background: transparent; color: var(--text-muted);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 11px; transition: all 0.15s;
}
.btn-node:hover { background: var(--accent-bg); color: var(--accent); }
.btn-node.danger:hover { background: rgba(208,90,60,0.08); color: #d05a3c; }
.btn-node:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── 右侧表单 ─────────────────────────────────── */
.edit-panel {
  flex: 1; border: 1px solid var(--border); border-radius: 10px;
  background: var(--bg-card); display: flex; flex-direction: column;
  overflow: hidden;
}
.edit-empty {
  flex: 1; display: flex; align-items: center; justify-content: center;
}
.empty-hint { font-size: 12px; color: #8a7a6a; }

.edit-form { padding: 24px; }
.form-title { font-size: 15px; font-weight: 600; color: #2c2420; margin-bottom: 20px; }
.form-row { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.form-label {
  width: 48px; flex-shrink: 0; font-size: 12px; color: #6b5e4e;
  text-align: right; display: flex; align-items: center; justify-content: flex-end; gap: 2px;
}
.required { color: #d05a3c; font-size: 14px; line-height: 1; }
.form-input {
  flex: 1; height: 34px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg); color: var(--text-primary);
  font-size: 13px; font-family: inherit;
  outline: none; transition: border-color 0.2s;
}
.form-input:focus { border-color: var(--accent); }

/* 颜色选择器 */
.color-picker { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.color-dot {
  width: 22px; height: 22px; border-radius: 50%;
  cursor: pointer; transition: transform 0.15s;
  border: 2px solid transparent;
}
.color-dot:hover { transform: scale(1.15); }
.color-dot.selected { border-color: #3a3028; transform: scale(1.15); }
.color-custom {
  width: 22px; height: 22px; border-radius: 50%;
  border: 2px solid var(--border); cursor: pointer;
  padding: 0; background: none; outline: none;
}

/* 预览 */
.label-preview {
  display: inline-block; font-size: 12px; font-weight: 500;
  padding: 3px 10px; border-radius: 4px; border: 1px solid;
}

.form-error { font-size: 12px; color: #d05a3c; margin-bottom: 12px; padding-left: 60px; }
.form-actions { display: flex; gap: 8px; justify-content: flex-end; }

.btn {
  display: inline-flex; align-items: center; gap: 6px;
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