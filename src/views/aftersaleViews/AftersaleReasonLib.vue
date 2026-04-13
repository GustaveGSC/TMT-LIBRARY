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
const loading    = ref(false)
const submitting = ref(false)

// 当前激活的 Tab
const activeTab = ref('reasons')

// ── 售后原因库状态 ─────────────────────────────────
const categories  = ref([])
const activeCatId = ref(null)
const groups      = ref([])
const editingCat  = ref(null)   // null | { id: number|null, name: string }
const reasonForm  = ref(null)   // null | { id?, name, keywords, sort_order, category_id }
const reasonError = ref('')
const kwInput     = ref('')

// ── 发货物料简称库状态 ─────────────────────────────
const shippingAliases = ref([])
// editingShipping: { id, name, product_codes: string[], sort_order }
const editingShipping = ref(null)
const shippingError   = ref('')
const shipCodeInput   = ref('')   // 产品代码输入框
const shippingSearch  = ref('')   // 发货简称搜索词

// ── 售后物料简称库状态 ─────────────────────────────
const returnAliases  = ref([])
// editingReturn: { id, name, keywords: string[], sort_order }
const editingReturn  = ref(null)
const returnError    = ref('')
const retKwInput     = ref('')    // 商家备注片段输入框
const returnSearch   = ref('')    // 售后简称搜索词

// ── 发货物料匹配过滤词状态 ─────────────────────────
const ignoreTerms    = ref([])    // [{id, term}]
const ignoreInput    = ref('')    // 输入框
const ignoreLoading  = ref(false)
const ruleSaving     = ref(false)
const reasonRuleForm = ref({
  stopwords: [],
  fault_terms: [],
  component_terms: [],
  short_keep_terms: [],
  synonyms: [],
  newStopword: '',
  newFaultTerm: '',
  newComponentTerm: '',
  newShortKeepTerm: '',
  newSynonymAlias: '',
  newSynonymAliases: [],
  newReplacement: '',
  newIsRegex: true,
})

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

const filteredShippingAliases = computed(() => {
  const q = (shippingSearch.value || '').trim().toLowerCase()
  if (!q) return shippingAliases.value
  return shippingAliases.value.filter(item => {
    const name = (item.name || '').toLowerCase()
    const kws = (item.keywords || []).join(' ').toLowerCase()
    return name.includes(q) || kws.includes(q)
  })
})

const filteredReturnAliases = computed(() => {
  const q = (returnSearch.value || '').trim().toLowerCase()
  if (!q) return returnAliases.value
  return returnAliases.value.filter(item => {
    const name = (item.name || '').toLowerCase()
    const kws = (item.keywords || []).join(' ').toLowerCase()
    return name.includes(q) || kws.includes(q)
  })
})

// ── Watch ─────────────────────────────────────────
watch(visible, (v) => {
  if (v) {
    loadAll()
    editingCat.value          = null
    reasonForm.value          = null
    editingShipping.value     = null
    editingReturn.value       = null
    shippingSearch.value      = ''
    returnSearch.value        = ''
  }
})

// ── 加载方法 ──────────────────────────────────────
async function loadAll() {
  loading.value = true
  try {
    const [catRes, reasonRes, shipRes, retRes, ignoreRes, rulesRes] = await Promise.all([
      http.get('/api/aftersale/reason-categories'),
      http.get('/api/aftersale/reasons'),
      http.get('/api/aftersale/shipping-aliases'),
      http.get('/api/aftersale/return-aliases'),
      http.get('/api/aftersale/shipping-ignore-terms'),
      http.get('/api/aftersale/reason-keyword-rules'),
    ])
    if (catRes.success)     categories.value      = catRes.data
    if (reasonRes.success)  groups.value          = reasonRes.data
    if (shipRes.success)    shippingAliases.value  = shipRes.data
    if (retRes.success)     returnAliases.value    = retRes.data
    if (ignoreRes.success)  ignoreTerms.value      = ignoreRes.data
    if (rulesRes.success)   setReasonRuleForm(rulesRes.data)

    if (activeCatId.value === null && categories.value.length > 0) {
      activeCatId.value = categories.value[0].id
    }
  } finally {
    loading.value = false
  }
}

