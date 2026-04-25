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

// ── 词典自动建议 ──────────────────────────────────
const dictSuggestions       = ref([])
const dictSuggestionsLoaded = ref(false)
const dictSugExpanded       = ref(false)  // 建议区块是否展开
const pendingSuggestionsCount = computed(
  () => dictSuggestions.value.filter(s => s.status === 'pending').length
)

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

// ── 发货物料匹配过滤词状态 ─────────────────────────
const ignoreTerms      = ref([])    // [{id, term}]
const ignoreInput      = ref('')
const ignoreLoading    = ref(false)
const ambiguousTerms   = ref([])    // [{id, term}]
const ambiguousInput   = ref('')
const ambiguousLoading = ref(false)
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
  newSynonymAliasText: '',  // 逗号分隔的别名词，如"粉色,粉红,浅粉"
  newReplacement: '',
  newIsRegex: true,
})

// ── 产品留言词典状态（材质/颜色/驱动/尺寸）──────────────
const remarkDictItems  = ref([])   // [{id, type, value, display, enabled, sort_order}]
const remarkDictSaving = ref(false)
// 新增输入框
const newRemarkInputs = ref({ material: '', color: '', drive_type: '', sizeValue: '', sizeDisplay: '' })

// 同义词候选建议：接受时需输入归一词
const synCanonicalMap = ref({})   // sug.id → 用户输入的归一词

// 晋升关键词拆分模式：sug.id → { component: '', fault: '' }
const splitMap = ref({})

// 同义词行内编辑状态
const editingSynIdx         = ref(-1)
const editingSynAliasText   = ref('')
const editingSynReplacement = ref('')
const editingSynIsRegex     = ref(true)

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

// ── Watch ─────────────────────────────────────────
watch(visible, (v) => {
  if (v) {
    loadAll()
    editingCat.value          = null
    reasonForm.value          = null
    editingShipping.value     = null
    shippingSearch.value      = ''
  }
})

// ── 加载方法 ──────────────────────────────────────
async function loadAll() {
  loading.value = true
  try {
    const [catRes, reasonRes, shipRes, ignoreRes, rulesRes, remarkDictRes, ambiguousRes] = await Promise.all([
      http.get('/api/aftersale/reason-categories'),
      http.get('/api/aftersale/reasons'),
      http.get('/api/aftersale/shipping-aliases'),
      http.get('/api/aftersale/shipping-ignore-terms'),
      http.get('/api/aftersale/reason-keyword-rules'),
      http.get('/api/aftersale/product-remark-dict'),
      http.get('/api/aftersale/shipping-ambiguous-terms'),
    ])
    if (catRes.success)        categories.value      = catRes.data
    if (reasonRes.success)     groups.value          = reasonRes.data
    if (shipRes.success)       shippingAliases.value  = shipRes.data
    if (ignoreRes.success)     ignoreTerms.value      = ignoreRes.data
    if (rulesRes.success)      setReasonRuleForm(rulesRes.data)
    if (remarkDictRes.success) remarkDictItems.value  = remarkDictRes.data
    if (ambiguousRes.success)  ambiguousTerms.value   = ambiguousRes.data

    if (activeCatId.value === null && categories.value.length > 0) {
      activeCatId.value = categories.value[0].id
    }
  } finally {
    loading.value = false
  }
}

async function loadDictSuggestions(force = false) {
  if (dictSuggestionsLoaded.value && !force) return
  const res = await http.get('/api/aftersale/dictionary-suggestions')
  if (res.success) {
    dictSuggestions.value = res.data
    dictSuggestionsLoaded.value = true
    if (dictSuggestions.value.some(s => s.status === 'pending')) {
      dictSugExpanded.value = true
    }
  }
}

async function acceptDictSuggestion(sug, targetType = null, canonical = null) {
  // synonym_candidate 需要用户填入归一词
  if (sug.type === 'synonym_candidate') {
    canonical = (synCanonicalMap.value[sug.id] || '').trim()
    if (!canonical) {
      ElMessage.warning('请先填写归一词')
      return
    }
  }
  const body = {}
  if (targetType)  body.target_type = targetType
  if (canonical)   body.canonical   = canonical
  const res = await http.post(`/api/aftersale/dictionary-suggestions/${sug.id}/accept`, body)
  if (res.success) {
    const idx = dictSuggestions.value.findIndex(s => s.id === sug.id)
    if (idx >= 0) dictSuggestions.value[idx] = res.data
    delete synCanonicalMap.value[sug.id]
    ElMessage.success('已接受')
    if (sug.type !== 'promoted_keyword') emit('updated')
  }
}

// 拆分晋升关键词：将 component + fault 两个词分别追加到词典表单，并标记建议为已接受
async function confirmSplit(sug) {
  const entry = splitMap.value[sug.id]
  if (!entry) return
  const component = (entry.component || '').trim()
  const fault     = (entry.fault     || '').trim()
  if (!component && !fault) {
    ElMessage.warning('请至少填写一项')
    return
  }
  // 追加到词典表单（保存时统一写库）
  if (component && !reasonRuleForm.value.component_terms.includes(component)) {
    reasonRuleForm.value.component_terms.push(component)
  }
  if (fault && !reasonRuleForm.value.fault_terms.includes(fault)) {
    reasonRuleForm.value.fault_terms.push(fault)
  }
  // 标记建议为已接受（不指定 target_type，仅确认）
  const res = await http.post(`/api/aftersale/dictionary-suggestions/${sug.id}/accept`, {})
  if (res.success) {
    const idx = dictSuggestions.value.findIndex(s => s.id === sug.id)
    if (idx >= 0) dictSuggestions.value[idx] = res.data
    delete splitMap.value[sug.id]
    ElMessage.success('已拆分，请保存词典')
  }
}

