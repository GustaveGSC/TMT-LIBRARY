<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, watch } from 'vue'
import { WarningFilled, Picture, Plus, Edit, Delete, ZoomIn, Close, Check, Back, View, TrendCharts } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MediaViewer from '@/components/common/MediaViewer.vue'
import MaterialBomDialog from './MaterialBomDialog.vue'
import MaterialCostView from './MaterialCostView.vue'
import MaterialPriceTrendDialog from './MaterialPriceTrendDialog.vue'
import { pickFile } from '@/utils/download'
import http from '@/api/http'
import { usePermission } from '@/composables/usePermission'

// 价格属于研发成本数据。usePermission 返回普通布尔值不是 ref，不能写 .value。
const { canMaterialPrice, canEditMaterial: permEditMaterial } = usePermission()

// ── Props / Emits ─────────────────────────────────
const props = defineProps({
  visible:  { type: Boolean, default: false },
  code:     { type: String,  default: '' },
  // 只读：从产品库的 BOM / 成本打开时只看不改（用户 2026-09-29 定）——不能改人工维护、图片、价格、供应商、不计价
  readonly: { type: Boolean, default: false },
})

// 编辑权限 = 物料权限且不是只读打开
const canEditMaterial = computed(() => permEditMaterial && !props.readonly)
const canEditPrice    = computed(() => canMaterialPrice && !props.readonly)
const emit = defineEmits(['update:visible', 'saved'])

// ── 响应式状态 ────────────────────────────────────
// 当前显示的物料编码：打开时取 props.code；在 BOM 区点编码可以在卡片内跳到其他物料，
// 跳转前的状态压进 navStack，标题栏出现「返回」。
// 每项 { code, bomDialog }：从 BOM 弹窗里点进去的，bomDialog 记下当时看的 BOM 和筛选词，
// 返回时重新打开那个弹窗——用户感知的「上一层」是弹窗，不只是上一个物料
const activeCode = ref('')
const navStack   = ref([])
const detail   = ref(null)
const loading  = ref(false)
const saving   = ref(false)
const errorMsg = ref('')

// 人工可编辑的字段草稿。ERP 侧字段（code/name/group）只读展示，
// 它们归 import_product_raw 所有，不在这里改。
//
// 停用状态**不可人工设置**（用户 2026-08-07 决定：只来源于导入数据），
// 所以表单里没有它，卡片只在 ERP 信息区做只读展示。
//
// type_override：单独指定的物料类型，空数组 = 不单独指定（按编码前缀规则/分组默认类型判定）。
// 判定优先级：单独指定 > 编码前缀规则 > 分组默认类型。
//
// 简称/分类/规格已去掉（用户 2026-09-27 决定）：生产上简称 0 条、分类 1 条、规格全部等于 ERP 规格，
// 且没有任何下游使用；名称/规格一律以 ERP 为准。数据库列保留未删，只是不再显示和提交。
const form = ref({ remark: '', type_override: [], no_price: false })

// 物料类型定义，与后端 CATEGORY_TYPES / TYPE_LABELS 一致
const TYPE_OPTIONS = [
  { key: 'finished', label: '成品',     color: '#c4883a' },
  { key: 'packaged', label: '产成品',   color: '#4a8fc0' },
  { key: 'semi',     label: '半成品',   color: '#9c6fba' },
  { key: 'material', label: '原材料',   color: '#6ab47a' },
  { key: 'useless',  label: '无用物料', color: '#8a7a6a' },
]
const typeLabel = Object.fromEntries(TYPE_OPTIONS.map(t => [t.key, t.label]))
const SOURCE_TEXT = { manual: '单独指定', rule: '编码前缀规则', group: '分组默认类型' }

// 已保存状态的快照（规范化后的 JSON），与 form 比较得出是否有未保存的修改
const savedSnapshot = ref('')
function snapshotOf(f) {
  return JSON.stringify({
    remark: (f.remark || '').trim(), no_price: !!f.no_price,
    type_override: [...(f.type_override || [])].sort(),
  })
}
const isDirty = computed(() => !!detail.value && snapshotOf(form.value) !== savedSnapshot.value)

function fillForm(data) {
  form.value = {
    remark:     data.remark     || '',
    no_price:   !!data.no_price,
    type_override: [...(data.type_override || [])],
  }
  savedSnapshot.value = snapshotOf(form.value)
}

// 规则判定的类型（不含单独指定）：编码前缀规则 > 分组默认类型
const ruleTypes = computed(() => detail.value?.rule_categories || [])

// 类型选择器直接显示「当前生效」的类型：有单独指定显示指定值，否则显示规则判定结果
const shownTypes = computed(() =>
  form.value.type_override.length ? form.value.type_override : ruleTypes.value)

function sameSet(a, b) {
  return a.length === b.length && a.every(k => b.includes(k))
}

// 点选类型：在「当前生效」的基础上增减。
// 选完与规则判定结果一致时自动回到「按规则判定」（清空单独指定）；至少保留一个类型。
function toggleType(key) {
  const list = [...shownTypes.value]
  const i = list.indexOf(key)
  if (i >= 0) {
    if (list.length === 1) return
    list.splice(i, 1)
  } else {
    list.push(key)
  }
  form.value.type_override = sameSet(list, ruleTypes.value) ? [] : list
}

// 当前生效类型含成品/产成品/半成品时不能设「不计价」（成本由下级计算）；改成这些类型时自动取消勾选
const isAssembly = computed(() => shownTypes.value.some(t => ['finished', 'packaged', 'semi'].includes(t)))
watch(isAssembly, v => { if (v && form.value.no_price) form.value.no_price = false })

// 恢复按规则判定
function resetTypes() { form.value.type_override = [] }

// 物料类型来源说明（悬停显示完整文案）
const typeHintFull = computed(() => {
  const d = detail.value
  if (!d) return ''
  const ruleText = `${SOURCE_TEXT[d.rule_source] || '规则'}判定为 ${formatTypes(ruleTypes.value)}`
  if (form.value.type_override.length) return `单独指定；若恢复规则判定，将按${ruleText}`
  return d.rule_source ? `按${ruleText}` : '未匹配到编码前缀规则或分组默认类型'
})

function formatTypes(list) {
  return (list || []).map(k => typeLabel[k] || k).join(' / ') || '未分类'
}

// ── 图片（多张，存 material_image）────────────────────
// 新增/编辑/删除都是**即时生效**的独立操作，不跟随底部「保存/取消」——
// 图片要先传 OSS，放进表单草稿里等保存反而会在取消时留下孤儿文件。
const ownImages  = ref([])   // 物料自己的图片 material_image：[{id, url, orig_url, sort_order}]
const productImages = ref([]) // 成品沿用产品库主图（只读）：[{url, orig_url}]
// 展示用的完整列表：产品库图片排在最前，不可编辑/删除（在产品库维护）
const images = computed(() => [
  ...productImages.value.map((img, i) => ({ ...img, id: `product-${i}`, fromProduct: true })),
  ...ownImages.value,
])
const currentIdx = ref(0)
const imgBusy    = ref(false)
const viewerOpen = ref(false)
const currentImage = computed(() => images.value[currentIdx.value] || null)
const viewerItems = computed(() => images.value.map(img => ({
  id: img.id, file_type: 'image', oss_url: img.orig_url || img.url, original_filename: '',
})))

