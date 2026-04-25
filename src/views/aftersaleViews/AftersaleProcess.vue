<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Setting, ArrowDown, Refresh, Loading } from '@element-plus/icons-vue'
import http from '@/api/http.js'
import { usePermission } from '@/composables/usePermission.js'
import AftersaleReasonLib from './AftersaleReasonLib.vue'

// ── Props / Emits ─────────────────────────────────
const emit = defineEmits(['case-confirmed'])

// ── 权限 ──────────────────────────────────────────
const { canEditAftersale } = usePermission()

// ── 响应式状态 ────────────────────────────────────
// 左侧队列
const orders      = ref([])
const totalOrders = ref(0)
const page        = ref(1)
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]
const pageSize    = ref(Number(localStorage.getItem('aftersale_page_size') || 50))
const loadingList = ref(false)
const totalPages  = computed(() => Math.ceil(totalOrders.value / pageSize.value))
const currentPageRemaining = computed(() => orders.value.length)

// 批量处理
const batchMode         = ref(false)
const batchResults      = ref({})   // orderNo → { status, content, order, products }
const batchRunning      = ref(false)
const batchSubmitting   = ref(false)
const selectingOrder    = ref(false) // 切换工单期间屏蔽 contentItems watch
// auto + ignore 均视为可批量处理（ignore 工单批量时调忽略接口）
const BATCH_WHITELIST = new Set(['auto', 'ignore'])
const allBatchAuto    = computed(() =>
  !batchRunning.value &&
  batchMode.value &&
  orders.value.length > 0 &&
  orders.value.every(o => BATCH_WHITELIST.has(batchResults.value[o.ecommerce_order_no]?.status?.level))
)

// 当前工单
const currentOrder  = ref(null)
const saving        = ref(false)
const ignoring      = ref(false)

// 当前工单日期编辑状态
const aftersaleDate = ref(null)   // 售后日期（来自 shipped_date，可编辑）

// 弹窗
const showReasonLib = ref(false)

// 物料简称列表（用于发货物料别名合并显示）

// 发货物料简称库（下拉候选）
const shippingAliasOptions  = ref([])   // [{id, name, keywords}]
const ambiguousTerms        = ref([])   // string[] 歧义词列表
// 发货物料匹配过滤词（物料名称含这些词时跳过简称匹配）
const shippingIgnoreTerms  = ref([])   // [{id, term}]

// 品类树（三级联动，缓存）
const categoryTree = ref([])

// 型号生命周期范围 { model_id: { listed_yymm, delisted_yymm } }
const modelLifecycles = ref({})

// 产品留言词典（材质/颜色/驱动/尺寸），从 DB 加载，供 parseRemark 使用
const remarkDict = ref({ materials: [], colors: [], drive_types: [], sizes: {} })

// 一级原因分类列表（所有分类，含空分类）
const reasonCategories = ref([])   // [{id, name, sort_order}]
// 原因按分类分组（含二级原因列表）
const reasonGroups = ref([])       // [{category_id, category_name, reasons:[{id,name,...}]}]

// 售后内容列表
// 每项：{ category_id, series_id, model_id,
//         shipping_alias_id, reason_category_id, reason_id }
const contentItems = ref([])

// 产品匹配依据（选单后填充，用于底部说明面板）
const matchDebug          = ref(null)   // null | { source, text, category_name, ... }
const showMatchDebug      = ref(true)   // 展开/折叠控制
const expandedCandidates  = ref(new Set())   // 已展开系列的下标集合
// ── 计算属性 ──────────────────────────────────────

// 当前工单自动匹配状态：auto=可直接确认 / confirm=需再次确认 / ignore=可忽略
const matchStatus = computed(() => {
  const d = matchDebug.value
  if (!d) return null

  const hasProduct = !!d.source
  const hasAlias   = !!d.alias_id
  const hasReason  = (d.reason_candidates?.length > 0)  // 仅关键词匹配算有原因；纯历史建议不计入

  // 可忽略：售后产品未找到匹配
  if (!hasProduct) {
    return { level: 'ignore', label: '可忽略', tip: '未匹配到售后产品，该工单可能无需处理' }
  }

  // 可直接确认：系列高置信 + 型号高/空置信 + 日期有效 + 有原因 + 有发货简称
  const seriesOk = d.series_confidence === 'high'
  const modelOk  = d.model_confidence === 'high' || d.model_confidence == null
  const dateOk   = d.date_ok !== false
  if (hasProduct && seriesOk && modelOk && dateOk && hasReason && hasAlias) {
    return { level: 'auto', label: '直接确认', tip: '系列与型号高置信匹配，购买日期在售，原因与简称均已匹配' }
  }

  // 其余：需用户确认
  const reasons = []
  if (!hasProduct)        reasons.push('未匹配到型号')
  else if (!seriesOk)     reasons.push('系列置信度低')
  else if (!modelOk)      reasons.push('型号置信度低')
  if (!dateOk)            reasons.push('购买日期不在生命周期内')
  if (!hasReason)         reasons.push('未匹配到售后原因')
  if (!hasAlias)          reasons.push('未匹配到发货简称')
  return { level: 'confirm', label: '待核实', tip: reasons.join('；') || '请核实匹配结果后确认' }
})

// 品类选项（产品库三级联动第一级）
const categoryOptions = computed(() =>
  categoryTree.value.map(c => ({ value: c.id, label: c.name }))
)

// 当前工单「发货物料」列表（只读）
const resolvedProducts = computed(() => currentOrder.value?.products || [])

// 是否有多个售后内容面板（决定是否显示物料勾选区）
const multipleItems = computed(() => contentItems.value.length >= 2)

// 提交按钮可用条件：所有内容项必填字段均已填写
const canConfirm = computed(() => {
  if (!contentItems.value.length) return false
  return contentItems.value.every(item => {
    const hasReason = !!(item.reason_id || item.custom_reason?.trim())
    const hasProducts = !multipleItems.value || item._selectedProducts?.length > 0
    return !!(
      item.model_id &&
      item.shipping_alias_id &&

      item.reason_category_id &&
      hasReason &&
      item.purchase_date &&
      hasProducts
    )
  })
})

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  // 先并发加载匹配所需的基础数据，再加载订单列表
  // 避免 selectOrder 运行时 categoryTree / productAliases / reasonGroups 尚未就绪
  await Promise.all([loadCategoryTree(), loadAliases(), loadReasonOptions(), loadRemarkDict(), loadAmbiguousTerms()])
  loadOrders()
})

// ── 方法 ──────────────────────────────────────────

// 加载指定页（p 省略时重置第1页）
async function loadOrders(p) {
  loadingList.value = true
  if (p != null) page.value = p
  else page.value = 1
  try {
    const res = await http.get('/api/aftersale/pending', {
      params: { page: page.value, page_size: pageSize.value },
    })
    if (res.success) {
      orders.value      = res.data.items
      totalOrders.value = res.data.total
      if (!currentOrder.value && orders.value.length > 0) {
        selectOrder(orders.value[0])
      }
    }
  } finally {
    loadingList.value = false
  }
}

function goPrev() { if (page.value > 1) loadOrders(page.value - 1) }
function goNext() { if (page.value < totalPages.value) loadOrders(page.value + 1) }

// 每页条数变更时持久化并重载
watch(pageSize, v => { localStorage.setItem('aftersale_page_size', String(v)); loadOrders(1) })

// 用户修改工单内容时，若批量状态为 auto，降级为 modified，防止误批量提交
watch(contentItems, () => {
  if (!batchMode.value || !currentOrder.value || selectingOrder.value) return
  const orderNo = currentOrder.value.ecommerce_order_no
  const r = batchResults.value[orderNo]
  if (r?.status?.level === 'auto') {
    batchResults.value[orderNo] = {
      ...r,
      status: { level: 'modified', label: '直接确认（有修改）', tip: '内容已手动修改，请通过工单内提交' },
    }
  }
}, { deep: true, flush: 'sync' })

// 刷新队列并退出批量模式
function refreshQueue() {
  batchMode.value    = false
  batchResults.value = {}
  loadOrders(1)
}

// 加载品类树 + 型号生命周期（并发）
async function loadCategoryTree() {
  const [treeRes, lcRes] = await Promise.allSettled([
    http.get('/api/category/tree'),
    http.get('/api/category/model-lifecycles'),
  ])
  if (treeRes.status === 'fulfilled' && treeRes.value?.success)
    categoryTree.value    = treeRes.value.data
  if (lcRes.status === 'fulfilled' && lcRes.value?.success)
    modelLifecycles.value = lcRes.value.data
}

// 加载发货物料歧义词
async function loadAmbiguousTerms() {
  const res = await http.get('/api/aftersale/shipping-ambiguous-terms').catch(() => null)
  if (res?.success) ambiguousTerms.value = (res.data || []).map(t => t.term.toLowerCase())
}

// 加载产品留言词典（材质/颜色/驱动/尺寸）
async function loadRemarkDict() {
  const res = await http.get('/api/aftersale/product-remark-dict').catch(() => null)
  if (!res?.success) return
  const dict = { materials: [], colors: [], drive_types: [], sizes: {} }
  for (const item of res.data) {
    if (!item.enabled) continue
    if (item.type === 'material')   dict.materials.push(item.value)
    else if (item.type === 'color') dict.colors.push(item.value)
    else if (item.type === 'drive_type') dict.drive_types.push(item.value)
    else if (item.type === 'size' && item.display) dict.sizes[item.value] = item.display
  }
  remarkDict.value = dict
}

// 加载物料简称（发货简称库 + 过滤词）
// 使用 allSettled 确保任一请求失败不会阻断其他加载
async function loadAliases() {
  const [shipRes, ignoreRes] = await Promise.allSettled([
    http.get('/api/aftersale/shipping-aliases'),
    http.get('/api/aftersale/shipping-ignore-terms'),
  ])
  if (shipRes.status === 'fulfilled' && shipRes.value?.success)
    shippingAliasOptions.value = shipRes.value.data
  if (ignoreRes.status === 'fulfilled' && ignoreRes.value?.success)
    shippingIgnoreTerms.value  = ignoreRes.value.data
}

// 同时加载原因分类（全部）和原因分组（含二级）
async function loadReasonOptions() {
  const [catRes, reasonRes] = await Promise.all([
    http.get('/api/aftersale/reason-categories'),
    http.get('/api/aftersale/reasons'),
  ])
  if (catRes.success)    reasonCategories.value = catRes.data
  if (reasonRes.success) reasonGroups.value     = reasonRes.data
}


/**
 * 从备注文本中尝试识别购买日期，返回 'YYYY-MM-DD' 或 null。
 * 匹配顺序（优先级从高到低）：
 *   1. YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD
 *   2. YYYY年M月D日
 *   3. YY-MM-DD / YY/MM/DD（自动补 20xx）
 *   4. YYYYMMDD（8位纯数字）
 */
function parsePurchaseDateFromRemark(text) {
  if (!text) return null

  // YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD
  let m = text.match(/(\d{4})[-\/.](\d{1,2})[-\/.](\d{1,2})/)
  if (m) {
    const [, y, mo, d] = m
    return `${y}-${mo.padStart(2, '0')}-${d.padStart(2, '0')}`
  }

  // YYYY年M月D日
  m = text.match(/(\d{4})年(\d{1,2})月(\d{1,2})日?/)
  if (m) {
    const [, y, mo, d] = m
    return `${y}-${mo.padStart(2, '0')}-${d.padStart(2, '0')}`
  }

  // YY-MM-DD / YY/MM/DD
  m = text.match(/(\d{2})[-\/](\d{1,2})[-\/](\d{1,2})/)
  if (m) {
    const [, y, mo, d] = m
    return `20${y}-${mo.padStart(2, '0')}-${d.padStart(2, '0')}`
  }

  // YYYYMMDD（8位纯数字，月份和日期做基本合法性检查）
  m = text.match(/\b(\d{4})(\d{2})(\d{2})\b/)
  if (m) {
    const [, y, mo, d] = m
    if (+mo >= 1 && +mo <= 12 && +d >= 1 && +d <= 31) {
      return `${y}-${mo}-${d}`
    }
  }

  return null
}