async function rejectDictSuggestion(sug) {
  const res = await http.post(`/api/aftersale/dictionary-suggestions/${sug.id}/reject`)
  if (res.success) {
    const idx = dictSuggestions.value.findIndex(s => s.id === sug.id)
    if (idx >= 0) dictSuggestions.value[idx] = res.data
    ElMessage.success('已忽略')
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
    (reasonRuleForm.value.newSynonymAliasText || '')
      .split(',').map(s => s.trim()).filter(Boolean)
  )]
  const replacement = (reasonRuleForm.value.newReplacement || '').trim()
  if (!aliases.length || !replacement) return
  reasonRuleForm.value.synonyms.push({
    pattern: aliases.join('|'),
    replacement,
    is_regex: reasonRuleForm.value.newIsRegex,
  })
  reasonRuleForm.value.newSynonymAliasText = ''
  reasonRuleForm.value.newReplacement = ''
}

function removeSynonymRule(idx) {
  if (editingSynIdx.value === idx) editingSynIdx.value = -1
  reasonRuleForm.value.synonyms.splice(idx, 1)
}

function startEditSynonym(idx) {
  const row = reasonRuleForm.value.synonyms[idx]
  if (!row) return
  editingSynIdx.value = idx
  editingSynAliasText.value   = (row.pattern || '').split('|').join(', ')
  editingSynReplacement.value = row.replacement || ''
  editingSynIsRegex.value     = row.is_regex !== false
}

