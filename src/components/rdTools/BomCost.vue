<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, watch, onMounted, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Upload, Search, Delete, Plus, Close, Setting,
} from '@element-plus/icons-vue'
import http from '@/api/http'

// ── 响应式状态 ────────────────────────────────────
const subTab = ref('snapshots')    // snapshots | nodes | estimate

// ─── 快照管理 ─────────────────────────────────────
const snapshots        = ref([])
const snapshotTotal    = ref(0)
const snapshotPage     = ref(1)
const snapshotsLoading = ref(false)
// BOM 详情对话框（成本快照 Tab 里用）
const bomDialogVisible   = ref(false)
const bomDialogLoading   = ref(false)
const bomDialogSku       = ref(null)      // 当前查看的 SKU 行
const bomDialogTree      = ref([])        // 原始树（含 children）
const bomDialogCollapsed = reactive(new Set())  // 已折叠的半成品 child_code

// 扁平化 BOM 树（计算属性，受折叠状态控制）
const bomDialogFlat = computed(() => {
  const flat = []
  function walk(nodes, depth, parentSeq) {
    nodes.forEach((n, i) => {
      const seq = parentSeq ? `${parentSeq}.${i + 1}` : String(i + 1)
      flat.push({ ...n, _depth: depth, _seq: seq })
      const isSemi = n.child_node_type === 'semi'
      if (isSemi && !bomDialogCollapsed.has(n.child_code)) {
        if (n.children?.length) walk(n.children, depth + 1, seq)
      }
    })
  }
  walk(bomDialogTree.value, 0, '')
  return flat
})

// BOM 详情合计（顶层行的 total_price 之和）
const bomDialogTotal = computed(() => {
  return bomDialogTree.value.reduce((s, n) => s + (n.total_price || 0), 0)
})

// 导入对话框（两步：选文件→预览→确认导入）
const importVisible   = ref(false)
const importFile      = ref(null)
const importFileName  = ref('')
const importForm      = ref({ snapshot_date: '', notes: '' })
const importStep      = ref('form')   // 'form' | 'preview' | 'done'
const previewing      = ref(false)
const previewData     = ref(null)     // { order_no, sku_count, skus, warnings }
const importing       = ref(false)
const importResult    = ref(null)
// 预览树状态
const purchasedSemis = reactive({})  // { child_code: true } → 用户标记为外购半成品
const skuExpanded   = ref({})        // { finished_code: bool }

// ─── 预览 BOM 树（扁平化 + 展开/收拢）────────────
const previewCollapsed  = reactive(new Set())  // 已收拢节点的 key（child_code|sku_code）
const selectedSkuCodes  = ref(new Set())       // 预览时勾选要导入的 SKU finished_code 集合

const skuFlatTrees = computed(() => {
  if (!previewData.value) return []
  return previewData.value.skus.map(sku => {
    // 1. 检测半成品：在其他行中作为 parent_code 出现的 child_code
    const semiCodes = new Set()
    const lines = sku.lines || []
    lines.forEach(l => {
      if (l.parent_code && l.parent_code !== sku.finished_code) semiCodes.add(l.parent_code)
    })
    // 2. 按 parent_code 分组
    const byParent = {}
    lines.forEach(l => {
      const pc = l.parent_code || sku.finished_code
      ;(byParent[pc] ??= []).push(l)
    })
    // 3. 计算衍生合计（半成品无价格时 = 子件合计）
    function derivedTotal(parentCode, visited) {
      if (visited.has(parentCode)) return 0
      const v2 = new Set(visited); v2.add(parentCode)
      return (byParent[parentCode] || []).reduce((s, l) => {
        if (semiCodes.has(l.child_code)) return s + derivedTotal(l.child_code, v2)
        return s + ((l.unit_price || 0) * (l.quantity || 0))
      }, 0)
    }
    // 4. 生成可见行（受折叠状态控制）
    const visible = []
    function walk(parentCode, depth, visited, parentSeq) {
      if (visited.has(parentCode)) return
      const v2 = new Set(visited); v2.add(parentCode)
      let idx = 1
      for (const l of byParent[parentCode] || []) {
        const seq     = parentSeq ? `${parentSeq}.${idx}` : String(idx)
        const isSemi  = semiCodes.has(l.child_code)
        const hasKids = (byParent[l.child_code] || []).length > 0
        const nodeKey       = l.child_code + '|' + sku.finished_code
        const isPurchased   = isSemi && !!purchasedSemis[l.child_code]
        const dTotal        = (isSemi && !isPurchased)
          ? derivedTotal(l.child_code, new Set([parentCode]))
          : ((l.unit_price || 0) * (l.quantity || 0))
        visible.push({ ...l, _depth: depth, _key: nodeKey, _hasKids: hasKids, is_semi: isSemi, _isPurchasedSemi: isPurchased, _dTotal: dTotal, _sku_code: sku.finished_code, _seq: seq })
        if (hasKids && !previewCollapsed.has(nodeKey)) walk(l.child_code, depth + 1, v2, seq)
        idx++
      }
    }
    walk(sku.finished_code, 0, new Set(), '')
    return { ...sku, visible }
  })
})

function toggleSku(fc) {
  skuExpanded.value[fc] = !(skuExpanded.value[fc] ?? true)
}
function toggleNode(key) {
  if (previewCollapsed.has(key)) previewCollapsed.delete(key)
  else previewCollapsed.add(key)
}
function displayName(row) {
  return [row.child_name, row.child_spec].filter(Boolean).join('  ')
}
function onPriceEdit(row, val) {
  const price = parseFloat(val) || 0
  const sku = previewData.value?.skus.find(s => s.finished_code === row._sku_code)
  if (!sku) return
  const line = sku.lines.find(l => l.child_code === row.child_code && l.parent_code === row.parent_code)
  if (!line) return
  line.unit_price  = price
  line.total_price = price * (line.quantity || 0)
  // 触发 computed 重新计算
  previewData.value = { ...previewData.value }
}

// BOM 树抽屉（物料查询里用）
const bomDrawerVisible = ref(false)
const bomDrawerLoading = ref(false)
const activeSku        = ref(null)
const bomTree          = ref([])


// ─── 物料节点查询 ──────────────────────────────────
const nodeSearchQ     = ref('')
const nodeList        = ref([])
const nodeTotal       = ref(0)
const nodePage        = ref(1)
const nodesLoading    = ref(false)
const nodeTypeFilter  = ref('material')

// 节点详情抽屉
const nodeDrawerVisible = ref(false)
const nodeDrawerLoading = ref(false)
const nodeDrawerWidth   = ref(780)   // 默认宽度 px

