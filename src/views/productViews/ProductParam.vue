<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted } from 'vue'
import { Plus, Delete, Edit } from '@element-plus/icons-vue'
import http from '@/api/http'

// ── 分组定义 ──────────────────────────────────────
const GROUP_DEFS = [
  { key: 'dimension', label: '尺寸' },
  { key: 'config',    label: '配置' },
  { key: 'brand',     label: '品牌' },
  { key: 'other',     label: '其他' },
]

// ── 状态 ──────────────────────────────────────────
const activeGroup = ref('dimension')
const allKeys     = ref({ dimension: [], config: [], brand: [], other: [] })
const loading     = ref(false)
const error       = ref('')

// 当前分组下的键名列表
const currentKeys = computed(() => allKeys.value[activeGroup.value] || [])

// ── 表单 ──────────────────────────────────────────
const formMode    = ref('')   // 'create' | 'edit' | ''
const editingItem = ref(null)
const formName    = ref('')
const formSort    = ref(0)
const formError   = ref('')
const submitting  = ref(false)
const deletingId  = ref(null)

// ── 生命周期 ──────────────────────────────────────
onMounted(loadKeys)

// ── 加载所有键名 ──────────────────────────────────
async function loadKeys() {
  loading.value = true
  error.value   = ''
  try {
    const res = await http.get('/api/product/params/keys')
    if (res.success) allKeys.value = res.data
    else error.value = res.message || '加载失败'
  } catch (e) {
    error.value = e.message || '网络错误'
  } finally {
    loading.value = false
  }
}

// ── 切换分组时关闭表单 ────────────────────────────
function switchGroup(key) {
  activeGroup.value = key
  handleCancel()
}

// ── 打开新增表单 ──────────────────────────────────
function openCreate() {
  formMode.value    = 'create'
  editingItem.value = null
  formName.value    = ''
  formSort.value    = 0
  formError.value   = ''
}

// ── 打开编辑表单 ──────────────────────────────────
function openEdit(item) {
  formMode.value    = 'edit'
  editingItem.value = item
  formName.value    = item.name
  formSort.value    = item.sort_order
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
      res = await http.post('/api/product/params/keys', {
        name,
        group_name: activeGroup.value,
        sort_order: formSort.value,
      })
    } else {
      res = await http.put(`/api/product/params/keys/${editingItem.value.id}`, {
        name,
        sort_order: formSort.value,
      })
    }
    if (res.success) {
      formMode.value = ''
      await loadKeys()
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
async function handleDelete(item) {
  deletingId.value = item.id
  try {
    const res = await http.delete(`/api/product/params/keys/${item.id}`)
    if (res.success) {
      const usage = res.data?.usage ?? 0
      if (usage > 0) {
        // 已通过 CASCADE 删除，仅提示
        console.log(`已删除，影响 ${usage} 个成品`)
      }
      if (editingItem.value?.id === item.id) handleCancel()
      await loadKeys()
    } else {
      error.value = res.message || '删除失败'
    }
  } catch (e) {
    error.value = e.message || '网络错误'
  } finally {
    deletingId.value = null
  }
}
</script>

<template>
  <div class="product-param">

    <div v-if="error" class="error-bar">{{ error }}</div>

    <!-- ── 分组 Tabs ────────────────────────────── -->
    <div class="group-tabs">
      <button
        v-for="g in GROUP_DEFS" :key="g.key"
        class="group-tab"
        :class="{ active: activeGroup === g.key }"
        @click="switchGroup(g.key)"
      >{{ g.label }}</button>
    </div>

    <div class="layout">

      <!-- ── 左侧键名列表 ──────────────────────── -->
      <div class="list-panel">
        <div class="panel-header">
          <span class="panel-title">参数键名</span>
          <button class="btn-add" @click="openCreate" title="新增键名">
            <el-icon><Plus /></el-icon>
          </button>
        </div>

        <div v-if="loading" class="panel-state">加载中...</div>
        <div v-else-if="!currentKeys.length" class="panel-state">暂无键名，点击 + 新增</div>

        <div v-else class="list-body">
          <div
            v-for="item in currentKeys" :key="item.id"
            class="key-row"
            :class="{ active: editingItem?.id === item.id }"
            @click="openEdit(item)"
          >
            <span class="key-name">{{ item.name }}</span>
            <div class="key-actions">
              <button class="btn-node" title="编辑" @click.stop="openEdit(item)">
                <el-icon><Edit /></el-icon>
              </button>
              <button
                class="btn-node danger"
                title="删除"
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
          <span class="empty-hint">选择键名编辑，或点击 + 新增</span>
        </div>

        <div v-else class="edit-form">
          <div class="form-title">{{ formMode === 'create' ? '新增键名' : '编辑键名' }}</div>

          <!-- 名称 -->
          <div class="form-row">
            <label class="form-label">名称 <span class="required">*</span></label>
            <input
              v-model="formName"
              class="form-input"
              placeholder="如：桌面（mm）"
              @keyup.enter="handleSubmit"
            />
          </div>

          <!-- 分组（只读） -->
          <div class="form-row">
            <label class="form-label">分组</label>
            <span class="form-static">{{ GROUP_DEFS.find(g => g.key === activeGroup)?.label }}</span>
          </div>

          <!-- 排序序号 -->
          <div class="form-row">
            <label class="form-label">排序</label>
            <input
              v-model.number="formSort"
              type="number"
              class="form-input form-input-sm"
              placeholder="0"
            />
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
.product-param {
  height: 400px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.error-bar {
  margin-bottom: 10px; padding: 8px 12px;
  background: rgba(208,90,60,0.06); border: 1px solid rgba(208,90,60,0.2);
  border-radius: 7px; color: #d05a3c; font-size: 12px;
}

/* ── 分组 Tabs ────────────────────────────────── */
.group-tabs {
  display: flex; gap: 2px; margin-bottom: 10px;
  border-bottom: 1px solid var(--border); padding-bottom: 0;
}
.group-tab {
  padding: 6px 16px; border: none; background: transparent;
  font-size: 13px; color: var(--text-muted);
  cursor: pointer; border-radius: 7px 7px 0 0;
  transition: all 0.15s; position: relative; bottom: -1px;
  border: 1px solid transparent;
  font-family: inherit;
}
.group-tab:hover { color: var(--accent); }
.group-tab.active {
  color: var(--accent); font-weight: 600;
  border: 1px solid var(--border); border-bottom-color: var(--bg-card);
  background: var(--bg-card);
}

/* ── 布局 ─────────────────────────────────────── */
.layout {
  display: flex; gap: 12px;
  flex: 1; min-height: 0;
  overflow: hidden;
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

.key-row {
  display: flex; align-items: center; gap: 8px;
  padding: 0 10px; height: 36px;
  cursor: pointer; transition: background 0.15s;
}
.key-row:hover  { background: rgba(196,136,58,0.05); }
.key-row.active { background: var(--accent-bg); }
.key-name {
  flex: 1; font-size: 12px; color: #3a3028;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.key-actions {
  display: none; gap: 2px;
}
.key-row:hover .key-actions { display: flex; }

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
.form-input-sm { max-width: 100px; flex: none; }
.form-static {
  font-size: 13px; color: #3a3028;
  padding: 6px 10px; background: rgba(0,0,0,0.03);
  border-radius: 7px; border: 1px solid var(--border);
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