function saveSynonymEdit(idx) {
  const aliases = [...new Set(
    editingSynAliasText.value.split(',').map(s => s.trim()).filter(Boolean)
  )]
  const replacement = editingSynReplacement.value.trim()
  if (!aliases.length || !replacement) return
  reasonRuleForm.value.synonyms.splice(idx, 1, {
    pattern:    aliases.join('|'),
    replacement,
    is_regex:   editingSynIsRegex.value,
  })
  editingSynIdx.value = -1
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

// ── 产品留言词典操作 ───────────────────────────────

function remarkDictByType(type) {
  return remarkDictItems.value.filter(item => item.type === type)
}

function addRemarkDictItem(type) {
  const value   = (newRemarkInputs.value[type === 'size' ? 'sizeValue' : type] || '').trim()
  const display = type === 'size' ? (newRemarkInputs.value.sizeDisplay || '').trim() : null
  if (!value) { ElMessage.warning('词条不能为空'); return }
  if (type === 'size' && !display) { ElMessage.warning('尺寸需填写米制表达（如 1.2米）'); return }
  if (remarkDictItems.value.some(i => i.type === type && i.value === value)) {
    ElMessage.warning('已存在相同词条'); return
  }
  remarkDictItems.value.push({ id: null, type, value, display, enabled: true, sort_order: 0 })
  if (type === 'size') { newRemarkInputs.value.sizeValue = ''; newRemarkInputs.value.sizeDisplay = '' }
  else newRemarkInputs.value[type] = ''
}

function removeRemarkDictItem(item) {
  remarkDictItems.value = remarkDictItems.value.filter(i => i !== item)
}

async function saveRemarkDict() {
  remarkDictSaving.value = true
  try {
    const items = remarkDictItems.value.map((item, idx) => ({
      type: item.type,
      value: item.value,
      display: item.display || null,
      enabled: item.enabled !== false,
      sort_order: idx,
    }))
    const res = await http.put('/api/aftersale/product-remark-dict', { items })
    if (res.success) {
      remarkDictItems.value = res.data
      ElMessage.success('产品词典已保存')
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } finally {
    remarkDictSaving.value = false
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

// ── 歧义词操作 ────────────────────────────────────

async function addAmbiguousTerm() {
  const term = (ambiguousInput.value || '').trim()
  if (!term) return
  ambiguousLoading.value = true
  try {
    const res = await http.post('/api/aftersale/shipping-ambiguous-terms', { term })
    if (res.success) {
      ambiguousTerms.value.push(res.data)
      ambiguousInput.value = ''
      emit('updated')
    } else {
      ElMessage.error(res.message || '添加失败')
    }
  } finally {
    ambiguousLoading.value = false
  }
}

async function deleteAmbiguousTerm(item) {
  const res = await http.delete(`/api/aftersale/shipping-ambiguous-terms/${item.id}`)
  if (res.success) {
    ambiguousTerms.value = ambiguousTerms.value.filter(t => t.id !== item.id)
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

        <button class="lib-tab" :class="{ active: activeTab === 'reasonRules' }" @click="activeTab = 'reasonRules'; loadDictSuggestions()">
          词典
          <span v-if="pendingSuggestionsCount > 0" class="sug-badge">{{ pendingSuggestionsCount }}</span>
        </button>
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
              @click="startEditReason(r)"
            >
              <div class="reason-item-left">
                <span class="reason-name">{{ r.name }}</span>
                <span v-if="r.use_count > 0" class="use-count">已用 {{ r.use_count }} 次</span>
              </div>
              <div class="reason-item-actions">
                <button class="btn-tiny btn-del" title="删除" @click.stop="deleteReason(r)">
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
            <div>点击「＋」新建，或点击中间列的原因条目编辑</div>
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

      <!-- ── 词典 Tab ──────────────────────────────── -->
      <div v-if="activeTab === 'reasonRules'" class="rule-lib">

        <!-- 可滚动内容区 -->
        <div class="rule-lib-body">

        <!-- 词典优化建议折叠区块 -->
        <div v-if="dictSuggestionsLoaded && pendingSuggestionsCount > 0" class="dict-sug-panel">
          <div class="dict-sug-header" @click="dictSugExpanded = !dictSugExpanded">
            <span class="dict-sug-title">
              待优化建议
              <span class="sug-badge inline">{{ pendingSuggestionsCount }}</span>
            </span>
            <span class="dict-sug-toggle">{{ dictSugExpanded ? '▲ 收起' : '▼ 展开' }}</span>
          </div>
          <div v-if="dictSugExpanded" class="dict-sug-body">

            <!-- 停用词建议 -->
            <div v-if="dictSuggestions.filter(s => s.status === 'pending' && s.type === 'stopword').length" class="sug-group">
              <div class="sug-group-label">停用词建议</div>
              <div v-for="sug in dictSuggestions.filter(s => s.status === 'pending' && s.type === 'stopword')" :key="sug.id" class="sug-row">
                <span class="sug-value">{{ sug.value }}</span>
                <span class="sug-count">×{{ sug.count }}</span>
                <span class="sug-reason">{{ sug.reason }}</span>
                <div class="sug-actions">
                  <el-button size="small" type="primary" @click="acceptDictSuggestion(sug)">加入停用词</el-button>
                  <el-button size="small" @click="rejectDictSuggestion(sug)">忽略</el-button>
                </div>
              </div>
            </div>

            <!-- 过滤词建议 -->
            <div v-if="dictSuggestions.filter(s => s.status === 'pending' && s.type === 'ignore_term').length" class="sug-group">
              <div class="sug-group-label">发货过滤词建议</div>
              <div v-for="sug in dictSuggestions.filter(s => s.status === 'pending' && s.type === 'ignore_term')" :key="sug.id" class="sug-row">
                <span class="sug-value">{{ sug.value }}</span>
                <span class="sug-count">×{{ sug.count }}</span>
                <span class="sug-reason">{{ sug.reason }}</span>
                <div class="sug-actions">
                  <el-button size="small" type="primary" @click="acceptDictSuggestion(sug)">加入过滤词</el-button>
                  <el-button size="small" @click="rejectDictSuggestion(sug)">忽略</el-button>
                </div>
              </div>
            </div>

            <!-- 晋升关键词建议 -->
            <div v-if="dictSuggestions.filter(s => s.status === 'pending' && s.type === 'promoted_keyword').length" class="sug-group">
              <div class="sug-group-label">晋升关键词（可归类）</div>
              <div v-for="sug in dictSuggestions.filter(s => s.status === 'pending' && s.type === 'promoted_keyword')" :key="sug.id" class="sug-row sug-row--block">
                <!-- 主行 -->
                <div class="sug-row-main">
                  <span class="sug-value">{{ sug.value }}</span>
                  <span class="sug-count">×{{ sug.count }}</span>
                  <span class="sug-reason">{{ sug.reason }}</span>
                  <div class="sug-actions">
                    <el-button size="small" type="warning" @click="acceptDictSuggestion(sug, 'fault_term')">故障词</el-button>
                    <el-button size="small" type="success" @click="acceptDictSuggestion(sug, 'component_term')">部件词</el-button>
                    <el-button size="small" @click="splitMap[sug.id] = splitMap[sug.id] ? null : { component: sug.value, fault: '' }">
                      拆分
                    </el-button>
                    <el-button size="small" @click="acceptDictSuggestion(sug)">仅确认</el-button>
                    <el-button size="small" @click="rejectDictSuggestion(sug)">忽略</el-button>
                  </div>
                </div>
                <!-- 拆分展开区 -->
                <div v-if="splitMap[sug.id]" class="sug-split-row">
                  <div class="sug-split-field">
                    <span class="sug-split-label">部件词</span>
                    <el-input v-model="splitMap[sug.id].component" size="small" placeholder="如：后固定桌面板" />
                  </div>
                  <div class="sug-split-field">
                    <span class="sug-split-label">故障词</span>
                    <el-input v-model="splitMap[sug.id].fault" size="small" placeholder="如：开裂" />
                  </div>
                  <el-button size="small" type="primary" @click="confirmSplit(sug)">确认拆分</el-button>
                  <el-button size="small" @click="delete splitMap[sug.id]">取消</el-button>
                </div>
              </div>
            </div>

            <!-- 同义词候选建议 -->
            <div v-if="dictSuggestions.filter(s => s.status === 'pending' && s.type === 'synonym_candidate').length" class="sug-group">
              <div class="sug-group-label">同义词候选</div>
              <div v-for="sug in dictSuggestions.filter(s => s.status === 'pending' && s.type === 'synonym_candidate')" :key="sug.id" class="sug-row sug-row--syn">
                <div class="sug-syn-main">
                  <span class="sug-value">{{ sug.value }}</span>
                  <span class="sug-count">×{{ sug.count }}</span>
                  <span class="sug-reason">{{ sug.reason }}</span>
                </div>
                <div class="sug-syn-input">
                  <el-input
                    v-model="synCanonicalMap[sug.id]"
                    size="small"
                    placeholder="填写归一词（标准形式）"
                    style="width:160px"
                    @keyup.enter="acceptDictSuggestion(sug)"
                  />
                  <el-button size="small" type="primary"
                    :disabled="!(synCanonicalMap[sug.id] || '').trim()"
                    @click="acceptDictSuggestion(sug)">创建同义词规则</el-button>
                  <el-button size="small" @click="rejectDictSuggestion(sug)">忽略</el-button>
                </div>
              </div>
            </div>

          </div>
        </div>

        <!-- 4 个 tag 类词典：2×2 grid -->
        <div class="rule-grid">

          <!-- 停用词 -->
          <div class="rule-card rule-card--neutral">
            <div class="rule-card-header">
              <span class="rule-card-title">停用词</span>
              <span class="rule-card-count">{{ reasonRuleForm.stopwords.length }}</span>
            </div>
            <div class="rule-card-desc">匹配时过滤这些泛义词，降低误匹配</div>
            <div class="rule-input-row">
              <el-input v-model="reasonRuleForm.newStopword" size="small" placeholder="如：补偿，回车添加" @keyup.enter="addRuleTerm('stopwords', 'newStopword')" />
              <el-button size="small" @click="addRuleTerm('stopwords', 'newStopword')">添加</el-button>
            </div>
            <div class="rule-tags">
              <el-tag v-for="(t, i) in reasonRuleForm.stopwords" :key="`sw-${i}-${t}`"
                closable size="small" title="点击编辑"
                @click="editRuleTerm('stopwords', i)" @close="removeRuleTerm('stopwords', i)"
              >{{ t }}</el-tag>
              <span v-if="!reasonRuleForm.stopwords.length" class="tag-empty">暂无</span>
            </div>
          </div>

          <!-- 故障核心词 -->
          <div class="rule-card rule-card--danger">
            <div class="rule-card-header">
              <span class="rule-card-title">故障核心词</span>
              <span class="rule-card-count">{{ reasonRuleForm.fault_terms.length }}</span>
            </div>
            <div class="rule-card-desc">描述损坏/缺陷的关键词，命中时提升匹配权重</div>
            <div class="rule-input-row">
              <el-input v-model="reasonRuleForm.newFaultTerm" size="small" placeholder="如：开裂，回车添加" @keyup.enter="addRuleTerm('fault_terms', 'newFaultTerm')" />
              <el-button size="small" @click="addRuleTerm('fault_terms', 'newFaultTerm')">添加</el-button>
            </div>
            <div class="rule-tags">
              <el-tag v-for="(t, i) in reasonRuleForm.fault_terms" :key="`ft-${i}-${t}`"
                closable size="small" type="danger" title="点击编辑"
                @click="editRuleTerm('fault_terms', i)" @close="removeRuleTerm('fault_terms', i)"
              >{{ t }}</el-tag>
              <span v-if="!reasonRuleForm.fault_terms.length" class="tag-empty">暂无</span>
            </div>
          </div>

          <!-- 部件词 -->
          <div class="rule-card rule-card--warning">
            <div class="rule-card-header">
              <span class="rule-card-title">部件词</span>
              <span class="rule-card-count">{{ reasonRuleForm.component_terms.length }}</span>
            </div>
            <div class="rule-card-desc">产品零部件名称，命中时辅助提升匹配权重</div>
            <div class="rule-input-row">
              <el-input v-model="reasonRuleForm.newComponentTerm" size="small" placeholder="如：后固定板，回车添加" @keyup.enter="addRuleTerm('component_terms', 'newComponentTerm')" />
              <el-button size="small" @click="addRuleTerm('component_terms', 'newComponentTerm')">添加</el-button>
            </div>
            <div class="rule-tags">
              <el-tag v-for="(t, i) in reasonRuleForm.component_terms" :key="`ct-${i}-${t}`"
                closable size="small" type="warning" title="点击编辑"
                @click="editRuleTerm('component_terms', i)" @close="removeRuleTerm('component_terms', i)"
              >{{ t }}</el-tag>
              <span v-if="!reasonRuleForm.component_terms.length" class="tag-empty">暂无</span>
            </div>
          </div>

          <!-- 短词保留 -->
          <div class="rule-card rule-card--success">
            <div class="rule-card-header">
              <span class="rule-card-title">短词保留</span>
              <span class="rule-card-count">{{ reasonRuleForm.short_keep_terms.length }}</span>
            </div>
            <div class="rule-card-desc">≤2字默认视为泛词；列在此处的短词仍参与匹配</div>
            <div class="rule-input-row">
              <el-input v-model="reasonRuleForm.newShortKeepTerm" size="small" placeholder="如：气杆，回车添加" @keyup.enter="addRuleTerm('short_keep_terms', 'newShortKeepTerm')" />
              <el-button size="small" @click="addRuleTerm('short_keep_terms', 'newShortKeepTerm')">添加</el-button>
            </div>
            <div class="rule-tags">
              <el-tag v-for="(t, i) in reasonRuleForm.short_keep_terms" :key="`sk-${i}-${t}`"
                closable size="small" type="success" title="点击编辑"
                @click="editRuleTerm('short_keep_terms', i)" @close="removeRuleTerm('short_keep_terms', i)"
              >{{ t }}</el-tag>
              <span v-if="!reasonRuleForm.short_keep_terms.length" class="tag-empty">暂无</span>
            </div>
          </div>

        </div><!-- /rule-grid -->

        <!-- 同义词规则：全宽 -->
        <div class="rule-card rule-card--synonym">
          <div class="rule-card-header">
            <span class="rule-card-title">同义词规则</span>
            <span class="rule-card-count">{{ reasonRuleForm.synonyms.length }}</span>
          </div>
          <div class="rule-card-desc">将别名词归一为标准词再匹配，如「粉色,粉红 → 红色」</div>

          <!-- 新增行 -->
          <div class="synonym-add-form">
            <div class="synonym-add-field">
              <span class="syn-label">别名（逗号分隔）</span>
              <el-input
                v-model="reasonRuleForm.newSynonymAliasText"
                size="small"
                placeholder="如：粉色,粉红,浅粉"
                @keyup.enter="addSynonymRule"
              />
            </div>
            <span class="syn-arrow">→</span>
            <div class="synonym-add-field">
              <span class="syn-label">归一为</span>
              <el-input
                v-model="reasonRuleForm.newReplacement"
                size="small"
                placeholder="如：红色"
                @keyup.enter="addSynonymRule"
              />
            </div>
            <div class="synonym-add-field syn-type-field">
              <span class="syn-label">
                类型
                <el-tooltip placement="right" :show-after="100" :hide-after="0" effect="light" popper-class="syn-type-tip">
                  <template #content>
                    <div class="syn-tip-body">
                      <div class="syn-tip-title">选哪种类型？</div>

                      <div class="syn-tip-mode">
                        <span class="syn-tip-badge syn-tip-badge--text">文本</span>
                        <span>只做精确匹配，「坏了」只替换「坏了」，写什么匹配什么</span>
                      </div>
                      <div class="syn-tip-mode">
                        <span class="syn-tip-badge syn-tip-badge--regex">正则</span>
                        <span>支持特殊语法，一条规则可以同时匹配多种写法</span>
                      </div>

                      <div class="syn-tip-section">常用正则写法举例</div>

                      <div class="syn-tip-ex">
                        <div class="syn-tip-ex-label">① 多个词同时匹配（用 | 分隔，长词写前面）</div>
                        <div class="syn-tip-ex-row">
                          <span class="syn-tip-ex-tag">别名</span>
                          <code>损毁|损伤|坏了|坏</code>
                        </div>
                        <div class="syn-tip-ex-row">
                          <span class="syn-tip-ex-tag">归一</span>
                          <code>损坏</code>
                        </div>
                        <div class="syn-tip-ex-result">「扭扭坏了」「椅背损毁」→「扭扭损坏」「椅背损坏」</div>
                      </div>

                      <div class="syn-tip-ex">
                        <div class="syn-tip-ex-label">② 去掉颜色前缀（用 [ ] 列出可能的字）</div>
                        <div class="syn-tip-ex-row">
                          <span class="syn-tip-ex-tag">别名</span>
                          <code>[粉蓝绿白黑]椅背</code>
                        </div>
                        <div class="syn-tip-ex-row">
                          <span class="syn-tip-ex-tag">归一</span>
                          <code>椅背</code>
                        </div>
                        <div class="syn-tip-ex-result">「粉椅背」「蓝椅背」「白椅背」→「椅背」</div>
                      </div>

                      <div class="syn-tip-ex">
                        <div class="syn-tip-ex-label">③ 匹配任意字符（. 代表任意一个字）</div>
                        <div class="syn-tip-ex-row">
                          <span class="syn-tip-ex-tag">别名</span>
                          <code>.+椅背</code>
                        </div>
                        <div class="syn-tip-ex-row">
                          <span class="syn-tip-ex-tag">归一</span>
                          <code>椅背</code>
                        </div>
                        <div class="syn-tip-ex-result">「粉色椅背」「深蓝椅背」→「椅背」</div>
                      </div>

                      <div class="syn-tip-ex">
                        <div class="syn-tip-ex-label">④ 仅匹配单独出现的字，排除复合词（词边界）</div>
                        <div class="syn-tip-ex-row">
                          <span class="syn-tip-ex-tag">别名</span>
                          <code>(?&lt;![^\s])断(?!裂)</code>
                        </div>
                        <div class="syn-tip-ex-row">
                          <span class="syn-tip-ex-tag">归一</span>
                          <code>破损</code>
                        </div>
                        <div class="syn-tip-ex-result">「螺丝断」→「螺丝破损」；「断裂」不受影响</div>
                      </div>

                      <div class="syn-tip-tip">不确定时选正则，多个写法用 | 隔开即可</div>
                    </div>
                  </template>
                  <span class="syn-type-hint">?</span>
                </el-tooltip>
              </span>
              <el-select v-model="reasonRuleForm.newIsRegex" size="small">
                <el-option :value="false" label="文本" />
                <el-option :value="true"  label="正则" />
              </el-select>
            </div>
            <el-button size="small" type="primary" class="syn-add-btn" @click="addSynonymRule">添加</el-button>
          </div>

          <!-- 规则列表 -->
          <div class="synonym-list">
            <template v-for="(s, i) in reasonRuleForm.synonyms" :key="`syn-${i}-${s.pattern}`">
              <!-- 查看行 -->
              <div v-if="editingSynIdx !== i" class="synonym-item">
                <span class="synonym-pattern">{{ (s.pattern || '').split('|').join(' / ') }}</span>
                <span class="path-sep">→</span>
                <span class="synonym-replacement">{{ s.replacement }}</span>
                <span class="source-badge" :class="s.is_regex ? 'src-api' : 'src-text'">{{ s.is_regex ? '正则' : '文本' }}</span>
                <button class="btn-tiny" title="编辑" @click="startEditSynonym(i)">
                  <el-icon><Edit /></el-icon>
                </button>
                <button class="btn-tiny btn-del" @click="removeSynonymRule(i)">
                  <el-icon><Delete /></el-icon>
                </button>
              </div>
              <!-- 行内编辑行 -->
              <div v-else class="synonym-item synonym-item-editing">
                <el-input v-model="editingSynAliasText"   size="small" placeholder="别名（逗号分隔）" style="flex:1;min-width:0" />
                <span class="path-sep">→</span>
                <el-input v-model="editingSynReplacement" size="small" placeholder="归一词" style="width:110px;flex-shrink:0" />
                <el-select v-model="editingSynIsRegex" size="small" style="width:72px;flex-shrink:0">
                  <el-option :value="false" label="文本" />
                  <el-option :value="true"  label="正则" />
                </el-select>
                <button class="btn-tiny btn-ok" title="保存" @click="saveSynonymEdit(i)">
                  <el-icon><Check /></el-icon>
                </button>
                <button class="btn-tiny" title="取消" @click="editingSynIdx = -1">
                  <el-icon><Close /></el-icon>
                </button>
              </div>
            </template>
            <div v-if="!reasonRuleForm.synonyms.length" class="col-empty">暂无同义词规则</div>
          </div>
        </div>

        <!-- 物料匹配过滤词 -->
        <div class="rule-card rule-card--ignore">
          <div class="rule-card-header">
            <span class="rule-card-title">物料过滤词</span>
            <span class="rule-card-count">{{ ignoreTerms.length }}</span>
          </div>
          <div class="rule-card-desc">物料名称中与该词完全相同的分段，跳过简称匹配与学习</div>
          <div class="rule-input-row">
            <el-input v-model="ignoreInput" size="small" placeholder="输入过滤词，回车添加"
              @keyup.enter="addIgnoreTerm" />
            <el-button size="small" :loading="ignoreLoading" @click="addIgnoreTerm">添加</el-button>
          </div>
          <div class="rule-tags">
            <el-tag v-for="item in ignoreTerms" :key="item.id"
              closable size="small"
              @close="deleteIgnoreTerm(item)">{{ item.term }}</el-tag>
            <span v-if="!ignoreTerms.length" class="col-empty" style="font-size:12px">暂无过滤词</span>
          </div>
        </div>

        <!-- 物料歧义词 -->
        <div class="rule-card rule-card--ambiguous">
          <div class="rule-card-header">
            <span class="rule-card-title">物料歧义词</span>
            <span class="rule-card-count">{{ ambiguousTerms.length }}</span>
          </div>
          <div class="rule-card-desc">当发货物料中包含该词时，视为歧义词——该词被多个简称共用，系统将额外借助商家备注内容对候选简称进行二次评分排序</div>
          <div class="rule-input-row">
            <el-input v-model="ambiguousInput" size="small" placeholder="输入物料词，回车添加"
              @keyup.enter="addAmbiguousTerm" />
            <el-button size="small" :loading="ambiguousLoading" @click="addAmbiguousTerm">添加</el-button>
          </div>
          <div class="rule-tags">
            <el-tag v-for="item in ambiguousTerms" :key="item.id"
              closable size="small" type="warning"
              @close="deleteAmbiguousTerm(item)">{{ item.term }}</el-tag>
            <span v-if="!ambiguousTerms.length" class="col-empty" style="font-size:12px">暂无歧义词</span>
          </div>
        </div>

        <!-- 产品留言词典（材质/颜色/驱动/尺寸）-->
        <div class="rule-card rule-card--product-dict">
          <div class="rule-card-header">
            <span class="rule-card-title">产品匹配词典</span>
            <span class="rule-card-count">{{ remarkDictItems.length }}</span>
          </div>
          <div class="rule-card-desc">供买家留言结构化解析使用；尺寸需同时填写数字和米制表达</div>

          <!-- 材质 -->
          <div class="rdict-group">
            <div class="rdict-group-label">材质</div>
            <div class="rule-tags">
              <el-tag v-for="item in remarkDictByType('material')" :key="item.value"
                closable size="small" @close="removeRemarkDictItem(item)">{{ item.value }}</el-tag>
            </div>
            <div class="rule-input-row">
              <el-input v-model="newRemarkInputs.material" size="small" placeholder="如：橡胶木" @keyup.enter="addRemarkDictItem('material')" />
              <el-button size="small" @click="addRemarkDictItem('material')">添加</el-button>
            </div>
          </div>

          <!-- 颜色 -->
          <div class="rdict-group">
            <div class="rdict-group-label">颜色</div>
            <div class="rule-tags">
              <el-tag v-for="item in remarkDictByType('color')" :key="item.value"
                closable size="small" @close="removeRemarkDictItem(item)">{{ item.value }}</el-tag>
            </div>
            <div class="rule-input-row">
              <el-input v-model="newRemarkInputs.color" size="small" placeholder="如：红色" @keyup.enter="addRemarkDictItem('color')" />
              <el-button size="small" @click="addRemarkDictItem('color')">添加</el-button>
            </div>
          </div>

          <!-- 驱动方式 -->
          <div class="rdict-group">
            <div class="rdict-group-label">驱动方式</div>
            <div class="rule-tags">
              <el-tag v-for="item in remarkDictByType('drive_type')" :key="item.value"
                closable size="small" @close="removeRemarkDictItem(item)">{{ item.value }}</el-tag>
            </div>
            <div class="rule-input-row">
              <el-input v-model="newRemarkInputs.drive_type" size="small" placeholder="如：手摇式" @keyup.enter="addRemarkDictItem('drive_type')" />
              <el-button size="small" @click="addRemarkDictItem('drive_type')">添加</el-button>
            </div>
          </div>

          <!-- 尺寸 -->
          <div class="rdict-group">
            <div class="rdict-group-label">尺寸</div>
            <div class="rule-tags">
              <el-tag v-for="item in remarkDictByType('size')" :key="item.value"
                closable size="small" @close="removeRemarkDictItem(item)">
                {{ item.value }} → {{ item.display }}
              </el-tag>
            </div>
            <div class="rule-input-row">
              <el-input v-model="newRemarkInputs.sizeValue" size="small" placeholder="数字（如 120）" style="width:120px" @keyup.enter="addRemarkDictItem('size')" />
              <el-input v-model="newRemarkInputs.sizeDisplay" size="small" placeholder="米制（如 1.2米）" style="width:130px" @keyup.enter="addRemarkDictItem('size')" />
              <el-button size="small" @click="addRemarkDictItem('size')">添加</el-button>
            </div>
          </div>

          <div class="rdict-footer">
            <el-button size="small" type="primary" :loading="remarkDictSaving" @click="saveRemarkDict">保存产品词典</el-button>
          </div>
        </div>

        </div><!-- /rule-lib-body -->

        <!-- 固定底部操作栏 -->
        <div class="rule-lib-footer">
          <el-button size="small" :loading="loading" @click="loadAll(); loadDictSuggestions(true)">刷新</el-button>
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
  height: 560px;
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
  transition: background 0.15s; cursor: pointer;
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
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}
.rule-lib-body {
  flex: 1;
  overflow-y: auto;
  padding: 6px 0 4px;
  min-height: 0;
}
.rule-lib-body::-webkit-scrollbar { width: 4px; }
.rule-lib-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.rule-lib-footer {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 10px 0 2px;
  border-top: 1px solid var(--border);
  background: #fff;
}
.rule-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 10px;
}
.rule-card {
  border: 1px solid var(--border);
  border-left: 3px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  background: #fff;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 0;
}
/* 颜色变体 */
.rule-card--neutral  { border-left-color: #8a7a6a; }
.rule-card--danger   { border-left-color: #e04a4a; background: #fffafa; }
.rule-card--warning  { border-left-color: #e09050; background: #fffaf5; }
.rule-card--success  { border-left-color: #5cb87a; background: #f8fff9; }
.rule-card--synonym  { border-left-color: #5b8dee; background: #f8faff; margin-bottom: 10px; }
.rule-card--ignore       { border-left-color: #8a8a8a; background: #f9f9f7; }
.rule-card--ambiguous    { border-left-color: #e07a20; background: #fffaf5; margin-bottom: 0; }
.rule-card--product-dict { border-left-color: #5b8dee; background: #f8faff; margin-top: 10px; }
.rdict-group {
  margin-top: 10px;
}
.rdict-group-label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 600;
  margin-bottom: 4px;
}
.rdict-footer {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
/* 卡片标题行 */
.rule-card-header {
  display: flex;
  align-items: center;
  gap: 6px;
}
.rule-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.rule-card-count {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  background: #f0ebe4;
  border-radius: 10px;
  padding: 1px 7px;
  line-height: 1.6;
}
.rule-card-desc {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-top: -2px;
}
.rule-input-row {
  display: flex;
  gap: 8px;
  margin-bottom: 0;
}
.rule-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  min-height: 28px;
  max-height: 100px;
  overflow-y: auto;
  padding-right: 2px;
}
.rule-tags::-webkit-scrollbar { width: 4px; }
.rule-tags::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.rule-tags::-webkit-scrollbar-track { background: transparent; }
.rule-card .form-label {
  margin-bottom: 0;
}
.synonym-add-form {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.synonym-add-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 110px;
}
.synonym-add-field.syn-type-field { flex: 0 0 80px; min-width: 80px; }
.syn-label {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1;
  display: flex;
  align-items: center;
  gap: 3px;
}
.syn-type-hint {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  cursor: help;
  user-select: none;
  flex-shrink: 0;
  line-height: 1;
}
.syn-arrow {
  font-size: 14px;
  color: var(--text-secondary);
  padding-bottom: 4px;
  flex-shrink: 0;
}
.syn-add-btn { flex-shrink: 0; }
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
.synonym-item-editing {
  background: #fffaf3;
  gap: 6px;
}
.btn-ok {
  color: #27ae60;
}
.btn-ok:hover { color: #1e8449; }
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

/* ── Tab 红点徽标 ────────────────────────────────── */
.sug-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #e74c3c;
  color: #fff;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 600;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  margin-left: 4px;
  vertical-align: middle;
}
.sug-badge.inline { margin-left: 6px; }

/* ── 词典优化建议区块 ─────────────────────────────── */
.dict-sug-panel {
  border: 1px solid #f0e0c8;
  border-radius: 8px;
  margin-bottom: 12px;
  background: #fffaf4;
  overflow: hidden;
}
.dict-sug-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  background: #fdf3e3;
}
.dict-sug-header:hover { background: #fae8cc; }
.dict-sug-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
}
.dict-sug-toggle {
  font-size: 11px;
  color: var(--text-secondary);
}
.dict-sug-body {
  padding: 8px 12px 12px;
}
.sug-group {
  margin-top: 8px;
}
.sug-group:first-child { margin-top: 0; }
.sug-group-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.sug-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid #f5ebe0;
  flex-wrap: wrap;
}
.sug-row:last-child { border-bottom: none; }
.sug-row--block { flex-direction: column; align-items: stretch; gap: 0; }
.sug-row-main { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 4px 0; }
.sug-split-row {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 8px 10px;
  margin-top: 4px;
  background: #faf7f2;
  border-radius: 6px;
  border: 1px dashed #e0d4c0;
}
.sug-split-field { display: flex; align-items: center; gap: 6px; }
.sug-split-label { font-size: 11px; color: var(--text-muted); white-space: nowrap; }
.sug-row--syn { flex-direction: column; align-items: flex-start; gap: 6px; }
.sug-syn-main { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sug-syn-input { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.sug-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  min-width: 48px;
}
.sug-count {
  font-size: 11px;
  color: var(--accent);
  background: #fdf0e0;
  border-radius: 4px;
  padding: 1px 5px;
  white-space: nowrap;
}
.sug-reason {
  font-size: 11px;
  color: var(--text-secondary);
  flex: 1;
  min-width: 120px;
}
.sug-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
</style>

<style>
/* ── 同义词类型说明 tooltip（挂到 body，需全局样式）── */
.syn-type-tip.el-popper {
  max-width: 340px;
  padding: 0 !important;
}
.syn-tip-body {
  padding: 14px 16px;
  font-size: 12px;
  color: #3a3028;
  line-height: 1.5;
}
.syn-tip-title {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 10px;
  color: #2c2420;
}
.syn-tip-mode {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 6px;
}
.syn-tip-badge {
  flex-shrink: 0;
  padding: 1px 7px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.8;
  white-space: nowrap;
}
.syn-tip-badge--text  { background: #e8e0d4; color: #6b5e4e; }
.syn-tip-badge--regex { background: #fde8c8; color: #c4883a; }
.syn-tip-section {
  font-size: 11px;
  font-weight: 600;
  color: #8a7a6a;
  margin: 12px 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.syn-tip-ex {
  background: #faf7f2;
  border-left: 3px solid #e0d4c0;
  border-radius: 0 6px 6px 0;
  padding: 8px 10px;
  margin-bottom: 8px;
}
.syn-tip-ex-label {
  font-size: 11px;
  color: #8a7a6a;
  margin-bottom: 5px;
}
.syn-tip-ex-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}
.syn-tip-ex-tag {
  flex-shrink: 0;
  font-size: 10px;
  color: #8a7a6a;
  background: #e8e0d4;
  padding: 1px 5px;
  border-radius: 4px;
  white-space: nowrap;
}
.syn-tip-ex code {
  font-size: 12px;
  background: #fff;
  border: 1px solid #e0d4c0;
  border-radius: 4px;
  padding: 1px 6px;
  color: #c4883a;
  font-family: 'Consolas', monospace;
}
.syn-tip-ex-result {
  font-size: 11px;
  color: #6b5e4e;
  margin-top: 5px;
  padding-left: 2px;
}
.syn-tip-tip {
  margin-top: 10px;
  padding: 6px 10px;
  background: #fff8ee;
  border-radius: 6px;
  font-size: 11px;
  color: #c4883a;
  font-weight: 500;
}
</style>