function onDrawerResizeStart(e) {
  e.preventDefault()
  const startX  = e.clientX
  const startW  = nodeDrawerWidth.value
  function onMove(ev) {
    const delta = startX - ev.clientX   // 从右侧拖，向左拖 = 增大
    nodeDrawerWidth.value = Math.max(400, Math.min(window.innerWidth - 60, startW + delta))
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}
const activeNode        = ref(null)
const priceHistory      = ref([])
const nodeUsages        = ref([])
const nodeDetailTab     = ref('info')
// 物料价格记录
const materialPrices     = ref([])
const priceFormVisible   = ref(false)
const priceForm          = ref({ unit_price: '', price_date: '', supplier_name: '', notes: '' })
const priceSaving        = ref(false)

// 供应商表单
const supplierFormVisible = ref(false)
const supplierForm        = ref({ supplier_name: '', unit_price: '', price_date: '', is_preferred: false, notes: '' })
const supplierSaving      = ref(false)

// ─── 成本预估 ─────────────────────────────────────
const estimateMode    = ref('ref')   // ref | free
// 参考模式
const refSkuOptions   = ref([])
const refSkuLoading   = ref(false)
const selectedRefSku  = ref(null)
const refBomTree      = ref([])
const refBomFlat      = ref([])   // 扁平化后可编辑的行
// 自由模式
const freeLines       = ref([])   // [{ name, code, quantity, unit_price, purchase_type, is_new }]
const freeSearchQ     = ref('')
const freeSearchRes   = ref([])
const freeSearching   = ref(false)
// 汇总
const estimateTotal   = computed(() => {
  const lines = estimateMode.value === 'ref' ? refBomFlat.value : freeLines.value
  return lines.reduce((s, r) => s + (parseFloat(r.quantity) || 0) * (parseFloat(r.unit_price) || 0), 0)
})
const estimatePurchaseTotal = computed(() => {
  const lines = estimateMode.value === 'ref' ? refBomFlat.value : freeLines.value
  return lines
    .filter(r => !r.purchase_type?.includes('自制'))
    .reduce((s, r) => s + (parseFloat(r.quantity) || 0) * (parseFloat(r.unit_price) || 0), 0)
})
const estimateSelfTotal = computed(() => estimateTotal.value - estimatePurchaseTotal.value)

// ─── 列名配置 ─────────────────────────────────────
const colAliasVisible = ref(false)
const colAliasLoading = ref(false)
const colAliasSaving  = ref(false)
// 可编辑的别名（每个字段一个逗号分隔的字符串）
const colAliasForm = ref({})
// 字段的中文标签
const COL_ALIAS_LABELS = {
  finished_code: '主件品号（成品品号）',
  finished_name: '主件品名',
  finished_spec: '主件规格',
  parent_code:   '品号（BOM父件）',
  parent_name:   '品名',
  parent_spec:   '规格',
  seq:           '序号',
  quantity:      '组成用量',
  child_code:    '元件品号',
  child_std_code:'标准号',
  child_name:    '元件品名',
  child_spec:    '元件规格',
  child_category:'元件品名分类',
  unit_price:    '单价',
  total_price:   '金额/总价',
}

async function openColAliasDialog() {
  colAliasVisible.value = true
  colAliasLoading.value = true
  const res = await http.get('/api/rd/cost/col-aliases')
  colAliasLoading.value = false
  if (res.success) {
    // 转为逗号分隔字符串
    const form = {}
    for (const [k, v] of Object.entries(res.data)) {
      form[k] = Array.isArray(v) ? v.join('，') : v
    }
    colAliasForm.value = form
  }
}

async function saveColAliases() {
  colAliasSaving.value = true
  // 转回数组（按中文逗号或英文逗号分割）
  const payload = {}
  for (const [k, v] of Object.entries(colAliasForm.value)) {
    payload[k] = String(v || '').split(/[,，]/).map(s => s.trim()).filter(Boolean)
  }
  const res = await http.put('/api/rd/cost/col-aliases', payload)
  colAliasSaving.value = false
  if (res.success) {
    ElMessage.success('已保存')
    colAliasVisible.value = false
  } else {
    ElMessage.error(res.message)
  }
}

// ── 生命周期 ──────────────────────────────────────
onMounted(() => {
  loadSnapshots()
})

watch(subTab, (val) => {
  if (val === 'snapshots' && snapshots.value.length === 0) loadSnapshots()
  if (val === 'nodes' && nodeList.value.length === 0) loadNodes()
})

// ─────────────────────────────────────────────────
// 快照管理方法
// ─────────────────────────────────────────────────

async function loadSnapshots() {
  snapshotsLoading.value = true
  const res = await http.get('/api/rd/cost/snapshots', {
    params: { page: snapshotPage.value, per_page: 30 },
  })
  snapshotsLoading.value = false
  if (res.success) {
    snapshots.value     = res.data.items
    snapshotTotal.value = res.data.total
  }
}

async function openBomDialog(row) {
  bomDialogSku.value     = row
  bomDialogTree.value    = []
  bomDialogCollapsed.clear()
  bomDialogVisible.value = true
  bomDialogLoading.value = true
  const res = await http.get(`/api/rd/cost/sku/${row.sku_id}/bom`)
  bomDialogLoading.value = false
  if (res.success) {
    bomDialogTree.value = res.data.tree || []
    // 默认折叠所有半成品节点
    function collectSemis(nodes) {
      for (const n of nodes) {
        if (n.child_node_type === 'semi') {
          bomDialogCollapsed.add(n.child_code)
          if (n.children?.length) collectSemis(n.children)
        }
      }
    }
    collectSemis(bomDialogTree.value)
  }
}

function toggleBomNode(childCode) {
  if (bomDialogCollapsed.has(childCode)) bomDialogCollapsed.delete(childCode)
  else bomDialogCollapsed.add(childCode)
}

function openImportDialog() {
  importFile.value     = null
  importFileName.value = ''
  importForm.value     = { snapshot_date: '', notes: '' }
  importStep.value     = 'form'
  previewData.value    = null
  importResult.value   = null
  importVisible.value  = true
}

function handleFileChange(uploadFile) {
  importFile.value     = uploadFile.raw
  importFileName.value = uploadFile.name
}

async function doPreview() {
  if (!importFile.value) {
    ElMessage.warning('请先选择 Excel 文件')
    return
  }
  previewing.value = true
  const fd = new FormData()
  fd.append('file', importFile.value)
  const res = await http.post('/api/rd/cost/preview', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  previewing.value = false

  if (res.success) {
    previewData.value = res.data
    // 从订单号中提取的建议日期自动填入（用户未手填时）
    if (res.data.suggested_date && !importForm.value.snapshot_date) {
      importForm.value.snapshot_date = res.data.suggested_date
    }
    if (res.data.order_no && !importForm.value.notes) {
      importForm.value.notes = res.data.order_no
    }
    // 初始化展开状态 & 清空外购半成品标记（默认全部折叠）
    Object.keys(purchasedSemis).forEach(k => delete purchasedSemis[k])
    const expanded = {}
    const allCodes = new Set()
    res.data.skus.forEach(sku => {
      expanded[sku.finished_code] = false
      allCodes.add(sku.finished_code)
    })
    skuExpanded.value = expanded
    selectedSkuCodes.value = allCodes   // 默认全选
    importStep.value = 'preview'
  } else {
    ElMessage.error(res.message || '预览失败')
  }
}

async function doImport() {
  importing.value = true
  const purchasedSemiCodes = Object.entries(purchasedSemis).filter(([, v]) => v).map(([k]) => k)
  const selectedSkus = previewData.value.skus.filter(s => selectedSkuCodes.value.has(s.finished_code))
  const res = await http.post('/api/rd/cost/import', {
    preview_data:  { ...previewData.value, skus: selectedSkus, purchased_semi_codes: purchasedSemiCodes },
    snapshot_date: importForm.value.snapshot_date || '',
    notes:         importForm.value.notes || '',
  })
  importing.value = false

  if (res.success) {
    importResult.value = res.data
    importStep.value   = 'done'
    loadSnapshots()
  } else {
    ElMessage.error(res.message || '导入失败')
  }
}

async function deleteSnapshot(order) {
  const label = order.order_no || order.snapshot_date || 'BOM'
  await ElMessageBox.confirm(
    `确认删除订单「${label}」的 BOM 数据？此操作不可撤销。`,
    '确认删除', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
  )
  const res = await http.delete(`/api/rd/cost/skus/${order.sku_id}`)
  if (res.success) {
    ElMessage.success('已删除')
    loadSnapshots()
  } else {
    ElMessage.error(res.message)
  }
}

async function openBomDrawer(sku) {
  activeSku.value     = sku
  bomDrawerVisible.value = true
  bomDrawerLoading.value = true
  const res = await http.get(`/api/rd/cost/sku/${sku.id}/bom`)
  bomDrawerLoading.value = false
  if (res.success) {
    bomTree.value = res.data.tree
  }
}

// ─────────────────────────────────────────────────
// 物料节点方法
// ─────────────────────────────────────────────────

async function loadNodes() {
  nodesLoading.value = true
  const res = await http.get('/api/rd/cost/nodes', {
    params: { q: nodeSearchQ.value, page: nodePage.value, per_page: 30, node_type: nodeTypeFilter.value },
  })
  nodesLoading.value = false
  if (res.success) {
    nodeList.value  = res.data.items
    nodeTotal.value = res.data.total
  }
}

function doNodeSearch() {
  nodePage.value = 1
  loadNodes()
}

async function openNodeDrawer(node) {
  activeNode.value      = { ...node }
  nodeDrawerVisible.value = true
  nodeDrawerLoading.value = true
  nodeDetailTab.value   = 'info'
  priceHistory.value    = []
  nodeUsages.value      = []
  materialPrices.value  = []

  const [detailRes, usageRes, pricesRes] = await Promise.all([
    http.get(`/api/rd/cost/nodes/${node.id}`),
    http.get(`/api/rd/cost/nodes/${node.id}/usages`),
    http.get(`/api/rd/cost/nodes/${node.id}/prices`),
  ])
  nodeDrawerLoading.value = false

  if (detailRes.success)  activeNode.value = detailRes.data
  if (usageRes.success)   nodeUsages.value = usageRes.data
  if (pricesRes.success)  materialPrices.value = pricesRes.data.map(p => ({ ...p, _supplierDraft: p.supplier_name || '' }))
}

async function addMaterialPrice() {
  if (!priceForm.value.unit_price) { ElMessage.warning('请填写单价'); return }
  priceSaving.value = true
  const res = await http.post(`/api/rd/cost/nodes/${activeNode.value.id}/prices`, {
    unit_price:    parseFloat(priceForm.value.unit_price),
    price_date:    priceForm.value.price_date || '',
    supplier_name: priceForm.value.supplier_name || '',
    notes:         priceForm.value.notes || '',
  })
  priceSaving.value = false
  if (res.success) {
    materialPrices.value.unshift({ ...res.data, _supplierDraft: res.data.supplier_name || '' })
    priceFormVisible.value = false
    priceForm.value = { unit_price: '', price_date: '', supplier_name: '', notes: '' }
    ElMessage.success('已添加')
  } else {
    ElMessage.error(res.message)
  }
}

async function confirmPriceSupplier(row) {
  const newVal = row._supplierDraft || ''
  const res = await http.patch(`/api/rd/cost/prices/${row.id}`, { supplier_name: newVal })
  if (res.success) {
    row.supplier_name = newVal
    // 同步更新 BOM 详情对话框里相同 node 的供应商列
    if (bomDialogFlat.value.length && activeNode.value) {
      const nodeCode = activeNode.value.code
      bomDialogTree.value.forEach(function patch(n) {
        if (n.child_code === nodeCode) n.supplier_name = newVal
        if (n.children?.length) n.children.forEach(patch)
      })
    }
    ElMessage.success('供应商已更新')
  } else {
    ElMessage.error(res.message)
  }
}

async function deleteMaterialPrice(row) {
  await ElMessageBox.confirm('确认删除该价格记录？', '确认', {
    type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
  })
  const res = await http.delete(`/api/rd/cost/prices/${row.id}`)
  if (res.success) {
    materialPrices.value = materialPrices.value.filter(p => p.id !== row.id)
    ElMessage.success('已删除')
  } else {
    ElMessage.error(res.message)
  }
}

async function saveNodePatch() {
  const n = activeNode.value
  if (!n) return
  const res = await http.patch(`/api/rd/cost/nodes/${n.id}`, {
    is_purchased_semi: n.is_purchased_semi,
    notes:             n.notes,
  })
  if (res.success) {
    ElMessage.success('已保存')
    loadNodes()
  } else {
    ElMessage.error(res.message)
  }
}

// 供应商操作
function openSupplierForm() {
  supplierForm.value = { supplier_name: '', unit_price: '', price_date: '', is_preferred: false, notes: '' }
  supplierFormVisible.value = true
}

async function saveSupplier() {
  if (!supplierForm.value.supplier_name || !supplierForm.value.unit_price) {
    ElMessage.warning('供应商名称和单价不能为空')
    return
  }
  supplierSaving.value = true
  const res = await http.post('/api/rd/cost/suppliers', {
    node_id: activeNode.value.id,
    ...supplierForm.value,
  })
  supplierSaving.value = false
  if (res.success) {
    ElMessage.success('已添加')
    supplierFormVisible.value = false
    // 刷新节点详情
    const detailRes = await http.get(`/api/rd/cost/nodes/${activeNode.value.id}`)
    if (detailRes.success) activeNode.value = detailRes.data
  } else {
    ElMessage.error(res.message)
  }
}

async function deleteSupplier(supplier) {
  await ElMessageBox.confirm(`确认删除供应商「${supplier.supplier_name}」的报价？`, '确认', {
    type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
  })
  const res = await http.delete(`/api/rd/cost/suppliers/${supplier.id}`)
  if (res.success) {
    ElMessage.success('已删除')
    const detailRes = await http.get(`/api/rd/cost/nodes/${activeNode.value.id}`)
    if (detailRes.success) activeNode.value = detailRes.data
  }
}

async function togglePreferred(supplier) {
  const res = await http.patch(`/api/rd/cost/suppliers/${supplier.id}`, {
    is_preferred: !supplier.is_preferred,
  })
  if (res.success) {
    const detailRes = await http.get(`/api/rd/cost/nodes/${activeNode.value.id}`)
    if (detailRes.success) activeNode.value = detailRes.data
  }
}

// ─────────────────────────────────────────────────
// 成本预估方法
// ─────────────────────────────────────────────────

// 参考模式：搜索 SKU
async function searchRefSku(query) {
  if (!query) {
    refSkuOptions.value = []
    return
  }
  refSkuLoading.value = true
  // 从快照中搜索匹配的 SKU
  const res = await http.get('/api/rd/cost/nodes', { params: { q: query, node_type: 'finished', per_page: 20 } })
  refSkuLoading.value = false
  if (res.success) {
    refSkuOptions.value = res.data.items
  }
}

async function onRefSkuSelect(node) {
  if (!node) return
  // 找到该节点最新的 SKU
  const usageRes = await http.get(`/api/rd/cost/nodes/${node.id}/usages`)
  if (!usageRes.success || !usageRes.data.length) {
    ElMessage.warning('未找到该产品的 BOM 记录')
    return
  }
  // 取最新的 sku_id
  const latestUsage = usageRes.data[0]
  const bomRes = await http.get(`/api/rd/cost/sku/${latestUsage.sku_id}/bom`)
  if (!bomRes.success) return

  selectedRefSku.value = bomRes.data.sku
  refBomTree.value     = bomRes.data.tree

  // 扁平化为可编辑行（仅叶节点物料行）
  const flat = []
  function flatten(nodes) {
    for (const n of nodes) {
      if (n.child_node_type === 'material') {
        flat.push({
          _key:         n.id,
          parent_name:  n.parent_name,
          child_code:   n.child_code,
          child_name:   n.child_name,
          purchase_type: n.child_purchase_type,
          quantity:     n.quantity,
          unit_price:   n.unit_price,
          total_price:  n.total_price,
        })
      }
      if (n.children?.length) flatten(n.children)
    }
  }
  flatten(refBomTree.value)
  refBomFlat.value = flat
}

function recalcRefLine(row) {
  row.total_price = (parseFloat(row.quantity) || 0) * (parseFloat(row.unit_price) || 0)
}

// 自由模式：搜索物料
async function searchFreeMaterial(q) {
  if (!q || q.length < 2) {
    freeSearchRes.value = []
    return
  }
  freeSearching.value = true
  const res = await http.get('/api/rd/cost/nodes', { params: { q, per_page: 20 } })
  freeSearching.value = false
  if (res.success) freeSearchRes.value = res.data.items
}

function addFreeLineFromSearch(node) {
  freeLines.value.push({
    _key:         Date.now(),
    child_code:   node.code,
    child_name:   node.name,
    purchase_type: node.purchase_type || '',
    quantity:     1,
    unit_price:   node.latest_price || 0,
    is_new:       false,
  })
  freeSearchQ.value   = ''
  freeSearchRes.value = []
}

function addFreeLineNew() {
  freeLines.value.push({
    _key:         Date.now(),
    child_code:   '',
    child_name:   '新物料',
    purchase_type: '采购件',
    quantity:     1,
    unit_price:   0,
    is_new:       true,
  })
}

function removeFreeLine(idx) {
  freeLines.value.splice(idx, 1)
}

function copyEstimate() {
  const lines = estimateMode.value === 'ref' ? refBomFlat.value : freeLines.value
  const text = lines.map(r =>
    `${r.child_name}\t×${r.quantity}\t￥${r.unit_price}\t小计￥${((parseFloat(r.quantity)||0)*(parseFloat(r.unit_price)||0)).toFixed(2)}`
  ).join('\n') + `\n\n合计：￥${estimateTotal.value.toFixed(2)}`
  navigator.clipboard.writeText(text).then(() => ElMessage.success('已复制'))
}
</script>

<template>
  <div class="bom-cost">
    <!-- ── 子 Tab 切换 ───────────────────────────── -->
    <div class="sub-nav">
      <button
        v-for="t in [
          { key: 'snapshots', label: '成本快照' },
          { key: 'nodes',     label: '物料查询' },
          { key: 'estimate',  label: '成本预估' },
        ]"
        :key="t.key"
        class="sub-nav-item"
        :class="{ active: subTab === t.key }"
        @click="subTab = t.key"
      >{{ t.label }}</button>
      <div class="sub-nav-spacer"/>
      <button class="sub-nav-config" title="配置 Excel 列名映射" @click="openColAliasDialog">
        <el-icon><Setting /></el-icon> 列名配置
      </button>
    </div>

    <!-- ═══════════════════════════════════════════ -->
    <!-- Tab 1：成本快照                             -->
    <!-- ═══════════════════════════════════════════ -->
    <div v-show="subTab === 'snapshots'" class="panel">
      <div class="toolbar">
        <el-button type="primary" :icon="Upload" @click="openImportDialog">导入 BOM 成本 Excel</el-button>
      </div>

      <el-table
        :data="snapshots"
        v-loading="snapshotsLoading"
        size="small"
        class="cost-table"
        row-class-name="table-row"
        row-key="finished_code"
      >
        <el-table-column prop="finished_code" label="产成品编码" width="150" />
        <el-table-column prop="finished_name" label="产成品名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="订单号 / BOM详情" min-width="260">
          <template #default="{ row }">
            <div class="order-tags">
              <el-tag
                v-for="order in row.orders"
                :key="order.sku_id"
                size="small"
                class="order-tag"
                @click="openBomDialog({ ...order, finished_code: row.finished_code, finished_name: row.finished_name })"
              >{{ order.order_no || '（无订单号）' }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" fixed="right">
          <template #default="{ row }">
            <el-dropdown trigger="click" @command="deleteSnapshot">
              <el-button link size="small" type="danger">删除</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="order in row.orders"
                    :key="order.sku_id"
                    :command="order"
                  >删除「{{ order.order_no || order.snapshot_date }}」</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>

      <!-- BOM 详情对话框 -->
      <el-dialog
        v-model="bomDialogVisible"
        :title="bomDialogSku ? `BOM 详情 — ${bomDialogSku.finished_code} ${bomDialogSku.finished_name}${bomDialogSku.order_no ? '　订单：' + bomDialogSku.order_no : ''}` : 'BOM 详情'"
        width="90vw"
        style="max-height:90vh"
        destroy-on-close
      >
        <div class="bom-dialog-body">
          <div v-if="bomDialogLoading" class="bom-dialog-loading">加载中…</div>
          <template v-else-if="bomDialogFlat.length">
            <table class="bom-inline-table bom-dialog-table">
              <thead>
                <tr>
                  <th style="width:70px">序号</th>
                  <th style="width:150px">品号</th>
                  <th>品名规格</th>
                  <th style="width:140px">物料分类</th>
                  <th style="width:120px">供应商</th>
                  <th style="width:70px;text-align:center">用量</th>
                  <th style="width:110px;text-align:right">单价 (¥)</th>
                  <th style="width:110px;text-align:right">合计 (¥)</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(line, idx) in bomDialogFlat"
                  :key="idx"
                  :class="{
                    'bom-semi-row': line.child_node_type === 'semi',
                    'bom-purchased-row': line.child_is_purchased_semi,
                    'bom-depth0-row': line._depth === 0,
                  }"
                >
                  <td class="bom-col-seq bom-text-black">{{ line._seq }}</td>
                  <td class="bom-col-code">
                    <span class="bom-code-link" @click="openNodeDrawer({ id: line.child_node_id, code: line.child_code })">{{ line.child_code_with_version || line.child_code }}</span>
                  </td>
                  <td class="bom-col-name bom-text-black" :style="{ paddingLeft: line._depth * 1.5 + 0.5 + 'em' }">
                    <template v-if="line.child_node_type === 'semi' && line.children?.length">
                      <span class="bom-toggle" @click="toggleBomNode(line.child_code)">
                        {{ bomDialogCollapsed.has(line.child_code) ? '▶' : '▼' }}
                      </span>
                    </template>
                    {{ line.child_name }}
                    <span v-if="line.child_spec" class="bom-spec">{{ line.child_spec }}</span>
                    <el-tag v-if="line.child_is_purchased_semi" size="small" type="warning" style="margin-left:4px;vertical-align:middle">外购</el-tag>
                  </td>
                  <td class="bom-col-category bom-text-black">{{ line.material_category || '—' }}</td>
                  <td class="bom-col-supplier bom-text-black">{{ line.supplier_name || '—' }}</td>
                  <td class="bom-col-qty bom-text-black">{{ line.quantity }}</td>
                  <td class="bom-col-price">{{ line.unit_price != null ? '¥' + Number(line.unit_price).toFixed(4) : '—' }}</td>
                  <td class="bom-col-total">{{ line.total_price != null ? '¥' + Number(line.total_price).toFixed(2) : '—' }}</td>
                </tr>
              </tbody>
              <tfoot>
                <tr class="bom-total-row">
                  <td colspan="7" style="text-align:right;font-weight:700;padding-right:12px">BOM 合计</td>
                  <td class="bom-col-total">¥{{ bomDialogTotal.toFixed(2) }}</td>
                </tr>
              </tfoot>
            </table>
          </template>
          <div v-else class="empty-tip" style="padding:24px 0">暂无 BOM 明细</div>
        </div>
      </el-dialog>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="snapshotPage"
          :total="snapshotTotal"
          :page-size="30"
          layout="total, prev, pager, next"
          size="small"
          @current-change="loadSnapshots"
        />
      </div>
    </div>

    <!-- ═══════════════════════════════════════════ -->
    <!-- Tab 2：物料查询                             -->
    <!-- ═══════════════════════════════════════════ -->
    <div v-show="subTab === 'nodes'" class="panel">
      <div class="toolbar">
        <el-input
          v-model="nodeSearchQ"
          placeholder="搜索品号 / 品名"
          clearable
          style="width: 240px"
          @keyup.enter="doNodeSearch"
        >
          <template #append>
            <el-button :icon="Search" @click="doNodeSearch" />
          </template>
        </el-input>
        <el-select
          v-model="nodeTypeFilter"
          placeholder="全部类型"
          clearable
          style="width: 110px"
          @change="doNodeSearch"
        >
          <el-option label="原材料" value="material" />
          <el-option label="半成品" value="semi" />
          <el-option label="成品"   value="finished" />
        </el-select>
      </div>

      <el-table
        :data="nodeList"
        v-loading="nodesLoading"
        size="small"
        class="cost-table"
        row-class-name="table-row"
      >
        <el-table-column prop="material_category" label="物料分类" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="{ 'text-muted': !row.material_category }">{{ row.material_category || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="品号" min-width="130" />
        <el-table-column prop="name" label="品名" min-width="160" show-overflow-tooltip />
        <el-table-column label="最新单价" width="110" align="right">
          <template #default="{ row }">
            <span v-if="row.latest_price != null" class="price-val">¥{{ row.latest_price.toFixed(4) }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" @click="openNodeDrawer(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="nodePage"
          :total="nodeTotal"
          :page-size="30"
          layout="total, prev, pager, next"
          size="small"
          @current-change="loadNodes"
        />
      </div>
    </div>

    <!-- ═══════════════════════════════════════════ -->
    <!-- Tab 3：成本预估                             -->
    <!-- ═══════════════════════════════════════════ -->
    <div v-show="subTab === 'estimate'" class="panel estimate-panel">
      <!-- 模式切换 -->
      <div class="toolbar estimate-toolbar">
        <el-radio-group v-model="estimateMode" size="small">
          <el-radio-button value="ref">基于已有 SKU</el-radio-button>
          <el-radio-button value="free">自由组合</el-radio-button>
        </el-radio-group>
        <el-button size="small" @click="copyEstimate">复制结果</el-button>
      </div>

      <!-- 参考模式 -->
      <template v-if="estimateMode === 'ref'">
        <div class="ref-search-bar">
          <span class="ref-label">参考产品：</span>
          <el-select
            v-model="selectedRefSku"
            filterable remote clearable
            placeholder="输入成品品号或品名搜索…"
            :remote-method="searchRefSku"
            :loading="refSkuLoading"
            value-key="id"
            style="width: 320px"
            @change="onRefSkuSelect"
          >
            <el-option
              v-for="n in refSkuOptions"
              :key="n.id"
              :label="`${n.code}  ${n.name}`"
              :value="n"
            />
          </el-select>
          <span v-if="selectedRefSku" class="ref-hint">（单价可修改，实时重算）</span>
        </div>

        <el-table
          v-if="refBomFlat.length"
          :data="refBomFlat"
          size="small"
          class="cost-table estimate-table"
        >
          <el-table-column prop="parent_name"  label="所属半成品" width="130" show-overflow-tooltip />
          <el-table-column prop="child_code"   label="品号"       width="120" />
          <el-table-column prop="child_name"   label="品名"       min-width="140" show-overflow-tooltip />
          <el-table-column prop="purchase_type" label="类型"      width="80" />
          <el-table-column label="数量" width="80" align="center">
            <template #default="{ row }">
              <el-input-number
                v-model="row.quantity" size="small"
                :min="0" :precision="4" :controls="false"
                style="width: 70px"
                @change="recalcRefLine(row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="单价 (¥)" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.unit_price" size="small"
                :min="0" :precision="4" :controls="false"
                style="width: 100px"
                @change="recalcRefLine(row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="小计 (¥)" width="100" align="right">
            <template #default="{ row }">
              <span class="price-val">{{ ((parseFloat(row.quantity)||0)*(parseFloat(row.unit_price)||0)).toFixed(2) }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div v-else-if="selectedRefSku" class="empty-tip">无物料明细</div>
        <div v-else class="empty-tip">请先选择参考产品</div>
      </template>

      <!-- 自由模式 -->
      <template v-else>
        <div class="free-add-bar">
          <el-autocomplete
            v-model="freeSearchQ"
            :fetch-suggestions="(q, cb) => { searchFreeMaterial(q).then(() => cb(freeSearchRes.map(n => ({ value: n.name + ' ' + n.code, node: n })))) }"
            placeholder="搜索已有物料添加…"
            clearable
            style="width: 280px"
            @select="({ node }) => addFreeLineFromSearch(node)"
          />
          <el-button size="small" :icon="Plus" @click="addFreeLineNew">手填新物料</el-button>
        </div>

        <el-table
          :data="freeLines"
          size="small"
          class="cost-table estimate-table"
        >
          <el-table-column label="品号" width="130">
            <template #default="{ row }">
              <el-input v-model="row.child_code" size="small" :disabled="!row.is_new" />
            </template>
          </el-table-column>
          <el-table-column label="品名" min-width="140">
            <template #default="{ row }">
              <el-input v-model="row.child_name" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="采购类型" width="100">
            <template #default="{ row }">
              <el-select v-model="row.purchase_type" size="small" style="width: 90px">
                <el-option label="采购件" value="采购件" />
                <el-option label="自制件" value="自制件" />
                <el-option label="3D打印" value="3D打印" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="数量" width="90" align="center">
            <template #default="{ row }">
              <el-input-number
                v-model="row.quantity" size="small"
                :min="0" :precision="4" :controls="false"
                style="width: 80px"
              />
            </template>
          </el-table-column>
          <el-table-column label="单价 (¥)" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.unit_price" size="small"
                :min="0" :precision="4" :controls="false"
                style="width: 100px"
              />
            </template>
          </el-table-column>
          <el-table-column label="小计 (¥)" width="100" align="right">
            <template #default="{ row }">
              <span class="price-val">{{ ((parseFloat(row.quantity)||0)*(parseFloat(row.unit_price)||0)).toFixed(2) }}</span>
            </template>
          </el-table-column>
          <el-table-column width="50" fixed="right">
            <template #default="{ $index }">
              <el-button link size="small" type="danger" :icon="Close" @click="removeFreeLine($index)" />
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!freeLines.length" class="empty-tip">搜索物料或手填新物料来开始预估</div>
      </template>

      <!-- 汇总栏 -->
      <div v-if="(estimateMode === 'ref' && refBomFlat.length) || (estimateMode === 'free' && freeLines.length)" class="estimate-summary">
        <span>采购件：<b>¥{{ estimatePurchaseTotal.toFixed(2) }}</b></span>
        <span>自制件：<b>¥{{ estimateSelfTotal.toFixed(2) }}</b></span>
        <span class="total-label">合计：<b class="total-val">¥{{ estimateTotal.toFixed(2) }}</b></span>
      </div>
    </div>


    <!-- ═══════════════════════════════════════════ -->
    <!-- 导入对话框（两步）                           -->
    <!-- ═══════════════════════════════════════════ -->
    <el-dialog
      v-model="importVisible"
      :title="importStep === 'preview' ? '预览内容确认' : importStep === 'done' ? '导入完成' : '导入 BOM 成本 Excel'"
      :width="importStep === 'preview' ? '90%' : '600px'"
      :close-on-click-modal="false"
    >
      <!-- Step 1: 选文件 + 填写信息 -->
      <div v-if="importStep === 'form'" class="import-form">
        <div class="import-file-row">
          <el-upload
            :auto-upload="false"
            :limit="1"
            accept=".xlsx,.xls"
            :show-file-list="false"
            :on-change="handleFileChange"
          >
            <el-button size="small" :icon="Upload">选择 Excel 文件</el-button>
          </el-upload>
          <span class="file-name-display" :class="{ 'has-file': !!importFileName }">
            {{ importFileName || '未选择文件（支持 .xlsx / .xls）' }}
          </span>
        </div>
        <el-form :model="importForm" label-width="80px" size="small" style="margin-top: 16px">
          <el-form-item label="核算日期">
            <el-date-picker
              v-model="importForm.snapshot_date"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择核算日期"
              style="width: 200px"
            />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="importForm.notes" placeholder="可选备注" style="width: 100%" />
          </el-form-item>
        </el-form>
      </div>

      <!-- Step 2: 预览（BOM 树结构） -->
      <div v-else-if="importStep === 'preview' && previewData" class="preview-content">
        <!-- 顶部信息 + 可编辑核算日期/备注 -->
        <div class="preview-header-bar">
          <div class="preview-meta">
            <span>订单号：<b>{{ previewData.order_no || '—' }}</b></span>
            <span class="preview-meta-sep">共 {{ previewData.sku_count }} 个 SKU</span>
            <span class="preview-meta-sep">
              已选 {{ selectedSkuCodes.size }} / {{ previewData.sku_count }}
            </span>
            <button class="btn-sel-all" @click="selectedSkuCodes = new Set(previewData.skus.map(s => s.finished_code))">全选</button>
            <button class="btn-sel-all" @click="selectedSkuCodes = new Set()">取消</button>
          </div>
          <div class="preview-form-inline">
            <span class="pf-label">核算日期</span>
            <el-date-picker
              v-model="importForm.snapshot_date"
              type="date" value-format="YYYY-MM-DD"
              size="small" placeholder="核算日期" style="width:150px"
            />
            <span class="pf-label">备注</span>
            <el-input v-model="importForm.notes" size="small" placeholder="备注" style="width:220px" />
          </div>
          <div class="preview-tip">
            ▸ 点击展开/收拢各层级 · 半成品行可标记「外购」（整体采购，下级成本不计入）
          </div>
        </div>

        <!-- 各 SKU BOM 树（扁平行 + 缩进） -->
        <div class="preview-sku-list">
          <div v-for="skuItem in skuFlatTrees" :key="skuItem.finished_code" class="preview-sku-block">
            <!-- SKU 标题行 -->
            <div class="sku-block-header" @click="toggleSku(skuItem.finished_code)">
              <label class="sku-select-check" @click.stop>
                <input
                  type="checkbox"
                  :checked="selectedSkuCodes.has(skuItem.finished_code)"
                  @change="e => {
                    const s = new Set(selectedSkuCodes)
                    e.target.checked ? s.add(skuItem.finished_code) : s.delete(skuItem.finished_code)
                    selectedSkuCodes = s
                  }"
                />
              </label>
              <span class="sku-toggle-icon">{{ skuExpanded[skuItem.finished_code] !== false ? '▾' : '▸' }}</span>
              <span class="sku-code">{{ skuItem.finished_code }}</span>
              <span class="sku-name">{{ skuItem.finished_name }}</span>
              <span class="sku-meta">{{ skuItem.lines?.length ?? 0 }} 行</span>
              <span class="sku-cost">¥{{ skuItem.total_cost?.toFixed(2) ?? '—' }}</span>
            </div>
            <!-- BOM 明细（扁平 + 网格列对齐） -->
            <div v-show="skuExpanded[skuItem.finished_code] !== false" class="sku-bom-tree">
              <!-- 表头 -->
              <div class="ptree-header">
                <div class="ptree-col-expand"/>
                <div class="ptree-col-seq">序号</div>
                <div class="ptree-col-code">品号</div>
                <div class="ptree-col-name">品名规格</div>
                <div class="ptree-col-qty">用量</div>
                <div class="ptree-col-price">单价</div>
                <div class="ptree-col-total">合计</div>
                <div class="ptree-col-semi">类型</div>
              </div>
              <div
                v-for="(row, i) in skuItem.visible"
                :key="row._key + i"
                class="ptree-row"
                :class="{ 'is-semi': row.is_semi }"
              >
                <!-- 展开按钮（含缩进） -->
                <div class="ptree-col-expand" :style="{ paddingLeft: row._depth * 16 + 'px' }">
                  <button v-if="row._hasKids" class="ptree-expand" :class="{ collapsed: previewCollapsed.has(row._key) }" @click.stop="toggleNode(row._key)">
                    ▼
                  </button>
                  <span v-else class="ptree-indent-dot"/>
                </div>
                <!-- 序号 -->
                <div class="ptree-col-seq">{{ row._seq }}</div>
                <!-- 品号 -->
                <div class="ptree-col-code" :title="row.child_code">{{ row.child_code }}</div>
                <!-- 品名规格（按层级缩进） -->
                <div class="ptree-col-name" :title="displayName(row)" :style="{ paddingLeft: row._depth * 2 + 'em' }">{{ displayName(row) }}</div>
                <!-- 用量 -->
                <div class="ptree-col-qty">×{{ row.quantity ?? '—' }}</div>
                <!-- 单价（材料行可编辑；外购半成品只读显示） -->
                <div class="ptree-col-price">
                  <template v-if="!row.is_semi">
                    <input
                      class="ptree-price-input"
                      :class="{ 'no-price': !row.unit_price }"
                      type="number"
                      :value="row.unit_price ?? 0"
                      min="0" step="0.0001"
                      @change="onPriceEdit(row, $event.target.value)"
                    />
                  </template>
                  <template v-else-if="row._isPurchasedSemi">
                    <input
                      class="ptree-price-input purchased-semi-price"
                      type="number"
                      :value="row.unit_price ?? 0"
                      min="0" step="0.0001"
                      @change="onPriceEdit(row, $event.target.value)"
                    />
                  </template>
                </div>
                <!-- 合计 -->
                <div class="ptree-col-total" :class="{ derived: row.is_semi }">
                  {{ row._dTotal ? '¥' + Number(row._dTotal).toFixed(2) : '' }}
                </div>
                <!-- 半成品属性：仅半成品行显示 -->
                <div class="ptree-col-semi">
                  <label v-if="row.is_semi" class="ptree-virtual-toggle" @click.stop>
                    <input type="checkbox" v-model="purchasedSemis[row.child_code]"/>
                    外购半成品
                  </label>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="previewData.warnings?.length" class="preview-warnings">
          <div v-for="(w, i) in previewData.warnings" :key="i" class="warn-item">⚠ {{ w }}</div>
        </div>
      </div>

      <!-- Step 3: 完成 -->
      <div v-else-if="importStep === 'done' && importResult">
        <el-result icon="success" title="导入成功">
          <template #sub-title>
            共导入 <b>{{ importResult.sku_count }}</b> 个SKU，<b>{{ importResult.line_count }}</b> 条 BOM 明细
          </template>
        </el-result>
        <div v-if="importResult.warnings?.length" class="preview-warnings">
          <div v-for="(w, i) in importResult.warnings" :key="i" class="warn-item">⚠ {{ w }}</div>
        </div>
      </div>

      <template #footer>
        <template v-if="importStep === 'form'">
          <el-button @click="importVisible = false">取消</el-button>
          <el-button type="primary" :loading="previewing" :disabled="!importFile" @click="doPreview">
            下一步：预览内容
          </el-button>
        </template>
        <template v-else-if="importStep === 'preview'">
          <el-button @click="importStep = 'form'">上一步</el-button>
          <el-button type="primary" :loading="importing" @click="doImport">确认导入</el-button>
        </template>
        <template v-else-if="importStep === 'done'">
          <el-button type="primary" @click="importVisible = false">完成</el-button>
        </template>
      </template>
    </el-dialog>


    <!-- ═══════════════════════════════════════════ -->
    <!-- BOM 树抽屉（物料查询里使用）                 -->
    <!-- ═══════════════════════════════════════════ -->
    <el-drawer
      v-model="bomDrawerVisible"
      :title="activeSku ? `BOM：${activeSku.finished_code}` : 'BOM'"
      size="600px"
      direction="rtl"
    >
      <div v-loading="bomDrawerLoading" class="bom-tree-wrap">
        <BomTreeNode v-for="node in bomTree" :key="node.id" :node="node" />
        <div v-if="!bomTree.length && !bomDrawerLoading" class="empty-tip">暂无明细</div>
      </div>
    </el-drawer>


    <!-- ═══════════════════════════════════════════ -->
    <!-- 节点详情抽屉                                -->
    <!-- ═══════════════════════════════════════════ -->
    <el-drawer
      v-model="nodeDrawerVisible"
      :size="nodeDrawerWidth + 'px'"
      direction="rtl"
    >
      <!-- 左侧拖拽条 -->
      <div class="drawer-resize-handle" @mousedown="onDrawerResizeStart" />
      <template #header>
        <div class="drawer-header" v-if="activeNode">
          <div class="drawer-code-line">{{ activeNode.code_with_version || activeNode.code }}</div>
          <div class="drawer-name-line">
            {{ activeNode.name }}<template v-if="activeNode.spec">　{{ activeNode.spec }}</template>
          </div>
        </div>
        <span v-else>物料详情</span>
      </template>
      <div v-if="activeNode" v-loading="nodeDrawerLoading">
        <el-tabs v-model="nodeDetailTab">
          <!-- 基本信息 -->
          <el-tab-pane label="基本信息" name="info">
            <el-form :model="activeNode" label-width="90px" class="node-form">
              <el-form-item label="品号">
                <span class="form-val">{{ activeNode.code }}</span>
              </el-form-item>
              <el-form-item label="含版品号">
                <span class="form-val">{{ activeNode.code_with_version }}</span>
              </el-form-item>
              <el-form-item label="品名">
                <span class="form-val">{{ activeNode.name }}</span>
              </el-form-item>
              <el-form-item label="规格">
                <span class="form-val">{{ activeNode.spec }}</span>
              </el-form-item>
              <el-form-item label="物料分类">
                <span class="form-val">{{ activeNode.material_category || '—' }}</span>
              </el-form-item>
              <el-form-item v-if="activeNode.node_type === 'semi'" label="外购半成品">
                <el-switch v-model="activeNode.is_purchased_semi" />
                <span class="form-hint">整体采购，下级物料无需计价</span>
              </el-form-item>
              <el-form-item label="备注">
                <el-input v-model="activeNode.notes" type="textarea" :rows="2" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="saveNodePatch">保存修改</el-button>
              </el-form-item>
            </el-form>
          </el-tab-pane>

          <!-- 价格记录（合并原价格记录+价格历史） -->
          <el-tab-pane label="价格记录" name="prices">
            <div class="supplier-actions">
              <el-button size="small" :icon="Plus" @click="priceFormVisible = true">手动添加</el-button>
            </div>
            <el-table :data="materialPrices" size="small" class="cost-table">
              <el-table-column prop="price_date" label="日期" width="105" />
              <el-table-column prop="order_no" label="订单号" min-width="120" show-overflow-tooltip />
              <el-table-column label="单价 (¥)" width="110" align="right">
                <template #default="{ row }">
                  <span class="price-val">¥{{ row.unit_price?.toFixed(4) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="供应商" min-width="150">
                <template #default="{ row }">
                  <div class="supplier-edit-cell">
                    <el-input
                      v-model="row._supplierDraft"
                      size="small"
                      placeholder="点击填写"
                      @keyup.enter="confirmPriceSupplier(row)"
                    />
                    <el-button
                      v-if="row._supplierDraft !== row.supplier_name"
                      link size="small" type="success"
                      style="margin-left:4px;font-size:16px"
                      title="确认"
                      @click="confirmPriceSupplier(row)"
                    >✓</el-button>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="来源" width="80" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.source === 'bom_import' ? 'info' : 'success'">
                    {{ row.source === 'bom_import' ? 'BOM导入' : '手动' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="60" align="center">
                <template #default="{ row }">
                  <el-button link size="small" type="danger" @click="deleteMaterialPrice(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="!materialPrices.length" class="empty-tip">暂无价格记录</div>
          </el-tab-pane>

          <!-- 使用记录 -->
          <el-tab-pane label="使用记录" name="usages">
            <el-table :data="nodeUsages" size="small" class="cost-table">
              <el-table-column prop="snapshot_date" label="快照日期"   width="115" />
              <el-table-column prop="order_no"      label="订单号"     min-width="180" />
              <el-table-column prop="finished_code" label="成品品号"   min-width="150" />
              <el-table-column label="数量" width="70" align="center">
                <template #default="{ row }">{{ row.quantity }}</template>
              </el-table-column>
              <el-table-column label="单价 (¥)" width="110" align="right">
                <template #default="{ row }">
                  <span class="price-val">{{ row.unit_price != null ? '¥' + row.unit_price.toFixed(4) : '—' }}</span>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="!nodeUsages.length" class="empty-tip">暂无使用记录</div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-drawer>


    <!-- ═══════════════════════════════════════════ -->
    <!-- 添加供应商报价对话框                         -->
    <!-- ═══════════════════════════════════════════ -->
    <!-- ═══════════════════════════════════════════ -->
    <!-- 列名配置对话框                               -->
    <!-- ═══════════════════════════════════════════ -->
    <el-dialog v-model="colAliasVisible" title="Excel 列名配置" width="560px" :close-on-click-modal="false">
      <div v-loading="colAliasLoading" class="col-alias-wrap">
        <p class="col-alias-tip">配置 Excel 表头对应的列名（多个别名用逗号分隔）。导入时按精确匹配查找列，找不到时使用默认位置。</p>
        <el-form label-width="160px" size="small">
          <el-form-item
            v-for="(label, field) in COL_ALIAS_LABELS"
            :key="field"
            :label="label"
          >
            <el-input v-model="colAliasForm[field]" placeholder="多个别名用逗号分隔" style="width: 280px" />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="colAliasVisible = false">取消</el-button>
        <el-button type="primary" :loading="colAliasSaving" @click="saveColAliases">保存</el-button>
      </template>
    </el-dialog>

    <!-- 手动添加价格记录 -->
    <el-dialog v-model="priceFormVisible" title="添加价格记录" width="360px" :close-on-click-modal="false">
      <el-form :model="priceForm" label-width="80px" size="small">
        <el-form-item label="单价 (¥)" required>
          <el-input-number v-model="priceForm.unit_price" :min="0" :precision="4" :controls="false" style="width: 150px" />
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="priceForm.price_date" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" style="width: 150px" />
        </el-form-item>
        <el-form-item label="供应商">
          <el-input v-model="priceForm.supplier_name" placeholder="可选" style="width: 180px" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="priceForm.notes" placeholder="可选" style="width: 180px" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="priceFormVisible = false">取消</el-button>
        <el-button size="small" type="primary" :loading="priceSaving" @click="addMaterialPrice">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="supplierFormVisible" title="添加供应商报价" width="380px" :close-on-click-modal="false">
      <el-form :model="supplierForm" label-width="90px" size="small">
        <el-form-item label="供应商名称" required>
          <el-input v-model="supplierForm.supplier_name" />
        </el-form-item>
        <el-form-item label="单价 (¥)" required>
          <el-input-number v-model="supplierForm.unit_price" :min="0" :precision="4" :controls="false" style="width: 150px" />
        </el-form-item>
        <el-form-item label="报价日期">
          <el-date-picker v-model="supplierForm.price_date" type="date" value-format="YYYY-MM-DD" style="width: 150px" />
        </el-form-item>
        <el-form-item label="设为首选">
          <el-switch v-model="supplierForm.is_preferred" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="supplierForm.notes" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="supplierFormVisible = false">取消</el-button>
        <el-button type="primary" :loading="supplierSaving" @click="saveSupplier">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<!-- BOM 树节点组件（递归） -->
<script>
const BomTreeNode = {
  name: 'BomTreeNode',
  props: { node: Object },
  data() { return { expanded: true } },
  template: `
    <div class="bom-node">
      <div class="bom-node-row" :class="{ semi: node.child_node_type === 'semi' }">
        <button
          v-if="node.children?.length"
          class="expand-btn"
          @click="expanded = !expanded"
        >{{ expanded ? '▾' : '▸' }}</button>
        <span v-else class="expand-placeholder" />
        <span class="node-code">{{ node.child_code }}</span>
        <span class="node-name">{{ node.child_name }}</span>
        <span class="node-qty">×{{ node.quantity }}</span>
        <span class="node-price" v-if="node.unit_price != null">¥{{ node.unit_price.toFixed(4) }}</span>
        <span class="node-total" v-if="node.total_price != null">小计 ¥{{ node.total_price.toFixed(2) }}</span>
        <el-tag v-if="node.child_is_purchased_semi" size="small" type="warning" style="margin-left:4px">外购</el-tag>
      </div>
      <div v-show="expanded" class="bom-children" v-if="node.children?.length">
        <BomTreeNode v-for="child in node.children" :key="child.id" :node="child" />
      </div>
    </div>
  `,
}
export default { components: { BomTreeNode } }
</script>

<style scoped>
.bom-cost {
  display: flex; flex-direction: column;
  height: 100%; overflow: hidden;
}

/* ── 子导航 ── */
.sub-nav {
  display: flex; align-items: center; gap: 4px;
  padding: 0 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-card);
  flex-shrink: 0; height: 38px;
}
.sub-nav-item {
  height: 30px; padding: 0 14px;
  border: none; border-radius: 7px 7px 0 0;
  background: transparent; color: var(--text-muted);
  font-size: 13px; font-family: var(--font-family);
  cursor: pointer; transition: all 0.15s;
  border-bottom: 2px solid transparent;
}
.sub-nav-item:hover { color: var(--text-primary); }
.sub-nav-item.active { color: var(--accent); font-weight: 600; border-bottom-color: var(--accent); }
.sub-nav-spacer { flex: 1; }
.sub-nav-config {
  height: 26px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 6px;
  background: transparent; color: var(--text-muted);
  font-size: 12px; font-family: var(--font-family);
  cursor: pointer; display: flex; align-items: center; gap: 4px;
  transition: all 0.15s;
}
.sub-nav-config:hover { color: var(--text-primary); background: var(--bg); }

/* ── 面板 ── */
.panel {
  flex: 1; overflow-y: auto;
  padding: 12px 16px;
  display: flex; flex-direction: column; gap: 10px;
}
.estimate-panel { overflow-y: auto; }

/* ── 工具栏 ── */
.toolbar {
  display: flex; align-items: center; gap: 8px; flex-shrink: 0;
}
.estimate-toolbar { justify-content: space-between; }

/* ── 表格 ── */
.cost-table { border-radius: 8px; flex-shrink: 0; }
:deep(.table-row) { font-size: 12px; }
:deep(.el-table__header th) { background: #f5f0e8; font-size: 12px; }

/* ── 分页 ── */
.pagination-bar { display: flex; justify-content: flex-end; }

/* ── 价格 ── */
.price-val { color: #c4883a; font-weight: 500; }
.text-muted { color: var(--text-muted); }

/* ── 导入对话框 ── */
.import-form { padding: 4px 0; }
.import-file-row {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px;
  background: #faf7f2; border: 1px dashed var(--border);
  border-radius: 8px;
}
.file-name-display {
  font-size: 12px; color: var(--text-muted);
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.file-name-display:has(+ *) { color: var(--text-primary); }

/* ── 预览 ── */
:deep(.el-dialog) {
  display: flex; flex-direction: column;
  max-height: 90vh !important;
  margin: 5vh auto !important;
}
:deep(.el-dialog__body) {
  flex: 1; min-height: 0;
  overflow: hidden; padding: 12px 16px;
  display: flex; flex-direction: column;
}
.preview-content {
  display: flex; flex-direction: column; gap: 8px;
  flex: 1; min-height: 0; overflow: hidden;
}
.preview-header-bar {
  flex-shrink: 0; display: flex; flex-direction: column; gap: 5px;
  padding-bottom: 6px; border-bottom: 1px solid var(--border);
}
.preview-meta {
  display: flex; align-items: center;
  font-size: 13px; font-weight: 600; color: var(--text-primary);
}
.preview-meta-sep { margin-left: 16px; font-weight: 400; color: var(--text-muted); }
.btn-sel-all {
  margin-left: 8px; height: 22px; padding: 0 8px;
  border: 1px solid var(--border); border-radius: 5px;
  background: transparent; color: var(--text-muted);
  font-size: 12px; cursor: pointer; font-family: var(--font-family);
}
.btn-sel-all:hover { background: var(--bg-card); color: var(--text-primary); }
.preview-form-inline { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.pf-label { font-size: 12px; color: var(--text-muted); }
.preview-tip { font-size: 12px; color: var(--text-muted); }

/* SKU 块 */
.preview-sku-list { display: flex; flex-direction: column; gap: 8px; flex: 1; min-height: 0; overflow-y: auto; }
.preview-sku-block { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; flex-shrink: 0; }
.sku-block-header {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 14px; cursor: pointer;
  background: #f5f0e8; user-select: none;
  border-radius: 8px 8px 0 0;
  position: sticky; top: 0; z-index: 2;
}
.sku-block-header:hover { background: #ede8dc; }
.sku-select-check { display: flex; align-items: center; flex-shrink: 0; cursor: pointer; }
.sku-select-check input { width: 14px; height: 14px; cursor: pointer; accent-color: #c4883a; }
.sku-toggle-icon { color: var(--text-muted); font-size: 11px; width: 12px; flex-shrink: 0; }
.sku-code { font-weight: 700; color: var(--accent); min-width: 160px; font-family: monospace; font-size: 13px; flex-shrink: 0; }
.sku-name { color: var(--text-primary); font-weight: 600; font-size: 13px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sku-meta { font-size: 12px; color: var(--text-muted); flex-shrink: 0; }
.sku-cost { font-weight: 700; color: var(--accent); font-size: 14px; min-width: 90px; text-align: right; flex-shrink: 0; }
.sku-bom-tree { padding: 2px 0 4px; }

/* ── 预览树：网格列布局 ── */
/* 列定义：seq | expand | code | name | qty | price | total | semi-attr */
.ptree-header,
.ptree-row {
  display: grid;
  grid-template-columns: 40px 48px 158px 1fr 60px 106px 90px 110px;
  align-items: center;
  min-height: 27px;
}
.ptree-header {
  font-size: 12px; color: var(--text-primary); font-weight: 500;
  padding: 3px 0; border-bottom: 1px solid var(--border);
  background: #f5f0e8;
}
.ptree-header > div { padding: 0 4px; }
.ptree-row { transition: background 0.1s; font-size: 12px; color: var(--text-primary); }
.ptree-row:hover { background: #faf7f2; }
.ptree-row.is-semi { background: rgba(196,136,58,0.04); font-weight: 600; }

/* 各列公共 */
.ptree-col-seq {
  text-align: right; padding-right: 6px;
  font-size: 12px; color: var(--text-primary);
  user-select: none;
}
.ptree-col-expand {
  display: flex; align-items: center; justify-content: flex-start;
}
.ptree-expand {
  width: 18px; height: 18px;
  border: none; background: none; cursor: pointer;
  color: var(--text-muted); font-size: 12px; padding: 0;
  display: flex; align-items: center; justify-content: center;
  transition: transform 0.15s;
}
.ptree-expand.collapsed { transform: rotate(-90deg); }
.ptree-indent-dot { display: inline-block; width: 20px; }

.ptree-col-code {
  color: var(--text-primary); font-size: 12px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  padding: 0 4px;
}
.ptree-col-name {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  padding: 0 6px;
}
.ptree-col-qty {
  text-align: center; color: var(--text-primary);
}
.ptree-col-price { padding: 2px 4px; }
.ptree-col-semi {
  display: flex; align-items: center; justify-content: center; padding: 0 4px; text-align: center;
}
.ptree-virtual-toggle {
  display: flex; align-items: center; gap: 4px;
  font-size: 11px; color: #c4883a; cursor: pointer;
}
.ptree-virtual-toggle input { cursor: pointer; width: 12px; height: 12px; accent-color: #c4883a; }
.ptree-price-input {
  width: 100%; height: 22px;
  border: 1px solid var(--border); border-radius: 4px;
  font-size: 12px; text-align: right; padding: 0 4px;
  background: #fff; color: #3a3028;
  font-family: var(--font-family);
  outline: none;
}
.ptree-price-input:focus { border-color: var(--accent); }
.ptree-price-input.no-price { background: #e8f3ff; border-color: #a0c8f0; }
.ptree-price-input.purchased-semi-price { background: #fff8ee; border-color: #e0b870; color: #c4883a; font-weight: 600; }

.ptree-col-total {
  text-align: right; padding-right: 8px;
  color: #c4883a; font-weight: 600;
}
.ptree-col-total.derived { color: var(--text-muted); font-weight: 400; }

.warn-item { font-size: 12px; color: #e6a23c; margin-top: 3px; }

/* ── 订单标签 ── */
.order-tags { display: flex; flex-wrap: wrap; gap: 4px; padding: 2px 0; }
.order-tag {
  cursor: pointer; background: #f0ebe0; border-color: #d4b896;
  color: #6b4c2a; transition: background 0.15s;
}
.order-tag:hover { background: #e0c8a0; border-color: #c4883a; color: #3a2010; }

/* ── 抽屉拖拽条 ── */
.drawer-resize-handle {
  position: absolute; left: 0; top: 0; bottom: 0; width: 5px;
  cursor: ew-resize; z-index: 10;
  background: transparent;
}
.drawer-resize-handle:hover { background: rgba(196,136,58,0.3); }

/* ── 抽屉自定义 header ── */
.drawer-header { line-height: 1.5; }
.drawer-code-line { font-size: 16px; font-weight: 700; color: var(--text-primary); }
.drawer-name-line { font-size: 14px; color: var(--text-primary); margin-top: 2px; }
.supplier-edit-cell { display: flex; align-items: center; }

/* ── 节点表单 ── */
.node-form { padding: 4px 0; font-size: 14px; }
.node-form :deep(.el-form-item__label) { font-size: 14px; }
.node-form :deep(.el-form-item__content) { font-size: 14px; }
.node-form :deep(.el-input__inner),
.node-form :deep(.el-textarea__inner) { font-size: 14px; }
.form-val { font-size: 14px; color: var(--text-primary); word-break: break-all; }
.form-hint { font-size: 13px; color: var(--text-muted); margin-left: 8px; }
.form-hint { font-size: 11px; color: var(--text-muted); margin-left: 8px; }
.supplier-actions { margin-bottom: 8px; }

/* ── 空提示 ── */
.empty-tip {
  text-align: center; color: var(--text-muted);
  font-size: 13px; padding: 32px 0;
}

/* ── 预估 ── */
.ref-search-bar { display: flex; align-items: center; gap: 8px; }
.ref-label { font-size: 13px; color: var(--text-primary); flex-shrink: 0; }
.ref-hint { font-size: 12px; color: var(--text-muted); }
.free-add-bar { display: flex; align-items: center; gap: 8px; }
.estimate-table { flex: 1; }

.estimate-summary {
  display: flex; align-items: center; gap: 24px;
  padding: 10px 16px;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; font-size: 13px;
  margin-top: 4px; flex-shrink: 0;
}
.total-label { margin-left: auto; font-weight: 600; }
.total-val { font-size: 16px; color: var(--accent); }

/* ── 列名配置 ── */
.col-alias-wrap { max-height: 60vh; overflow-y: auto; }
.col-alias-tip { font-size: 12px; color: var(--text-muted); margin: 0 0 12px; line-height: 1.6; }

/* ── BOM 详情对话框 ── */
.bom-dialog-body { max-height: calc(90vh - 120px); overflow-y: auto; }
.bom-dialog-loading { padding: 24px; text-align: center; font-size: 14px; color: var(--text-muted); }
.bom-dialog-table { margin: 0; }
.bom-dialog-table th { font-size: 14px; padding: 7px 8px; }
.bom-dialog-table td { font-size: 14px; padding: 6px 8px; font-family: inherit; font-weight: 400; }
.bom-text-black { color: #1a1a1a !important; }
.bom-spec { margin-left: 6px; color: #6b5e4e; font-size: 13px; }
.bom-toggle {
  display: inline-block; width: 1.2em; text-align: center;
  cursor: pointer; color: #c4883a; font-size: 11px;
  margin-right: 2px; user-select: none;
}
.bom-col-category { width: 140px; font-size: 13px; color: #1a1a1a !important; }
.bom-col-supplier { width: 120px; font-size: 13px; color: #1a1a1a !important; }
.bom-code-link {
  color: #3a7fd5; cursor: pointer; text-decoration: underline;
  text-underline-offset: 2px;
}
.bom-code-link:hover { color: #1a5cb8; }
.bom-total-row td {
  background: #fff3e0; color: #a0520a; font-size: 14px; font-weight: 700;
  border-top: 2px solid #e0b06a; padding: 8px 8px;
}

/* ── 内联 BOM 表格 ── */
.bom-inline-loading { padding: 12px 16px; font-size: 12px; color: var(--text-muted); }
.bom-inline-table {
  width: 100%; border-collapse: collapse;
  font-size: 12px; margin: 4px 0;
}
.bom-inline-table th {
  background: #f5f0e8; padding: 5px 8px;
  font-weight: 500; color: var(--text-primary);
  text-align: left; white-space: nowrap;
  border-bottom: 1px solid var(--border);
}
.bom-inline-table td {
  padding: 4px 8px; border-bottom: 1px solid #f0ebe0;
  vertical-align: middle;
}
.bom-inline-table tr:last-child td { border-bottom: none; }
.bom-depth0-row td { font-weight: 700; }
.bom-semi-row td { background: rgba(196,136,58,0.04); font-weight: 600; }
.bom-purchased-row td { background: #fff8ee; }
.bom-col-seq   { width: 50px; text-align: right; }
.bom-col-code  { width: 140px; }
.bom-col-name  { min-width: 200px; }
.bom-col-type  { width: 70px; color: var(--text-muted); }
.bom-col-qty   { width: 60px; text-align: center; }
.bom-col-price { width: 100px; text-align: right; color: #c4883a; }
.bom-col-total { width: 100px; text-align: right; color: #c4883a; font-weight: 600; }

/* ── BOM 树（物料查询抽屉） ── */
.bom-tree-wrap { font-size: 12px; }
:deep(.bom-node) { padding-left: 16px; }
:deep(.bom-node-row) {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 6px; border-radius: 5px;
  transition: background 0.1s;
}
:deep(.bom-node-row:hover) { background: #faf7f2; }
:deep(.bom-node-row.semi) { color: #9b7b3c; }
:deep(.expand-btn) {
  width: 16px; text-align: center;
  border: none; background: none; cursor: pointer;
  color: var(--text-muted); font-size: 10px;
}
:deep(.expand-placeholder) { display: inline-block; width: 16px; }
:deep(.node-code) { color: var(--text-muted); min-width: 110px; font-family: monospace; }
:deep(.node-name) { flex: 1; }
:deep(.node-qty) { color: var(--text-muted); }
:deep(.node-price) { color: #c4883a; min-width: 80px; text-align: right; }
:deep(.node-total) { color: var(--text-muted); min-width: 90px; text-align: right; }
:deep(.bom-children) { border-left: 1px dashed var(--border); margin-left: 8px; }
</style>
