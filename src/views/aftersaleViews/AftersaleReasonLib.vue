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

// 当前激活的 Tab
const activeTab = ref('reasons')

// ── 售后原因库状态 ─────────────────────────────────
const categories   = ref([])
const activeCatId  = ref(null)
const groups       = ref([])
const editingCat   = ref(null)   // null | { id: number|null, name: string }
const reasonForm   = ref(null)   // null | {id?, name, keywords, sort_order, category_id}
const reasonError  = ref('')
const kwInput      = ref('')

// ── 发货物料简称库状态 ─────────────────────────────
const shippingAliases = ref([])
const editingShipping = ref(null)   // null | { id: number|null, name: string, sort_order: number }
const shippingError   = ref('')

// ── 售后物料简称库状态 ─────────────────────────────
const returnAliases   = ref([])
const editingReturn   = ref(null)   // null | { id: number|null, name: string, sort_order: number }
const returnError     = ref('')

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
    editingCat.value     = null
    reasonForm.value     = null
    editingShipping.value = null
    editingReturn.value  = null
  }
})

// ── 加载方法 ──────────────────────────────────────

async function loadAll() {
  loading.value = true
  try {
    const [catRes, reasonRes, shipRes, retRes] = await Promise.all([
      http.get('/api/aftersale/reason-categories'),
      http.get('/api/aftersale/reasons'),
      http.get('/api/aftersale/shipping-aliases'),
      http.get('/api/aftersale/return-aliases'),
    ])
    if (catRes.success)    categories.value    = catRes.data
    if (reasonRes.success) groups.value        = reasonRes.data
    if (shipRes.success)   shippingAliases.value = shipRes.data
    if (retRes.success)    returnAliases.value   = retRes.data

    if (activeCatId.value === null && categories.value.length > 0) {
      activeCatId.value = categories.value[0].id
    }
  } finally {
    loading.value = false
  }
}

// ── 一级分类操作 ───────────────────────────────────

function startNewCategory() {
  editingCat.value  = { id: null, name: '' }
  reasonForm.value  = null
}

function startEditCategory(cat) {
  editingCat.value = { id: cat.id, name: cat.name }
  reasonForm.value = null
}

function cancelEditCategory() {
  editingCat.value = null
}

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
      if (isNew && res.data?.id) activeCatId.value = res.data.id
      emit('updated')
    } else {
      ElMessage.error(res.message || '操作失败')
    }
  } finally {
    submitting.value = false
  }
}

