<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit, Delete, Check, Close } from '@element-plus/icons-vue'
import http from '@/api/http.js'

// ── Props / Emits ─────────────────────────────────
const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'updated'])

// ── 响应式状态 ────────────────────────────────────
const loading      = ref(false)
const submitting   = ref(false)

// 一级分类列表
const categories   = ref([])
// 选中的一级分类 id
const activeCatId  = ref(null)
// 各分类下的二级原因 [{category_id, category_name, reasons:[]}]
const groups       = ref([])

// 分类内联编辑：{id: editingName}，null 表示新建
const editingCat   = ref(null)     // null | { id: number|null, name: string }

// 原因表单
const reasonForm   = ref(null)     // null = 隐藏；{id?, name, keywords, sort_order, category_id}
const reasonError  = ref('')
const kwInput      = ref('')

// 是否显示弹窗
const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// 当前分类下的原因
const currentReasons = computed(() => {
  const g = groups.value.find(g => g.category_id === activeCatId.value)
  return g ? g.reasons : []
})

// ── Watch ─────────────────────────────────────────
watch(visible, (v) => {
  if (v) {
    loadAll()
    editingCat.value  = null
    reasonForm.value  = null
  }
})

// ── 方法 ──────────────────────────────────────────

// 同时加载分类列表和原因分组
async function loadAll() {
  loading.value = true
  try {
    const [catRes, reasonRes] = await Promise.all([
      http.get('/api/aftersale/reason-categories'),
      http.get('/api/aftersale/reasons'),
    ])
    if (catRes.success)    categories.value = catRes.data
    if (reasonRes.success) groups.value     = reasonRes.data

    // 默认选第一个分类
    if (activeCatId.value === null && categories.value.length > 0) {
      activeCatId.value = categories.value[0].id
    }
  } finally {
    loading.value = false
  }
}

// ── 一级分类操作 ───────────────────────────────────

// 开始新建分类
function startNewCategory() {
  editingCat.value  = { id: null, name: '' }
  reasonForm.value  = null
}

// 开始编辑分类名
function startEditCategory(cat) {
  editingCat.value = { id: cat.id, name: cat.name }
  reasonForm.value = null
}

// 取消分类编辑
function cancelEditCategory() {
  editingCat.value = null
}

// 提交分类（创建或更新）
async function submitCategory() {
  const name = (editingCat.value?.name || '').trim()
  if (!name) { ElMessage.warning('分类名称不能为空'); return }

  submitting.value = true
  try {
    const isNew = editingCat.value.id === null
    const res = isNew
      ? await http.post('/api/aftersale/reason-categories', { name })
      : await http.put(`/api/aftersale/reason-categories/${editingCat.value.id}`, { name })

    if (res.success) {
      ElMessage.success(isNew ? '分类已创建' : '分类已更新')
      editingCat.value = null
      await loadAll()
      // 新建时自动跳到新分类
      if (isNew && res.data?.id) activeCatId.value = res.data.id
      emit('updated')
    } else {
      ElMessage.error(res.message || '操作失败')
    }
  } finally {
    submitting.value = false
  }
}

// 删除分类（检查是否有原因）
async function deleteCategory(cat) {
  const count = groups.value.find(g => g.category_id === cat.id)?.reasons?.length || 0
  const msg = count > 0
    ? `分类「${cat.name}」下还有 ${count} 个原因，请先删除或移走这些原因`
    : `确认删除分类「${cat.name}」？`

  if (count > 0) {
    ElMessage.warning(msg)
    return
  }

  try {
    await ElMessageBox.confirm(msg, '删除分类', {
      confirmButtonText: '删除',
      cancelButtonText:  '取消',
      type:              'warning',
    })
  } catch { return }

  const res = await http.delete(`/api/aftersale/reason-categories/${cat.id}`)
  if (res.success) {
    ElMessage.success('已删除')
    if (activeCatId.value === cat.id) activeCatId.value = categories.value[0]?.id ?? null
    await loadAll()
    emit('updated')
  } else {
    ElMessage.error(res.message || '删除失败')
  }
}

// ── 二级原因操作 ───────────────────────────────────

// 打开新建原因表单（预填当前分类）
function startNewReason() {
  editingCat.value = null
  reasonForm.value = {
    id:          null,
    name:        '',
    keywords:    '',
    sort_order:  0,
    category_id: activeCatId.value,
  }
  reasonError.value = ''
  kwInput.value     = ''
}

// 打开编辑原因表单
function startEditReason(reason) {
  editingCat.value = null
  reasonForm.value = {
    id:          reason.id,
    name:        reason.name,
    keywords:    reason.keywords || '',
    sort_order:  reason.sort_order || 0,
    category_id: reason.category_id ?? activeCatId.value,
  }
  reasonError.value = ''
  kwInput.value     = ''
}

