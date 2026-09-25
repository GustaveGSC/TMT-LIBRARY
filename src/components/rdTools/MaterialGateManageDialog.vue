<script setup>
// ── 物料门禁维护弹窗 ────────────────────────────────
// 仅 rd:admin 可打开（调用方负责按钮的权限门禁，本组件本身不重复判断）。入口固定在研发工具
// 首页"设置"分组（不再放在"变更申请单填写"里）。新增/编辑/上下架，结构照抄原"管理变更提醒"
// 弹窗的交互模式；name 是命中门禁时弹窗要展示的名称来源，必须登记。
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'changed'])

const _user     = JSON.parse(localStorage.getItem('user') || '{}')
const submitter = _user.display_name || _user.username || ''

const LEVEL_OPTS = [
  { value: 'warn',  label: '提醒' },
  { value: 'block', label: '禁止' },
]

function blankForm() { return { code: '', name: '', level: 'warn', reason: '' } }

const gates      = ref([])       // 全部记录（含下架历史）
const loading    = ref(false)
const newGate    = reactive(blankForm())
const createLoading = ref(false)
const editingId   = ref(null)
const editForm    = reactive(blankForm())
const editLoading = ref(false)

async function loadAll() {
  loading.value = true
  try {
    const res = await http.get('/api/rd/material-gates/all')
    if (res.success) gates.value = res.data
    else ElMessage.error(res.message || '加载失败')
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, (visible) => {
  if (visible) loadAll()
})

function startEdit(item) {
  editingId.value = item.id
  editForm.code   = item.code
  editForm.name   = item.name
  editForm.level  = item.level
  editForm.reason = item.reason
}
function cancelEdit() { editingId.value = null }

function validateFields(f) {
  if (!f.code.trim())   { ElMessage.warning('请填写物料编码'); return false }
  if (!f.name.trim())   { ElMessage.warning('请填写名称'); return false }
  if (!f.reason.trim()) { ElMessage.warning('请填写门禁原因'); return false }
  return true
}

async function handleCreate() {
  if (!validateFields(newGate)) return
  createLoading.value = true
  try {
    const res = await http.post('/api/rd/material-gates', {
      code:       newGate.code.trim(),
      name:       newGate.name.trim(),
      level:      newGate.level,
      reason:     newGate.reason.trim(),
      created_by: submitter,
    })
    if (res.success) {
      ElMessage.success('已创建')
      Object.assign(newGate, blankForm())
      gates.value.unshift(res.data)
      emit('changed')
    } else {
      ElMessage.error(res.message || '创建失败')
    }
  } finally {
    createLoading.value = false
  }
}

async function handleUpdate(id) {
  if (!validateFields(editForm)) return
  editLoading.value = true
  try {
    const res = await http.put(`/api/rd/material-gates/${id}`, {
      code:   editForm.code.trim(),
      name:   editForm.name.trim(),
      level:  editForm.level,
      reason: editForm.reason.trim(),
    })
    if (res.success) {
      const item = gates.value.find(g => g.id === id)
      if (item) Object.assign(item, res.data)
      editingId.value = null
      emit('changed')
      ElMessage.success('已更新')
    } else {
      ElMessage.error(res.message || '更新失败')
    }
  } finally {
    editLoading.value = false
  }
}

async function handleDeactivate(id) {
  const res = await http.put(`/api/rd/material-gates/${id}/deactivate`, {})
  if (res.success) {
    const item = gates.value.find(g => g.id === id)
    if (item) item.is_active = false
    emit('changed')
    ElMessage.success('已下架')
  } else {
    ElMessage.error(res.message || '操作失败')
  }
}

async function handleActivate(id) {
  const res = await http.put(`/api/rd/material-gates/${id}/activate`, {})
  if (res.success) {
    const item = gates.value.find(g => g.id === id)
    if (item) item.is_active = true
    emit('changed')
    ElMessage.success('已重新上架')
  } else {
    ElMessage.error(res.message || '操作失败')
  }
}

function levelLabel(level) {
  return LEVEL_OPTS.find(o => o.value === level)?.label || level
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="v => emit('update:modelValue', v)"
    title="物料门禁维护"
    width="min(720px, 94vw)"
    draggable
    :close-on-click-modal="false"
    class="gate-mgmt-dialog"
  >
    <!-- 新建表单 -->
    <div class="mgmt-create-form">
      <div class="mgmt-create-title">新增门禁</div>
      <div class="mgmt-create-row">
        <el-input v-model="newGate.code" placeholder="物料编码（必填）" maxlength="64" style="flex:1" />
        <el-select v-model="newGate.level" style="width:110px">
          <el-option v-for="o in LEVEL_OPTS" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </div>
      <el-input
        v-model="newGate.name"
        placeholder="名称（必填，命中时展示）"
        maxlength="200"
        style="margin-top:8px"
      />
      <el-input
        v-model="newGate.reason"
        type="textarea"
        :rows="2"
        placeholder="门禁原因（必填，命中时会展示给用户）"
        style="margin-top:8px"
        maxlength="500"
        show-word-limit
      />
      <div style="text-align:right;margin-top:8px">
        <el-button type="primary" size="small" :loading="createLoading" @click="handleCreate">
          发布门禁
        </el-button>
      </div>
    </div>

    <el-divider />

    <div v-if="loading" style="text-align:center;padding:20px;color:var(--text-muted)">加载中…</div>
    <div v-else-if="!gates.length" style="text-align:center;padding:20px;color:var(--text-muted)">暂无记录</div>
    <div v-else class="mgmt-list">
      <div
        v-for="item in gates"
        :key="item.id"
        class="mgmt-item"
        :class="{ 'mgmt-item--inactive': !item.is_active, 'mgmt-item--block': item.level === 'block' && item.is_active }"
      >
        <template v-if="editingId === item.id">
          <div class="mgmt-item-main">
            <div class="mgmt-create-row">
              <el-input v-model="editForm.code" placeholder="物料编码" maxlength="64" style="flex:1" />
              <el-select v-model="editForm.level" style="width:110px">
                <el-option v-for="o in LEVEL_OPTS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </div>
            <el-input v-model="editForm.name" placeholder="名称" maxlength="200" style="margin-top:6px" />
            <el-input v-model="editForm.reason" type="textarea" :rows="2" placeholder="门禁原因" style="margin-top:6px" maxlength="500" show-word-limit />
          </div>
          <div class="mgmt-item-actions">
            <el-button size="small" type="primary" :loading="editLoading" @click="handleUpdate(item.id)">保存</el-button>
            <el-button size="small" @click="cancelEdit">取消</el-button>
          </div>
        </template>
        <template v-else>
          <div class="mgmt-item-main">
            <div class="mgmt-item-content">
              <span class="mgmt-item-code">{{ item.code }}</span>
              <span class="mgmt-item-name">{{ item.name }}</span>
              <el-tag size="small" :type="item.level === 'block' ? 'danger' : 'warning'">{{ levelLabel(item.level) }}</el-tag>
            </div>
            <div class="mgmt-item-notes">{{ item.reason }}</div>
            <div class="mgmt-item-meta">
              {{ item.created_at }}
              <template v-if="item.created_by"> · {{ item.created_by }}</template>
              <el-tag v-if="!item.is_active" size="small" type="info" style="margin-left:8px">已下架</el-tag>
            </div>
          </div>
          <div class="mgmt-item-actions">
            <el-button size="small" @click="startEdit(item)">编辑</el-button>
            <el-button v-if="item.is_active" size="small" type="danger" plain @click="handleDeactivate(item.id)">下架</el-button>
            <el-button v-else size="small" @click="handleActivate(item.id)">重新上架</el-button>
          </div>
        </template>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.mgmt-create-form { padding: 4px 0 0; }
.mgmt-create-title { font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 8px; }
.mgmt-create-row { display: flex; gap: 8px; }

.mgmt-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
}
.mgmt-list::-webkit-scrollbar       { width: 4px; }
.mgmt-list::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.15); border-radius: 2px; }
.mgmt-list::-webkit-scrollbar-track { background: transparent; }

.mgmt-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 14px;
  background: #fff;
  border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: 8px;
  transition: opacity 0.15s;
}
.mgmt-item--block   { border-left-color: #c0402a; }
.mgmt-item--inactive { opacity: 0.5; border-left-color: #bbb; }
.mgmt-item-main    { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.mgmt-item-content { font-size: 13px; font-weight: 600; color: var(--text-primary); word-break: break-word; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.mgmt-item-code    { font-family: monospace; }
.mgmt-item-name    { font-weight: 400; color: var(--text-muted); }
.mgmt-item-notes   { font-size: 12px; color: var(--text-muted); word-break: break-word; white-space: pre-wrap; }
.mgmt-item-meta    { font-size: 11px; color: #a09080; margin-top: 2px; display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.mgmt-item-actions { flex-shrink: 0; display: flex; flex-direction: column; gap: 6px; align-items: flex-end; }
</style>