// 选中某个待处理订单：自动创建第一条售后内容并推断型号
async function selectOrder(order) {
  currentOrder.value  = order
  aftersaleDate.value = order.shipped_date || null
  matchDebug.value    = null

  // 从商家备注解析购买日期（仅用于初始推断，存入第一条内容项）
  const parsedPurchaseDate = parsePurchaseDateFromRemark(order.seller_remark)

  // 检测买家/商家备注是否含 / 多产品段落
  const slashSegments = detectSlashSegments(order.buyer_remark, order.seller_remark)
  const isMultiProduct = slashSegments.length >= 2

  // 先放一条空内容占位，并预填购买日期
  const firstItem = makeEmptyItem()
  firstItem.purchase_date = parsedPurchaseDate
  selectingOrder.value = true
  contentItems.value = [firstItem]

  const orderNo   = order.ecommerce_order_no
  const debugText = [order.buyer_remark, order.seller_remark].filter(Boolean).join(' ')
  const debugBuyerRemark  = order.buyer_remark  || ''
  const debugSellerRemark = order.seller_remark || ''

  // ── 来源1：产品代码 + 历史工单（后端）+ 原因候选（并发）──
  let apiResult        = null   // 原始 API 返回（含 suggested_shipping_alias）
  let reasonCandidates = []     // auto-match 返回的原因候选列表
  let reasonCleanedText = ''   // auto-match 清洗后的参与匹配文本

  try {
    await Promise.all([
      // 每次选单时刷新歧义词（词典页可能刚更新）
      http.get('/api/aftersale/shipping-ambiguous-terms')
        .then(r => { if (r?.success) ambiguousTerms.value = (r.data || []).map(t => t.term.toLowerCase()) })
        .catch(() => null),
      (order.buyer_remark?.trim() || order.products?.length)
        ? http.post('/api/aftersale/suggest-product', {
            products:      order.products || [],
            purchase_date: parsedPurchaseDate || null,
            seller_remark: order.seller_remark || null,
            buyer_remark:  order.buyer_remark  || null,
          }).then(r => { if (r.success && r.data) apiResult = r.data })
        : Promise.resolve(),
      debugText.trim()
        ? http.post('/api/aftersale/auto-match', {
            text: debugText,
            buyer_remark: order.buyer_remark || '',
          }).then(r => { if (r.success && r.data) { reasonCandidates = r.data.items || []; reasonCleanedText = r.data.cleaned_text || '' } })
        : Promise.resolve(),
    ])
  } catch (e) {
    console.warn('[selectOrder] API error, proceeding without suggestions', e)
  }

  // API 型号匹配（需有 category_id 才算匹配到型号）
  const apiMatch = apiResult?.category_id ? apiResult : null

  // ── 来源2：买家留言 + 商家备注 文本匹配（前端） ──────
  const textMatch = matchTextToModel(order.buyer_remark, null, parsedPurchaseDate)

  // ── 简称候选（前端实时计算）────────────────────────
  const shippingAliasCandidates = computeShippingAliasCandidates(order.products, order.seller_remark, apiResult?.product_tokens || [])

  // 防止切换工单太快导致覆盖
  if (currentOrder.value?.ecommerce_order_no !== orderNo) return
  const item = contentItems.value[0]
  if (!item) return

  // ── 发货物料简称自动匹配（来自历史工单）────────────────
  const historyShippingId = apiResult?.suggested_shipping_alias_id || null
  const aliasSource = apiResult?.suggested_shipping_alias_source || (historyShippingId ? 'history' : null)
  if (historyShippingId) item.shipping_alias_id = historyShippingId

  // 歧义模式覆盖：当产品含歧义词时，不依赖历史记录，改用商家备注评分决定自动选择
  // remark_score=0 说明备注无法区分，不自动选任何简称
  const topCandForAlias = shippingAliasCandidates[0]
  if (topCandForAlias?.is_ambiguous) {
    const best = (topCandForAlias.remark_score ?? 0) > 0 ? topCandForAlias : null
    item.shipping_alias_id = best?.id ?? null
  }

  // 售后原因：来自历史工单（最频繁的 reason_id + category_id）
  const suggestedReasonId    = apiResult?.suggested_reason_id           || null
  const suggestedCategoryId  = apiResult?.suggested_reason_category_id  || null
  const suggestedReasonCount = apiResult?.suggested_reason_count        || null
  // 原因自动填写优先级：关键词候选 > 历史推荐（纯历史不自动填）
  if (reasonCandidates.length > 0) {
    const top = reasonCandidates[0]
    item.reason_id          = top.reason_id   || null
    item.reason_category_id = top.category_id || null
  }
  // 无关键词候选时不自动填写历史推荐，留给人工判断

  const productTokens = apiResult?.product_tokens || []

  // 最终简称 id/name/source（歧义覆盖后的实际值，用于 matchDebug）
  const finalAliasId    = item.shipping_alias_id
  const finalAliasName  = finalAliasId
    ? (shippingAliasOptions.value.find(o => o.id === finalAliasId)?.name || null)
    : null
  const finalAliasSource = topCandForAlias?.is_ambiguous
    ? (finalAliasId ? 'ambiguous' : null)
    : aliasSource

  // ── 填充型号 + 构建匹配依据 ──────────────────────────
  if (apiMatch) {
    // API 匹配到（产品代码/历史工单）
    // date_ok=false 表示购买日期不在该型号生命周期内
    const dateOk = apiMatch.date_ok !== false
    let dateReason = null
    if (!dateOk && apiMatch.model_id) {
      const buyYm = parsedPurchaseDate ? parsedPurchaseDate.slice(0, 7) : null
      if (buyYm) {
        const lc = modelLifecycles.value[apiMatch.model_id]
        if (lc) {
          const tooEarly  = lc.listed_yymm && buyYm < lc.listed_yymm
          dateReason = tooEarly ? 'too_early' : 'too_late'
        }
      }
    }
    // date_ok=false 时仅填品类/系列，不自动填入型号——生命周期不符的型号让用户手动确认
    item.category_id      = apiMatch.category_id
    item.series_id        = apiMatch.series_id
    item.model_id         = dateOk ? apiMatch.model_id : null
    item.confidence       = apiMatch.series_confidence || (dateOk ? 'high' : 'low')
    item.model_confidence = dateOk ? (apiMatch.model_confidence || null) : null
    const names = resolveModelNames(apiMatch.category_id, apiMatch.series_id, apiMatch.model_id)
    matchDebug.value = {
      source:             'api',
      text:               debugText,
      date_ok:            dateOk,
      date_reason:        dateReason,
      category_name:      names.category_name,
      series_name:        names.series_name,
      model_name:         names.model_name,
      model_code:         names.model_code,
      score:              null,
      confidence:         apiMatch.series_confidence || 'high',
      series_confidence:  apiMatch.series_confidence || null,
      model_confidence:   apiMatch.model_confidence  || null,
      candidates:             (apiMatch.candidates || []).map(c => ({
        ...c,
        models: (c.models || []).map(m => ({
          ...m,
          lifecycleOk:     m.date_ok !== false,
          lifecycleStatus: m.date_ok === false ? 'too_early' : null,
        })),
      })),
      alias_source:              finalAliasSource,
      alias_id:                  finalAliasId,
      alias_value:               finalAliasName,
      suggested_reason_id:       suggestedReasonId,
      suggested_category_id:     suggestedCategoryId,
      suggested_reason_count:    suggestedReasonCount,
      shipping_alias_candidates: shippingAliasCandidates,
      reason_candidates:         reasonCandidates,
      product_tokens:            productTokens,
      reason_cleaned_text:       reasonCleanedText,
      buyer_remark:              debugBuyerRemark,
      seller_remark:             debugSellerRemark,
    }
  } else if (textMatch?.noMatch) {
    // 文本匹配明确失败（如生命周期全部不符）→ 不填型号，显示失败原因
    matchDebug.value = {
      source:                    null,
      no_match_reason:           textMatch.reason,
      text:                      debugText,
      confidence:                null,
      candidates:                [],
      alias_source:              finalAliasSource,
      alias_id:                  finalAliasId,
      alias_value:               finalAliasName,
      suggested_reason_id:       suggestedReasonId,
      suggested_category_id:     suggestedCategoryId,
      suggested_reason_count:    suggestedReasonCount,
      shipping_alias_candidates: shippingAliasCandidates,
      reason_candidates:         reasonCandidates,
      product_tokens:            productTokens,
      reason_cleaned_text:       reasonCleanedText,
      buyer_remark:              debugBuyerRemark,
      seller_remark:             debugSellerRemark,
    }
  } else if (textMatch) {
    // 仅文本匹配 → 根据分数设置置信度
    item.category_id      = textMatch.category_id
    item.series_id        = textMatch.series_id
    item.model_id         = textMatch.model_id
    item.confidence       = textMatch.series_confidence
    item.model_confidence = textMatch.model_confidence || null
    matchDebug.value = {
      source:             'text',
      text:               debugText,
      category_name:      textMatch.category_name,
      series_name:        textMatch.series_name,
      model_name:         textMatch.model_name,
      model_code:         textMatch.model_code,
      score:              textMatch.score,
      confidence:         textMatch.series_confidence,
      series_confidence:  textMatch.series_confidence,
      model_confidence:   textMatch.model_confidence || null,
      candidates:             textMatch.candidates || [],
      alias_source:              finalAliasSource,
      alias_id:                  finalAliasId,
      alias_value:               finalAliasName,
      suggested_reason_id:       suggestedReasonId,
      suggested_category_id:     suggestedCategoryId,
      suggested_reason_count:    suggestedReasonCount,
      shipping_alias_candidates: shippingAliasCandidates,
      reason_candidates:         reasonCandidates,
      product_tokens:            productTokens,
      reason_cleaned_text:       reasonCleanedText,
      buyer_remark:              debugBuyerRemark,
      seller_remark:             debugSellerRemark,
    }
  } else {
    // 型号无匹配 → 保持空白
    matchDebug.value = {
      source:                 null,
      text:                   debugText,
      confidence:             null,
      candidates:             [],
      alias_source:              finalAliasSource,
      alias_id:                  finalAliasId,
      alias_value:               finalAliasName,
      suggested_reason_id:       suggestedReasonId,
      suggested_category_id:     suggestedCategoryId,
      suggested_reason_count:    suggestedReasonCount,
      shipping_alias_candidates: shippingAliasCandidates,
      reason_candidates:         reasonCandidates,
      product_tokens:            productTokens,
      reason_cleaned_text:       reasonCleanedText,
      buyer_remark:              debugBuyerRemark,
      seller_remark:             debugSellerRemark,
    }
  }

  // ── 多产品模式：为每段额外建面板并独立匹配 ──────────────
  if (isMultiProduct && currentOrder.value?.ecommerce_order_no === orderNo) {
    // 为每个段落创建 item（第一个复用已有 firstItem）
    while (contentItems.value.length < slashSegments.length) {
      const ni = makeEmptyItem()
      ni.purchase_date = parsedPurchaseDate
      contentItems.value.push(ni)
    }
    // 每段独立产品匹配 + 原因候选
    await Promise.all(slashSegments.map(async (seg, i) => {
      if (currentOrder.value?.ecommerce_order_no !== orderNo) return
      const item = contentItems.value[i]
      if (!item) return
      item._segmentText = seg
      // 文本匹配产品
      const tm = matchTextToModel(seg, null, parsedPurchaseDate)
      if (tm && !tm.noMatch) {
        item.category_id = tm.category_id
        item.series_id   = tm.series_id
        item.model_id    = tm.model_id
        item.confidence  = scoreToConfidence(tm.score)
      }
      // 原因候选（per-segment auto-match）
      try {
        const r = await http.post('/api/aftersale/auto-match', { text: seg, buyer_remark: '' })
        if (r.success && currentOrder.value?.ecommerce_order_no === orderNo) {
          item._reasonCandidates = r.data || []
        }
      } catch (_) { /* ignore */ }
    }))
  }
  selectingOrder.value = false
}

// 从队列移除当前工单并选下一条
function removeCurrentFromList() {
  const idx = orders.value.findIndex(
    o => o.ecommerce_order_no === currentOrder.value?.ecommerce_order_no
  )
  if (idx !== -1) {
    orders.value.splice(idx, 1)
    totalOrders.value = Math.max(0, totalOrders.value - 1)
  }
  const next = orders.value[idx] || orders.value[idx - 1] || null
  if (next) {
    selectOrder(next)
  } else {
    currentOrder.value  = null
    contentItems.value  = []
    aftersaleDate.value = null
    matchDebug.value    = null
  }
}

// 原因库更新后刷新（同时刷新两个简称库，原因库弹窗现在也管理它们）
function onReasonLibUpdated() {
  loadReasonOptions()
  loadAliases()
}

// 物料简称更新后刷新

// ── 售后内容项操作 ──────────────────────────────────

// 创建一条空白售后内容对象（confidence: null 表示用户手动添加）
function makeEmptyItem() {
  return {
    category_id:              null,
    series_id:                null,
    model_id:                 null,
    shipping_alias_id:  null,
    reason_category_id: null,
    reason_id:          null,
    custom_reason:      '',
    confidence:         null,   // null | 'high' | 'medium' | 'low'
    purchase_date:      null,   // 该条内容的购买日期（每条可不同）
    // 内部：reason select 当前输入文字（用于显示「新」选项）
    _reasonQuery:      '',
    // 内部：发货物料简称 select 当前输入文字（用于显示「新增」选项）
    _shippingQuery:    '',
    // 内部：多面板时该内容对应的发货物料 code 列表
    _selectedProducts: [],
    // 内部：单面板时用户点选的物料 code（用于推断简称），null=未点选
    _pinnedProduct:    null,
    // 多产品模式：该面板对应的文本段（来自 / 分割）
    _segmentText:      null,
    // 多产品模式：该面板的原因候选列表（per-item auto-match 结果）
    _reasonCandidates: [],
    // 多内容时每条单独填写的商家备注（单内容时不显示，使用工单级备注）
    _seller_remark:    '',
  }
}

// 检测买家/商家备注是否包含 / 分隔的多产品段落
// 返回有效段列表（≥2 段且每段至少 2 字才触发）
function detectSlashSegments(buyerRemark, sellerRemark) {
  const text = (buyerRemark || sellerRemark || '').trim()
  if (!text.includes('/')) return []
  const segs = text.split('/').map(s => s.trim()).filter(s => s.length >= 2)
  return segs.length >= 2 ? segs : []
}

// 新增一条空白售后内容（手动添加，不带置信度标记）
function addContentItem() {
  contentItems.value.push(makeEmptyItem())
}

// 删除指定索引的售后内容
function removeContentItem(idx) {
  contentItems.value.splice(idx, 1)
}

// 品类变更时重置下级
function onCategoryChange(item) {
  item.series_id = null
  item.model_id  = null
}

// 系列变更时重置型号
function onSeriesChange(item) {
  item.model_id = null
}

// 原因一级分类变更时重置二级
function onReasonCategoryChange(item) {
  item.reason_id     = null
  item.custom_reason = ''
}

// 发货物料简称 select 变更：若选中值为字符串（新增），调 API 创建后回填 id
async function onShippingAliasChange(item, val) {
  if (val === null || val === undefined || val === '') {
    item.shipping_alias_id = null
    return
  }
  // 已是数字 id → 直接赋值
  if (typeof val === 'number') {
    item.shipping_alias_id = val
    return
  }
  // 字符串 → 新增
  const name = String(val).trim()
  if (!name) return
  const res = await http.post('/api/aftersale/shipping-aliases', { name })
  if (res.success) {
    shippingAliasOptions.value.push(res.data)
    item.shipping_alias_id = res.data.id
  } else {
    ElMessage.error(res.message || '新增发货物料简称失败')
    item.shipping_alias_id = null
  }
  item._shippingQuery = ''
}

// 具体原因 select 变更：值在原因库中 → 库原因；否则 → 自定义原因
// 选定原因后，用亲和度对发货简称候选列表做二次排序
async function onReasonChange(item, val) {
  if (val === null || val === undefined || val === '') {
    item.reason_id     = null
    item.custom_reason = ''
    return
  }
  // 收集当前分类下所有原因 ID（兼容 number 和 string 类型传值）
  const group = reasonGroups.value.find(g => g.category_id === item.reason_category_id)
  const knownIds = (group?.reasons || []).map(r => r.id)
  const numVal = Number(val)
  if (!isNaN(numVal) && knownIds.includes(numVal)) {
    item.reason_id     = numVal
    item.custom_reason = ''
    // 有库原因 → 查亲和度，对候选简称重排
    await applyAffinity(numVal)
  } else {
    item.reason_id     = null
    item.custom_reason = String(val)
  }
}

// 根据 reason_id 的历史亲和度对 matchDebug.shipping_alias_candidates 做二次排序
// base_score 相同时，亲和度高的排前；有亲和度的候选加 affinity_count 字段供模板标注
async function applyAffinity(reasonId) {
  const candidates = matchDebug.value?.shipping_alias_candidates
  if (!candidates?.length || !reasonId) return
  const aliasIds = candidates.map(c => c.id)
  const res = await http.post('/api/aftersale/alias-affinity', { reason_id: reasonId, alias_ids: aliasIds })
  if (!res.success) return
  const affinity = res.data   // { alias_id: count }
  // 附加 affinity_count 字段，并按 matched_count desc → affinity_count desc → score desc 重排
  const updated = candidates.map(c => ({
    ...c,
    affinity_count: affinity[c.id] || 0,
  })).sort((a, b) =>
    (b.matched_count - a.matched_count) ||
    (b.affinity_count - a.affinity_count) ||
    (b.score - a.score)
  )
  matchDebug.value = { ...matchDebug.value, shipping_alias_candidates: updated }
}