function setReasonRuleForm(data) {
  reasonRuleForm.value.stopwords = [...new Set((data?.stopwords || []).map(s => (s || '').trim()).filter(Boolean))]
  reasonRuleForm.value.fault_terms = [...new Set((data?.fault_terms || []).map(s => (s || '').trim()).filter(Boolean))]
  reasonRuleForm.value.component_terms = [...new Set((data?.component_terms || []).map(s => (s || '').trim()).filter(Boolean))]
  reasonRuleForm.value.short_keep_terms = [...new Set((data?.short_keep_terms || []).map(s => (s || '').trim()).filter(Boolean))]
  reasonRuleForm.value.synonyms = (data?.synonyms || [])
    .map(s => ({
      pattern: (s.pattern || '').trim(),
      replacement: (s.replacement || '').trim(),
      is_regex: s.is_regex !== false,
    }))
    .filter(s => s.pattern && s.replacement)
}

function addRuleTerm(field, inputField) {
  const term = (reasonRuleForm.value[inputField] || '').trim()
  if (!term) return
  if (!reasonRuleForm.value[field].includes(term)) {
    reasonRuleForm.value[field].push(term)
  }
  reasonRuleForm.value[inputField] = ''
}

function removeRuleTerm(field, idx) {
  reasonRuleForm.value[field].splice(idx, 1)
}

async function editRuleTerm(field, idx) {
  const current = reasonRuleForm.value[field]?.[idx] || ''
  try {
    const { value } = await ElMessageBox.prompt('', '编辑词条', {
      inputValue: current,
      inputPlaceholder: '请输入词条',
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '词条不能为空',
    })
    const next = (value || '').trim()
    if (!next) return
    reasonRuleForm.value[field].splice(idx, 1, next)
    reasonRuleForm.value[field] = [...new Set(reasonRuleForm.value[field])]
  } catch {}
}

function addSynonymRule() {
  const aliases = [...new Set(
    (reasonRuleForm.value.newSynonymAliases || [])
      .map(s => (s || '').trim())
      .filter(Boolean)
  )]
  const pattern = aliases.join('|')
  const replacement = (reasonRuleForm.value.newReplacement || '').trim()
  if (!pattern || !replacement) return
  reasonRuleForm.value.synonyms.push({
    pattern,
    replacement,
    is_regex: reasonRuleForm.value.newIsRegex,
  })
  reasonRuleForm.value.newSynonymAlias = ''
  reasonRuleForm.value.newSynonymAliases = []
  reasonRuleForm.value.newReplacement = ''
}

function removeSynonymRule(idx) {
  reasonRuleForm.value.synonyms.splice(idx, 1)
}

function addSynonymAlias() {
  const alias = (reasonRuleForm.value.newSynonymAlias || '').trim()
  if (!alias) return
  if (!reasonRuleForm.value.newSynonymAliases.includes(alias)) {
    reasonRuleForm.value.newSynonymAliases.push(alias)
  }
  reasonRuleForm.value.newSynonymAlias = ''
}

function removeSynonymAlias(idx) {
  reasonRuleForm.value.newSynonymAliases.splice(idx, 1)
}

async function editSynonymRule(idx) {
  const row = reasonRuleForm.value.synonyms[idx]
  if (!row) return
  try {
    const { value: aliasesVal } = await ElMessageBox.prompt('', '编辑同义词别名（逗号分隔）', {
      inputValue: (row.pattern || '').split('|').join(','),
      inputPlaceholder: '例如：红,粉色,浅粉',
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '别名不能为空',
    })
    const aliases = [...new Set(
      (aliasesVal || '')
        .split(',')
        .map(s => s.trim())
        .filter(Boolean)
    )]
    if (!aliases.length) return
    const { value: replacementVal } = await ElMessageBox.prompt('', '编辑归一词', {
      inputValue: row.replacement || '',
      inputPlaceholder: '例如：红色',
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '归一词不能为空',
    })
    const pattern = aliases.join('|')
    const replacement = (replacementVal || '').trim()
    if (!pattern || !replacement) return
    reasonRuleForm.value.synonyms.splice(idx, 1, { pattern, replacement, is_regex: row.is_regex !== false })
  } catch {}
}