// ── 价格（研发 BOM 成本数据）────────────────────────
// 价格与研发部 BOM 共用同一份 cost_material_price，不是物料库独有的副本。
// 物料若还没有成本节点（8091 个物料里只有 130 个有），首次加价时后端惰性创建。
const prices        = ref([])
const costLoading   = ref(false)
// 价格趋势弹窗（「使用记录」已去掉，2026-09-27）
const trendOpen     = ref(false)
const priceFormOpen = ref(false)
const priceSaving   = ref(false)
// 价格日期默认今天（本地时区），可改
const todayStr = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
const priceForm     = ref({ unit_price: '', price_date: todayStr(), supplier_name: '', notes: '' })
const priceErr      = ref('')

// 无用物料不允许维护价格（用户 2026-08-07 决定：金蝶旧编码那两组已不再使用）。
// 后端同样有门禁，这里只是不给入口。后端若返回 can_add_price 则优先用它。
const canAddPrice = computed(() => {
  const d = detail.value
  if (!d || !canEditPrice.value) return false
  if (typeof d.can_add_price === 'boolean') return d.can_add_price
  return !(d.categories || []).includes('useless')
})
const isUseless = computed(() => (detail.value?.categories || []).includes('useless'))

async function loadCost() {
  if (!canMaterialPrice || !activeCode.value) return
  costLoading.value = true
  const c = encodeURIComponent(activeCode.value)
  try {
    const pRes = await http.get(`/api/material/items/${c}/prices`)
    loadSupplierOptions()
    prices.value = (pRes.success ? (pRes.data || []) : [])
      .map(x => ({ ...x, _supplierDraft: x.supplier_name || '' }))
  } catch { /* 价格拿不到不该阻塞整张卡片 */ }
  finally { costLoading.value = false }
}

async function submitPrice() {
  priceErr.value = ''
  if (!String(priceForm.value.unit_price).trim()) { priceErr.value = '请填写单价'; return }
  // 价格日期必填：无日期价格会回溯到所有历史时点（Codex 审计 #3）
  if (!priceForm.value.price_date) { priceErr.value = '请填写价格日期'; return }
  priceSaving.value = true
  try {
    const res = await http.post(
      `/api/material/items/${encodeURIComponent(activeCode.value)}/prices`, {
        unit_price:    priceForm.value.unit_price,
        price_date:    priceForm.value.price_date || '',
        supplier_name: priceForm.value.supplier_name || '',
        notes:         priceForm.value.notes || '',
      })
    if (res.success) {
      // 重新拉取而不是本地 unshift：最新价由 price_date 排序决定，
      // 新加的一条不一定就是最新（可能补录的是更早日期）。
      await loadCost()
      priceFormOpen.value = false
      priceForm.value = { unit_price: '', price_date: todayStr(), supplier_name: '', notes: '' }
      // 通知列表刷新该行的价格列
      emit('saved', { ...detail.value, _priceChanged: true })
    } else {
      priceErr.value = res.message || '添加失败'
    }
  } catch (e) { priceErr.value = e.message || '网络错误' }
  finally { priceSaving.value = false }
}

async function saveSupplier(row) {
  const next = row._supplierDraft || ''
  const res = await http.patch(`/api/material/prices/${row.id}`, { supplier_name: next })
  if (res.success) row.supplier_name = next
  else priceErr.value = res.message || '供应商更新失败'
}