// ── 产品型号文本匹配 ────────────────────────────────

// 根据 ID 从品类树中解析名称（用于依据面板）
function resolveModelNames(category_id, series_id, model_id) {
  const cat    = categoryTree.value.find(c => c.id === category_id)
  const series = cat?.series?.find(s => s.id === series_id)
  const model  = series?.models?.find(m => m.id === model_id)
  return {
    category_name: cat?.name    || '',
    series_name:   series?.name || '',
    model_name:    model?.name  || '',
    model_code:    model?.model_code || '',
  }
}


/**
 * 型号置信度：独立于系列置信度，基于型号 model_code 是否存在。
 * hasTokens = 型号有独立标识（model_code 非空），否则无法区分型号返回 null。
 */
const round2 = v => Math.round(v * 100) / 100

/**
 * 解析买家留言为结构化字段：版本/新老款/驱动/尺寸/材质/颜色/变体/基础名
 * dict 来自 remarkDict.value（从 DB 加载），缺省时使用空列表（不影响基础名解析）
 */
function parseRemark(text, dict) {
  const d = dict || remarkDict.value
  const MATERIALS    = d.materials   || []
  const COLORS       = d.colors      || []
  const DRIVE_TYPES  = d.drive_types || []
  const SIZE_TO_METER = d.sizes      || {}

  let remaining = text.trim()
  const parsed = { version: null, recency: null, size: null, materials: new Set(), colors: new Set(), variant: null, baseText: '' }

  // 版本号（V3.1 或独立 3.1）
  let m = remaining.match(/[Vv](\d+\.\d+)/)
  if (m) {
    parsed.version = m[1]
    remaining = remaining.replace(m[0], '')
  } else {
    m = remaining.match(/(?<![0-9.])([1-9]\.\d+)(?![0-9.])/)
    if (m) { parsed.version = m[1]; remaining = remaining.replace(m[0], '') }
  }

  // 新款/老款/智能款
  for (const [word, tag] of [['智能款', 'smart'], ['新款', 'new'], ['老款', 'old']]) {
    if (remaining.includes(word)) { parsed.recency = tag; remaining = remaining.replace(word, ''); break }
  }

  // 驱动方式（去除避免干扰基础名）
  for (const dt of DRIVE_TYPES) {
    if (remaining.includes(dt)) { remaining = remaining.replace(dt, ''); break }
  }

  // 材质
  for (const mat of MATERIALS) {
    if (remaining.includes(mat)) { parsed.materials.add(mat); remaining = remaining.replace(mat, '') }
  }

  // 颜色
  for (const col of COLORS) {
    if (remaining.includes(col)) { parsed.colors.add(col); remaining = remaining.replace(col, '') }
  }

  // 尺寸
  m = remaining.match(/(?<!\d)(0?80|0?90|100|105|120|140|160|180|200)(?!\d)/)
  if (m) {
    const raw = String(parseInt(m[1]))
    if (SIZE_TO_METER[raw]) { parsed.size = raw; remaining = remaining.replace(m[0], '') }
  }

  // 变体字母（前置：C新款；后置：探索家B）
  const stripped = remaining.trim()
  const mFront = stripped.match(/^([A-D])(?=[\u4e00-\u9fff])/i)
  if (mFront) {
    parsed.variant = mFront[1].toUpperCase(); remaining = stripped.slice(mFront[0].length)
  } else {
    const mBack = stripped.match(/(?<=[\u4e00-\u9fff0-9])([A-D])$/i)
    if (mBack) { parsed.variant = mBack[1].toUpperCase(); remaining = stripped.slice(0, mBack.index) }
  }

  parsed.baseText = remaining.replace(/[\s/／,，]+/g, '').trim()
  parsed.sizeToMeter = SIZE_TO_METER
  return parsed
}

/**
 * 将系列名中的版本号括号去掉：'进取（V3.1）' → '进取'
 */
function seriesBaseName(name) {
  return (name || '').replace(/\s*[（(][Vv][^）)]*[）)]/g, '').trim()
}

/**
 * 提取系列版本号字符串：'进取（V3.1）' → '3.1'
 */
function seriesVersionStr(name) {
  const m = (name || '').match(/[Vv](\d+\.\d+)/)
  return m ? m[1] : null
}

/**
 * 提取系列版本号为可比较数组：'进取（V3.1）' → [3, 1]
 */
function seriesVersionTuple(name) {
  const m = (name || '').match(/[Vv](\d+)\.(\d+)/)
  return m ? [parseInt(m[1]), parseInt(m[2])] : [0, 0]
}

/**
 * 判断型号是否在指定购买月份（YYYY-MM）内在售
 */
function isModelActive(modelId, buyYm, currentYm) {
  const lc = modelLifecycles.value[modelId]
  if (!lc) return true
  if (lc.listed_yymm && buyYm < lc.listed_yymm) return false
  if (buyYm > (lc.delisted_yymm || currentYm)) return false
  return true
}

/**
 * 判断系列是否在指定购买月份内至少有一个型号在售
 */
function isSeriesActive(series, buyYm, currentYm) {
  return (series.models || []).some(m => isModelActive(m.id, buyYm, currentYm))
}

/**
 * 两阶段匹配：结构化解析 + 生命周期优先
 *   阶段一：解析买家留言 → 名称匹配 → 版本/新老款/生命周期过滤 → 候选系列
 *   阶段二：在候选系列内按尺寸/材质/颜色/变体 + 生命周期 匹配型号
 *
 * 返回 { category_id, series_id, model_id, series_confidence, model_confidence, ... } 或 null
 */
function matchTextToModel(remark1, remark2, purchaseDateStr = null) {
  const text = [remark1, remark2].filter(Boolean).join(' ').trim()
  if (!text || text.length < 2 || !categoryTree.value.length) return null

  const buyYm     = purchaseDateStr ? purchaseDateStr.slice(0, 7) : null
  const currentYm = new Date().toISOString().slice(0, 7)

  // ── 解析买家留言 ──────────────────────────────────────────────────────
  const parsed = parseRemark(text)
  const baseTextLower = parsed.baseText.toLowerCase()

  // ── 阶段一：系列匹配 ─────────────────────────────────────────────────
  // 建立 baseName → series 列表（跨所有品类）
  const allSeries = []
  for (const cat of categoryTree.value) {
    for (const series of (cat.series || [])) {
      if (!series.models?.length) continue
      allSeries.push({ cat, series, baseName: seriesBaseName(series.name) })
    }
  }

  // 1a. 名称匹配：精确 > 系列基础名包含于买家文本（大小写不敏感）
  const exactMatches     = allSeries.filter(s => s.baseName.toLowerCase() === baseTextLower)
  const substringMatches = allSeries.filter(s => {
    const bn = s.baseName.toLowerCase()
    return bn.length >= 2 && bn !== baseTextLower && baseTextLower.includes(bn)
  })
  let candidates = exactMatches.length ? exactMatches : substringMatches
  if (!candidates.length) return { noMatch: true, reason: '买家留言中未找到与产品库相似的系列名称' }

  // 1b. 版本号过滤（精确命中则锁定版本）
  // 原则：留言明确给出版本号 + 系列名已匹配 → 版本不符直接返回空，不降级
  let versionConfirmed = false
  if (parsed.version) {
    const vMatched = candidates.filter(s => seriesVersionStr(s.series.name) === parsed.version)
    if (vMatched.length) { candidates = vMatched; versionConfirmed = true }
    else return { noMatch: true, reason: `留言中指定版本 ${parsed.version} 未找到对应系列` }  // 版本明确但无匹配，终止
  }

  // 1c. 生命周期过滤（购买日期落在系列至少一个型号的上下市区间）
  if (buyYm) {
    const active = candidates.filter(s => isSeriesActive(s.series, buyYm, currentYm))
    if (active.length) {
      candidates = active
    } else if (!parsed.version) {
      // 无版本 + 购买日期有效 + 生命周期全部不符 → 无法确定版本，终止
      return { noMatch: true, reason: '购买日期与所有匹配系列的生命周期不符，无法确定版本' }
    }
  }

  // 1d. 新款/老款：取版本最高/最低
  if (parsed.recency === 'new' && candidates.length > 1) {
    const best = candidates.reduce((a, b) => {
      const [a1, a2] = seriesVersionTuple(a.series.name)
      const [b1, b2] = seriesVersionTuple(b.series.name)
      return (a1 > b1 || (a1 === b1 && a2 > b2)) ? a : b
    })
    candidates = [best]
  } else if (parsed.recency === 'old' && candidates.length > 1) {
    const best = candidates.reduce((a, b) => {
      const [a1, a2] = seriesVersionTuple(a.series.name)
      const [b1, b2] = seriesVersionTuple(b.series.name)
      return (a1 < b1 || (a1 === b1 && a2 < b2)) ? a : b
    })
    candidates = [best]
  }

  // 1e. 多候选时按版本降序排列（新版本优先展示）
  if (candidates.length > 1) {
    candidates.sort((a, b) => {
      const [a1, a2] = seriesVersionTuple(a.series.name)
      const [b1, b2] = seriesVersionTuple(b.series.name)
      return b1 !== a1 ? b1 - a1 : b2 - a2
    })
  }

  // 1f. 系列置信度
  const n = candidates.length
  const seriesConf = (versionConfirmed || (parsed.recency && n === 1) || n === 1) ? 'high'
    : n <= 3 ? 'medium' : 'low'
  const seriesScore = seriesConf === 'high' ? 1.0 : seriesConf === 'medium' ? 0.75 : 0.5

  // ── 阶段二：型号匹配 ─────────────────────────────────────────────────
  // 最高可能匹配分（用于置信度归一化）
  let maxScore = 0
  if (parsed.size)              maxScore += 3
  maxScore += 2 * parsed.materials.size
  maxScore += parsed.colors.size
  if (parsed.variant)           maxScore += 2
  if (parsed.recency === 'smart') maxScore += 2

  function scoreModel(model) {
    const mname = model.name || ''
    const mcode = model.model_code || ''
    let score = 0

    // 尺寸（精确米制 +3，数字兜底 +1）
    if (parsed.size) {
      const meter = parsed.sizeToMeter[parsed.size] || ''
      if (meter && mname.includes(meter))        score += 3
      else if (mname.includes(parsed.size) || mcode.includes(parsed.size)) score += 1
    }
    // 材质
    for (const mat of parsed.materials) { if (mname.includes(mat)) score += 2 }
    // 颜色
    for (const col of parsed.colors)    { if (mname.includes(col)) score += 1 }
    // 变体字母
    if (parsed.variant) {
      const v = parsed.variant
      if (mcode.endsWith(`-${v}`) || mname.endsWith(`_${v}`)) score += 2
    }
    // 智能款
    if (parsed.recency === 'smart' && mname.includes('智能')) score += 2

    return score
  }

  function modelConf(score) {
    if (maxScore === 0) return null
    const r = score / maxScore
    return r >= 0.7 ? 'high' : r >= 0.4 ? 'medium' : 'low'
  }

  // 构建 allCandidates（最多5个系列）
  const allCandidates = []
  for (const { cat, series } of candidates.slice(0, 5)) {
    const modelDetails = series.models.map(model => {
      const ms = scoreModel(model)
      const lifecycleOk = buyYm ? isModelActive(model.id, buyYm, currentYm) : null
      return {
        id:               model.id,
        name:             model.name,
        model_code:       model.model_code || '',
        score:            maxScore ? round2(ms / maxScore) : 0,
        model_confidence: modelConf(ms),
        lifecycleOk,
        _raw:             ms,
      }
    })
    // 排序：生命周期优先，其次匹配分
    modelDetails.sort((a, b) => {
      const lcA = a.lifecycleOk === null ? 1 : a.lifecycleOk ? 1 : 0
      const lcB = b.lifecycleOk === null ? 1 : b.lifecycleOk ? 1 : 0
      return lcB !== lcA ? lcB - lcA : b._raw - a._raw
    })
    for (const m of modelDetails) delete m._raw

    const bestM = modelDetails[0]
    allCandidates.push({
      category_id:       cat.id,
      category_name:     cat.name,
      series_id:         series.id,
      series_name:       series.name,
      series_score:      seriesScore,
      score:             seriesScore,   // 向后兼容
      series_confidence: seriesConf,
      model_id:          bestM?.id,
      model_name:        bestM?.name,
      model_code:        bestM?.model_code || '',
      model_confidence:  bestM?.model_confidence ?? null,
      models:            modelDetails,
    })
  }

  if (!allCandidates.length) return null

  const best = allCandidates[0]
  return { ...best, candidates: allCandidates }
}

/**
 * 将 0~1 的匹配分转为置信等级。
 * API（产品代码/历史工单）匹配到的直接视为 'high'。
 */
function scoreToConfidence(score) {
  if (score >= 0.6) return 'high'
  if (score >= 0.3) return 'medium'
  return 'low'
}

// ── 简称候选计算（前端实时，复用已加载的简称库数据）───────────

/**
 * 按关键词命中数给发货物料简称打分，返回 Top5 候选。
 * 绝对命中数优先（主键），覆盖率（matched/len(kws)）仅作次级排序。
 * 兼容历史数据：keywords 可能是物料名称或物料代码，二者都参与命中。
 */
function computeShippingAliasCandidates(products, sellerRemark = '', cleanedTokens = []) {
  if (!products?.length || !shippingAliasOptions.value.length) return []
  const productTexts = new Set(
    products
      .flatMap(p => [p.code, p.name])
      .map(v => (v || '').toLowerCase().trim())
      .filter(Boolean)
  )

  // 用后端清洗后的 token 匹配（与简称库 keywords 同源）；无则回退原始文本
  const matchTokens = new Set(
    cleanedTokens.length
      ? cleanedTokens.map(t => t.toLowerCase())
      : [...productTexts]
  )

  // 歧义词检测：同样基于清洗后 token
  const ambiguousSet = new Set(ambiguousTerms.value)
  const hasAmbiguous = [...matchTokens].some(t => ambiguousSet.has(t))

  // 商家备注归一（小写）用于歧义二次评分
  const remarkLower = (sellerRemark || '').toLowerCase()

  return shippingAliasOptions.value
    .map(alias => {
      const kws = alias.keywords || []
      if (!kws.length) return null
      const matched = kws.filter(k => matchTokens.has((k || '').toLowerCase().trim()))
      if (!matched.length) return null
      const score = matched.length / kws.length

      // 歧义词命中时：用商家备注对简称名称做相似度评分
      let remark_score = null
      if (hasAmbiguous && remarkLower) {
        const aliasLower = alias.name.toLowerCase()
        if (remarkLower.includes(aliasLower)) {
          remark_score = 1.0
        } else {
          // 找简称名最长连续子串在备注里的占比
          let maxLen = 0
          for (let len = aliasLower.length - 1; len >= 2; len--) {
            for (let i = 0; i <= aliasLower.length - len; i++) {
              if (remarkLower.includes(aliasLower.slice(i, i + len))) {
                maxLen = len; break
              }
            }
            if (maxLen) break
          }
          remark_score = maxLen >= 2 ? maxLen / aliasLower.length : 0
        }
      }

      return {
        id: alias.id, name: alias.name,
        score, matched_count: matched.length, matched_keywords: matched,
        remark_score, is_ambiguous: hasAmbiguous,
      }
    })
    .filter(Boolean)
    .sort((a, b) => {
      // 歧义时优先按备注分排序，无备注分则回退到原排序
      if (a.is_ambiguous && a.remark_score !== null) {
        return (b.remark_score - a.remark_score) || (b.matched_count - a.matched_count) || (b.score - a.score)
      }
      return (b.matched_count - a.matched_count) || (b.score - a.score)
    })
}