// 取消原因表单
function cancelReason() {
  reasonForm.value = null
}

// 提交原因
async function submitReason() {
  reasonError.value = ''
  const name = (reasonForm.value?.name || '').trim()
  if (!name) { reasonError.value = '名称不能为空'; return }

  submitting.value = true
  try {
    const payload = {
      name,
      category_id: reasonForm.value.category_id ?? null,
      keywords:    reasonForm.value.keywords || '',
      sort_order:  Number(reasonForm.value.sort_order) || 0,
    }
    const isNew = reasonForm.value.id === null
    const res = isNew
      ? await http.post('/api/aftersale/reasons', payload)
      : await http.put(`/api/aftersale/reasons/${reasonForm.value.id}`, payload)

    if (res.success) {
      ElMessage.success(isNew ? '原因已创建' : '原因已更新')
      reasonForm.value = null
      await loadAll()
      emit('updated')
    } else {
      reasonError.value = res.message || '操作失败'
    }
  } finally {
    submitting.value = false
  }
}

// 删除原因
async function deleteReason(reason) {
  const usageRes = await http.get(`/api/aftersale/reasons/${reason.id}/usage`)
  const usage    = usageRes.success ? usageRes.data.usage_count : 0

  const msg = usage > 0
    ? `该原因已被 ${usage} 条记录引用，删除后历史记录中的名称将保留，是否继续？`
    : `确认删除原因「${reason.name}」？`

  try {
    await ElMessageBox.confirm(msg, '删除原因', {
      confirmButtonText: '删除',
      cancelButtonText:  '取消',
      type:              'warning',
    })
  } catch { return }

  const res = await http.delete(`/api/aftersale/reasons/${reason.id}`)
  if (res.success) {
    ElMessage.success('已删除')
    await loadAll()
    emit('updated')
    if (reasonForm.value?.id === reason.id) reasonForm.value = null
  } else {
    ElMessage.error(res.message || '删除失败')
  }
}

// ── 关键词 tag 工具 ────────────────────────────────

// 将关键词字符串转为数组
function kws(str) {
  return (str || '').split(',').map(s => s.trim()).filter(Boolean)
}

function addKeyword(keyword) {
  const kw = (keyword || '').trim()
  if (!kw || !reasonForm.value) return
  const existing = kws(reasonForm.value.keywords)
  if (!existing.includes(kw)) {
    reasonForm.value.keywords = [...existing, kw].join(',')
  }
}

function removeKeyword(idx) {
  if (!reasonForm.value) return
  const list = kws(reasonForm.value.keywords)
  list.splice(idx, 1)
  reasonForm.value.keywords = list.join(',')
}