async function removePrice(row) {
  const { ElMessageBox } = await import('element-plus')
  try {
    await ElMessageBox.confirm('确认删除该价格记录？', '确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch { return }
  const res = await http.delete(`/api/material/prices/${row.id}`)
  if (res.success) { await loadCost(); emit('saved', { ...detail.value, _priceChanged: true }) }
  else priceErr.value = res.message || '删除失败'
}

const SOURCE_LABELS = { bom_import: 'BOM 导入', manual: '手动', bom_calc: 'BOM 推算' }

// 供应商候选（下拉）。allow-create 允许直接打新名字——后端 resolve() 会自动
// 登记进 material_supplier 并回填 supplier_id，不用先去供应商页登记一遍。
const supplierOptions = ref([])
async function loadSupplierOptions() {
  if (!canMaterialPrice) return
  try {
    const res = await http.get('/api/material/suppliers/options')
    if (res.success) supplierOptions.value = res.data || []
  } catch { /* 候选拿不到仍可自由输入 */ }
}

// ── 按 BOM 计算的价格（仅 material:price）：部件价格不存储，由下级原材料价格实时计算 ──
// 历史 = 在下级各价格日期上重算一次（新→旧），也是后端现算的
const calcPrice   = ref(null)    // { bom, versions, current, missing_items, composition, history } | null
// 成本视图（页签、标记不计价）在 MaterialCostView 里

// 有 BOM 的物料：外购价只在「外购半成品」或已经有自身价格时显示（普通部件的价格由下级计算）
const showOwnPrice = computed(() => !calcPrice.value
  || !!detail.value?.is_purchased_semi || prices.value.length > 0)

async function loadCalcPrice() {
  const code = activeCode.value
  calcPrice.value = null
  if (!canMaterialPrice || !bom.value?.versions?.length) return
  try {
    const res = await http.get(`/api/material/items/${encodeURIComponent(code)}/calc-price`)
    if (code !== activeCode.value) return
    if (res.success && res.data?.current) {
      calcPrice.value = res.data
    }
  } catch { /* 计算价拿不到不影响卡片 */ }
}

// ── 研发 BOM：「BOM下级」列出该物料挂的全部研发 BOM（如 -A01、-A02 各一条），
//    点「查看」单独弹窗展开完整结构；「被使用」是另一个分区 ─────
const bom        = ref(null)     // { versions[+line_count], direct_parents, top_products }
const bomLoading = ref(false)

async function loadBom() {
  const code = activeCode.value
  bomLoading.value = true
  try {
    const res = await http.get(`/api/material/items/${encodeURIComponent(code)}/bom`)
    if (code !== activeCode.value) return
    // 只接受形状完整的数据，避免异常响应让模板渲染报错、拖垮整张卡片
    if (res.success && Array.isArray(res.data?.versions)) {
      bom.value = res.data
      loadCalcPrice()
    }
  } catch { /* BOM 拿不到不影响卡片其余内容 */ } finally {
    if (code === activeCode.value) bomLoading.value = false
  }
}

// BOM 下级弹窗：展开某一个研发版本的完整多层结构（MaterialBomDialog）
const bomDialogRef = ref(null)

function openBomDialog(v, keyword = '', priceBatch = null) {
  bomDialogRef.value?.open(v, keyword, priceBatch)
}

// 弹窗里点子件编码：卡片跳到该物料；snapshot 记下当时的 BOM/筛选词/计价依据，返回时重新打开弹窗
async function onBomDialogCode(code, snapshot) {
  // 先确认能跳（可能有未保存修改被取消），再关弹窗
  if (await navigateTo(code, snapshot)) bomDialogRef.value?.close()
}

// 在卡片内跳到另一个物料（BOM 子件/上级）；有未保存的人工维护时先确认
async function navigateTo(code, bomDialog = null) {
  if (!code || code === activeCode.value) return false
  if (!(await confirmDiscard())) return false
  navStack.value.push({ code: activeCode.value, bomDialog })
  activeCode.value = code
  resetForCode()
  return true
}

async function navigateBack() {
  if (!navStack.value.length) return
  if (!(await confirmDiscard())) return
  const prev = navStack.value.pop()
  activeCode.value = prev.code
  resetForCode()
  // 从 BOM 弹窗点进来的：回到那个弹窗（保留当时的筛选词）
  if (prev.bomDialog?.head) openBomDialog(prev.bomDialog.head, prev.bomDialog.keyword, prev.bomDialog.priceBatch)
}

function resetForCode() {
  prices.value = []
  priceFormOpen.value = false; priceErr.value = ''; trendOpen.value = false
  bom.value = null; bomDialogRef.value?.close(); calcPrice.value = null
  loadDetail()
}

// ── 加载详情 ──────────────────────────────────────
async function loadDetail() {
  if (!activeCode.value) return
  loading.value  = true
  errorMsg.value = ''
  detail.value   = null
  try {
    const res = await http.get(`/api/material/items/${encodeURIComponent(activeCode.value)}`)
    if (res.success) {
      detail.value = res.data
      fillForm(res.data)
      ownImages.value = res.data.images || []
      productImages.value = res.data.product_images || []
      currentIdx.value = 0
      loadCost()
      loadBom()
    } else {
      errorMsg.value = res.message || '加载失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
  } finally {
    loading.value = false
  }
}

// ── 保存人工维护 ──────────────────────────────────
// 卡片底部不再有保存/取消：图片操作即时生效，人工维护用分区标题行里的确认图标单独保存，
// 保存后卡片保持打开。操作类错误用消息提示，errorMsg 只留给"详情加载失败"（它会替换整张卡片）。
async function handleSave() {
  if (!isDirty.value || saving.value) return
  saving.value = true
  try {
    // 刻意不传 is_disabled：该列是「人工覆盖」，一旦传值就会覆盖导入数据的判定。
    // 停用状态只来源于导入，卡片无权修改。
    const payload = {
      remark:     form.value.remark,
      no_price:   form.value.no_price,
      type_override: form.value.type_override,
    }
    const res = await http.put(
      `/api/material/items/${encodeURIComponent(activeCode.value)}`, payload,
    )
    if (res.success) {
      // 用服务端返回值回写（物料类型的判定结果也会随之更新），并通知列表更新对应行
      detail.value = { ...detail.value, ...(res.data || {}) }
      fillForm(detail.value)
      emit('saved', detail.value)
      ElMessage.success('已保存')
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '网络错误')
  } finally {
    saving.value = false
  }
}

// ── 图片操作 ──────────────────────────────────────
async function pickImageDataUrl() {
  const file = await pickFile('image/*')
  if (!file) return ''
  if (file.size > 5 * 1024 * 1024) { ElMessage.error('图片不能超过 5MB'); return '' }
  return new Promise((resolve) => {
    const fr = new FileReader()
    fr.onload = () => resolve(String(fr.result || ''))
    fr.onerror = () => resolve('')
    fr.readAsDataURL(file)
  })
}

const imagesUrl = () => `/api/material/items/${encodeURIComponent(activeCode.value)}/images`

// 各操作后端都返回最新的完整图片列表，直接替换
async function runImageOp(request, { selectLast = false } = {}) {
  imgBusy.value = true
  try {
    const res = await request()
    if (!res.success) { ElMessage.error(res.message || '图片操作失败'); return }
    ownImages.value = res.data || []
    if (selectLast) currentIdx.value = images.value.length - 1
    else if (currentIdx.value >= images.value.length) currentIdx.value = Math.max(0, images.value.length - 1)
  } catch (e) {
    ElMessage.error(e.message || '网络错误')
  } finally {
    imgBusy.value = false
  }
}

async function addImage() {
  const dataUrl = await pickImageDataUrl()
  if (!dataUrl) return
  await runImageOp(() => http.post(imagesUrl(), { data_url: dataUrl }), { selectLast: true })
}

async function replaceImage() {
  const img = currentImage.value
  if (!img || img.fromProduct) return
  const dataUrl = await pickImageDataUrl()
  if (!dataUrl) return
  await runImageOp(() => http.put(`${imagesUrl()}/${img.id}`, { data_url: dataUrl }))
}

async function deleteImage() {
  const img = currentImage.value
  if (!img || img.fromProduct) return
  try {
    await ElMessageBox.confirm('确认删除这张图片？删除后不可恢复。', '删除图片',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch { return }
  await runImageOp(() => http.delete(`${imagesUrl()}/${img.id}`))
}

function viewImage() {
  if (currentImage.value) viewerOpen.value = true
}

function close() { emit('update:visible', false) }

async function confirmDiscard() {
  if (!isDirty.value) return true
  try {
    await ElMessageBox.confirm('人工维护有未保存的修改，确定关闭？', '未保存',
      { type: 'warning', confirmButtonText: '放弃修改并关闭', cancelButtonText: '继续编辑' })
    return true
  } catch { return false }
}

async function requestClose() {
  if (await confirmDiscard()) close()
}

// el-dialog 的 ESC / 点遮罩关闭
async function beforeClose(done) {
  if (await confirmDiscard()) done()
}

// 打开时才拉详情，关闭不清理（同一条再打开可秒开）
watch(() => props.visible, v => {
  if (!v) return
  activeCode.value = props.code
  navStack.value = []
  resetForCode()
})
</script>

<template>
  <el-dialog
    :model-value="props.visible"
    :show-close="false"
    :before-close="beforeClose"
    class="material-card-dialog"
    :width="canMaterialPrice ? 900 : 760"
    align-center
    append-to-body
    @update:model-value="emit('update:visible', $event)"
  >
    <!-- 标题栏：不用 el-dialog 原生标题，改为「状态 编码 名称 …… 关闭」一行，
         下方分割线与内容隔开。名称单行省略（悬停看全文） -->
    <template #header>
      <div class="mc-erp-line">
        <button v-if="navStack.length" class="mc-back-btn" type="button"
                :title="`返回 ${navStack[navStack.length - 1].code}`" aria-label="返回" @click="navigateBack">
          <el-icon><Back /></el-icon>
        </button>
        <template v-if="detail">
          <span
            class="ro-badge"
            :class="detail.is_disabled ? 'off' : 'on'"
            :title="`ERP 状态：${detail.status || '—'}`"
          >{{ detail.is_disabled ? '已停用' : '启用' }}</span>
          <span class="mc-erp-code mono">{{ detail.code }}</span>
          <span class="mc-erp-name" :title="detail.name">{{ detail.name }}</span>
        </template>
        <span v-else class="mc-erp-name">物料卡片</span>
        <button class="mc-close-btn" type="button" aria-label="关闭" @click="requestClose">
          <el-icon><Close /></el-icon>
        </button>
      </div>
    </template>
    <div class="material-card">

      <div v-if="loading" class="state-tip">加载中...</div>

      <div v-else-if="errorMsg" class="error-bar">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ errorMsg }}</span>
      </div>

      <template v-else-if="detail">
       <!-- 排版（用户 2026-09-27 指定）：第一行 图片 | ERP 信息；
            第二行 人工维护（通栏）；第三行 价格（通栏，仅 material:price 可见） -->
       <div class="mc-scroll">
        <div class="mc-top">
        <div class="mc-top-image">
        <!-- 图片：悬停出现遮罩 + 圆形图标按键（新增/编辑/删除/查看）；无图时直接显示新增 -->
        <div class="mc-image" :class="{ busy: imgBusy, 'no-images': !images.length }">
          <template v-if="currentImage">
            <img :src="currentImage.url" alt="" />
            <div class="mc-img-mask">
              <button v-if="canEditMaterial" class="mc-round-btn" title="新增图片" :disabled="imgBusy" @click="addImage">
                <el-icon><Plus /></el-icon>
              </button>
              <button v-if="canEditMaterial && !currentImage.fromProduct" class="mc-round-btn" title="编辑（替换当前图片）" :disabled="imgBusy" @click="replaceImage">
                <el-icon><Edit /></el-icon>
              </button>
              <button v-if="canEditMaterial && !currentImage.fromProduct" class="mc-round-btn danger" title="删除当前图片" :disabled="imgBusy" @click="deleteImage">
                <el-icon><Delete /></el-icon>
              </button>
              <button class="mc-round-btn" title="查看大图" @click="viewImage">
                <el-icon><ZoomIn /></el-icon>
              </button>
            </div>
            <span v-if="currentImage.fromProduct" class="mc-img-source" title="沿用产品库成品主图，请到产品库修改">产品库</span>
            <span v-if="images.length > 1" class="mc-img-count">{{ currentIdx + 1 }} / {{ images.length }}</span>
          </template>
          <div v-else class="mc-image-empty">
            <button v-if="canEditMaterial" class="mc-round-btn solo" title="新增图片" :disabled="imgBusy" @click="addImage">
              <el-icon><Plus /></el-icon>
            </button>
            <template v-else>
              <el-icon><Picture /></el-icon>
              <span>暂无图片</span>
            </template>
          </div>
          <div v-if="imgBusy" class="mc-img-busy">处理中...</div>
        </div>
        <!-- 缩略图条：只要有图（含仅一张）就显示，点击切换当前图。
             无图时不渲染，由图片框占满整列高度（.no-images），保证 0/1/多张图卡片尺寸不变 -->
        <div v-if="images.length" class="mc-thumbs">
          <button
            v-for="(img, i) in images"
            :key="img.id"
            class="mc-thumb"
            :class="{ active: i === currentIdx }"
            @click="currentIdx = i"
          ><img :src="img.url" alt="" /></button>
        </div>
        </div><!-- /mc-top-image -->

        <!-- 人工维护：放在图片右侧（可编辑内容是卡片的主要操作对象），
             所有字段标签同宽右对齐，输入框左边缘在一条竖线上 -->
        <div class="mc-section mc-manual">
          <!-- 标题行右侧的确认图标：只保存人工维护，有修改时才可点 -->
          <div class="mc-section-title">
            <span>人工维护<span v-if="isDirty" class="mc-dirty">未保存</span></span>
            <button
              v-if="canEditMaterial"
              class="mc-save-btn"
              :class="{ active: isDirty }"
              type="button"
              aria-label="保存人工维护"
              :disabled="!isDirty || saving"
              @click="handleSave"
            ><el-icon><Check /></el-icon></button>
          </div>
          <!-- 物料类型：单独指定 > 编码前缀规则 > 分组默认类型 -->
          <div class="mc-field mc-field-top">
            <label>物料类型</label>
            <div class="mt-box">
              <div class="mt-chips">
                <button
                  v-for="t in TYPE_OPTIONS"
                  :key="t.key"
                  class="mt-chip"
                  :class="{ on: shownTypes.includes(t.key) }"
                  :style="shownTypes.includes(t.key)
                    ? { color: t.color, borderColor: t.color, background: t.color + '18' } : {}"
                  :disabled="!canEditMaterial"
                  @click="toggleType(t.key)"
                >{{ t.label }}</button>
              </div>
              <!-- 固定单行（超出省略，悬停看全文），避免换行把右侧区域撑高、破坏与图片列的对齐 -->
              <div class="mt-hint" :title="typeHintFull">
                <template v-if="form.type_override.length">
                  单独指定｜规则判定：<b>{{ formatTypes(ruleTypes) }}</b>
                  <a v-if="canEditMaterial" class="mt-reset" @click="resetTypes">恢复规则判定</a>
                </template>
                <template v-else-if="detail.rule_source">来源：{{ SOURCE_TEXT[detail.rule_source] }}</template>
                <template v-else>未匹配规则，请单独指定</template>
              </div>
            </div>
          </div>
          <!-- 不计价：客供件/赠送件等永远不会有采购价的物料，计价按 0 元、算作已有价格，
               否则用到它的部件永远到不了「下级价格齐全」、无法开始计价 -->
          <div class="mc-field">
            <label>计价</label>
            <div class="np-box">
              <label class="np-check" :class="{ on: form.no_price, off: isAssembly }">
                <input v-model="form.no_price" type="checkbox" :disabled="!canEditMaterial || isAssembly" />
                不计价
              </label>
              <span v-if="isAssembly" class="np-hint">成品、产成品、半成品的成本由下级计算，不能设为不计价</span>
              <span v-else class="np-hint">客供件、赠送件等不会有采购价的物料，计价时按 0 元计</span>
            </div>
          </div>
          <div class="mc-field mc-field-top mc-field-remark">
            <label>备注</label>
            <textarea v-model="form.remark" class="mc-textarea" :disabled="!canEditMaterial" rows="2"></textarea>
          </div>
        </div>
        </div><!-- /mc-top -->

        <!-- ── BOM下级：该物料挂的全部研发 BOM（每个研发版本一行），点「查看」弹窗看完整结构
             （在「物料BOM」页导入）── -->
        <div v-if="bom?.versions.length" class="mc-section mc-bom">
          <div class="mc-section-title">
            <span>BOM下级</span>
            <span v-if="bom?.versions.length" class="bom-ver-text">{{ bom.versions.length }} 个研发版本</span>
          </div>
          <table class="cost-table bom-ver-table">
            <thead>
              <tr>
                <th style="width:160px">图纸编码</th>
                <th>名称</th>
                <th style="width:150px">导入</th>
                <th style="width:90px"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="v in bom.versions" :key="v.id">
                <td class="mono bom-drawing">{{ v.drawing }}</td>
                <td class="bom-name">{{ v.name || '—' }}</td>
                <td class="cell-muted">{{ v.imported_at }}</td>
                <td class="ta-r">
                  <button class="bom-view-btn" type="button" @click="openBomDialog(v)">
                    <el-icon><View /></el-icon>查看
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- ── 被使用：直接上级 + 沿上级一路找到的最终产品 ── -->
        <div v-if="bom?.direct_parents.length" class="mc-section mc-used">
          <div class="mc-section-title">
            <span>被使用</span>
            <span v-if="bom?.top_products.length" class="bom-ver-text">{{ bom.top_products.length }} 个最终产品</span>
          </div>
          <template v-if="bom">
            <div v-if="bom?.top_products.length" class="used-block">
              <div class="used-label">最终产品</div>
              <div class="used-chips">
                <button v-for="t in bom.top_products" :key="t.id" class="used-chip"
                        :class="{ nolink: !t.erp_code }"
                        :title="t.erp_code ? `${t.name || ''}（点击查看 ${t.erp_code}）` : 'ERP 未匹配'"
                        @click="navigateTo(t.erp_code)">
                  <b class="mono">{{ t.drawing }}</b><span>{{ t.name }}</span>
                </button>
              </div>
            </div>
            <table v-if="bom?.direct_parents.length" class="cost-table">
              <thead>
                <tr>
                  <th style="width:160px">直接上级</th>
                  <th>名称</th>
                  <th style="width:70px" class="ta-r">用量</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in bom.direct_parents" :key="p.id + '-' + p.child_drawing">
                  <!-- 显示完整研发编码（成品/产成品带完整版本）；能对应到 ERP 物料时可跳转，否则置灰 -->
                  <td class="mono">
                    <span v-if="p.erp_code" class="bom-link" @click="navigateTo(p.erp_code)">{{ p.drawing }}</span>
                    <span v-else class="cell-muted" title="ERP 物料表里没有对应编码">{{ p.drawing }}</span>
                  </td>
                  <td class="ellip">{{ p.name || '—' }}</td>
                  <td class="ta-r">{{ p.qty }}{{ p.unit ? ' ' + p.unit : '' }}</td>
                </tr>
              </tbody>
            </table>
          </template>
        </div>

        <!-- ── 价格（仅 rd:view 可见）────────────────────────
             与研发部 BOM 共用同一份 cost_material_price，不是副本。
             后端在无 rd:view 时根本不返回价格字段，此处隐藏只是体验层。 -->
        <div v-if="canMaterialPrice" class="mc-section">
          <div class="mc-section-title">
            <span>{{ calcPrice ? '成本（按 BOM 计算）' : '价格' }}</span>
            <span v-if="!calcPrice && detail.latest_price != null" class="mc-latest">
              最新　<b>¥{{ Number(detail.latest_price).toFixed(4) }}</b>
              <span class="mc-src">{{ SOURCE_LABELS[detail.latest_price_source] || '' }}</span>
            </span>
          </div>

          <!-- 有研发 BOM 的部件：成本由下级原材料价格实时计算（不存储）
               成本 + 完整度 → 成本变化（按订单，拆价格涨跌/新增计价）/ 成本构成 / 缺价清单 -->
          <MaterialCostView v-if="calcPrice" :data="calcPrice"
                            :trend-disabled="!calcPrice.history.length && !prices.length" :readonly="readonly"
                            @open-code="navigateTo" @changed="loadCalcPrice" @trend="trendOpen = true" />

          <!-- 外购价：普通部件不显示；外购半成品或已有自身价格时显示（下级全无价格时计算用它） -->
          <template v-if="showOwnPrice">
          <div v-if="!calcPrice && detail.no_price" class="np-note">已标记「不计价」：用到它的部件计价时按 0 元计</div>
          <div v-if="calcPrice" class="own-title">外购价 <span>下级全都没有价格时，成本改用这里的价格</span></div>
          <div class="cost-tabs">
            <span class="cost-count">价格记录（{{ prices.length }}）</span>
            <button v-if="!calcPrice" class="cost-trend" type="button" :disabled="!prices.length && !calcPrice?.history?.length"
                    title="按价格日期显示价格走势" @click="trendOpen = true">
              <el-icon><TrendCharts /></el-icon>价格趋势
            </button>
            <button v-if="canAddPrice" class="cost-add" @click="priceFormOpen = !priceFormOpen">
              {{ priceFormOpen ? '取消添加' : '+ 添加价格' }}
            </button>
            <span v-else-if="isUseless" class="cost-locked" title="金蝶旧编码物料已不再使用">
              无用物料不维护价格
            </span>
          </div>

          <div v-if="priceErr" class="error-bar mini">
            <el-icon><WarningFilled /></el-icon><span>{{ priceErr }}</span>
          </div>

          <!-- 添加价格 -->
          <div v-if="priceFormOpen && canAddPrice" class="price-form">
            <div class="pf-row">
              <label>单价 <b>*</b></label>
              <input v-model="priceForm.unit_price" class="mc-input" placeholder="如 12.3456" />
              <label>日期 <b>*</b></label>
              <input v-model="priceForm.price_date" class="mc-input" type="date" />
            </div>
            <div class="pf-row">
              <label>供应商</label>
              <el-select
                v-model="priceForm.supplier_name" class="pf-select" size="small"
                filterable clearable allow-create default-first-option
                placeholder="选择或直接输入"
              >
                <el-option v-for="s in supplierOptions" :key="s.id" :label="s.name" :value="s.name" />
              </el-select>
              <label>备注</label>
              <input v-model="priceForm.notes" class="mc-input" placeholder="可留空" />
            </div>
            <div class="pf-actions">
              <button class="btn btn-primary sm" :disabled="priceSaving" @click="submitPrice">
                {{ priceSaving ? '提交中...' : '确认添加' }}
              </button>
              <span v-if="!detail.has_cost_node" class="pf-hint">
                该物料尚无成本节点，首次加价会自动创建
              </span>
            </div>
          </div>

          <div v-if="costLoading" class="state-tip mini">加载中...</div>

          <!-- 价格记录 -->
          <table v-else-if="prices.length" class="cost-table">
            <thead>
              <tr>
                <th style="width:96px">日期</th>
                <th style="width:96px" class="ta-r">单价</th>
                <th style="width:170px">订单号</th>
                <th>供应商</th>
                <th style="width:104px">来源</th>
                <th v-if="canEditPrice" style="width:44px"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in prices" :key="row.id">
                <td>{{ row.price_date || '—' }}</td>
                <td class="ta-r price-val">¥{{ Number(row.unit_price).toFixed(4) }}</td>
                <!-- 导入时的采购订单号；手动添加的价格没有订单号 -->
                <td>
                  <span v-if="row.order_no" class="order-tag mono" :title="row.order_no">{{ row.order_no }}</span>
                  <span v-else class="cell-muted">—</span>
                </td>
                <td>
                  <template v-if="canEditPrice">
                    <div class="sup-cell">
                      <el-select
                        v-model="row._supplierDraft" class="sup-select" size="small"
                        filterable clearable allow-create default-first-option
                        placeholder="选择或输入"
                      >
                        <el-option v-for="s in supplierOptions" :key="s.id" :label="s.name" :value="s.name" />
                      </el-select>
                      <button v-if="(row._supplierDraft || '') !== (row.supplier_name || '')"
                              class="sup-ok" title="确认" @click="saveSupplier(row)">✓</button>
                    </div>
                  </template>
                  <span v-else>{{ row.supplier_name || '—' }}</span>
                </td>
                <td>
                  <span class="src-tag" :class="'src-' + row.source">
                    {{ SOURCE_LABELS[row.source] || row.source }}
                  </span>
                </td>
                <td v-if="canEditPrice">
                  <button class="del-btn" title="删除" @click="removePrice(row)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>

          <div v-else class="cost-empty">暂无价格记录</div>
          </template>

          <!-- 成本备注：属于 cost_bom_node.notes，与上面「人工维护」的备注是
               两个不同字段，刻意分开显示避免互相覆盖 -->
          <div v-if="detail.has_cost_node && detail.cost_notes" class="cost-notes">
            <label>成本备注</label><span>{{ detail.cost_notes }}</span>
          </div>
        </div>
       </div><!-- /mc-scroll -->

      </template>
    </div>
  </el-dialog>

  <MaterialBomDialog ref="bomDialogRef" @open-code="onBomDialogCode" />

  <MaterialPriceTrendDialog
    v-model="trendOpen"
    :title="detail ? `${detail.code} ${detail.name || ''}` : ''"
    :prices="prices"
    :calc-history="calcPrice?.history || []"
    :title-prefix="calcPrice ? '成本趋势' : '价格趋势'"
  />

  <MediaViewer v-model="viewerOpen" :items="viewerItems" :initial-index="currentIdx" />
</template>

<style scoped>
.material-card {
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 13px; color: var(--text-primary);
}
.state-tip { font-size: 13px; color: #6b5e4e; padding: 32px 0; text-align: center; }
.error-bar {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 12px; padding: 8px 12px;
  background: rgba(208,90,60,0.06); border: 1px solid rgba(208,90,60,0.2);
  border-radius: 7px; color: #d05a3c; font-size: 12px;
}

/* ── 图片 ─────────────────────────────────────── */
.mc-image {
  height: 180px; margin-bottom: 16px;
  border: 1px solid var(--border); border-radius: 12px;
  background: #fff; overflow: hidden;
  display: flex; align-items: center; justify-content: center;
}
/* 图片在固定尺寸的框内等比缩放居中，框本身不随图片实际尺寸变化 */
.mc-image img { width: 100%; height: 100%; object-fit: contain; display: block; }
.mc-image-empty {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  color: var(--text-muted); font-size: 12px;
}
.mc-image-empty .el-icon { font-size: 28px; }

/* ── 分区 ─────────────────────────────────────── */
.mc-section {
  margin-bottom: 18px; padding: 14px;
  background: var(--bg-card);
  border: 1px solid var(--border); border-radius: 12px;
}
.mc-section-title {
  font-size: 11px; font-weight: 700; color: var(--accent);
  letter-spacing: 0.08em; margin-bottom: 12px;
}
.mc-field { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.mc-field:last-of-type { margin-bottom: 0; }
.mc-field-top { align-items: flex-start; }
.mc-field label {
  width: 52px; flex-shrink: 0;
  font-size: 12px; color: #6b5e4e; text-align: right;
}
.mc-field-top > label { padding-top: 5px; }

/* 物料类型：单独指定 */
.mt-box { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.mt-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.mt-chip {
  padding: 3px 10px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--bg);
  color: #6b5e4e; font-size: 11px; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
}
.mt-chip:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.mt-chip.on { font-weight: 600; }
.mt-chip:disabled { cursor: not-allowed; opacity: 0.7; }
.mt-hint {
  font-size: 11px; color: #6b5e4e; line-height: 1.6;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mt-hint b { color: #3a3028; }
.mt-reset { margin-left: 6px; color: var(--accent); cursor: pointer; }
.mt-reset:hover { text-decoration: underline; }
.mc-field > span { flex: 1; min-width: 0; word-break: break-all; }
/* 状态文字与停用角标紧挨着显示，角标不参与撑满 */
.mc-field > span.status-text, .mc-field > span.ro-badge { flex: none; }
.mono { font-family: monospace; font-size: 12px; }
.muted { color: #6b5e4e; }

.mc-input {
  flex: 1; height: 30px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg); color: var(--text-primary);
  font-size: 12px; font-family: inherit; outline: none;
  transition: border-color 0.2s;
}
.mc-input:focus { border-color: var(--accent); }
.mc-textarea {
  flex: 1; padding: 7px 10px;
  border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg); color: var(--text-primary);
  font-size: 12px; font-family: inherit; outline: none; resize: vertical;
  transition: border-color 0.2s;
}
.mc-textarea:focus { border-color: var(--accent); }


/* 只读的停用角标——停用状态来源于导入数据，卡片不提供修改入口 */
.ro-badge {
  font-size: 10px; font-weight: 600;
  border: 1px solid; border-radius: 4px; padding: 1px 7px; flex-shrink: 0;
}
.ro-badge.on  { color: #4a8f6a; background: rgba(74,143,106,0.12); border-color: rgba(74,143,106,0.4); }
.ro-badge.off { color: #d05a3c; background: rgba(208,90,60,0.1);  border-color: rgba(208,90,60,0.35); }


/* ── 操作 ─────────────────────────────────────── */
.btn {
  padding: 6px 18px; border-radius: 7px;
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.2s; border: none;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { background: var(--bg); border: 1px solid var(--border); color: #6b5e4e; }
.btn-secondary:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover:not(:disabled) { filter: brightness(1.1); }

/* ── 布局：第一行 图片|ERP 信息，其下 人工维护、价格 通栏 ── */
/* 整体一个滚动容器，价格表很长时只滚卡片内容，操作按钮始终可见 */
.mc-scroll { max-height: 72vh; overflow-y: auto; padding-right: 4px; }
.mc-scroll::-webkit-scrollbar { width: 4px; }
.mc-scroll::-webkit-scrollbar-track { background: transparent; }
.mc-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.mc-scroll > .mc-section:last-child { margin-bottom: 0; }

.mc-top { display: flex; align-items: stretch; gap: 16px; margin-bottom: 18px; }
.mc-top-image { width: 40%; flex-shrink: 0; display: flex; flex-direction: column; }
/* 图片列总高固定 = 图片框 220 + 缩略图条 56（上间距 8 + 条高 48）；
   无图时图片框直接占满 276，卡片尺寸不随图片数量变化 */
.mc-top-image { height: 276px; }
.mc-top-image .mc-image { flex: none; height: 220px; margin-bottom: 0; }
.mc-top-image .mc-image.no-images { height: 276px; }

/* 图片悬停遮罩 + 圆形图标按键 */
.mc-image { position: relative; }
.mc-img-mask {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center; gap: 12px;
  background: rgba(30,24,18,0.45);
  opacity: 0; transition: opacity 0.18s;
}
.mc-image:hover .mc-img-mask { opacity: 1; }
.mc-round-btn {
  width: 36px; height: 36px; border-radius: 50%;
  border: none; background: rgba(255,255,255,0.92); color: #3a3028;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 16px; cursor: pointer;
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
  transition: transform 0.15s, background 0.15s, color 0.15s;
}
.mc-round-btn:hover:not(:disabled) { transform: scale(1.08); background: #fff; color: var(--accent); }
.mc-round-btn.danger:hover:not(:disabled) { color: #d05a3c; }
.mc-round-btn:disabled { opacity: 0.5; cursor: not-allowed; }
/* 无图时的新增按键：直接放在图片区域中间 */
.mc-round-btn.solo {
  width: 48px; height: 48px; font-size: 22px;
  background: var(--bg-card); color: var(--accent);
  border: 1.5px dashed var(--accent); box-shadow: none;
}
.mc-img-count {
  position: absolute; right: 8px; bottom: 8px;
  font-size: 11px; color: #fff; background: rgba(0,0,0,0.45);
  border-radius: 10px; padding: 1px 8px; pointer-events: none;
}
/* 产品库图片来源角标（左上角） */
.mc-img-source {
  position: absolute; left: 8px; top: 8px;
  padding: 2px 8px; border-radius: 10px;
  background: rgba(0,0,0,0.5); color: #fff; font-size: 11px;
  pointer-events: none;
}
.mc-img-busy {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,0.6); color: #3a3028; font-size: 12px;
}
.mc-thumbs {
  display: flex; gap: 6px; margin-top: 8px;
  height: 48px; flex: none; box-sizing: border-box;
  overflow-x: auto; overflow-y: hidden; align-items: flex-start;
}
.mc-thumbs::-webkit-scrollbar { height: 4px; }
.mc-thumbs::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.mc-thumb {
  width: 44px; height: 44px; flex-shrink: 0; padding: 0; box-sizing: border-box;
  border: 1.5px solid var(--border); border-radius: 6px; background: #fff;
  overflow: hidden; cursor: pointer;
}
.mc-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.mc-thumb.active { border-color: var(--accent); }

/* 人工维护在图片右侧：与图片列等高，备注框吃掉剩余高度 */
.mc-top .mc-manual {
  flex: 1; min-width: 0; margin-bottom: 0;
  display: flex; flex-direction: column;
}
.mc-manual > .mc-field { margin-bottom: 8px; }
.mc-manual .mc-field-remark { flex: 1; min-height: 0; margin-bottom: 0; }
.mc-manual .mc-field-remark .mc-textarea { height: 100%; min-height: 48px; resize: none; }

/* 标题栏（el-dialog #header 插槽）：状态 编码 名称 …… 关闭，底部分割线 */
.mc-erp-line {
  display: flex; align-items: center; gap: 12px; min-width: 0;
}
.mc-erp-code {
  /* 固定黑色加粗，不跟随主题 */
  flex-shrink: 0;
  font-size: 17px; font-weight: 700; color: #000;
}
.mc-erp-name {
  /* 不占满剩余空间，状态角标紧跟在名称后面；过长时省略 */
  flex: 0 1 auto; min-width: 0;
  font-size: 15px; font-weight: 400; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mc-erp-line .ro-badge { flex-shrink: 0; font-size: 11px; padding: 2px 8px; }
/* 关闭：圆形图标按键 */
.mc-close-btn {
  margin-left: auto; flex-shrink: 0;
  width: 30px; height: 30px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  border: 1px solid var(--border); background: var(--bg-card);
  color: #3a3028; font-size: 15px; cursor: pointer;
  transition: all 0.15s;
}
.mc-back-btn {
  flex-shrink: 0; width: 30px; height: 30px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  border: 1px solid var(--border); background: var(--bg-card);
  color: #3a3028; font-size: 15px; cursor: pointer; transition: all 0.15s;
}
.mc-back-btn:hover { border-color: var(--accent); color: var(--accent); }

/* ── 研发 BOM 区 ── */
.mc-bom .mc-section-title, .mc-used .mc-section-title { align-items: center; }
.bom-drawing { font-weight: 700; color: #2c2420; }
/* 研发版本名称用 ERP 全名（较长），完整显示、需要时换行，不截断 */
.bom-name { word-break: break-all; }
.bom-view-btn {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 2px 10px; border-radius: 12px; cursor: pointer;
  border: 1px solid var(--accent); background: transparent; color: var(--accent);
  font-size: 12px; font-family: inherit; white-space: nowrap; transition: all 0.15s;
}
.bom-view-btn:hover { background: var(--accent); color: #fff; }

.own-title { margin: 6px 0 -2px; font-size: 13px; font-weight: 600; color: #3a3028; }
.np-note { margin: 4px 0 6px; font-size: 12px; color: #6b5e4e; }
.np-box { display: flex; align-items: center; gap: 8px; min-width: 0; }
.np-check {
  display: inline-flex; align-items: center; gap: 6px; cursor: pointer; flex-shrink: 0;
  font-size: 13px; color: #3a3028; width: auto !important; text-align: left !important;
}
.np-check input { margin: 0; cursor: pointer; }
.np-check.on { font-weight: 600; }
.np-check.off { color: #b0a494; cursor: not-allowed; }
.np-check.off input { cursor: not-allowed; }
.np-hint { font-size: 11px; color: #8a7a6a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.own-title span { margin-left: 6px; font-size: 11px; font-weight: 400; color: #8a7a6a; }
.bom-ver-text { font-size: 12px; font-weight: 400; color: #6b5e4e; letter-spacing: 0; }
.used-block { margin-bottom: 10px; }
.used-label { font-size: 12px; color: #6b5e4e; margin-bottom: 6px; }
.used-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.used-chip {
  display: inline-flex; align-items: center; gap: 6px; max-width: 100%;
  padding: 3px 10px; border-radius: 12px; cursor: pointer;
  border: 1px solid rgba(196,136,58,0.4); background: rgba(196,136,58,0.08);
  font-size: 12px; font-family: inherit; color: #3a3028;
}
.used-chip b { font-weight: 700; color: #000; }
.used-chip span { color: #6b5e4e; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.used-chip:hover:not(.nolink) { border-color: var(--accent); }
.used-chip.nolink { cursor: default; }
.bom-link { cursor: pointer; }
.bom-link:hover { color: var(--accent); text-decoration: underline; }
.cell-muted { color: var(--text-muted); }

.mc-close-btn:hover { border-color: #d05a3c; color: #d05a3c; background: rgba(208,90,60,0.06); }

/* 人工维护标题行：右侧确认图标。按键高度压在 22px 内，保证分区仍与图片列等高 */
.mc-manual .mc-section-title { align-items: center; min-height: 22px; margin-bottom: 8px; }
.mc-dirty {
  margin-left: 8px; font-size: 11px; font-weight: 400; letter-spacing: 0;
  color: #c0782a;
}
.mc-save-btn {
  width: 22px; height: 22px; border-radius: 50%; padding: 0;
  display: inline-flex; align-items: center; justify-content: center;
  border: 1px solid var(--border); background: var(--bg-card);
  color: #8a7a6a; font-size: 13px; cursor: pointer; transition: all 0.15s;
}
.mc-save-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.mc-save-btn.active:hover { filter: brightness(1.1); }
.mc-save-btn:disabled { cursor: not-allowed; }
.mc-save-btn:not(.active):disabled { opacity: 0.6; }

/* ── 价格区 ───────────────────────────────────── */
.mc-section-title { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.mc-latest { font-size: 12px; color: var(--text-secondary); font-weight: 400; }
.mc-latest b { font-family: 'SF Mono', Consolas, monospace; color: #3d2b1a; font-size: 13px; }
.mc-src { margin-left: 6px; color: var(--text-secondary); }

.cost-tabs { display: flex; align-items: center; gap: 6px; margin: 10px 0 8px; }
.cost-count { font-size: 13px; font-weight: 600; color: #3a3028; }
/* 订单号 tag：浅蓝底，超长省略（悬停看全文） */
.order-tag {
  display: inline-block; max-width: 160px; vertical-align: middle;
  padding: 0 7px; border-radius: 4px; font-size: 11px; line-height: 18px;
  color: #3d6f94; background: rgba(74,143,192,0.1); border: 1px solid rgba(74,143,192,0.35);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cost-trend {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 12px; border-radius: 12px; cursor: pointer;
  border: 1px solid var(--accent); background: transparent; color: var(--accent);
  font-size: 12px; font-family: inherit; transition: all 0.15s;
}
.cost-trend:hover:not(:disabled) { background: var(--accent); color: #fff; }
.cost-trend:disabled { opacity: 0.45; cursor: not-allowed; }
.cost-add {
  margin-left: auto; padding: 4px 12px; border-radius: 7px;
  border: 1px solid var(--accent); background: var(--accent-bg);
  color: var(--accent); font-size: 12px; font-family: inherit; cursor: pointer;
}
.cost-add:hover { background: var(--accent); color: #fff; }
.cost-locked { margin-left: auto; font-size: 12px; color: var(--text-secondary); }

/* 添加价格表单 */
.price-form {
  padding: 10px 12px; margin-bottom: 8px;
  background: var(--bg); border: 1px solid var(--border); border-radius: 9px;
}
.pf-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.pf-row label { font-size: 12px; color: var(--text-secondary); flex-shrink: 0; width: 46px; }
.pf-row label b { color: #d05a3c; }
.pf-row .mc-input { flex: 1; min-width: 0; }
.pf-actions { display: flex; align-items: center; gap: 10px; }
.pf-hint { font-size: 11px; color: var(--text-secondary); }
.btn.sm { padding: 5px 14px; font-size: 12px; }

/* 价格 / 使用记录表 */
.cost-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.cost-table th {
  text-align: left; font-weight: 600; color: var(--text-secondary);
  padding: 6px 8px; border-bottom: 1px solid var(--border); white-space: nowrap;
}
.cost-table td {
  padding: 5px 8px; border-bottom: 1px solid var(--border);
  color: var(--text-primary); vertical-align: middle;
}
.cost-table tr:last-child td { border-bottom: none; }
.ta-r { text-align: right; }
.ellip { max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.price-val { font-family: 'SF Mono', Consolas, monospace; font-weight: 600; }

.src-tag {
  display: inline-block; padding: 1px 6px; border-radius: 4px;
  font-size: 11px; border: 1px solid;
  white-space: nowrap;   /* 「BOM 导入」含空格，不加会断成两行 */
}
.src-bom_import { color: #4a8fc0; background: rgba(74,143,192,0.1);  border-color: rgba(74,143,192,0.35); }
.src-manual     { color: #6ab47a; background: rgba(106,180,122,0.1); border-color: rgba(106,180,122,0.35); }
.src-bom_calc   { color: #9c6fba; background: rgba(156,111,186,0.1); border-color: rgba(156,111,186,0.35); }

.sup-cell { display: flex; align-items: center; gap: 4px; }
.sup-select { flex: 1; min-width: 0; }
.pf-select { flex: 1; min-width: 0; }
.mc-input.tiny { padding: 3px 7px; font-size: 12px; }
.sup-ok {
  border: none; background: transparent; color: #6ab47a;
  font-size: 15px; cursor: pointer; padding: 0 2px; line-height: 1;
}
.del-btn {
  border: none; background: transparent; color: #d05a3c;
  font-size: 12px; font-family: inherit; cursor: pointer; padding: 0;
}
.del-btn:hover { text-decoration: underline; }

.cost-empty { padding: 16px 0; text-align: center; font-size: 12px; color: var(--text-secondary); }
.state-tip.mini { padding: 16px 0; font-size: 12px; }
.error-bar.mini { margin: 0 0 8px; padding: 6px 10px; font-size: 12px; }

.cost-notes {
  margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border);
  display: flex; gap: 10px; font-size: 12px;
}
.cost-notes label { color: var(--text-secondary); flex-shrink: 0; }
</style>

<!-- 非 scoped：el-dialog 会被 Teleport 到 body，scoped/:deep() 都命不中它自身的结构，
     必须用自定义类名写全局样式（见 feedback_eldialog_teleport_scoped_css_bug）。
     第一条是占位：dev 环境下非 scoped 块的第一条规则可能被丢弃 -->
<style>
.material-card-dialog-css-order-guard { all: unset; }
.el-dialog.material-card-dialog { --el-dialog-border-radius: 14px; }
/* 标题栏分割线延伸到弹窗左右边界：抵消 el-dialog 自身的左右内边距 */
.el-dialog.material-card-dialog .el-dialog__header {
  margin: 0 calc(-1 * var(--el-dialog-padding-primary)) 16px;
  padding: 0 var(--el-dialog-padding-primary) 14px;
  border-bottom: 1px solid var(--border);
}
</style>