/**
 * 单面板模式：用户点选某个发货物料时，用该物料推断最优简称并写入 item。
 * 若已点选同一物料则取消点选（简称保留当前值不重置）。
 */
function onPinProduct(item, product) {
  if (item._pinnedProduct === product.code) {
    // 再次点击：取消固定，不重置 alias
    item._pinnedProduct = null
    return
  }
  item._pinnedProduct = product.code
  // 用该产品单独匹配简称（不传 cleanedTokens 以避免跨产品干扰）
  const cands = computeShippingAliasCandidates([product], currentOrder.value?.seller_remark, [])
  if (cands.length > 0) {
    item.shipping_alias_id = cands[0].id
  }
}

// ── 生命周期文字格式化 ───────────────────────────────
// 将 modelLifecycles 里的 YYYY-MM 格式化为 YY.MM，返回 "上市~退市" 或 "上市~在售"
function lifecycleText(modelId) {
  const lc = modelLifecycles.value[modelId]
  if (!lc) return null
  const fmt = s => s ? s.slice(2).replace('-', '.') : null   // "2021-03" → "21.03"
  const start = fmt(lc.listed_yymm)
  const end   = fmt(lc.delisted_yymm)
  if (!start && !end) return null
  return `${start || '?'}~${end || '在售'}`
}

// ── 候选一键应用 ────────────────────────────────────

function applyShippingAlias(id) {
  if (contentItems.value[0]) contentItems.value[0].shipping_alias_id = id
}

function applyModelCandidate(c) {
  const item = contentItems.value[0]
  if (!item) return
  item.category_id = c.category_id
  item.series_id   = c.series_id
  item.model_id    = c.model_id
  item.confidence  = scoreToConfidence(c.score)
}

function applyModelDetail(c, m) {
  const item = contentItems.value[0]
  if (!item) return
  item.category_id = c.category_id
  item.series_id   = c.series_id
  item.model_id    = m.id
  item.confidence  = scoreToConfidence(m.score)
}

function applyReasonCandidate(candidate, item) {
  const target = item || contentItems.value[0]
  if (!target) return
  // 在 reasonGroups 中查找 reason_id 对应的 category_id
  for (const group of reasonGroups.value) {
    if (group.reasons?.find(r => r.id === candidate.reason_id)) {
      target.reason_category_id = group.category_id
      target.reason_id          = candidate.reason_id
      return
    }
  }
  target.reason_id = candidate.reason_id
}

// 根据 reason_id 从 reasonGroups 中查找原因名称及一级分类名
function resolveReasonName(reason_id, category_id) {
  for (const group of reasonGroups.value) {
    const r = group.reasons?.find(r => r.id === reason_id)
    if (r) return { reason_name: r.name, category_name: group.category_name }
  }
  // 找不到时尝试用 reasonCategories 拿分类名
  const cat = reasonCategories.value.find(c => c.id === category_id)
  return { reason_name: null, category_name: cat?.name || null }
}

// ── 三级联动计算 ────────────────────────────────────

// 给定 item，返回可选的系列列表（含 code + name）
function seriesOptionsForItem(item) {
  if (!item.category_id) return []
  const cat = categoryTree.value.find(c => c.id === item.category_id)
  return (cat?.series || []).map(s => ({
    value: s.id,
    label: s.name,
    code:  s.code,
  }))
}

// 给定 item，返回可选的型号列表
function modelOptionsForItem(item) {
  if (!item.category_id || !item.series_id) return []
  const cat    = categoryTree.value.find(c => c.id === item.category_id)
  const series = cat?.series?.find(s => s.id === item.series_id)
  return (series?.models || []).map(m => ({
    value: m.id,
    label: `${m.model_code} ${m.name}`,
  }))
}

// 给定 item，返回该一级分类下的二级原因列表
function reasonOptionsForItem(item) {
  if (!item.reason_category_id) return []
  const group = reasonGroups.value.find(g => g.category_id === item.reason_category_id)
  return (group?.reasons || []).map(r => ({ value: r.id, label: r.name }))
}

// ── 一级原因分类新增 ────────────────────────────────