function onKwConfirm() {
  addKeyword(kwInput.value)
  kwInput.value = ''
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="原因库管理"
    width="740px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <div v-loading="loading" class="reason-lib">

      <!-- ── 左列：一级分类 ──────────────────────── -->
      <div class="col-cats">
        <div class="col-header">
          <span class="col-title">一级分类</span>
          <button class="btn-add" title="新建分类" @click="startNewCategory">＋</button>
        </div>

        <!-- 新建分类内联表单 -->
        <div v-if="editingCat && editingCat.id === null" class="cat-inline-form">
          <el-input
            v-model="editingCat.name"
            size="small"
            placeholder="分类名称"
            autofocus
            @keyup.enter="submitCategory"
            @keyup.escape="cancelEditCategory"
          />
          <button class="btn-inline-ok" title="确认" :disabled="submitting" @click="submitCategory">
            <el-icon><Check /></el-icon>
          </button>
          <button class="btn-inline-cancel" title="取消" @click="cancelEditCategory">
            <el-icon><Close /></el-icon>
          </button>
        </div>

        <!-- 分类列表 -->
        <div class="cat-list">
          <div
            v-for="cat in categories"
            :key="cat.id"
            class="cat-item"
            :class="{ active: activeCatId === cat.id }"
            @click="activeCatId = cat.id; reasonForm = null; editingCat = null"
          >
            <!-- 内联改名模式 -->
            <template v-if="editingCat && editingCat.id === cat.id">
              <el-input
                v-model="editingCat.name"
                size="small"
                style="flex:1"
                autofocus
                @click.stop
                @keyup.enter="submitCategory"
                @keyup.escape="cancelEditCategory"
              />
              <button class="btn-inline-ok" title="确认" :disabled="submitting" @click.stop="submitCategory">
                <el-icon><Check /></el-icon>
              </button>
              <button class="btn-inline-cancel" title="取消" @click.stop="cancelEditCategory">
                <el-icon><Close /></el-icon>
              </button>
            </template>

            <!-- 正常显示模式 -->
            <template v-else>
              <span class="cat-name">{{ cat.name }}</span>
              <span class="cat-count">
                {{ groups.find(g => g.category_id === cat.id)?.reasons?.length || 0 }}
              </span>
              <div class="cat-actions">
                <button class="btn-tiny" title="重命名" @click.stop="startEditCategory(cat)">
                  <el-icon><Edit /></el-icon>
                </button>
                <button class="btn-tiny btn-del" title="删除" @click.stop="deleteCategory(cat)">
                  <el-icon><Delete /></el-icon>
                </button>
              </div>
            </template>
          </div>

          <div v-if="categories.length === 0" class="col-empty">暂无分类</div>
        </div>
      </div>

      <div class="col-divider"></div>

      <!-- ── 中列：二级原因列表 ─────────────────── -->
      <div class="col-reasons">
        <div class="col-header">
          <span class="col-title">
            {{ categories.find(c => c.id === activeCatId)?.name || '二级原因' }}
          </span>
          <button
            v-if="activeCatId !== null"
            class="btn-add"
            title="新建原因"
            @click="startNewReason"
          >＋</button>
        </div>

        <div class="reason-list">
          <div
            v-for="r in currentReasons"
            :key="r.id"
            class="reason-item"
            :class="{ editing: reasonForm?.id === r.id }"
          >
            <div class="reason-item-left">
              <span class="reason-name">{{ r.name }}</span>
              <span v-if="r.use_count > 0" class="use-count">已用 {{ r.use_count }} 次</span>
            </div>
            <div class="reason-item-actions">
              <button class="btn-tiny" title="编辑" @click="startEditReason(r)">
                <el-icon><Edit /></el-icon>
              </button>
              <button class="btn-tiny btn-del" title="删除" @click="deleteReason(r)">
                <el-icon><Delete /></el-icon>
              </button>
            </div>
          </div>
          <div v-if="currentReasons.length === 0 && activeCatId !== null" class="col-empty">
            该分类暂无原因，点击右上角「＋」添加
          </div>
          <div v-if="activeCatId === null" class="col-empty">请先选择一级分类</div>
        </div>
      </div>

      <div class="col-divider"></div>

      <!-- ── 右列：原因表单 ─────────────────────── -->
      <div class="col-form">
        <template v-if="reasonForm">
          <div class="col-header">
            <span class="col-title">{{ reasonForm.id ? '编辑原因' : '新建原因' }}</span>
          </div>

          <div class="form-row">
            <label class="form-label">名称 <span class="required">*</span></label>
            <el-input
              v-model="reasonForm.name"
              placeholder="原因名称"
              @keyup.enter="submitReason"
            />
          </div>

          <div class="form-row">
            <label class="form-label">所属分类</label>
            <el-select
              v-model="reasonForm.category_id"
              placeholder="选择一级分类"
              clearable
              style="width:100%"
            >
              <el-option
                v-for="cat in categories"
                :key="cat.id"
                :value="cat.id"
                :label="cat.name"
              />
            </el-select>
          </div>

          <div class="form-row">
            <label class="form-label">关键词</label>
            <div class="kw-editor">
              <div class="kw-tags">
                <el-tag
                  v-for="(kw, i) in kws(reasonForm.keywords)"
                  :key="i"
                  closable
                  size="small"
                  @close="removeKeyword(i)"
                >{{ kw }}</el-tag>
              </div>
              <el-input
                v-model="kwInput"
                size="small"
                placeholder="输入关键词回车添加"
                style="margin-top:6px"
                @keyup.enter="onKwConfirm"
              />
              <div class="kw-hint">用于自动匹配 seller_remark</div>
            </div>
          </div>

          <div class="form-row">
            <label class="form-label">排序</label>
            <el-input-number
              v-model="reasonForm.sort_order"
              :min="0"
              :step="1"
              controls-position="right"
              style="width:100px"
            />
          </div>

          <div v-if="reasonError" class="form-error">{{ reasonError }}</div>

          <div class="form-actions">
            <el-button size="small" @click="cancelReason">取消</el-button>
            <el-button size="small" type="primary" :loading="submitting" @click="submitReason">
              {{ reasonForm.id ? '保存' : '创建' }}
            </el-button>
          </div>
        </template>

        <div v-else class="form-placeholder">
          <div class="placeholder-icon">📋</div>
          <div>点击「＋」新建，或点击原因右侧编辑按钮</div>
        </div>
      </div>

    </div>
  </el-dialog>
</template>

<style scoped>
.reason-lib {
  display: flex;
  height: 440px;
  gap: 0;
}

/* 通用列标题 */
.col-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px; flex-shrink: 0;
}
.col-title {
  font-size: 12px; font-weight: 600; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.05em;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.btn-add {
  width: 22px; height: 22px; border-radius: 5px;
  border: 1px dashed var(--border); background: transparent;
  color: var(--text-muted); cursor: pointer; font-size: 14px;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s; flex-shrink: 0;
}
.btn-add:hover { border-color: var(--accent); color: var(--accent); }

.col-empty {
  font-size: 12px; color: var(--text-muted);
  padding: 16px 0; text-align: center;
}

/* 分隔线 */
.col-divider {
  width: 1px; background: var(--border);
  margin: 0 14px; flex-shrink: 0;
}

/* ── 一级分类列 ────────────────────────────────── */
.col-cats {
  width: 180px; flex-shrink: 0;
  display: flex; flex-direction: column;
  overflow: hidden;
}

.cat-inline-form {
  display: flex; align-items: center; gap: 4px;
  margin-bottom: 6px;
}
.btn-inline-ok, .btn-inline-cancel {
  width: 22px; height: 22px; border-radius: 4px;
  border: 1px solid var(--border); background: transparent;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.15s; flex-shrink: 0;
  color: var(--text-muted);
}
.btn-inline-ok:hover   { border-color: var(--accent); color: var(--accent); }
.btn-inline-cancel:hover { border-color: #f0c0c0; color: #d05a3c; }

.cat-list {
  flex: 1; overflow-y: auto;
}
.cat-list::-webkit-scrollbar { width: 4px; }
.cat-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.cat-item {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 8px; border-radius: 6px;
  cursor: pointer; transition: background 0.15s;
  min-height: 34px;
}
.cat-item:hover { background: var(--bg); }
.cat-item.active { background: #fff7ed; }
.cat-item.active .cat-name { color: var(--accent); font-weight: 600; }

.cat-name {
  flex: 1; font-size: 13px; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cat-count {
  font-size: 10px; color: var(--text-muted);
  background: var(--border); border-radius: 8px;
  padding: 0 5px; flex-shrink: 0;
}
.cat-actions {
  display: none; gap: 2px; flex-shrink: 0;
}
.cat-item:hover .cat-actions { display: flex; }

/* ── 二级原因列 ────────────────────────────────── */
.col-reasons {
  width: 200px; flex-shrink: 0;
  display: flex; flex-direction: column;
  overflow: hidden;
}

.reason-list {
  flex: 1; overflow-y: auto;
}
.reason-list::-webkit-scrollbar { width: 4px; }
.reason-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.reason-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 7px 6px; border-radius: 6px;
  transition: background 0.15s;
}
.reason-item:hover { background: var(--bg); }
.reason-item.editing { background: #fff7ed; }

.reason-item-left {
  display: flex; flex-direction: column; gap: 1px;
  overflow: hidden; flex: 1;
}
.reason-name {
  font-size: 13px; color: var(--text-primary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.use-count {
  font-size: 10px; color: var(--text-muted);
}
.reason-item-actions {
  display: none; gap: 2px; flex-shrink: 0;
}
.reason-item:hover .reason-item-actions { display: flex; }

/* 通用小按钮 */
.btn-tiny {
  width: 22px; height: 22px; border-radius: 4px;
  border: 1px solid var(--border); background: transparent;
  color: var(--text-muted); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.btn-tiny:hover { background: var(--bg-card); color: var(--text-primary); }
.btn-del:hover  { border-color: #f0c0c0; color: #d05a3c; background: #fff0ee; }

/* ── 右列：原因表单 ────────────────────────────── */
.col-form {
  flex: 1; overflow-y: auto; min-width: 0;
}
.col-form::-webkit-scrollbar { width: 4px; }
.col-form::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.form-row {
  margin-bottom: 14px;
}
.form-label {
  display: block; font-size: 12px; color: var(--text-secondary);
  margin-bottom: 5px;
}
.required { color: #d05a3c; }

.kw-editor {
  background: #faf7f2; border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px;
}
.kw-tags {
  display: flex; flex-wrap: wrap; gap: 4px; min-height: 24px;
}
.kw-hint {
  font-size: 10px; color: var(--text-muted); margin-top: 4px;
}

.form-error {
  color: #d05a3c; font-size: 12px; margin-bottom: 10px;
}
.form-actions {
  display: flex; justify-content: flex-end; gap: 8px;
  padding-top: 4px;
}

.form-placeholder {
  height: 100%; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 8px; color: var(--text-muted); font-size: 12px;
  text-align: center; padding: 20px;
}
.placeholder-icon { font-size: 28px; opacity: 0.4; }
</style>