async function deleteCategory(cat) {
  const count = groups.value.find(g => g.category_id === cat.id)?.reasons?.length || 0
  if (count > 0) {
    ElMessage.warning(`分类「${cat.name}」下还有 ${count} 个原因，请先删除或移走这些原因`)
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除分类「${cat.name}」？`, '删除分类', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
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

function startNewReason() {
  editingCat.value = null
  reasonForm.value = {
    id: null, name: '', keywords: '', sort_order: 0,
    category_id: activeCatId.value,
  }
  reasonError.value = ''
  kwInput.value     = ''
}

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

function cancelReason() {
  reasonForm.value = null
}

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

async function deleteReason(reason) {
  const usageRes = await http.get(`/api/aftersale/reasons/${reason.id}/usage`)
  const usage    = usageRes.success ? usageRes.data.usage_count : 0
  const msg = usage > 0
    ? `该原因已被 ${usage} 条记录引用，删除后历史记录中的名称将保留，是否继续？`
    : `确认删除原因「${reason.name}」？`

  try {
    await ElMessageBox.confirm(msg, '删除原因', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
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

// ── 发货物料简称操作 ───────────────────────────────

function startNewShipping() {
  editingShipping.value = { id: null, name: '', sort_order: 0 }
  shippingError.value   = ''
}

function startEditShipping(item) {
  editingShipping.value = { id: item.id, name: item.name, sort_order: item.sort_order || 0 }
  shippingError.value   = ''
}

function cancelShipping() {
  editingShipping.value = null
}

async function submitShipping() {
  shippingError.value = ''
  const name = (editingShipping.value?.name || '').trim()
  if (!name) { shippingError.value = '简称不能为空'; return }

  submitting.value = true
  try {
    const payload = { name, sort_order: Number(editingShipping.value.sort_order) || 0 }
    const isNew = editingShipping.value.id === null
    const res = isNew
      ? await http.post('/api/aftersale/shipping-aliases', payload)
      : await http.put(`/api/aftersale/shipping-aliases/${editingShipping.value.id}`, payload)

    if (res.success) {
      ElMessage.success(isNew ? '简称已创建' : '简称已更新')
      editingShipping.value = null
      await loadAll()
      emit('updated')
    } else {
      shippingError.value = res.message || '操作失败'
    }
  } finally {
    submitting.value = false
  }
}

async function deleteShipping(item) {
  try {
    await ElMessageBox.confirm(`确认删除「${item.name}」？`, '删除简称', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }

  const res = await http.delete(`/api/aftersale/shipping-aliases/${item.id}`)
  if (res.success) {
    ElMessage.success('已删除')
    if (editingShipping.value?.id === item.id) editingShipping.value = null
    await loadAll()
    emit('updated')
  } else {
    ElMessage.error(res.message || '删除失败')
  }
}

// ── 售后物料简称操作 ───────────────────────────────

function startNewReturn() {
  editingReturn.value = { id: null, name: '', sort_order: 0 }
  returnError.value   = ''
}

function startEditReturn(item) {
  editingReturn.value = { id: item.id, name: item.name, sort_order: item.sort_order || 0 }
  returnError.value   = ''
}

function cancelReturn() {
  editingReturn.value = null
}

async function submitReturn() {
  returnError.value = ''
  const name = (editingReturn.value?.name || '').trim()
  if (!name) { returnError.value = '简称不能为空'; return }

  submitting.value = true
  try {
    const payload = { name, sort_order: Number(editingReturn.value.sort_order) || 0 }
    const isNew = editingReturn.value.id === null
    const res = isNew
      ? await http.post('/api/aftersale/return-aliases', payload)
      : await http.put(`/api/aftersale/return-aliases/${editingReturn.value.id}`, payload)

    if (res.success) {
      ElMessage.success(isNew ? '简称已创建' : '简称已更新')
      editingReturn.value = null
      await loadAll()
      emit('updated')
    } else {
      returnError.value = res.message || '操作失败'
    }
  } finally {
    submitting.value = false
  }
}

async function deleteReturn(item) {
  try {
    await ElMessageBox.confirm(`确认删除「${item.name}」？`, '删除简称', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }

  const res = await http.delete(`/api/aftersale/return-aliases/${item.id}`)
  if (res.success) {
    ElMessage.success('已删除')
    if (editingReturn.value?.id === item.id) editingReturn.value = null
    await loadAll()
    emit('updated')
  } else {
    ElMessage.error(res.message || '删除失败')
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="原因库 & 简称库管理"
    width="780px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <div v-loading="loading" class="lib-wrap">

      <!-- ── Tab 切换 ──────────────────────────────── -->
      <div class="lib-tabs">
        <button
          class="lib-tab"
          :class="{ active: activeTab === 'reasons' }"
          @click="activeTab = 'reasons'"
        >售后原因库</button>
        <button
          class="lib-tab"
          :class="{ active: activeTab === 'shipping' }"
          @click="activeTab = 'shipping'"
        >发货物料简称</button>
        <button
          class="lib-tab"
          :class="{ active: activeTab === 'return' }"
          @click="activeTab = 'return'"
        >售后物料简称</button>
      </div>

      <!-- ── 售后原因库 Tab ─────────────────────────── -->
      <div v-if="activeTab === 'reasons'" class="reason-lib">

        <!-- 左列：一级分类 -->
        <div class="col-cats">
          <div class="col-header">
            <span class="col-title">一级分类</span>
            <button class="btn-add" title="新建分类" @click="startNewCategory">＋</button>
          </div>

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

          <div class="cat-list">
            <div
              v-for="cat in categories"
              :key="cat.id"
              class="cat-item"
              :class="{ active: activeCatId === cat.id }"
              @click="activeCatId = cat.id; reasonForm = null; editingCat = null"
            >
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

        <!-- 中列：二级原因列表 -->
        <div class="col-reasons">
          <div class="col-header">
            <span class="col-title">
              {{ categories.find(c => c.id === activeCatId)?.name || '二级原因' }}
            </span>
            <button v-if="activeCatId !== null" class="btn-add" title="新建原因" @click="startNewReason">＋</button>
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

        <!-- 右列：原因表单 -->
        <div class="col-form">
          <template v-if="reasonForm">
            <div class="col-header">
              <span class="col-title">{{ reasonForm.id ? '编辑原因' : '新建原因' }}</span>
            </div>

            <div class="form-row">
              <label class="form-label">名称 <span class="required">*</span></label>
              <el-input v-model="reasonForm.name" placeholder="原因名称" @keyup.enter="submitReason" />
            </div>

            <div class="form-row">
              <label class="form-label">所属分类</label>
              <el-select v-model="reasonForm.category_id" placeholder="选择一级分类" clearable style="width:100%">
                <el-option v-for="cat in categories" :key="cat.id" :value="cat.id" :label="cat.name" />
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
                :min="0" :step="1"
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

      <!-- ── 发货物料简称库 Tab ───────────────────── -->
      <div v-if="activeTab === 'shipping'" class="alias-lib">

        <!-- 左列：简称列表 -->
        <div class="alias-list-col">
          <div class="col-header">
            <span class="col-title">发货物料简称（{{ shippingAliases.length }}）</span>
            <button class="btn-add" title="新建简称" @click="startNewShipping">＋</button>
          </div>

          <div class="alias-list">
            <div
              v-for="item in shippingAliases"
              :key="item.id"
              class="alias-item"
              :class="{ editing: editingShipping?.id === item.id }"
            >
              <span class="alias-name">{{ item.name }}</span>
              <div class="alias-actions">
                <button class="btn-tiny" title="编辑" @click="startEditShipping(item)">
                  <el-icon><Edit /></el-icon>
                </button>
                <button class="btn-tiny btn-del" title="删除" @click="deleteShipping(item)">
                  <el-icon><Delete /></el-icon>
                </button>
              </div>
            </div>
            <div v-if="shippingAliases.length === 0" class="col-empty">
              暂无简称，点击右上角「＋」添加
            </div>
          </div>
        </div>

        <div class="col-divider"></div>

        <!-- 右列：编辑表单 -->
        <div class="alias-form-col">
          <template v-if="editingShipping">
            <div class="col-header">
              <span class="col-title">{{ editingShipping.id ? '编辑简称' : '新建简称' }}</span>
            </div>

            <div class="form-row">
              <label class="form-label">简称名称 <span class="required">*</span></label>
              <el-input
                v-model="editingShipping.name"
                placeholder="如：拉链头套件"
                @keyup.enter="submitShipping"
              />
            </div>

            <div class="form-row">
              <label class="form-label">排序</label>
              <el-input-number
                v-model="editingShipping.sort_order"
                :min="0" :step="1"
                controls-position="right"
                style="width:100px"
              />
            </div>

            <div v-if="shippingError" class="form-error">{{ shippingError }}</div>

            <div class="form-actions">
              <el-button size="small" @click="cancelShipping">取消</el-button>
              <el-button size="small" type="primary" :loading="submitting" @click="submitShipping">
                {{ editingShipping.id ? '保存' : '创建' }}
              </el-button>
            </div>
          </template>

          <div v-else class="form-placeholder">
            <div class="placeholder-icon">🚚</div>
            <div>点击「＋」新建，或点击列表中的编辑按钮</div>
            <div class="placeholder-hint">这里维护发货物料的规范简称，在处理售后工单时可下拉选择</div>
          </div>
        </div>
      </div>

      <!-- ── 售后物料简称库 Tab ───────────────────── -->
      <div v-if="activeTab === 'return'" class="alias-lib">

        <!-- 左列：简称列表 -->
        <div class="alias-list-col">
          <div class="col-header">
            <span class="col-title">售后物料简称（{{ returnAliases.length }}）</span>
            <button class="btn-add" title="新建简称" @click="startNewReturn">＋</button>
          </div>

          <div class="alias-list">
            <div
              v-for="item in returnAliases"
              :key="item.id"
              class="alias-item"
              :class="{ editing: editingReturn?.id === item.id }"
            >
              <span class="alias-name">{{ item.name }}</span>
              <div class="alias-actions">
                <button class="btn-tiny" title="编辑" @click="startEditReturn(item)">
                  <el-icon><Edit /></el-icon>
                </button>
                <button class="btn-tiny btn-del" title="删除" @click="deleteReturn(item)">
                  <el-icon><Delete /></el-icon>
                </button>
              </div>
            </div>
            <div v-if="returnAliases.length === 0" class="col-empty">
              暂无简称，点击右上角「＋」添加
            </div>
          </div>
        </div>

        <div class="col-divider"></div>

        <!-- 右列：编辑表单 -->
        <div class="alias-form-col">
          <template v-if="editingReturn">
            <div class="col-header">
              <span class="col-title">{{ editingReturn.id ? '编辑简称' : '新建简称' }}</span>
            </div>

            <div class="form-row">
              <label class="form-label">简称名称 <span class="required">*</span></label>
              <el-input
                v-model="editingReturn.name"
                placeholder="如：拉链头"
                @keyup.enter="submitReturn"
              />
            </div>

            <div class="form-row">
              <label class="form-label">排序</label>
              <el-input-number
                v-model="editingReturn.sort_order"
                :min="0" :step="1"
                controls-position="right"
                style="width:100px"
              />
            </div>

            <div v-if="returnError" class="form-error">{{ returnError }}</div>

            <div class="form-actions">
              <el-button size="small" @click="cancelReturn">取消</el-button>
              <el-button size="small" type="primary" :loading="submitting" @click="submitReturn">
                {{ editingReturn.id ? '保存' : '创建' }}
              </el-button>
            </div>
          </template>

          <div v-else class="form-placeholder">
            <div class="placeholder-icon">🔧</div>
            <div>点击「＋」新建，或点击列表中的编辑按钮</div>
            <div class="placeholder-hint">这里维护出现问题的物料规范简称，在处理售后工单时可下拉选择</div>
          </div>
        </div>
      </div>

    </div>
  </el-dialog>
</template>

<style scoped>
.lib-wrap {
  display: flex;
  flex-direction: column;
  height: 500px;
}

/* ── Tab 切换 ────────────────────────────────────── */
.lib-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0;
  flex-shrink: 0;
}
.lib-tab {
  padding: 6px 16px;
  border: none;
  background: transparent;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: all 0.15s;
  border-radius: 0;
}
.lib-tab:hover { color: var(--text-primary); }
.lib-tab.active {
  color: var(--accent);
  font-weight: 600;
  border-bottom-color: var(--accent);
}

/* ── 原因库三列布局 ─────────────────────────────── */
.reason-lib {
  display: flex;
  flex: 1;
  overflow: hidden;
  gap: 0;
}

/* ── 简称库两列布局 ─────────────────────────────── */
.alias-lib {
  display: flex;
  flex: 1;
  overflow: hidden;
  gap: 0;
}

.alias-list-col {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.alias-form-col {
  flex: 1;
  overflow-y: auto;
  min-width: 0;
}
.alias-form-col::-webkit-scrollbar { width: 4px; }
.alias-form-col::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.alias-list {
  flex: 1;
  overflow-y: auto;
}
.alias-list::-webkit-scrollbar { width: 4px; }
.alias-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.alias-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 8px;
  border-radius: 6px;
  transition: background 0.15s;
}
.alias-item:hover { background: var(--bg); }
.alias-item.editing { background: #fff7ed; }

.alias-name {
  font-size: 13px;
  color: var(--text-primary);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.alias-actions {
  display: none;
  gap: 2px;
  flex-shrink: 0;
}
.alias-item:hover .alias-actions { display: flex; }

.placeholder-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  line-height: 1.5;
}

/* ── 通用列标题 ──────────────────────────────────── */
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

.col-divider {
  width: 1px; background: var(--border);
  margin: 0 14px; flex-shrink: 0;
}

/* ── 一级分类列 ─────────────────────────────────── */
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

.cat-list { flex: 1; overflow-y: auto; }
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
.cat-actions { display: none; gap: 2px; flex-shrink: 0; }
.cat-item:hover .cat-actions { display: flex; }

/* ── 二级原因列 ─────────────────────────────────── */
.col-reasons {
  width: 200px; flex-shrink: 0;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.reason-list { flex: 1; overflow-y: auto; }
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
.use-count { font-size: 10px; color: var(--text-muted); }

.reason-item-actions { display: none; gap: 2px; flex-shrink: 0; }
.reason-item:hover .reason-item-actions { display: flex; }

/* ── 通用小按钮 ─────────────────────────────────── */
.btn-tiny {
  width: 22px; height: 22px; border-radius: 4px;
  border: 1px solid var(--border); background: transparent;
  color: var(--text-muted); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.btn-tiny:hover { background: var(--bg-card); color: var(--text-primary); }
.btn-del:hover  { border-color: #f0c0c0; color: #d05a3c; background: #fff0ee; }

/* ── 右列：表单 ─────────────────────────────────── */
.col-form {
  flex: 1; overflow-y: auto; min-width: 0;
}
.col-form::-webkit-scrollbar { width: 4px; }
.col-form::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.form-row { margin-bottom: 14px; }
.form-label {
  display: block; font-size: 12px; color: var(--text-secondary);
  margin-bottom: 5px;
}
.required { color: #d05a3c; }

.kw-editor {
  background: #faf7f2; border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px;
}
.kw-tags { display: flex; flex-wrap: wrap; gap: 4px; min-height: 24px; }
.kw-hint { font-size: 10px; color: var(--text-muted); margin-top: 4px; }

.form-error { color: #d05a3c; font-size: 12px; margin-bottom: 10px; }
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