async function addReasonCategory(item) {
  let name
  try {
    const { value } = await ElMessageBox.prompt('', '新增原因分类', {
      confirmButtonText: '添加',
      cancelButtonText:  '取消',
      inputPlaceholder:  '请输入分类名称',
      inputPattern:      /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    name = value?.trim()
  } catch {
    return
  }
  if (!name) return

  const res = await http.post('/api/aftersale/reason-categories', { name })
  if (res.success) {
    ElMessage.success('分类已创建')
    await loadReasonOptions()
    // 自动选中新建的分类
    item.reason_category_id = res.data.id
    item.reason_id          = null
  } else {
    ElMessage.error(res.message || '创建失败')
  }
}

// ── 确认 / 忽略 ────────────────────────────────────

/**
 * 从 keywords 列表中提取公共模式，返回去重后的有效模式列表（长度≥2）。
 * "_" 作为分隔符：每条 keyword 先按 "_" 切分为 token，
 * 统计各 token 在多少条 keyword 中出现，保留出现 ≥2 次的 token 作为模式。
 * token 首尾的括号、空格等无意义字符会被去除。
 * 短模式若已被更长模式包含则去除，避免冗余。
 * 例：["原材料_木器_榉木_活动桌面板","原材料_木器_桦木_活动桌面板"] → ["活动桌面板","原材料","木器","桦木"]
 */
function extractKeywordPatterns(strs, minLen = 2) {
  if (strs.length < 2) return []

  // 将每条 keyword 按 _ 切分，清洗首尾无意义字符，统计各 token 出现次数
  const countMap = new Map()
  for (const str of strs) {
    const tokens = new Set(
      str.split('_')
        .map(t => t.replace(/^[\s（()）\-]+|[\s（()）\-]+$/g, '').toLowerCase())
        .filter(t => t.length >= minLen)
    )
    for (const token of tokens) {
      countMap.set(token, (countMap.get(token) || 0) + 1)
    }
  }

  // 保留出现 ≥2 次的 token，按长度降序排列
  const candidates = [...countMap.entries()]
    .filter(([, cnt]) => cnt >= 2)
    .map(([token]) => token)
    .sort((a, b) => b.length - a.length)

  // 去除已被更长模式包含的短模式
  return candidates.filter((p, i) => !candidates.slice(0, i).some(longer => longer.includes(p)))
}

/**
 * 发货物料简称自动学习（两级匹配）。
 *
 * 一级：用简称名称过滤当前工单产品（code/name 任一包含）。
 * 二级：一级无命中时，从该简称已有 keywords 推导公共模式，再匹配当前工单产品。
 * 两级均无命中则跳过，不修改 keywords。
 *
 * 重要：每次确认仅绑定 1 个 key，且优先写物料名称（name），避免新学习关键词被写成 code。
 */
async function learnShippingAliasKeywords(products, items) {
  if (!products?.length || !items?.length) return
  const aliasIds = [...new Set(items.map(i => i.shipping_alias_id).filter(Boolean))]
  if (!aliasIds.length) return

  const ignoreTerms  = shippingIgnoreTerms.value.map(t => t.term.toLowerCase())

  // 将物料名称清洗为有效 token（去掉 "_" 分隔的无用前缀和 ignore_term 子词）
  // 取最末一段作为最具体词；如全部过滤则回退到原始 name
  const cleanProductName = (name) => {
    if (!name) return ''
    const parts = name.split('_').filter(p => {
      if (!p || p.length <= 1) return false
      return !ignoreTerms.some(t => p.toLowerCase() === t)  // 精确匹配，与后端 _parse_product_tokens 保持一致
    })
    return parts[parts.length - 1] || name
  }

  const productEntries = products
    .map(p => ({
      code: (p.code || '').trim(),
      name: (p.name || '').trim(),
      quantity: Number(p.quantity) || 0,
      codeLower: (p.code || '').toLowerCase().trim(),
      nameLower: (p.name || '').toLowerCase().trim(),
    }))
    .filter(p => p.code || p.name)
  // 学习关键词时优先使用清洗后的物料名，避免将"原材料_塑胶件_书包挂钩盖子"整体存入
  const bindKey = (p) => cleanProductName(p.name) || p.name || p.code || ''
  const pickOneKey = (entries) => {
    if (!entries.length) return null
    const sorted = [...entries].sort((a, b) => b.quantity - a.quantity)
    return bindKey(sorted[0]) || null
  }
  const productByCode = new Map(productEntries.map(p => [p.code, p]))
  const aliasScopedProducts = new Map()
  for (const item of items) {
    if (!item.shipping_alias_id) continue
    const scoped = (multipleItems.value && item._selectedProducts?.length)
      ? item._selectedProducts.map(code => productByCode.get(code)).filter(Boolean)
      : productEntries
    if (!scoped.length) continue
    if (!aliasScopedProducts.has(item.shipping_alias_id)) aliasScopedProducts.set(item.shipping_alias_id, new Map())
    const dedup = aliasScopedProducts.get(item.shipping_alias_id)
    scoped.forEach(p => dedup.set(`${p.code}__${p.name}`, p))
  }

  for (const aliasId of aliasIds) {
    const aliasOpt = shippingAliasOptions.value.find(o => o.id === aliasId)
    if (!aliasOpt) continue

    const existing = aliasOpt.keywords || []
    const scopedEntries = [...(aliasScopedProducts.get(aliasId)?.values() || [])]
    if (!scopedEntries.length) continue

    // 一级：简称名称与产品代码或产品名称的包含匹配
    const namePat = (aliasOpt.name || '').toLowerCase()
    let newKey = namePat
      ? pickOneKey(
          scopedEntries
          .filter(p =>
            p.codeLower.includes(namePat) ||
            p.nameLower.includes(namePat)
          )
        )
      : null

    // 二级：一级无命中时，从已有 keywords 提取公共模式，再剔除含过滤词的模式，用剩余模式匹配
    if (!newKey && existing.length) {
      const rawPatterns = extractKeywordPatterns(existing)
      let patterns = rawPatterns
      if (ignoreTerms.length) {
        patterns = rawPatterns.filter(p => !ignoreTerms.some(t => p.toLowerCase() === t))  // 精确匹配
      }
      console.log(`[简称学习] alias="${aliasOpt.name}" 原始子串:`, rawPatterns, '过滤后:', patterns)
      if (patterns.length) {
        newKey = pickOneKey(
          scopedEntries
          .filter(p =>
            patterns.some(pt =>
              p.codeLower.includes(pt) || p.nameLower.includes(pt)
            )
          )
        )
      }
    }

    // 兜底：新简称首次学习且两级匹配均未命中时，直接绑定当前工单物料键
    // 绑定键优先使用 name；name 缺失时回退到 code，避免出现“新简称无任何 key”。
    if (!newKey && !existing.length) {
      newKey = pickOneKey(scopedEntries)
    }
    if (!newKey) continue

    const merged = [...new Set([...existing, newKey])]
    if (merged.length === existing.length && existing.includes(newKey)) continue

    const r = await http.put(`/api/aftersale/shipping-aliases/${aliasId}`, {
      name:       aliasOpt.name,
      keywords:   merged,
      sort_order: aliasOpt.sort_order || 0,
    })
    if (r.success) aliasOpt.keywords = merged
  }
}

// 歧义词晋升：当简称通过备注评分确认后，将产品特征码写入该简称 keywords
// 下次相同产品出现时可直接命中，不再依赖歧义备注评分
async function promoteAmbiguousAlias(products, items) {
  if (!products?.length || !items?.length) return
  const candidates = matchDebug.value?.shipping_alias_candidates
  if (!candidates?.length || !candidates[0]?.is_ambiguous) return

  const ignoreTerms = shippingIgnoreTerms.value.map(t => t.term.toLowerCase())
  const cleanProductName = (name) => {
    if (!name) return ''
    const parts = name.split('_').filter(p =>
      p && p.length > 1 && !ignoreTerms.some(t => p.toLowerCase() === t)
    )
    return parts[parts.length - 1] || name
  }

  for (const item of items) {
    if (!item.shipping_alias_id) continue
    const cand = candidates.find(c => c.id === item.shipping_alias_id)
    if (!cand?.is_ambiguous || (cand.remark_score ?? 0) <= 0) continue

    const aliasOpt = shippingAliasOptions.value.find(o => o.id === item.shipping_alias_id)
    if (!aliasOpt) continue

    const existing = aliasOpt.keywords || []
    // 优先绑定数量最多的产品清洗名，作为晋升 key
    const sorted = [...products].sort((a, b) => (Number(b.quantity) || 0) - (Number(a.quantity) || 0))
    const newKey = sorted
      .map(p => cleanProductName(p.name) || p.name || p.code || '')
      .map(k => k.toLowerCase().trim())
      .find(k => k && !existing.map(e => e.toLowerCase()).includes(k))

    if (!newKey) continue
    const merged = [...new Set([...existing, newKey])]
    const r = await http.put(`/api/aftersale/shipping-aliases/${aliasOpt.id}`, {
      name: aliasOpt.name, keywords: merged, sort_order: aliasOpt.sort_order || 0,
    })
    if (r.success) {
      aliasOpt.keywords = merged
      console.log(`[歧义晋升] "${aliasOpt.name}" ← "${newKey}"`)
    }
  }
}

// ── 批量处理 ─────────────────────────────────────────────────────────────────

/**
 * 对单个工单执行与 selectOrder 相同的匹配逻辑，但不修改任何响应式状态。
 * 返回 { status, content, order, products } 供批量确认使用。
 */
async function computeOrderBatchResult(order) {
  const parsedPurchaseDate = parsePurchaseDateFromRemark(order.seller_remark)
  const debugText = [order.buyer_remark, order.seller_remark].filter(Boolean).join(' ')
  const products  = order.products || []

  let apiResult        = null
  let reasonCandidates = []

  try {
    await Promise.all([
      (order.buyer_remark?.trim() || products.length)
        ? http.post('/api/aftersale/suggest-product', {
            products, purchase_date: parsedPurchaseDate || null,
            seller_remark: order.seller_remark || null,
            buyer_remark:  order.buyer_remark  || null,
          }).then(r => { if (r.success && r.data) apiResult = r.data })
        : Promise.resolve(),
      debugText.trim()
        ? http.post('/api/aftersale/auto-match', {
            text: debugText, buyer_remark: order.buyer_remark || '',
          }).then(r => { if (r.success && r.data) reasonCandidates = r.data.items || [] })
        : Promise.resolve(),
    ])
  } catch (_) { /* ignore */ }

  const apiMatch  = apiResult?.category_id ? apiResult : null
  const textMatch = matchTextToModel(order.buyer_remark, null, parsedPurchaseDate)
  const productTokens = apiResult?.product_tokens || []
  const shippingCands = computeShippingAliasCandidates(products, order.seller_remark, productTokens)

  // ── 确定简称 ──────────────────────────────────────
  const historyAliasId = apiResult?.suggested_shipping_alias_id || null
  let finalAliasId = historyAliasId
  const topCand = shippingCands[0]
  if (topCand?.is_ambiguous) {
    finalAliasId = (topCand.remark_score ?? 0) > 0 ? topCand.id : null
  }

  // ── 确定型号 / 系列 ───────────────────────────────
  let content = {
    model_id: null, category_id: null, series_id: null,
    shipping_alias_id: finalAliasId,
    reason_id: null, reason_category_id: null,
    purchase_date: parsedPurchaseDate,
  }
  let debugFields = { source: null, series_confidence: null, model_confidence: null, date_ok: true }

  if (apiMatch) {
    const dateOk = apiMatch.date_ok !== false
    content.category_id = apiMatch.category_id
    content.series_id   = apiMatch.series_id
    content.model_id    = dateOk ? apiMatch.model_id : null
    debugFields = {
      source: 'api', series_confidence: apiMatch.series_confidence || null,
      model_confidence: apiMatch.model_confidence || null, date_ok: dateOk,
    }
  } else if (textMatch && !textMatch.noMatch) {
    content.category_id = textMatch.category_id
    content.series_id   = textMatch.series_id
    content.model_id    = textMatch.model_id
    debugFields = {
      source: 'text', series_confidence: textMatch.series_confidence || null,
      model_confidence: textMatch.model_confidence || null, date_ok: true,
    }
  }

  // ── 确定原因（仅关键词候选存在时取历史原因）────────
  const suggestedReasonId   = apiResult?.suggested_reason_id          || null
  const suggestedCategoryId = apiResult?.suggested_reason_category_id || null
  if (suggestedReasonId && reasonCandidates.length > 0) {
    content.reason_id          = suggestedReasonId
    content.reason_category_id = suggestedCategoryId
  }

  // ── 计算 matchStatus ─────────────────────────────
  const hasProduct = !!debugFields.source
  const hasAlias   = !!finalAliasId
  const hasReason  = reasonCandidates.length > 0
  const seriesOk   = debugFields.series_confidence === 'high'
  const modelOk    = debugFields.model_confidence === 'high' || debugFields.model_confidence == null
  const dateOk2    = debugFields.date_ok !== false

  let status
  if (!hasProduct) {
    status = { level: 'ignore', label: '可忽略', tip: '未匹配到售后产品' }
  } else if (seriesOk && modelOk && dateOk2 && hasReason && hasAlias) {
    status = { level: 'auto', label: '直接确认', tip: '高置信匹配，可批量确认' }
  } else {
    const reasons = []
    if (!seriesOk)  reasons.push('系列置信度低')
    else if (!modelOk) reasons.push('型号置信度低')
    if (!dateOk2)   reasons.push('日期不在生命周期')
    if (!hasReason) reasons.push('未匹配到原因')
    if (!hasAlias)  reasons.push('未匹配到简称')
    status = { level: 'confirm', label: '待核实', tip: reasons.join('；') }
  }

  return { status, content, order, products }
}

/** 批量匹配当前页所有工单，每批5个并发，实时更新 batchResults */
async function runBatchMatch() {
  batchMode.value    = true
  batchRunning.value = true
  batchResults.value = {}
  const CHUNK = 5
  const list = [...orders.value]
  for (let i = 0; i < list.length; i += CHUNK) {
    const chunk = list.slice(i, i + CHUNK)
    await Promise.all(chunk.map(async order => {
      const r = await computeOrderBatchResult(order)
      batchResults.value[order.ecommerce_order_no] = r
    }))
  }
  batchRunning.value = false
}

/** 批量提交：auto 级别创建工单，ignore 级别调忽略接口 */
async function runBatchSubmit() {
  if (!allBatchAuto.value) return
  batchSubmitting.value = true
  let successCount = 0
  let ignoreCount  = 0
  for (const order of [...orders.value]) {
    const r     = batchResults.value[order.ecommerce_order_no]
    const level = r?.status?.level
    if (!BATCH_WHITELIST.has(level)) continue

    if (level === 'ignore') {
      // 可忽略工单：调忽略接口
      const res = await http.post(
        `/api/aftersale/cases/${encodeURIComponent(order.ecommerce_order_no)}/ignore`
      )
      if (res.success) {
        const idx = orders.value.findIndex(o => o.ecommerce_order_no === order.ecommerce_order_no)
        if (idx !== -1) { orders.value.splice(idx, 1); totalOrders.value = Math.max(0, totalOrders.value - 1) }
        ignoreCount++
      }
    } else {
      // auto 级别：创建工单
      const { content, products: prods } = r
      const res = await http.post('/api/aftersale/cases', {
        ecommerce_order_no: order.ecommerce_order_no,
        products:     prods,
        seller_remark: order.seller_remark,
        buyer_remark:  order.buyer_remark,
        shipped_date:  order.shipped_date,
        city:          order.city     || null,
        district:      order.district || null,
        operator:      order.operator,
        channel_name:  order.channel_name,
        province:      order.province,
        reasons: [{
          reason_id:          content.reason_id          || null,
          reason_category_id: content.reason_id ? null : (content.reason_category_id || null),
          model_id:           content.model_id           || null,
          shipping_alias_id:  content.shipping_alias_id  || null,
          purchase_date:      content.purchase_date      || null,
        }],
      })
      if (res.success) {
        const idx = orders.value.findIndex(o => o.ecommerce_order_no === order.ecommerce_order_no)
        if (idx !== -1) { orders.value.splice(idx, 1); totalOrders.value = Math.max(0, totalOrders.value - 1) }
        const fakeItems = [{ ...content, _selectedProducts: [], _shippingQuery: '' }]
        await learnShippingAliasKeywords(prods, fakeItems)
        successCount++
      }
    }
  }
  batchSubmitting.value = false
  batchMode.value    = false
  batchResults.value = {}
  const total = successCount + ignoreCount
  if (total) {
    const parts = []
    if (successCount) parts.push(`确认 ${successCount} 条`)
    if (ignoreCount)  parts.push(`忽略 ${ignoreCount} 条`)
    ElMessage.success(`批量处理完成：${parts.join('，')}`)
    emit('case-confirmed')
  }
  if (!orders.value.length) {
    currentOrder.value = null; contentItems.value = []; aftersaleDate.value = null; matchDebug.value = null
  }
}

async function confirmCase() {
  if (!currentOrder.value) return
  if (contentItems.value.length === 0) {
    ElMessage.warning('请至少添加一条售后内容')
    return
  }
  saving.value = true
  try {
    // 提交前：将自定义原因写入原因库，成功则回填 reason_id
    for (const item of contentItems.value) {
      if (!item.reason_id && item.custom_reason?.trim()) {
        const r = await http.post('/api/aftersale/reasons', {
          name:        item.custom_reason.trim(),
          category_id: item.reason_category_id || null,
        })
        if (r.success) {
          item.reason_id     = r.data.id
          item.custom_reason = ''
        }
        // 重名：查找已有的原因 ID
        else {
          const existing = reasonGroups.value
            .flatMap(g => g.reasons || [])
            .find(r => r.name === item.custom_reason.trim())
          if (existing) { item.reason_id = existing.id; item.custom_reason = '' }
        }
      }
    }

    const reasons = contentItems.value.map(item => ({
      reason_id:                item.reason_id || null,
      // reason_id 为空时传一级分类，供后端存储 reason_category_id
      reason_category_id:       item.reason_id ? null : (item.reason_category_id || null),
      model_id:          item.model_id         || null,
      shipping_alias_id: item.shipping_alias_id || null,
      purchase_date:            item.purchase_date || null,
      // 多内容时的独立商家备注，为空时后端回退到工单级备注
      seller_remark:            item._seller_remark?.trim() || null,
    }))

    const res = await http.post('/api/aftersale/cases', {
      ecommerce_order_no: currentOrder.value.ecommerce_order_no,
      products:           currentOrder.value.products,
      seller_remark:      currentOrder.value.seller_remark,
      buyer_remark:       currentOrder.value.buyer_remark,
      shipped_date:       aftersaleDate.value,
      city:               currentOrder.value.city || null,
      district:           currentOrder.value.district || null,
      operator:           currentOrder.value.operator,
      channel_name:       currentOrder.value.channel_name,
      province:           currentOrder.value.province,
      reasons,
    })
    if (res.success) {
      ElMessage.success('已确认')
      // 发货物料简称自动学习：用简称名称前缀过滤当前工单产品代码，合并写入 alias keywords
      await learnShippingAliasKeywords(currentOrder.value.products, contentItems.value)
      await promoteAmbiguousAlias(currentOrder.value.products, contentItems.value)
      removeCurrentFromList()
      emit('case-confirmed')
      // 刷新原因库选项（可能新增了原因）
      loadReasonOptions()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

async function ignoreCase() {
  if (!currentOrder.value) return
  try {
    await ElMessageBox.confirm('确认将该订单标记为「忽略」？', '忽略工单', {
      confirmButtonText: '忽略',
      cancelButtonText:  '取消',
      type:              'warning',
    })
  } catch {
    return
  }
  ignoring.value = true
  try {
    const res = await http.post(
      `/api/aftersale/cases/${encodeURIComponent(currentOrder.value.ecommerce_order_no)}/ignore`
    )
    if (res.success) {
      ElMessage.success('已忽略')
      removeCurrentFromList()
      emit('case-confirmed')
    } else {
      ElMessage.error(res.message)
    }
  } finally {
    ignoring.value = false
  }
}
</script>

<template>
  <div class="process-wrap">
    <!-- ── 左侧待处理队列 ─────────────────────── -->
    <aside class="order-queue">
      <div class="queue-header">
        <div class="queue-title">
          待处理
          <span class="queue-count">{{ totalOrders }}</span>
        </div>
        <div class="header-btns">
          <el-tooltip content="刷新队列" placement="top">
            <button class="btn-icon" @click="refreshQueue">
              <el-icon><Refresh /></el-icon>
            </button>
          </el-tooltip>
          <el-tooltip content="原因库" placement="top">
            <button class="btn-icon" @click="showReasonLib = true">
              <el-icon><Setting /></el-icon>
            </button>
          </el-tooltip>
        </div>
      </div>

      <!-- 批量操作按钮 -->
      <div class="batch-bar">
        <button class="btn-batch" :disabled="batchRunning" @click="runBatchMatch">
          <el-icon v-if="batchRunning" class="is-loading"><Loading /></el-icon>
          <span>{{ batchRunning ? '匹配中' : batchMode ? '重新匹配' : '批量处理' }}</span>
        </button>
        <button
          class="btn-batch-submit"
          :disabled="!allBatchAuto || batchSubmitting"
          :title="allBatchAuto ? '批量处理所有工单（自动确认 / 忽略）' : '存在需要手动核实的工单'"
          @click="runBatchSubmit"
        >
          {{ batchSubmitting ? '提交中…' : '提交' }}
        </button>
      </div>

      <div v-loading="loadingList" class="order-list">
        <div
          v-for="order in orders"
          :key="order.ecommerce_order_no"
          class="order-card"
          :class="{ active: currentOrder?.ecommerce_order_no === order.ecommerce_order_no }"
          @click="batchRunning ? undefined : selectOrder(order)"
        >
          <div class="order-no-row">
            <span class="order-no">{{ order.ecommerce_order_no }}</span>
            <span
              v-if="batchMode"
              class="batch-status-badge"
              :class="`bsb--${batchResults[order.ecommerce_order_no]?.status?.level ?? 'loading'}`"
            >{{ batchResults[order.ecommerce_order_no]?.status?.label ?? '…' }}</span>
          </div>
          <div class="order-meta">
            <span>{{ order.shipped_date }}</span>
            <span class="sep">·</span>
            <span>{{ order.channel_name || '—' }}</span>
          </div>
          <div class="order-meta">
            <span>{{ order.products?.length || 0 }} 个物料</span>
            <span class="sep">·</span>
            <span>{{ order.province || '—' }}</span>
          </div>
        </div>

        <div v-if="!loadingList && orders.length === 0" class="queue-empty">
          暂无待处理订单
        </div>
      </div>

      <!-- 分页 -->
      <div class="queue-pagination">
        <div class="pagination-info">
          <span class="remaining-count">剩余 {{ currentPageRemaining }} 项</span>
          <select v-model="pageSize" class="page-size-select">
            <option v-for="n in PAGE_SIZE_OPTIONS" :key="n" :value="n">{{ n }}条/页</option>
          </select>
        </div>
        <div v-if="totalPages > 1" class="pagination-nav">
          <button class="pg-btn" :disabled="page <= 1" @click="goPrev">‹</button>
          <span class="pg-info">{{ page }} / {{ totalPages }}</span>
          <button class="pg-btn" :disabled="page >= totalPages" @click="goNext">›</button>
        </div>
      </div>
    </aside>

    <!-- ── 右侧处理工作区 ──────────────────────── -->
    <div class="work-area">
      <div v-if="!currentOrder" class="work-empty">
        <div class="work-empty-icon">✓</div>
        <div>当前无待处理售后订单</div>
      </div>

      <template v-else>
        <!-- 工单信息栏 -->
        <div class="case-header">
          <div class="case-order-no">{{ currentOrder.ecommerce_order_no }}</div>
          <div class="case-meta-row">
            <span class="meta-item">
              <span class="meta-label">日期</span>{{ currentOrder.shipped_date || '—' }}
            </span>
            <span class="meta-item">
              <span class="meta-label">渠道</span>{{ currentOrder.channel_name || '—' }}
            </span>
            <span class="meta-item">
              <span class="meta-label">操作人</span>{{ currentOrder.operator || '—' }}
            </span>
            <span class="meta-item">
              <span class="meta-label">省市</span>
              {{ [currentOrder.province, currentOrder.city].filter(Boolean).join(' · ') || '—' }}
            </span>
          </div>
        </div>

        <!-- 工单内容（可滚动） -->
        <div class="case-body">

          <!-- 发货物料（单内容时可点选推断简称） -->
          <section class="case-section">
            <div class="section-title">
              发货物料
              <span v-if="!multipleItems && resolvedProducts.length > 1" class="section-hint">点选物料可自动匹配简称</span>
            </div>
            <div class="products-grid">
              <div
                v-for="p in resolvedProducts"
                :key="p.code"
                class="product-chip"
                :class="{
                  'product-chip--selectable': !multipleItems && resolvedProducts.length > 1,
                  'product-chip--selected':   !multipleItems && contentItems[0]?._pinnedProduct === p.code,
                }"
                :title="!multipleItems && resolvedProducts.length > 1 ? `点选「${p.name}」来推断发货简称` : `${p.code} ${p.name}`"
                @click="!multipleItems && resolvedProducts.length > 1 ? onPinProduct(contentItems[0], p) : undefined"
              >
                <span class="p-code">{{ p.code }}</span>
                <span class="p-name">{{ p.name }}</span>
                <span class="p-qty">×{{ p.quantity }}</span>
              </div>
            </div>
          </section>

          <!-- 买家留言 + 商家备注（只读） -->
          <section class="case-section remarks-section">
            <div class="remark-block">
              <div class="remark-label">买家留言</div>
              <div class="remark-text">{{ currentOrder.buyer_remark || '（无）' }}</div>
            </div>
            <div class="remark-block">
              <div class="remark-label">商家备注</div>
              <div class="remark-text">{{ currentOrder.seller_remark || '（无）' }}</div>
            </div>
          </section>

          <!-- 日期确认区 -->
          <section class="case-section dates-section">
            <div class="date-field">
              <span class="date-label">售后日期</span>
              <el-date-picker
                v-model="aftersaleDate"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="选择售后日期"
                class="date-picker"
              />
            </div>
          </section>

          <!-- 售后内容列表 -->
          <section class="case-section">
            <div class="section-title">
              售后内容
              <button v-if="canEditAftersale" class="btn-add-content" @click="addContentItem">
                <el-icon><Plus /></el-icon> 添加
              </button>
            </div>

            <div v-if="contentItems.length === 0" class="content-empty">
              点击「添加」填写本次售后的具体内容
            </div>

            <!-- 每条售后内容卡片 -->
            <div
              v-for="(item, idx) in contentItems"
              :key="idx"
              class="content-item"
            >
              <!-- 卡片序号 + 删除按钮 -->
              <div class="item-header">
                <span class="item-index"># {{ idx + 1 }}</span>
                <button class="btn-del-item" title="删除此条" @click="removeContentItem(idx)">
                  <el-icon><Delete /></el-icon>
                </button>
              </div>

              <!-- 售后产品：三级联动（置信度外框） -->
              <div class="item-row">
                <span class="item-label">售后产品</span>
                <div class="product-selects" :class="item.confidence ? `conf-${item.confidence}` : ''"
                  :title="item.confidence === 'low' ? '匹配置信度低，请人工确认' : item.confidence === 'medium' ? '匹配置信度一般，请确认是否正确' : ''"
                >
                  <el-select
                    v-model="item.category_id"
                    placeholder="品类"
                    clearable
                    @change="onCategoryChange(item)"
                  >
                    <el-option
                      v-for="opt in categoryOptions"
                      :key="opt.value"
                      :value="opt.value"
                      :label="opt.label"
                    />
                  </el-select>
                  <el-select
                    v-model="item.series_id"
                    placeholder="系列"
                    clearable
                    filterable
                    :disabled="!item.category_id"
                    @change="onSeriesChange(item)"
                  >
                    <el-option
                      v-for="opt in seriesOptionsForItem(item)"
                      :key="opt.value"
                      :value="opt.value"
                      :label="`${opt.code} ${opt.label}`"
                    />
                  </el-select>
                  <el-select
                    v-model="item.model_id"
                    placeholder="型号"
                    clearable
                    filterable
                    :disabled="!item.series_id"
                  >
                    <el-option
                      v-for="opt in modelOptionsForItem(item)"
                      :key="opt.value"
                      :value="opt.value"
                      :label="opt.label"
                    />
                  </el-select>
                </div>
              </div>

              <!-- 发货物料简称 -->
              <div class="item-row">
                <span class="item-label">发货物料简称</span>
                <el-select
                  :model-value="item.shipping_alias_id"
                  placeholder="选择或输入新简称"
                  clearable
                  filterable
                  :filter-method="q => { item._shippingQuery = q }"
                  style="width:100%"
                  @change="onShippingAliasChange(item, $event)"
                  @visible-change="v => { if (!v) item._shippingQuery = '' }"
                >
                  <el-option
                    v-if="item._shippingQuery && !shippingAliasOptions.some(o => o.name === item._shippingQuery)"
                    :value="item._shippingQuery"
                    :label="item._shippingQuery"
                    class="new-create-option"
                  >
                    <span>{{ item._shippingQuery }}</span>
                    <el-tag size="small" type="warning" style="margin-left:6px">新</el-tag>
                  </el-option>
                  <el-option
                    v-for="opt in shippingAliasOptions.filter(o => !item._shippingQuery || o.name.toLowerCase().includes(item._shippingQuery.toLowerCase()))"
                    :key="opt.id"
                    :value="opt.id"
                    :label="opt.name"
                  />
                </el-select>
              </div>

              <!-- 售后原因：两级 -->
              <div class="item-row">
                <span class="item-label">售后原因</span>
                <div class="reason-row-inner">
                  <!-- 一级分类 + 新增按钮 -->
                  <div class="reason-cat-wrap">
                    <el-select
                      v-model="item.reason_category_id"
                      placeholder="原因分类"
                      clearable
                      class="reason-cat-select"
                      @change="onReasonCategoryChange(item)"
                    >
                      <el-option
                        v-for="cat in reasonCategories"
                        :key="cat.id"
                        :value="cat.id"
                        :label="cat.name"
                      />
                    </el-select>
                    <el-tooltip content="新增原因分类" placement="top">
                      <button class="btn-add-cat" title="新增原因分类" @click="addReasonCategory(item)">
                        <el-icon><Plus /></el-icon>
                      </button>
                    </el-tooltip>
                  </div>
                  <!-- 二级原因（支持直接输入自定义原因） -->
                  <el-select
                    :model-value="item.reason_id ?? (item.custom_reason || null)"
                    placeholder="具体原因或自定义输入"
                    clearable
                    filterable
                    :filter-method="q => { item._reasonQuery = q }"
                    :disabled="!item.reason_category_id"
                    class="reason-select"
                    @change="onReasonChange(item, $event)"
                    @visible-change="v => { if (!v) item._reasonQuery = '' }"
                  >
                    <el-option
                      v-if="item._reasonQuery && !reasonOptionsForItem(item).some(r => r.label === item._reasonQuery)"
                      :value="item._reasonQuery"
                      :label="item._reasonQuery"
                      class="new-create-option"
                    >
                      <span>{{ item._reasonQuery }}</span>
                      <el-tag size="small" type="warning" style="margin-left:6px">新</el-tag>
                    </el-option>
                    <el-option
                      v-for="r in reasonOptionsForItem(item).filter(r => !item._reasonQuery || r.label.toLowerCase().includes(item._reasonQuery.toLowerCase()))"
                      :key="r.value"
                      :value="r.value"
                      :label="r.label"
                    />
                  </el-select>
                </div>
              </div>

              <!-- 购买日期（每条内容单独填写） -->
              <div class="item-row">
                <span class="item-label">购买日期</span>
                <el-date-picker
                  v-model="item.purchase_date"
                  type="date"
                  value-format="YYYY-MM-DD"
                  placeholder="根据备注填写购买日期"
                  style="width:100%"
                />
              </div>

              <!-- 商家备注（多内容时每条单独填写） -->
              <div v-if="multipleItems" class="item-row">
                <span class="item-label">商家备注</span>
                <el-input
                  v-model="item._seller_remark"
                  type="textarea"
                  :rows="2"
                  placeholder="填写与本条内容对应的商家备注"
                  style="width:100%"
                />
              </div>

              <!-- 发货物料分配（多面板时显示） -->
              <div v-if="multipleItems" class="item-row item-row--products">
                <span class="item-label">发货物料</span>
                <el-checkbox-group v-model="item._selectedProducts" class="item-products-check">
                  <el-checkbox
                    v-for="p in resolvedProducts"
                    :key="p.code"
                    :value="p.code"
                    class="product-checkbox"
                  >
                    <span class="p-code">{{ p.code }}</span>
                    <span class="p-name">{{ p.name }}</span>
                    <span class="p-qty">×{{ p.quantity }}</span>
                  </el-checkbox>
                </el-checkbox-group>
              </div>

              <!-- 多产品模式：该段的原因候选 -->
              <div v-if="item._segmentText && item._reasonCandidates?.length" class="item-reason-candidates">
                <div class="irc-header">
                  <span class="irc-segment">「{{ item._segmentText }}」</span>
                  <span class="irc-hint">原因建议 · 点击应用</span>
                </div>
                <div
                  v-for="(c, ci) in item._reasonCandidates"
                  :key="c.reason_id"
                  class="candidate-item alias-candidate"
                  :class="{ 'is-best': ci === 0 }"
                  @click="applyReasonCandidate(c, item)"
                  title="点击应用"
                >
                  <span class="cand-rank">{{ ci + 1 }}</span>
                  <span class="cand-path">
                    <span v-if="c.category_name" class="cand-cat">{{ c.category_name }} › </span>{{ c.name }}
                  </span>
                  <span v-if="c.matched_keywords?.length" class="cand-matched-hint">{{ c.matched_keywords.join('、') }}</span>
                  <span class="source-badge" :class="c.source === 'keyword' ? 'src-api' : 'src-text'" style="flex-shrink:0">
                    {{ c.source === 'keyword' ? '关键词' : '历史' }}
                  </span>
                  <span class="cand-score">{{ Math.round((c.total_score ?? c.confidence ?? 0) * 100) }}</span>
                  <div class="cand-bar-wrap">
                    <div class="cand-bar" :style="{ width: `${Math.round((c.total_score ?? c.confidence ?? 0) * 100)}%` }" />
                  </div>
                </div>
              </div>
            </div>
          </section>

          <!-- 产品匹配依据面板 -->
          <section v-if="matchDebug" class="case-section match-debug-section">
            <div class="section-title match-debug-title" @click="showMatchDebug = !showMatchDebug">
              <span>
                产品匹配依据
                <span
                  v-if="matchStatus"
                  class="match-status-badge"
                  :class="`match-status--${matchStatus.level}`"
                  :title="matchStatus.tip"
                >{{ matchStatus.label }}</span>
              </span>
              <el-icon class="toggle-icon" :class="{ 'is-expanded': showMatchDebug }">
                <ArrowDown />
              </el-icon>
            </div>

            <div v-if="showMatchDebug" class="match-debug-body">

              <!-- ─────────── 售后产品 ─────────── -->
              <div class="debug-section-divider">售后产品</div>

              <!-- 匹配来源 -->
              <div class="debug-row">
                <span class="debug-key">来源</span>
                <span
                  class="source-badge"
                  :class="matchDebug.source === 'api' ? 'src-api' : matchDebug.source === 'text' ? 'src-text' : 'src-none'"
                >
                  {{ matchDebug.source === 'api' ? '产品代码 / 历史工单' : matchDebug.source === 'text' ? '文本相似度匹配' : '未找到匹配' }}
                </span>
                <span v-if="!matchDebug.source && matchDebug.no_match_reason" class="match-no-match-reason">{{ matchDebug.no_match_reason }}</span>
              </div>

              <!-- 参与匹配的文本（售后产品仅用买家留言）-->
              <div v-if="matchDebug.buyer_remark" class="debug-row debug-row--top">
                <span class="debug-key">匹配文本</span>
                <span class="debug-text-val">{{ matchDebug.buyer_remark }}</span>
              </div>

              <!-- 最佳匹配结果 -->
              <div v-if="matchDebug.source" class="debug-row">
                <span class="debug-key">匹配结果</span>
                <div class="debug-result">
                  <span class="result-path">
                    {{ matchDebug.category_name }}
                    <span class="path-sep">›</span>
                    {{ matchDebug.series_name }}
                    <span class="path-sep">›</span>
                    <span class="result-model">{{ matchDebug.model_code }} {{ matchDebug.model_name }}</span>
                  </span>
                  <span class="conf-badge" :class="`conf-${matchDebug.confidence}`">
                    {{ matchDebug.confidence === 'high' ? '高置信' : matchDebug.confidence === 'medium' ? '中置信' : '低置信' }}
                  </span>
                  <span v-if="matchDebug.date_ok === false" class="lifecycle-warn" :title="matchDebug.date_reason === 'too_early' ? '购买日期早于该型号上市时间' : '购买日期晚于该型号退市时间'">
                    ⚠ {{ matchDebug.date_reason === 'too_early' ? '未上市' : '退市' }}
                  </span>
                  <span v-if="matchDebug.score !== null" class="score-num">
                    {{ Math.round(matchDebug.score * 100) }} 分
                  </span>
                </div>
              </div>

              <!-- 候选排名 -->
              <div v-if="matchDebug.candidates?.length" class="debug-row debug-row--top">
                <span class="debug-key">候选排名</span>
                <div class="candidates-list">
                  <div
                    v-for="(c, i) in matchDebug.candidates"
                    :key="i"
                    class="candidate-wrap"
                  >
                    <!-- 系列行 -->
                    <div
                      class="candidate-item"
                      :class="{ 'is-best': i === 0 }"
                      @click="expandedCandidates.has(i) ? expandedCandidates.delete(i) : expandedCandidates.add(i); expandedCandidates = new Set(expandedCandidates)"
                    >
                      <span class="cand-rank">{{ i + 1 }}</span>
                      <span class="cand-path">
                        {{ c.category_name }} › {{ c.series_name }}
                        <span v-if="c.model_code || c.model_name" class="cand-model">
                          › {{ c.model_code || c.model_name }}
                          <span v-if="lifecycleText(c.model_id)" class="cand-lc-text">{{ lifecycleText(c.model_id) }}</span>
                        </span>
                      </span>
                      <div class="cand-bar-wrap">
                        <div class="cand-bar" :style="{ width: `${Math.round(c.score * 100)}%` }" />
                      </div>
                      <span class="cand-score">{{ Math.round(c.score * 100) }}</span>
                      <span
                        class="cand-apply-btn"
                        @click.stop="applyModelCandidate(c)"
                        title="应用此型号"
                      >应用</span>
                      <span v-if="c.models?.length > 1" class="cand-expand-btn">
                        {{ expandedCandidates.has(i) ? '▲' : '▼' }}
                      </span>
                    </div>

                    <!-- 展开：系列内型号明细（点击应用对应型号）-->
                    <div v-if="expandedCandidates.has(i) && c.models?.length" class="model-detail-list">
                      <div
                        v-for="m in c.models"
                        :key="m.id"
                        class="model-detail-item"
                        :class="{ 'is-selected': m.id === c.model_id }"
                        @click="applyModelDetail(c, m)"
                        title="点击应用此型号"
                      >
                        <span class="model-detail-code">{{ m.model_code || m.name }}</span>
                        <span v-if="lifecycleText(m.id)" class="cand-lc-text" :class="m.lifecycleOk === false ? 'lc-fail-text' : ''">{{ lifecycleText(m.id) }}</span>
                        <span
                          v-if="m.lifecycleOk !== null"
                          class="model-lc-badge"
                          :class="m.lifecycleOk ? 'lc-ok' : 'lc-fail'"
                        >{{ m.lifecycleStatus === 'too_early' ? '未上市' : m.lifecycleStatus === 'too_late' ? '退市' : '在售' }}</span>
                        <div class="cand-bar-wrap">
                          <div class="cand-bar" :style="{ width: `${Math.max(0, Math.round(m.score * 100))}%` }" />
                        </div>
                        <span class="cand-score">{{ Math.round(m.score * 100) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- ─────────── 发货简称 ─────────── -->
              <div class="debug-section-divider">发货简称</div>
              <div class="debug-row debug-row--top">
                <div class="candidates-list" style="width:100%">
                  <!-- 参与匹配的清洗 token -->
                  <div v-if="matchDebug.product_tokens?.length" class="debug-cleaned-text">
                    参与匹配：{{ matchDebug.product_tokens.join('、') }}
                    <span v-if="matchDebug.shipping_alias_candidates?.[0]?.is_ambiguous" class="ambiguous-badge" title="该物料词被多个简称共用，已启用商家备注二次评分">歧义词</span>
                  </div>
                  <!-- 匹配结果 / 无匹配说明 -->
                  <div class="debug-result" style="margin-bottom:6px">
                    <template v-if="matchDebug.alias_value">
                      <span class="debug-key" style="flex-shrink:0;margin-right:6px">匹配结果</span>
                      <span class="result-plain">{{ matchDebug.alias_value }}</span>
                      <span class="source-badge" :class="matchDebug.alias_source === 'library' ? 'src-api' : 'src-text'">
                        {{ matchDebug.alias_source === 'library' ? '简称库' : '历史工单' }}
                      </span>
                      <template v-if="matchDebug.shipping_alias_candidates?.find(c => c.id === matchDebug.alias_id)">
                        <!-- 歧义时显示备注分，否则显示关键词覆盖分 -->
                        <template v-if="matchDebug.shipping_alias_candidates.find(c => c.id === matchDebug.alias_id).is_ambiguous">
                          <span class="cand-remark-label" style="margin-left:6px" title="商家备注匹配度">备注</span>
                          <div class="cand-bar-wrap" style="width:60px;display:inline-flex;margin-left:4px;vertical-align:middle">
                            <div class="cand-bar cand-bar--remark" :style="{ width: `${Math.round((matchDebug.shipping_alias_candidates.find(c => c.id === matchDebug.alias_id).remark_score ?? 0) * 100)}%` }" />
                          </div>
                          <span class="cand-score">{{ Math.round((matchDebug.shipping_alias_candidates.find(c => c.id === matchDebug.alias_id).remark_score ?? 0) * 100) }}</span>
                        </template>
                        <template v-else>
                          <div class="cand-bar-wrap" style="width:60px;display:inline-flex;margin-left:6px;vertical-align:middle">
                            <div class="cand-bar" :style="{ width: `${Math.round((matchDebug.shipping_alias_candidates.find(c => c.id === matchDebug.alias_id).score) * 100)}%` }" />
                          </div>
                          <span class="cand-score">{{ Math.round(matchDebug.shipping_alias_candidates.find(c => c.id === matchDebug.alias_id).score * 100) }}</span>
                        </template>
                      </template>
                    </template>
                    <span v-else class="debug-no-match-inline">未匹配到发货简称</span>
                  </div>
                  <!-- 候选列表 -->
                  <div
                    v-for="(c, i) in matchDebug.shipping_alias_candidates"
                    :key="c.id"
                    class="candidate-item alias-candidate"
                    :class="{ 'is-best': i === 0 && !matchDebug.alias_value }"
                    @click="applyShippingAlias(c.id)"
                    title="点击应用"
                  >
                    <span class="cand-rank">{{ i + 1 }}</span>
                    <span class="cand-path">{{ c.name }}</span>
                    <span v-if="c.affinity_count" class="affinity-badge" :title="`与当前原因历史共现 ${c.affinity_count} 次`">
                      历史匹配 ×{{ c.affinity_count }}
                    </span>
                    <span class="cand-matched-hint">{{ (c.matched_codes || []).join('、') }}</span>
                    <!-- 歧义词时：关键词分（参考）+ 备注分（排序依据）-->
                    <template v-if="c.is_ambiguous && c.remark_score !== null">
                      <div class="cand-bar-wrap" style="width:40px" title="关键词覆盖率">
                        <div class="cand-bar" :style="{ width: `${Math.round(c.score * 100)}%` }" />
                      </div>
                      <span class="cand-remark-label" title="商家备注匹配度">备注</span>
                      <div class="cand-bar-wrap">
                        <div class="cand-bar cand-bar--remark" :style="{ width: `${Math.round(c.remark_score * 100)}%` }" />
                      </div>
                      <span class="cand-score">{{ Math.round(c.remark_score * 100) }}</span>
                    </template>
                    <template v-else>
                      <div class="cand-bar-wrap">
                        <div class="cand-bar" :style="{ width: `${Math.round(c.score * 100)}%` }" />
                      </div>
                      <span class="cand-score">{{ Math.round(c.score * 100) }}</span>
                    </template>
                  </div>
                </div>
              </div>

              <!-- ─────────── 售后原因 ─────────── -->
              <div class="debug-section-divider">售后原因</div>
              <div class="debug-row debug-row--top">
                <div class="candidates-list" style="width:100%">
                  <!-- 参与匹配的清洗文本 -->
                  <div v-if="matchDebug.reason_cleaned_text" class="debug-cleaned-text">
                    参与匹配：{{ matchDebug.reason_cleaned_text }}
                  </div>
                  <!-- 匹配结果：仅在有关键词候选时显示；纯历史匹配不作为"匹配结果"展示 -->
                  <div class="debug-result" style="margin-bottom:6px">
                    <template v-if="matchDebug.reason_candidates?.length">
                      <span class="debug-key" style="flex-shrink:0;margin-right:6px">匹配结果</span>
                      <span class="result-path">
                        <span v-if="matchDebug.reason_candidates[0].category_name">{{ matchDebug.reason_candidates[0].category_name }} <span class="path-sep">›</span> </span>
                        <span class="result-model">{{ matchDebug.reason_candidates[0].name }}</span>
                      </span>
                      <span class="source-badge" :class="matchDebug.reason_candidates[0].source === 'keyword' ? 'src-api' : 'src-text'">
                        {{ matchDebug.reason_candidates[0].source === 'keyword' ? '关键词' : '历史' }}
                      </span>
                      <span class="cand-score">{{ Math.round((matchDebug.reason_candidates[0].total_score ?? 0) * 100) }}</span>
                    </template>
                    <span v-else class="debug-no-match-inline">未匹配到售后原因</span>
                  </div>
                  <!-- 候选列表：历史原因（不在关键词候选中时排第一）+ 关键词候选 -->
                  <div
                    v-if="matchDebug.suggested_reason_id && !matchDebug.reason_candidates?.find(c => c.reason_id === matchDebug.suggested_reason_id)"
                    class="candidate-item alias-candidate is-best"
                    @click="applyReasonCandidate({ reason_id: matchDebug.suggested_reason_id, reason_category_id: matchDebug.suggested_category_id })"
                    title="点击应用"
                  >
                    <span class="cand-rank">1</span>
                    <span class="cand-path">
                      <span v-if="resolveReasonName(matchDebug.suggested_reason_id, matchDebug.suggested_category_id).category_name" class="cand-cat">
                        {{ resolveReasonName(matchDebug.suggested_reason_id, matchDebug.suggested_category_id).category_name }} ›
                      </span>
                      {{ resolveReasonName(matchDebug.suggested_reason_id, matchDebug.suggested_category_id).reason_name }}
                    </span>
                    <span class="source-badge src-text" style="flex-shrink:0">历史工单</span>
                    <span v-if="matchDebug.suggested_reason_count" class="cand-score" title="该产品历史工单中出现频次">×{{ matchDebug.suggested_reason_count }}</span>
                  </div>
                  <!-- 关键词/相似度候选 -->
                  <div
                    v-for="(c, i) in matchDebug.reason_candidates"
                    :key="c.reason_id"
                    class="candidate-item alias-candidate"
                    :class="{ 'is-best': i === 0 && !matchDebug.suggested_reason_id }"
                    @click="applyReasonCandidate(c)"
                    title="点击应用"
                  >
                    <span class="cand-rank">{{ (matchDebug.suggested_reason_id && !matchDebug.reason_candidates?.find(c2 => c2.reason_id === matchDebug.suggested_reason_id)) ? i + 2 : i + 1 }}</span>
                    <span class="cand-path">
                      <span v-if="c.category_name" class="cand-cat">{{ c.category_name }} › </span>{{ c.name }}
                    </span>
                    <span
                      v-if="c.matched_keywords?.length"
                      class="cand-matched-hint"
                    >{{ c.matched_keywords.join('、') }}</span>
                    <span class="source-badge" :class="c.source === 'keyword' ? 'src-api' : 'src-text'" style="flex-shrink:0">
                      {{ c.source === 'keyword' ? '关键词' : '历史' }}
                    </span>
                    <span class="cand-score" :title="`关键词:${Math.round((c.keyword_score || 0) * 100)} 历史:${Math.round((c.history_score || 0) * 100)}`">
                      {{ Math.round((c.total_score ?? c.confidence ?? 0) * 100) }}
                    </span>
                    <div class="cand-bar-wrap">
                      <div class="cand-bar" :style="{ width: `${Math.round((c.total_score ?? c.confidence ?? 0) * 100)}%` }" />
                    </div>
                  </div>
                </div>
              </div>


            </div>
          </section>

        </div><!-- /case-body -->

        <!-- 底部操作栏 -->
        <div v-if="canEditAftersale" class="case-footer">
          <el-button :loading="ignoring" @click="ignoreCase">忽略</el-button>
          <el-button type="primary" :loading="saving" :disabled="!canConfirm" @click="confirmCase">确认</el-button>
        </div>
      </template>
    </div><!-- /work-area -->

    <!-- 原因库管理弹窗 -->
    <AftersaleReasonLib
      v-model="showReasonLib"
      @updated="onReasonLibUpdated"
    />


  </div>
</template>

<style scoped>
/* ── 整体布局 ──────────────────────────────────── */
.process-wrap {
  flex: 1; display: flex; overflow: hidden;
}

/* ── 左侧队列 ──────────────────────────────────── */
.order-queue {
  width: 280px; flex-shrink: 0;
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column;
  background: var(--bg-card);
}

.queue-header {
  padding: 12px 14px 8px;
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.header-btns { display: flex; gap: 4px; }
.queue-title {
  font-size: 13px; font-weight: 600; color: var(--text-primary);
  display: flex; align-items: center; gap: 6px;
}
.queue-count {
  background: var(--accent); color: #fff;
  font-size: 11px; font-weight: 700;
  padding: 1px 6px; border-radius: 10px;
}
.btn-icon {
  width: 26px; height: 26px; border-radius: 6px;
  border: 1px solid var(--border); background: transparent;
  color: var(--text-muted); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.btn-icon:hover { background: var(--bg); color: var(--text-primary); }

.batch-bar {
  flex-shrink: 0; display: flex; gap: 6px;
  padding: 8px 10px 6px;
  border-bottom: 1px solid var(--border);
}
.btn-batch {
  flex: 1; height: 28px; display: flex; align-items: center; justify-content: center; gap: 4px;
  border: 1px solid var(--border); border-radius: 7px;
  background: transparent; color: var(--text-secondary);
  font-size: 12px; font-family: var(--font-family);
  cursor: pointer; transition: all 0.15s;
}
.btn-batch:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.btn-batch:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-batch-submit {
  flex: 1; height: 28px;
  border: none; border-radius: 7px;
  background: var(--accent); color: #fff;
  font-size: 12px; font-family: var(--font-family);
  cursor: pointer; transition: background 0.15s;
}
.btn-batch-submit:hover:not(:disabled) { background: var(--accent-hover); }
.btn-batch-submit:disabled { background: #c8bfb0; cursor: not-allowed; }

.order-list {
  flex: 1; overflow-y: auto;
  padding: 4px 6px 8px;
}
.order-list::-webkit-scrollbar { width: 4px; }
.order-list::-webkit-scrollbar-track { background: transparent; }
.order-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.order-card {
  padding: 10px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s;
  margin-bottom: 4px;
}
.order-card:hover { background: var(--bg); border-color: var(--border); }
.order-card.active {
  background: #fff7ed;
  border-color: var(--accent);
  border-left: 3px solid var(--accent);
}

.order-no {
  font-size: 12px; font-weight: 600; color: var(--text-primary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  min-width: 0;
}
.order-meta { font-size: 11px; color: var(--text-muted); display: flex; gap: 4px; }
.sep { color: var(--border); }

.queue-empty {
  text-align: center; padding: 40px 0;
  font-size: 13px; color: var(--text-muted);
}
.queue-pagination {
  flex-shrink: 0; display: flex; flex-direction: column; gap: 4px;
  padding: 6px 10px; border-top: 1px solid var(--border);
}
.pagination-info { display: flex; align-items: center; justify-content: space-between; }
.remaining-count { font-size: 11px; color: var(--text-muted); }
.page-size-select {
  font-size: 11px; border: 1px solid var(--border); border-radius: 5px;
  background: var(--bg-card); color: var(--text-secondary); padding: 1px 4px;
  cursor: pointer; font-family: var(--font-family);
}
.pagination-nav { display: flex; align-items: center; justify-content: center; gap: 6px; }
.pg-btn {
  width: 24px; height: 24px;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg-card); color: var(--text-muted);
  font-size: 14px; line-height: 1; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.pg-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.pg-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.pg-info { font-size: 11px; color: var(--text-muted); }

/* 批量状态徽章 */
.order-no-row { display: flex; align-items: center; justify-content: space-between; gap: 4px; margin-bottom: 4px; }
.batch-status-badge { font-size: 10px; padding: 1px 5px; border-radius: 4px; flex-shrink: 0; white-space: nowrap; }
.bsb--auto    { background: #e6f7ee; color: #1a7a45; }
.bsb--confirm { background: #fff7e0; color: #9a6a00; }
.bsb--modified { background: #e8f0ff; color: #2255cc; }
.bsb--ignore  { background: #f0f0f0; color: #888; }
.bsb--loading { background: #f0f0f0; color: #aaa; }

/* ── 右侧工作区 ────────────────────────────────── */
.work-area {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
}
.work-empty {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px; color: var(--text-muted); font-size: 14px;
}
.work-empty-icon { font-size: 36px; color: #6ab47a; }

/* 工单信息栏 */
.case-header {
  padding: 14px 20px 12px;
  border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.7);
  flex-shrink: 0;
}
.case-order-no {
  font-size: 14px; font-weight: 700; color: var(--text-primary);
  margin-bottom: 6px;
}
.case-meta-row { display: flex; gap: 20px; flex-wrap: wrap; }
.meta-item { font-size: 12px; color: var(--text-secondary); }
.meta-label { font-size: 11px; color: var(--text-muted); margin-right: 4px; }

/* 工单内容（可滚动） */
.case-body { flex: 1; overflow-y: auto; padding: 16px 20px; }
.case-body::-webkit-scrollbar { width: 4px; }
.case-body::-webkit-scrollbar-track { background: transparent; }
.case-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.case-section { margin-bottom: 20px; }
.section-title {
  font-size: 12px; font-weight: 600; color: var(--text-secondary);
  letter-spacing: 0.05em; margin-bottom: 10px;
  display: flex; align-items: center; gap: 10px;
}

/* 发货物料芯片 */
.products-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.product-chip {
  padding: 4px 10px;
  background: #f5f0e8; border: 1px solid var(--border);
  border-radius: 6px; font-size: 12px;
  display: flex; align-items: center; gap: 6px;
}
.product-chip--selectable {
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.product-chip--selectable:hover {
  border-color: var(--accent);
  background: #fdf5ea;
}
.product-chip--selected {
  border-color: var(--accent);
  background: #fdefd8;
  box-shadow: 0 0 0 1px var(--accent);
}
.p-code { font-weight: 600; color: var(--text-primary); }
.p-name { color: var(--text-secondary); }
.p-qty  { color: var(--accent); font-weight: 600; }

.section-hint {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-muted);
  margin-left: 6px;
  opacity: 0.8;
}

/* 内容项：发货物料勾选区 */
.item-row--products { align-items: flex-start; }
.item-products-check {
  display: flex; flex-direction: column; gap: 4px;
  padding: 4px 0;
}
:deep(.product-checkbox) {
  height: auto; margin: 0;
  display: flex; align-items: center;
}
:deep(.product-checkbox .el-checkbox__label) {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px;
}

/* 备注区 */
.remarks-section { display: flex; gap: 16px; }
.remark-block {
  flex: 1;
  background: #faf7f2; border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 12px;
}
.remark-label { font-size: 11px; color: var(--text-muted); margin-bottom: 6px; }
.remark-text {
  font-size: 12px; color: var(--text-primary);
  line-height: 1.6; white-space: pre-wrap;
  max-height: 80px; overflow-y: auto;
}
.remark-text::-webkit-scrollbar { width: 3px; }
.remark-text::-webkit-scrollbar-thumb { background: var(--border); }

/* 日期确认区 */
.dates-section {
  display: flex; gap: 20px; align-items: center;
  background: #faf7f2; border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 14px;
}
.date-field { display: flex; align-items: center; gap: 8px; }
.date-label {
  font-size: 12px; color: var(--text-secondary);
  white-space: nowrap; flex-shrink: 0;
}
.date-picker { width: 160px; }

/* 售后内容区 */
.btn-add-content {
  padding: 3px 10px;
  border: 1px dashed var(--accent); border-radius: 6px;
  background: transparent; color: var(--accent);
  font-size: 12px; cursor: pointer;
  display: flex; align-items: center; gap: 4px;
  transition: all 0.15s;
}
.btn-add-content:hover { background: #fff7ed; }

.content-empty { font-size: 12px; color: var(--text-muted); padding: 12px 0; }

/* 售后内容卡片 */
.content-item {
  background: #ffffff; border: 1px solid #d8c8b0;
  border-radius: 10px; padding: 0 14px 12px;
  margin-bottom: 10px;
  box-shadow: 0 2px 8px rgba(80,60,40,0.12);
}

/* 多产品模式：per-item 原因候选区 */
.item-reason-candidates {
  margin-top: 10px;
  border-top: 1px dashed var(--border);
  padding-top: 8px;
}
.irc-header {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 6px;
}
.irc-segment {
  font-size: 12px; font-weight: 600; color: var(--accent);
}
.irc-hint {
  font-size: 11px; color: var(--text-muted);
}

/* 卡片头：序号 + 删除 */
.item-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 0 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 10px;
}
.item-index {
  font-size: 11px; font-weight: 700;
  color: var(--accent); letter-spacing: 0.04em;
}
.btn-del-item {
  width: 24px; height: 24px;
  border: 1px solid #f0c0c0; border-radius: 6px;
  background: transparent; color: #d05a3c;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.15s; flex-shrink: 0;
}
.btn-del-item:hover { background: #fff0ee; }

/* 每行 */
.item-row {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 8px;
}
.item-row:last-child { margin-bottom: 0; }

/* 行标签（左对齐固定宽度） */
.item-label {
  font-size: 11px; color: var(--text-muted);
  flex-shrink: 0; white-space: nowrap;
  width: 76px; text-align: right;
}

/* 三级联动 */
.product-selects { display: flex; gap: 6px; flex: 1; min-width: 0; }
.product-selects :deep(.el-select) { flex: 1; min-width: 0; }

/* 售后原因行 */
.reason-row-inner {
  display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0;
}
.reason-cat-wrap { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.reason-cat-select { width: 130px; }

/* 一级原因新增按钮 */
.btn-add-cat {
  width: 24px; height: 24px; flex-shrink: 0;
  border: 1px dashed var(--accent); border-radius: 6px;
  background: transparent; color: var(--accent);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.btn-add-cat:hover { background: #fff7ed; }

.reason-select { flex: 1; min-width: 0; }

/* 自定义创建选项布局 */
:deep(.new-create-option) { display: flex; align-items: center; }


/* 产品匹配置信度外框 */
.product-selects.conf-low :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #d05a3c !important;
}
.product-selects.conf-medium :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #e09050 !important;
}

/* ── 产品匹配依据面板 ──────────────────────────────── */
.match-debug-section { margin-top: 4px; }

.match-status-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 7px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  vertical-align: middle;
  cursor: default;
}
.match-status--auto    { background: #e6f7ee; color: #2a7a4b; border: 1px solid #b7dfca; }
.match-status--confirm { background: #fff7e6; color: #9a5c00; border: 1px solid #ffd88a; }
.match-status--ignore  { background: #f5f5f5; color: #888;    border: 1px solid #d9d9d9; }
.debug-remark-block { display: flex; flex-direction: column; gap: 3px; }
.debug-remark-line  { display: flex; align-items: baseline; gap: 6px; }
.debug-remark-label {
  flex-shrink: 0;
  font-size: 10px;
  color: #fff;
  background: #b09a80;
  border-radius: 3px;
  padding: 0 4px;
  line-height: 16px;
}
.debug-section-divider {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  font-weight: 600;
  color: #8a7a6a;
  margin: 10px 0 6px;
  letter-spacing: 0.05em;
}
.debug-section-divider::before,
.debug-section-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #e0d4c0;
}
.ambiguous-badge {
  margin-left: 6px;
  font-size: 10px;
  color: #fff;
  background: #e07a20;
  border-radius: 3px;
  padding: 0 5px;
  line-height: 16px;
  vertical-align: middle;
}
.cand-remark-label {
  font-size: 10px;
  color: #e07a20;
  margin-left: 4px;
  flex-shrink: 0;
}
.cand-bar--remark { background: #e09050; }
.debug-no-match-inline {
  font-size: 11px;
  color: #aaa;
  padding: 2px 0;
  font-style: italic;
}
.debug-cleaned-text {
  font-size: 11px;
  color: #8a7a6a;
  margin-bottom: 4px;
  padding: 2px 6px;
  background: #f5f0e8;
  border-radius: 4px;
  word-break: break-all;
}
.match-no-match-reason {
  margin-left: 6px;
  font-size: 11px;
  color: #c0712a;
  font-weight: normal;
}

.match-debug-title {
  cursor: pointer; user-select: none;
  justify-content: space-between;
}
.match-debug-title:hover { color: var(--accent); }

.toggle-icon {
  font-size: 12px; color: var(--text-muted);
  transition: transform 0.2s;
  transform: rotate(-90deg);
}
.toggle-icon.is-expanded { transform: rotate(0deg); }

.match-debug-body {
  background: #faf7f2; border: 1px solid var(--border);
  border-radius: 8px; padding: 12px 14px;
  display: flex; flex-direction: column; gap: 8px;
}

.debug-row {
  display: flex; align-items: flex-start; gap: 10px;
}
.debug-row--top { align-items: flex-start; }

.debug-key {
  font-size: 11px; color: var(--text-muted);
  width: 56px; flex-shrink: 0; padding-top: 2px;
  text-align: right;
}

/* 来源徽章 */
.source-badge {
  font-size: 11px; font-weight: 600;
  padding: 2px 8px; border-radius: 4px;
}
.src-api  { background: #e8f5e9; color: #2e7d32; }
.src-text { background: #e3f2fd; color: #1565c0; }
.src-none { background: #f3e5f5; color: #6a1b9a; }

/* 匹配文本 */
.debug-text-val {
  font-size: 11px; color: var(--text-secondary);
  line-height: 1.6; flex: 1;
  white-space: pre-wrap; word-break: break-all;
  max-height: 60px; overflow-y: auto;
}
.debug-text-val::-webkit-scrollbar { width: 3px; }
.debug-text-val::-webkit-scrollbar-thumb { background: var(--border); }

/* 最佳结果行 */
.debug-result {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap; flex: 1;
}
.result-path {
  font-size: 12px; color: var(--text-primary);
  display: flex; align-items: center; gap: 4px;
}
.path-sep { color: var(--text-muted); font-size: 11px; }
.result-model { font-weight: 600; color: var(--accent); }
.result-plain { font-size: 12px; font-weight: 600; color: var(--accent); }

/* 置信度徽章（依据面板内） */
.conf-badge {
  font-size: 10px; font-weight: 700;
  padding: 1px 6px; border-radius: 4px; flex-shrink: 0;
}
.conf-badge.conf-high   { background: #e8f5e9; color: #2e7d32; }
.conf-badge.conf-medium { background: #fff3e0; color: #e65100; }
.conf-badge.conf-low    { background: #fce4ec; color: #b71c1c; }

.cand-expand-btn {
  font-size: 9px; color: var(--text-muted); flex-shrink: 0; width: 12px; text-align: center;
}
.cand-apply-btn {
  font-size: 10px; flex-shrink: 0;
  padding: 1px 6px; border-radius: 4px;
  background: #fff7ed; color: var(--accent); border: 1px solid var(--accent);
  cursor: pointer;
}
.cand-apply-btn:hover { background: var(--accent); color: #fff; }

/* 型号明细展开面板 */
.model-detail-list {
  display: flex; flex-direction: column; gap: 1px;
  margin: 1px 0 4px 20px;
  border-left: 2px solid var(--border);
  padding-left: 8px;
}
.model-detail-item {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 6px; border-radius: 4px;
  font-size: 11px; cursor: pointer;
}
.model-detail-item:hover { background: #faf7f2; }
.model-detail-item.is-selected { background: #fff7ed; }
.model-detail-code {
  flex: 1; color: var(--text-secondary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0;
}
.model-detail-item.is-selected .model-detail-code { color: var(--accent); font-weight: 600; }
.model-lc-badge {
  font-size: 9px; font-weight: 600; padding: 0 4px; border-radius: 3px; flex-shrink: 0;
}
.lc-ok   { background: #e8f5e9; color: #2e7d32; }
.lc-fail { background: #fce4ec; color: #b71c1c; }
.cand-lc-text { font-size: 10px; color: var(--text-muted); flex-shrink: 0; }
.cand-lc-text.lc-fail-text { color: #b71c1c; }

.lifecycle-warn {
  font-size: 10px; font-weight: 600;
  padding: 1px 6px; border-radius: 4px; flex-shrink: 0;
  background: #fff3e0; color: #e65100;
}

.score-num {
  font-size: 11px; color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

/* 候选排名列表 */
.candidates-list { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.candidate-wrap  { display: flex; flex-direction: column; }

.candidate-item {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 8px; border-radius: 6px;
  cursor: pointer;
  background: #fff; border: 1px solid transparent;
}
.candidate-item.is-best {
  border-color: var(--accent);
  background: #fff7ed;
}

.cand-rank {
  font-size: 10px; font-weight: 700;
  color: var(--text-muted);
  width: 14px; flex-shrink: 0; text-align: center;
}
.candidate-item.is-best .cand-rank { color: var(--accent); }

.cand-path {
  font-size: 11px; color: var(--text-secondary);
  flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  min-width: 0;
}
.cand-model {
  font-weight: 600; color: var(--accent);
}

.cand-bar-wrap {
  width: 80px; height: 6px;
  background: #ede8dc; border-radius: 3px;
  overflow: hidden; flex-shrink: 0;
}
.cand-bar {
  height: 100%; border-radius: 3px;
  background: var(--accent);
  transition: width 0.3s;
  min-width: 2px;
}

.cand-score {
  font-size: 10px; color: var(--text-muted);
  width: 24px; text-align: right; flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.cand-cat { color: var(--text-muted); }

/* 简称候选 hover 效果（与型号候选区分：无展开箭头，直接点击应用）*/
.alias-candidate {
  transition: background 0.12s, border-color 0.12s;
}
.alias-candidate:hover {
  background: #fff7ed;
  border-color: var(--accent);
}
.affinity-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  background: #e8f4e8;
  color: #3a7a3a;
  white-space: nowrap;
  flex-shrink: 0;
}
.cand-matched-hint {
  font-size: 10px; color: var(--text-muted);
  flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  min-width: 0;
  font-style: italic;
}

/* 无匹配提示 */
.debug-no-match {
  font-size: 12px; color: var(--text-muted);
  padding: 4px 0;
}

/* 底部操作栏 */
.case-footer {
  padding: 12px 20px;
  border-top: 1px solid var(--border);
  background: rgba(255,255,255,0.7);
  display: flex; justify-content: flex-end; gap: 10px;
  flex-shrink: 0;
}
</style>