async function saveReasonRules() {
  ruleSaving.value = true
  try {
    const payload = {
      stopwords: [...new Set(reasonRuleForm.value.stopwords.map(s => s.trim()).filter(Boolean))],
      fault_terms: [...new Set(reasonRuleForm.value.fault_terms.map(s => s.trim()).filter(Boolean))],
      component_terms: [...new Set(reasonRuleForm.value.component_terms.map(s => s.trim()).filter(Boolean))],
      short_keep_terms: [...new Set(reasonRuleForm.value.short_keep_terms.map(s => s.trim()).filter(Boolean))],
      synonyms: reasonRuleForm.value.synonyms
        .map(s => ({
          pattern: (s.pattern || '').trim(),
          replacement: (s.replacement || '').trim(),
          is_regex: s.is_regex !== false,
        }))
        .filter(s => s.pattern && s.replacement),
    }
    const res = await http.put('/api/aftersale/reason-keyword-rules', payload)
    if (res.success) {
      setReasonRuleForm(res.data)
      ElMessage.success('原因词典已保存')
      emit('updated')
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } finally {
    ruleSaving.value = false
  }
}

// ── 一级分类操作 ───────────────────────────────────

function startNewCategory() {
  editingCat.value = { id: null, name: '' }
  reasonForm.value = null
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

// ── 关键词 tag 工具（原因库关键词）────────────────────
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
  editingShipping.value = { id: null, name: '', keywords: [], sort_order: 0 }
  shippingError.value   = ''
  shipCodeInput.value   = ''
}

function startEditShipping(item) {
  editingShipping.value = {
    id:        item.id,
    name:      item.name,
    keywords:  [...(item.keywords || [])],
    sort_order: item.sort_order || 0,
  }
  shippingError.value = ''
  shipCodeInput.value = ''
}

function cancelShipping() {
  editingShipping.value = null
}

function addShipCode() {
  const kw = (shipCodeInput.value || '').trim()
  if (!kw || !editingShipping.value) return
  if (!editingShipping.value.keywords.includes(kw)) {
    editingShipping.value.keywords = [...editingShipping.value.keywords, kw]
  }
  shipCodeInput.value = ''
}

function removeShipCode(idx) {
  if (!editingShipping.value) return
  const list = [...editingShipping.value.keywords]
  list.splice(idx, 1)
  editingShipping.value.keywords = list
}

async function submitShipping() {
  shippingError.value = ''
  const name = (editingShipping.value?.name || '').trim()
  if (!name) { shippingError.value = '简称不能为空'; return }

  submitting.value = true
  try {
    const payload = {
      name,
      keywords:   editingShipping.value.keywords,
      sort_order: Number(editingShipping.value.sort_order) || 0,
    }
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
  editingReturn.value = { id: null, name: '', keywords: [], sort_order: 0 }
  returnError.value   = ''
  retKwInput.value    = ''
}

function startEditReturn(item) {
  editingReturn.value = {
    id:       item.id,
    name:     item.name,
    keywords: [...(item.keywords || [])],
    sort_order: item.sort_order || 0,
  }
  returnError.value = ''
  retKwInput.value  = ''
}

function cancelReturn() {
  editingReturn.value = null
}

function addReturnKw() {
  const kw = (retKwInput.value || '').trim()
  if (!kw || !editingReturn.value) return
  if (!editingReturn.value.keywords.includes(kw)) {
    editingReturn.value.keywords = [...editingReturn.value.keywords, kw]
  }
  retKwInput.value = ''
}

function removeReturnKw(idx) {
  if (!editingReturn.value) return
  const list = [...editingReturn.value.keywords]
  list.splice(idx, 1)
  editingReturn.value.keywords = list
}

async function submitReturn() {
  returnError.value = ''
  const name = (editingReturn.value?.name || '').trim()
  if (!name) { returnError.value = '简称不能为空'; return }

  submitting.value = true
  try {
    const payload = {
      name,
      keywords:   editingReturn.value.keywords,
      sort_order: Number(editingReturn.value.sort_order) || 0,
    }
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

// ── 过滤词操作 ────────────────────────────────────

async function addIgnoreTerm() {
  const term = (ignoreInput.value || '').trim()
  if (!term) return
  ignoreLoading.value = true
  try {
    const res = await http.post('/api/aftersale/shipping-ignore-terms', { term })
    if (res.success) {
      ignoreTerms.value.push(res.data)
      ignoreInput.value = ''
      emit('updated')
    } else {
      ElMessage.error(res.message || '添加失败')
    }
  } finally {
    ignoreLoading.value = false
  }
}

async function deleteIgnoreTerm(item) {
  const res = await http.delete(`/api/aftersale/shipping-ignore-terms/${item.id}`)
  if (res.success) {
    ignoreTerms.value = ignoreTerms.value.filter(t => t.id !== item.id)
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
    width="820px"
    draggable
    :close-on-click-modal="false"
    destroy-on-close
  >
    <div v-loading="loading" class="lib-wrap">

      <!-- ── Tab 切换 ──────────────────────────────── -->
      <div class="lib-tabs">
        <button class="lib-tab" :class="{ active: activeTab === 'reasons' }"  @click="activeTab = 'reasons'">售后原因库</button>
        <button class="lib-tab" :class="{ active: activeTab === 'shipping' }" @click="activeTab = 'shipping'">发货物料简称</button>
        <button class="lib-tab" :class="{ active: activeTab === 'return' }"   @click="activeTab = 'return'">售后物料简称</button>
        <button class="lib-tab" :class="{ active: activeTab === 'ignore' }"   @click="activeTab = 'ignore'">过滤词</button>
        <button class="lib-tab" :class="{ active: activeTab === 'reasonRules' }" @click="activeTab = 'reasonRules'">原因词典</button>
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
            <el-input v-model="editingCat.name" size="small" placeholder="分类名称" autofocus
              @keyup.enter="submitCategory" @keyup.escape="cancelEditCategory" />
            <button class="btn-inline-ok" title="确认" :disabled="submitting" @click="submitCategory">
              <el-icon><Check /></el-icon>
            </button>
            <button class="btn-inline-cancel" title="取消" @click="cancelEditCategory">
              <el-icon><Close /></el-icon>
            </button>
          </div>

          <div class="cat-list">
            <div v-for="cat in categories" :key="cat.id" class="cat-item"
              :class="{ active: activeCatId === cat.id }"
              @click="activeCatId = cat.id; reasonForm = null; editingCat = null"
            >
              <template v-if="editingCat && editingCat.id === cat.id">
                <el-input v-model="editingCat.name" size="small" style="flex:1" autofocus
                  @click.stop @keyup.enter="submitCategory" @keyup.escape="cancelEditCategory" />
                <button class="btn-inline-ok" title="确认" :disabled="submitting" @click.stop="submitCategory">
                  <el-icon><Check /></el-icon>
                </button>
                <button class="btn-inline-cancel" title="取消" @click.stop="cancelEditCategory">
                  <el-icon><Close /></el-icon>
                </button>
              </template>
              <template v-else>
                <span class="cat-name">{{ cat.name }}</span>
                <span class="cat-count">{{ groups.find(g => g.category_id === cat.id)?.reasons?.length || 0 }}</span>
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
            <span class="col-title">{{ categories.find(c => c.id === activeCatId)?.name || '二级原因' }}</span>
            <button v-if="activeCatId !== null" class="btn-add" title="新建原因" @click="startNewReason">＋</button>
          </div>

          <div class="reason-list">
            <div v-for="r in currentReasons" :key="r.id" class="reason-item"
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
              <label class="form-label">关键词
                <span class="form-label-hint">用于自动匹配商家备注</span>
              </label>
              <div class="tag-editor">
                <div class="tag-list">
                  <el-tag v-for="(kw, i) in kws(reasonForm.keywords)" :key="i"
                    closable size="small" @close="removeKeyword(i)">{{ kw }}</el-tag>
                </div>
                <el-input v-model="kwInput" size="small" placeholder="输入关键词，回车添加"
                  style="margin-top:6px" @keyup.enter="onKwConfirm" />
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">排序</label>
              <el-input-number v-model="reasonForm.sort_order" :min="0" :step="1"
                controls-position="right" style="width:100px" />
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
            <span class="col-title">发货物料简称（{{ filteredShippingAliases.length }}/{{ shippingAliases.length }}）</span>
            <button class="btn-add" title="新建简称" @click="startNewShipping">＋</button>
          </div>
          <el-input
            v-model="shippingSearch"
            size="small"
            clearable
            class="alias-search"
            placeholder="搜索简称/关键词"
          />

          <div class="alias-list">
            <div v-for="item in filteredShippingAliases" :key="item.id" class="alias-item"
              :class="{ editing: editingShipping?.id === item.id }"
              @click="startEditShipping(item)"
            >
              <div class="alias-item-main">
                <span class="alias-name">{{ item.name }}</span>
                <span class="alias-meta">
                  {{ item.keywords?.length ? item.keywords.length + ' 个关键词' : '暂无关键词' }}
                </span>
              </div>
              <div class="alias-actions">
                <button class="btn-tiny btn-del" title="删除" @click.stop="deleteShipping(item)">
                  <el-icon><Delete /></el-icon>
                </button>
              </div>
            </div>
            <div v-if="!shippingAliases.length" class="col-empty">
              暂无简称，点击右上角「＋」添加
            </div>
            <div v-else-if="!filteredShippingAliases.length" class="col-empty">
              未找到匹配简称
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
              <el-input v-model="editingShipping.name" placeholder="如：拉链头套件" @keyup.enter="submitShipping" />
            </div>

            <div class="form-row">
              <label class="form-label">物料名称关键词
                <span class="form-label-hint">工单提交时自动积累，也可手动维护；匹配发货物料的 name 字段</span>
              </label>
              <div class="tag-editor">
                <div class="tag-list">
                  <el-tag v-for="(kw, i) in editingShipping.keywords" :key="i"
                    closable size="small" type="info" @close="removeShipCode(i)">{{ kw }}</el-tag>
                  <span v-if="!editingShipping.keywords.length" class="tag-empty">暂无</span>
                </div>
                <el-input v-model="shipCodeInput" size="small" placeholder="输入物料名称关键词，回车添加"
                  style="margin-top:6px" @keyup.enter="addShipCode" />
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">排序</label>
              <el-input-number v-model="editingShipping.sort_order" :min="0" :step="1"
                controls-position="right" style="width:100px" />
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
            <div>点击「＋」新建，或点击左侧列表项编辑</div>
            <div class="placeholder-hint">维护发货物料的规范简称；处理工单时可下拉选择，<br>选择后自动将订单产品代码关联到该简称</div>
          </div>
        </div>
      </div>

      <!-- ── 售后物料简称库 Tab ───────────────────── -->
      <div v-if="activeTab === 'return'" class="alias-lib">

        <!-- 左列：简称列表 -->
        <div class="alias-list-col">
          <div class="col-header">
            <span class="col-title">售后物料简称（{{ filteredReturnAliases.length }}/{{ returnAliases.length }}）</span>
            <button class="btn-add" title="新建简称" @click="startNewReturn">＋</button>
          </div>
          <el-input
            v-model="returnSearch"
            size="small"
            clearable
            class="alias-search"
            placeholder="搜索简称/关键词"
          />

          <div class="alias-list">
            <div v-for="item in filteredReturnAliases" :key="item.id" class="alias-item"
              :class="{ editing: editingReturn?.id === item.id }"
              @click="startEditReturn(item)"
            >
              <div class="alias-item-main">
                <span class="alias-name">{{ item.name }}</span>
                <span class="alias-meta">
                  {{ item.keywords?.length ? item.keywords.length + ' 条备注匹配' : '暂无关键词' }}
                </span>
              </div>
              <div class="alias-actions">
                <button class="btn-tiny btn-del" title="删除" @click.stop="deleteReturn(item)">
                  <el-icon><Delete /></el-icon>
                </button>
              </div>
            </div>
            <div v-if="!returnAliases.length" class="col-empty">
              暂无简称，点击右上角「＋」添加
            </div>
            <div v-else-if="!filteredReturnAliases.length" class="col-empty">
              未找到匹配简称
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
              <el-input v-model="editingReturn.name" placeholder="如：拉链头" @keyup.enter="submitReturn" />
            </div>

            <div class="form-row">
              <label class="form-label">备注关键词
                <span class="form-label-hint">工单提交时从商家备注自动采集，也可手动维护</span>
              </label>
              <div class="tag-editor">
                <div class="tag-list">
                  <el-tag v-for="(kw, i) in editingReturn.keywords" :key="i"
                    closable size="small" type="warning" @close="removeReturnKw(i)">{{ kw }}</el-tag>
                  <span v-if="!editingReturn.keywords.length" class="tag-empty">暂无</span>
                </div>
                <el-input v-model="retKwInput" size="small" placeholder="输入备注片段，回车添加"
                  style="margin-top:6px" @keyup.enter="addReturnKw" />
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">排序</label>
              <el-input-number v-model="editingReturn.sort_order" :min="0" :step="1"
                controls-position="right" style="width:100px" />
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
            <div>点击「＋」新建，或点击左侧列表项编辑</div>
            <div class="placeholder-hint">维护出现问题的物料规范简称；工单提交后商家备注<br>会自动采集为关键词，用于下次自动匹配</div>
          </div>
        </div>
      </div>

      <!-- ── 过滤词 Tab ────────────────────────────── -->
      <div v-if="activeTab === 'ignore'" class="ignore-lib">
        <div class="col-header">
          <span class="col-title">物料匹配过滤词（{{ ignoreTerms.length }}）</span>
        </div>
        <div class="ignore-desc">
          发货物料名称包含以下词时，该物料跳过简称自动匹配与学习（如「半成品」「定制件」「其他」）
        </div>

        <!-- 输入新词 -->
        <div class="ignore-input-row">
          <el-input
            v-model="ignoreInput"
            placeholder="输入过滤词，回车添加"
            size="small"
            style="flex:1"
            @keyup.enter="addIgnoreTerm"
          />
          <el-button size="small" type="primary" :loading="ignoreLoading" @click="addIgnoreTerm">添加</el-button>
        </div>

        <!-- 词列表 -->
        <div class="ignore-tags">
          <div v-for="item in ignoreTerms" :key="item.id" class="ignore-tag-item">
            <span class="ignore-tag-text">{{ item.term }}</span>
            <button class="btn-tiny btn-del" title="删除" @click="deleteIgnoreTerm(item)">
              <el-icon><Delete /></el-icon>
            </button>
          </div>
          <div v-if="ignoreTerms.length === 0" class="col-empty">暂无过滤词</div>
        </div>
      </div>

      <!-- ── 原因词典 Tab ────────────────────────────── -->
      <div v-if="activeTab === 'reasonRules'" class="rule-lib">
        <div class="col-header">
          <span class="col-title">售后原因关键词词典</span>
        </div>
        <div class="ignore-desc">
          规则实时加载于当前管理弹窗。词条支持直接新增/删除；同义词支持配置正则模式开关。
        </div>

        <div class="rule-grid">
          <div class="rule-card">
            <label class="form-label">停用词（stopwords）</label>
            <div class="rule-input-row">
              <el-input v-model="reasonRuleForm.newStopword" size="small" placeholder="如：补偿" @keyup.enter="addRuleTerm('stopwords', 'newStopword')" />
              <el-button size="small" @click="addRuleTerm('stopwords', 'newStopword')">添加</el-button>
            </div>
            <div class="rule-tags">
              <el-tag
                v-for="(t, i) in reasonRuleForm.stopwords"
                :key="`sw-${i}-${t}`"
                closable
                size="small"
                title="点击编辑"
                @click="editRuleTerm('stopwords', i)"
                @close="removeRuleTerm('stopwords', i)"
              >{{ t }}</el-tag>
              <span v-if="!reasonRuleForm.stopwords.length" class="tag-empty">暂无</span>
            </div>
          </div>

          <div class="rule-card">
            <label class="form-label">故障核心词（fault_terms）</label>
            <div class="rule-input-row">
              <el-input v-model="reasonRuleForm.newFaultTerm" size="small" placeholder="如：开裂" @keyup.enter="addRuleTerm('fault_terms', 'newFaultTerm')" />
              <el-button size="small" @click="addRuleTerm('fault_terms', 'newFaultTerm')">添加</el-button>
            </div>
            <div class="rule-tags">
              <el-tag
                v-for="(t, i) in reasonRuleForm.fault_terms"
                :key="`ft-${i}-${t}`"
                closable
                size="small"
                type="danger"
                title="点击编辑"
                @click="editRuleTerm('fault_terms', i)"
                @close="removeRuleTerm('fault_terms', i)"
              >{{ t }}</el-tag>
              <span v-if="!reasonRuleForm.fault_terms.length" class="tag-empty">暂无</span>
            </div>
          </div>
        </div>

        <div class="rule-card">
          <label class="form-label">部件词（component_terms）</label>
          <div class="rule-input-row">
            <el-input v-model="reasonRuleForm.newComponentTerm" size="small" placeholder="如：后固定板" @keyup.enter="addRuleTerm('component_terms', 'newComponentTerm')" />
            <el-button size="small" @click="addRuleTerm('component_terms', 'newComponentTerm')">添加</el-button>
          </div>
          <div class="rule-tags">
            <el-tag
              v-for="(t, i) in reasonRuleForm.component_terms"
              :key="`ct-${i}-${t}`"
              closable
              size="small"
              type="warning"
              title="点击编辑"
              @click="editRuleTerm('component_terms', i)"
              @close="removeRuleTerm('component_terms', i)"
            >{{ t }}</el-tag>
            <span v-if="!reasonRuleForm.component_terms.length" class="tag-empty">暂无</span>
          </div>
        </div>

        <div class="rule-card">
          <label class="form-label">短词保留（short_keep_terms）</label>
          <div class="ignore-desc" style="margin-bottom:8px">
            长度 ≤2 的词条默认当作泛词；在此维护的短词仍参与质量分与匹配（如：椅套、气杆）
          </div>
          <div class="rule-input-row">
            <el-input v-model="reasonRuleForm.newShortKeepTerm" size="small" placeholder="如：气杆" @keyup.enter="addRuleTerm('short_keep_terms', 'newShortKeepTerm')" />
            <el-button size="small" @click="addRuleTerm('short_keep_terms', 'newShortKeepTerm')">添加</el-button>
          </div>
          <div class="rule-tags">
            <el-tag
              v-for="(t, i) in reasonRuleForm.short_keep_terms"
              :key="`sk-${i}-${t}`"
              closable
              size="small"
              type="success"
              title="点击编辑"
              @click="editRuleTerm('short_keep_terms', i)"
              @close="removeRuleTerm('short_keep_terms', i)"
            >{{ t }}</el-tag>
            <span v-if="!reasonRuleForm.short_keep_terms.length" class="tag-empty">暂无</span>
          </div>
        </div>

        <div class="rule-card">
          <label class="form-label">同义词规则（synonyms）</label>
          <div class="synonym-input-grid">
            <div class="synonym-alias-wrap">
              <div class="rule-input-row">
                <el-input
                  v-model="reasonRuleForm.newSynonymAlias"
                  size="small"
                  placeholder="输入别名词（如：粉色）"
                  @keyup.enter="addSynonymAlias"
                />
                <el-button size="small" @click="addSynonymAlias">加入别名</el-button>
              </div>
              <div class="rule-tags">
                <el-tag
                  v-for="(a, i) in reasonRuleForm.newSynonymAliases"
                  :key="`new-alias-${i}-${a}`"
                  closable
                  size="small"
                  @close="removeSynonymAlias(i)"
                >{{ a }}</el-tag>
                <span v-if="!reasonRuleForm.newSynonymAliases.length" class="tag-empty">先添加别名词条</span>
              </div>
            </div>
            <el-input v-model="reasonRuleForm.newReplacement" size="small" placeholder="归一结果（如：红色）" @keyup.enter="addSynonymRule" />
            <el-select v-model="reasonRuleForm.newIsRegex" size="small" style="width:120px">
              <el-option :value="true" label="正则" />
              <el-option :value="false" label="文本" />
            </el-select>
            <el-button size="small" @click="addSynonymRule">添加规则</el-button>
          </div>
          <div class="synonym-list">
            <div v-for="(s, i) in reasonRuleForm.synonyms" :key="`syn-${i}-${s.pattern}`" class="synonym-item">
              <span class="synonym-pattern">{{ (s.pattern || '').split('|').join(' / ') }}</span>
              <span class="path-sep">→</span>
              <span class="synonym-replacement">{{ s.replacement }}</span>
              <span class="source-badge" :class="s.is_regex ? 'src-api' : 'src-text'">{{ s.is_regex ? '正则' : '文本' }}</span>
              <button class="btn-tiny" title="编辑" @click="editSynonymRule(i)">
                <el-icon><Edit /></el-icon>
              </button>
              <button class="btn-tiny btn-del" @click="removeSynonymRule(i)">
                <el-icon><Delete /></el-icon>
              </button>
            </div>
            <div v-if="!reasonRuleForm.synonyms.length" class="col-empty">暂无同义词规则</div>
          </div>
        </div>

        <div class="form-actions">
          <el-button size="small" :loading="loading" @click="loadAll">刷新</el-button>
          <el-button size="small" type="primary" :loading="ruleSaving" @click="saveReasonRules">保存词典</el-button>
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
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.alias-form-col {
  flex: 1;
  overflow-y: auto;
  min-width: 0;
  padding-left: 2px;
}
.alias-form-col::-webkit-scrollbar { width: 4px; }
.alias-form-col::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.alias-list {
  flex: 1;
  overflow-y: auto;
}
.alias-search {
  margin-bottom: 8px;
}
.alias-list::-webkit-scrollbar { width: 4px; }
.alias-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.alias-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}
.alias-item:hover { background: var(--bg); }
.alias-item.editing { background: #fff7ed; }

.alias-item-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}
.alias-name {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.alias-meta {
  font-size: 10px;
  color: var(--text-muted);
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

/* ── tag 编辑器（关键词/代码列表）─────────────────── */
.tag-editor {
  background: #faf7f2;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
}
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 24px;
}
.tag-empty {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 22px;
}

/* ── 通用 ────────────────────────────────────────── */
.placeholder-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  line-height: 1.6;
  text-align: center;
}

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
.form-label-hint {
  font-size: 10px; color: var(--text-muted);
  font-weight: normal; margin-left: 4px;
}
.required { color: #d05a3c; }

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

/* ── 过滤词 Tab ──────────────────────────────────── */
.ignore-lib {
  flex: 1; display: flex; flex-direction: column; gap: 10px; padding: 4px 0;
  overflow: hidden;
}
.ignore-desc {
  font-size: 11px; color: var(--text-muted); line-height: 1.5;
  padding: 6px 10px; background: #faf7f2; border-radius: 6px;
  border: 1px solid var(--border-color);
}
.ignore-input-row {
  display: flex; gap: 8px; align-items: center;
}
.ignore-tags {
  flex: 1; overflow-y: auto; display: flex; flex-wrap: wrap;
  gap: 6px; align-content: flex-start; padding: 4px 0;
}
.ignore-tag-item {
  display: flex; align-items: center; gap: 4px;
  background: #fff3e0; border: 1px solid #f5c078; border-radius: 8px;
  padding: 3px 8px 3px 10px; font-size: 12px; color: var(--text-primary);
}
.ignore-tag-text { line-height: 1.4; }

/* ── 原因词典 Tab ─────────────────────────────────── */
.rule-lib {
  flex: 1;
  overflow-y: auto;
  padding: 6px 0;
}
.rule-lib::-webkit-scrollbar { width: 4px; }
.rule-lib::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.rule-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}
.rule-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  background: #faf7f2;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}
.rule-input-row {
  display: flex;
  gap: 8px;
  margin-bottom: 0;
}
.rule-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 30px;
  max-height: 120px;
  overflow-y: auto;
  padding-right: 2px;
}
.rule-tags::-webkit-scrollbar { width: 4px; }
.rule-tags::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.rule-tags::-webkit-scrollbar-track { background: transparent; }
.rule-card .form-label {
  margin-bottom: 0;
}
.synonym-input-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 120px auto;
  gap: 8px;
  margin-bottom: 0;
}
.synonym-alias-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.synonym-alias-wrap .rule-input-row { margin-bottom: 0; }
.synonym-list {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
  max-height: 220px;
  overflow: auto;
}
.synonym-list::-webkit-scrollbar { width: 4px; }
.synonym-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.synonym-list::-webkit-scrollbar-track { background: transparent; }
.synonym-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px dashed var(--border);
}
.synonym-item:last-child { border-bottom: none; }
.synonym-pattern {
  flex: 1;
  font-family: Consolas, monospace;
  font-size: 12px;
  color: var(--text-primary);
}
.synonym-replacement {
  min-width: 80px;
  color: var(--accent);
  font-size: 12px;
}
</style>
