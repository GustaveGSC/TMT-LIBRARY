<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted, onUnmounted, watchEffect } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Setting, ArrowDown } from '@element-plus/icons-vue'
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
const PAGE_SIZE   = 30
const loadingList = ref(false)
const loadingMore = ref(false)
const hasMore     = computed(() => orders.value.length < totalOrders.value)

// 懒加载哨兵元素
const sentinel = ref(null)
let   observer = null

// 当前工单
const currentOrder  = ref(null)
const saving        = ref(false)
const ignoring      = ref(false)

// 当前工单日期编辑状态
const aftersaleDate = ref(null)   // 售后日期（来自 shipped_date，可编辑）
const purchaseDate  = ref(null)   // 购买日期（用户手动填写）

// 弹窗
const showReasonLib = ref(false)

// 物料简称列表（用于发货物料别名合并显示）

// 发货物料简称库（下拉候选）
const shippingAliasOptions = ref([])   // [{id, name}]
// 售后物料简称库（下拉候选）
const returnAliasOptions   = ref([])   // [{id, name}]

// 品类树（三级联动，缓存）
const categoryTree = ref([])

// 型号生命周期范围 { model_id: { listed_yymm, delisted_yymm } }
const modelLifecycles = ref({})

// 一级原因分类列表（所有分类，含空分类）
const reasonCategories = ref([])   // [{id, name, sort_order}]
// 原因按分类分组（含二级原因列表）
const reasonGroups = ref([])       // [{category_id, category_name, reasons:[{id,name,...}]}]

// 售后内容列表
// 每项：{ category_id, series_id, model_id,
//         shipping_material_alias, aftersale_material_alias,
//         reason_category_id, reason_id, custom_reason }
const contentItems = ref([])

// 产品匹配依据（选单后填充，用于底部说明面板）
const matchDebug          = ref(null)   // null | { source, text, category_name, ... }
const showMatchDebug      = ref(true)   // 展开/折叠控制
const expandedCandidates  = ref(new Set())   // 已展开系列的下标集合

// ── 计算属性 ──────────────────────────────────────

// 品类选项（产品库三级联动第一级）
const categoryOptions = computed(() =>
  categoryTree.value.map(c => ({ value: c.id, label: c.name }))
)

// 当前工单「发货物料」列表（只读）
const resolvedProducts = computed(() => currentOrder.value?.products || [])

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  initObserver()
  // 先并发加载匹配所需的基础数据，再加载订单列表
  // 避免 selectOrder 运行时 categoryTree / productAliases / reasonGroups 尚未就绪
  await Promise.all([loadCategoryTree(), loadAliases(), loadReasonOptions()])
  loadOrders()
})

onUnmounted(() => {
  observer?.disconnect()
})

// ── 方法 ──────────────────────────────────────────

// 初始化 IntersectionObserver，监听哨兵进入视口时追加加载
function initObserver() {
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && hasMore.value && !loadingMore.value) {
        loadMore()
      }
    },
    { threshold: 0.1 }
  )
  watchEffect(() => {
    if (sentinel.value) observer.observe(sentinel.value)
  })
}

// 初次加载（重置列表）
async function loadOrders() {
  loadingList.value = true
  page.value = 1
  try {
    const res = await http.get('/api/aftersale/pending', {
      params: { page: 1, page_size: PAGE_SIZE },
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

// 懒加载：追加下一页
async function loadMore() {
  if (!hasMore.value || loadingMore.value) return
  loadingMore.value = true
  page.value += 1
  try {
    const res = await http.get('/api/aftersale/pending', {
      params: { page: page.value, page_size: PAGE_SIZE },
    })
    if (res.success) {
      orders.value.push(...res.data.items)
      totalOrders.value = res.data.total
    }
  } finally {
    loadingMore.value = false
  }
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

// 加载物料简称（发货简称库 + 售后简称库）
// 使用 allSettled 确保任一请求失败不会阻断其他加载
async function loadAliases() {
  const [shipRes, retRes] = await Promise.allSettled([
    http.get('/api/aftersale/shipping-aliases'),
    http.get('/api/aftersale/return-aliases'),
  ])
  if (shipRes.status === 'fulfilled' && shipRes.value?.success)
    shippingAliasOptions.value = shipRes.value.data
  if (retRes.status === 'fulfilled' && retRes.value?.success)
    returnAliasOptions.value   = retRes.value.data
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
  console.log('[selectOrder]', order.ecommerce_order_no, 'products:', order.products)
  currentOrder.value  = order
  aftersaleDate.value = order.shipped_date || null
  purchaseDate.value  = parsePurchaseDateFromRemark(order.seller_remark)
  matchDebug.value    = null

  // 先放一条空内容占位
  const firstItem = makeEmptyItem()
  contentItems.value = [firstItem]

  const orderNo   = order.ecommerce_order_no
  const debugText = [order.buyer_remark, order.seller_remark].filter(Boolean).join(' ')

  // ── 来源1：产品代码 + 历史工单（后端）+ 原因候选（并发）──
  let apiResult        = null   // 原始 API 返回（含 suggested_shipping_alias）
  let reasonCandidates = []     // auto-match 返回的原因候选列表

  await Promise.all([
    (order.buyer_remark?.trim() || order.products?.length)
      ? http.post('/api/aftersale/suggest-product', {
          product_codes: order.products?.map(p => p.code) || [],
          purchase_date: purchaseDate.value || null,
          seller_remark: order.seller_remark || null,
          buyer_remark:  order.buyer_remark  || null,
        }).then(r => { if (r.success && r.data) apiResult = r.data })
      : Promise.resolve(),
    debugText.trim()
      ? http.post('/api/aftersale/auto-match', { text: debugText })
          .then(r => { if (r.success) reasonCandidates = r.data || [] })
      : Promise.resolve(),
  ])

  // API 型号匹配（需有 category_id 才算匹配到型号）
  const apiMatch = apiResult?.category_id ? apiResult : null

  // ── 来源2：买家留言 + 商家备注 文本匹配（前端） ──────
  const textMatch = matchTextToModel(order.buyer_remark, order.seller_remark)

  // ── 简称候选（前端实时计算）────────────────────────
  const shippingAliasCandidates = computeShippingAliasCandidates(order.products)
  const returnAliasCandidates   = computeReturnAliasCandidates(order.seller_remark)

  // 防止切换工单太快导致覆盖
  if (currentOrder.value?.ecommerce_order_no !== orderNo) return
  const item = contentItems.value[0]
  if (!item) return

  // ── 发货物料简称自动匹配（来自历史工单）────────────────
  const historyAlias  = apiResult?.suggested_shipping_alias || null
  const shippingAlias = historyAlias || ''
  const aliasSource   = historyAlias ? 'history' : null
  if (shippingAlias) item.shipping_material_alias = shippingAlias

  // 售后物料简称：来自历史工单
  const aftersaleAlias = apiResult?.suggested_aftersale_alias || null
  if (aftersaleAlias) item.aftersale_material_alias = aftersaleAlias

  // 售后原因：来自历史工单（最频繁的 reason_id + category_id）
  const suggestedReasonId  = apiResult?.suggested_reason_id          || null
  const suggestedCategoryId = apiResult?.suggested_reason_category_id || null
  if (suggestedReasonId) {
    item.reason_category_id = suggestedCategoryId
    item.reason_id          = suggestedReasonId
  }

  // ── 填充型号 + 构建匹配依据 ──────────────────────────
  if (apiMatch) {
    // API 匹配到（产品代码/历史工单）
    // date_ok=false 表示购买日期不在该型号生命周期内，置信度降为 low
    const dateOk = apiMatch.date_ok !== false
    let dateReason = null
    if (!dateOk && apiMatch.model_id) {
      const buyYm = purchaseDate.value ? purchaseDate.value.slice(0, 7) : null
      if (buyYm) {
        const lc = modelLifecycles.value[apiMatch.model_id]
        if (lc) {
          const currentYm = new Date().toISOString().slice(0, 7)
          const tooEarly  = lc.listed_yymm && buyYm < lc.listed_yymm
          dateReason = tooEarly ? 'too_early' : 'too_late'
        }
      }
    }
    item.category_id = apiMatch.category_id
    item.series_id   = apiMatch.series_id
    item.model_id    = apiMatch.model_id
    item.confidence  = dateOk ? 'high' : 'low'
    const names = resolveModelNames(apiMatch.category_id, apiMatch.series_id, apiMatch.model_id)
    matchDebug.value = {
      source:        'api',
      text:          debugText,
      date_ok:       dateOk,
      date_reason:   dateReason,
      category_name: names.category_name,
      series_name:   names.series_name,
      model_name:    names.model_name,
      model_code:    names.model_code,
      score:                  null,
      confidence:             'high',
      candidates:             (apiMatch.candidates || []).map(c => {
        const seriesMax = c.models?.[0]?.score || 1
        return {
          ...c,
          models: (c.models || []).map(m => ({
            ...m,
            score: m.score / seriesMax,
            lifecycleOk:     m.date_ok !== false,
            lifecycleStatus: m.date_ok === false ? 'too_early' : null,
          })),
        }
      }),
      alias_source:           aliasSource,
      alias_value:            shippingAlias || null,
      aftersale_alias_value:  aftersaleAlias,
      suggested_reason_id:    suggestedReasonId,
      suggested_category_id:  suggestedCategoryId,
      shipping_alias_candidates: shippingAliasCandidates,
      return_alias_candidates:   returnAliasCandidates,
      reason_candidates:         reasonCandidates,
    }
  } else if (textMatch) {
    // 仅文本匹配 → 根据分数设置置信度
    item.category_id = textMatch.category_id
    item.series_id   = textMatch.series_id
    item.model_id    = textMatch.model_id
    item.confidence  = scoreToConfidence(textMatch.score)
    matchDebug.value = {
      source:                 'text',
      text:                   debugText,
      category_name:          textMatch.category_name,
      series_name:            textMatch.series_name,
      model_name:             textMatch.model_name,
      model_code:             textMatch.model_code,
      score:                  textMatch.score,
      confidence:             scoreToConfidence(textMatch.score),
      candidates:             textMatch.candidates || [],
      alias_source:           aliasSource,
      alias_value:            shippingAlias || null,
      aftersale_alias_value:  aftersaleAlias,
      suggested_reason_id:    suggestedReasonId,
      suggested_category_id:  suggestedCategoryId,
      shipping_alias_candidates: shippingAliasCandidates,
      return_alias_candidates:   returnAliasCandidates,
      reason_candidates:         reasonCandidates,
    }
  } else {
    // 型号无匹配 → 保持空白
    matchDebug.value = {
      source:                 null,
      text:                   debugText,
      confidence:             null,
      candidates:             [],
      alias_source:           aliasSource,
      alias_value:            shippingAlias || null,
      aftersale_alias_value:  aftersaleAlias,
      suggested_reason_id:    suggestedReasonId,
      suggested_category_id:  suggestedCategoryId,
      shipping_alias_candidates: shippingAliasCandidates,
      return_alias_candidates:   returnAliasCandidates,
      reason_candidates:         reasonCandidates,
    }
  }
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
    purchaseDate.value  = null
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
    shipping_material_alias:  '',
    aftersale_material_alias: '',
    reason_category_id:       null,
    reason_id:                null,
    custom_reason:            '',
    confidence:               null,   // null | 'high' | 'medium' | 'low'
  }
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
  item.reason_id = null
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
 * 计算 text 与 name 的相似度（0~1）。
 * 规则：完全包含 → 1.0；text 包含 name → 0.9；
 *       找 name 中最长的、在 text 中出现的连续子串，长度比 → 部分分。
 * 对中文字符无需分词，直接滑窗匹配。
 */
function calcMatchScore(text, name) {
  if (!text || !name) return 0
  const t = text.toLowerCase()
  const n = name.toLowerCase()
  if (t === n)         return 1.0
  if (t.includes(n))   return 1.0
  if (n.includes(t))   return 0.9

  // 提取纯汉字后再比较，消除"（V1.1）"等版本号对评分的干扰
  // 例如：text="明睿 2022.6.1"，name="明睿（V1.1）" → tCn="明睿", nCn="明睿" → match
  const tCn = t.replace(/[^\u4e00-\u9fff]/g, '')
  const nCn = n.replace(/[^\u4e00-\u9fff]/g, '')
  if (tCn && nCn && nCn.length >= 2 && tCn.includes(nCn)) {
    // 汉字部分匹配后，再检查名称里的版本号是否也出现在文本中
    // 例如 "2.2骑士" → 匹配 "骑士（V2.2）"(0.95) 优先于 "骑士（V2.1）"(0.9)
    // 用独立边界正则避免 "11.1" 误匹配 "1.1"
    const verM = n.match(/[vV](\d+\.\d+)/)
    if (verM) {
      const escaped = verM[1].replace('.', '\\.')
      if (new RegExp(`(?<!\\d)${escaped}(?!\\d)`).test(t)) return 0.95
    }
    return 0.9
  }

  // 找最长公共连续子串（n 中出现在 t 里的）
  let maxLen = 0
  outer: for (let len = n.length - 1; len >= 2; len--) {
    for (let i = 0; i <= n.length - len; i++) {
      if (t.includes(n.slice(i, i + len))) {
        maxLen = len
        break outer
      }
    }
  }
  return maxLen >= 2 ? maxLen / n.length : 0
}

/**
 * 对品类树中每个系列/型号与备注文本打分，返回最佳匹配。
 * 策略：
 *   1. 对每个系列，取系列名与文本的分值（seriesScore）
 *   2. 在该系列的型号中，取型号名/model_code 与文本的最高分值（modelScore）
 *   3. 取 max(seriesScore*0.8, modelScore) 作为该系列的最终分
 *   4. 若系列分最高但无具体型号匹配，默认选第一个型号，分值打 0.7 折
 *
 * 返回 { category_id, series_id, model_id, score } 或 null
 */
function matchTextToModel(remark1, remark2) {
  const text = [remark1, remark2].filter(Boolean).join(' ')
  if (!text.trim() || !categoryTree.value.length) return null

  let bestScore  = 0
  let bestResult = null
  const allCandidates = []

  for (const cat of categoryTree.value) {
    for (const series of (cat.series || [])) {
      if (!series.models?.length) continue

      // 系列分：系列名 + 系列代码
      const seriesScore = Math.max(
        calcMatchScore(text, series.name),
        calcMatchScore(text, series.code) * 0.6,
      )

      // 在系列内找最佳型号（考虑文本分 + 生命周期）
      // 购买日期的年月（YYYY-MM），用于生命周期过滤
      const buyYm = purchaseDate.value ? purchaseDate.value.slice(0, 7) : null

      const currentYm = new Date().toISOString().slice(0, 7)
      let bestModelScore = 0
      let bestModel      = series.models[0]
      const modelDetails = []   // 用于展开面板

      for (const model of series.models) {
        let s = Math.max(
          calcMatchScore(text, model.name),
          calcMatchScore(text, model.code)       * 0.5,
          calcMatchScore(text, model.model_code) * 0.5,
        )
        // 变体字母加成：型号末尾为单字母（如 -GN-B），且该字母以词首形式出现在文本中（如"B新款"）
        const variantM = model.model_code?.match(/-([A-Z])$/i)
        if (variantM) {
          const letter = variantM[1]
          if (new RegExp(`(^|[\\s（(【])${letter}(?=[\\u4e00-\\u9fff0-9])`, 'i').test(text)) {
            s += 0.1
          }
        }
        // 生命周期调整：不论文本得分高低，只要有购买日期就参与计算
        // 无法从文本区分型号时（各型号文本分相同），生命周期是唯一区分依据
        let lifecycleOk = null      // null=无数据, true=在周期内, false=不符
        let lifecycleStatus = null  // 'ok' | 'too_early' | 'too_late' | null
        if (buyYm) {
          const lc = modelLifecycles.value[model.id]
          if (lc) {
            const effectiveDelisted = lc.delisted_yymm || currentYm
            const tooEarly = lc.listed_yymm && buyYm < lc.listed_yymm
            const tooLate  = buyYm > effectiveDelisted
            lifecycleOk = !tooEarly && !tooLate
            lifecycleStatus = tooEarly ? 'too_early' : tooLate ? 'too_late' : 'ok'
            s += lifecycleOk ? 0.15 : -0.15
          }
        }
        modelDetails.push({
          id:             model.id,
          name:           model.name,
          model_code:     model.model_code || '',
          score:          s,
          lifecycleOk,
          lifecycleStatus,
        })
        if (s > bestModelScore) { bestModelScore = s; bestModel = model }
      }

      // 型号明细按得分降序
      modelDetails.sort((a, b) => b.score - a.score)

      // 本系列最终得分
      let totalScore    = Math.max(seriesScore * 0.8, bestModelScore)
      let selectedModel = bestModel

      // 系列分更高但型号无明显文本匹配 → 用 bestModel（已含生命周期筛选），降分
      // 阈值 0.5 = 纯文本 0.35 + 生命周期加成 0.15，避免已有生命周期优选的 model 被覆盖
      if (seriesScore * 0.8 > bestModelScore && bestModelScore < 0.5) {
        totalScore    = seriesScore * 0.7
        selectedModel = bestModel   // 保留生命周期筛选结果，不强制回第一个
      }

      // 收集所有得分 > 0.05 的候选，供依据面板展示
      if (totalScore > 0.05) {
        allCandidates.push({
          category_id:   cat.id,
          category_name: cat.name,
          series_id:     series.id,
          series_name:   series.name,
          model_id:      selectedModel.id,
          model_name:    selectedModel.name,
          model_code:    selectedModel.model_code || '',
          score:         totalScore,
          models:        modelDetails,   // 系列内所有型号得分
        })
      }

      if (totalScore > bestScore) {
        bestScore  = totalScore
        bestResult = {
          category_id:   cat.id,
          category_name: cat.name,
          series_id:     series.id,
          series_name:   series.name,
          model_id:      selectedModel.id,
          model_name:    selectedModel.name,
          model_code:    selectedModel.model_code || '',
          score:         totalScore,
        }
      }
    }
  }

  if (bestScore <= 0.1) return null

  // 候选按分数降序，最多保留 5 条
  allCandidates.sort((a, b) => b.score - a.score)
  bestResult.candidates = allCandidates.slice(0, 5)
  return bestResult
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
 * 按产品代码覆盖率给发货物料简称打分，返回 Top5 候选。
 * score = 订单产品代码与简称绑定代码的交集数 / 简称绑定代码总数
 */
function computeShippingAliasCandidates(products) {
  if (!products?.length || !shippingAliasOptions.value.length) return []
  const orderCodes = new Set(products.map(p => p.code))
  return shippingAliasOptions.value
    .map(alias => {
      const bound = alias.product_codes || []
      if (!bound.length) return null
      const matched = bound.filter(c => orderCodes.has(c))
      if (!matched.length) return null
      const score = matched.length / bound.length
      return { id: alias.id, name: alias.name, score, matched_codes: matched }
    })
    .filter(Boolean)
    .sort((a, b) => b.score - a.score)
    .slice(0, 5)
}

/**
 * 按关键词与商家备注的文本相似度给售后物料简称打分，返回 Top5 候选。
 * 取该简称所有关键词中最高的 calcMatchScore，阈值 0.3。
 */
function computeReturnAliasCandidates(sellerRemark) {
  if (!sellerRemark?.trim() || !returnAliasOptions.value.length) return []
  const text = sellerRemark.toLowerCase()
  return returnAliasOptions.value
    .map(alias => {
      const kws = alias.keywords || []
      if (!kws.length) return null
      let bestScore = 0
      const matchedKws = []
      for (const kw of kws) {
        const s = calcMatchScore(text, kw.toLowerCase())
        if (s >= 0.3) {
          if (!matchedKws.includes(kw)) matchedKws.push(kw)
          if (s > bestScore) bestScore = s
        }
      }
      if (!matchedKws.length) return null
      return { id: alias.id, name: alias.name, score: bestScore, matched_keywords: matchedKws }
    })
    .filter(Boolean)
    .sort((a, b) => b.score - a.score)
    .slice(0, 5)
}

// ── 候选一键应用 ────────────────────────────────────

function applyShippingAlias(name) {
  if (contentItems.value[0]) contentItems.value[0].shipping_material_alias = name
}

function applyReturnAlias(name) {
  if (contentItems.value[0]) contentItems.value[0].aftersale_material_alias = name
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

function applyReasonCandidate(candidate) {
  const item = contentItems.value[0]
  if (!item) return
  // 在 reasonGroups 中查找 reason_id 对应的 category_id
  for (const group of reasonGroups.value) {
    if (group.reasons?.find(r => r.id === candidate.reason_id)) {
      item.reason_category_id = group.category_id
      item.reason_id          = candidate.reason_id
      return
    }
  }
  item.reason_id = candidate.reason_id
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

async function confirmCase() {
  if (!currentOrder.value) return
  if (contentItems.value.length === 0) {
    ElMessage.warning('请至少添加一条售后内容')
    return
  }
  saving.value = true
  try {
    const reasons = contentItems.value.map(item => ({
      reason_id:                item.reason_id || null,
      // reason_id 为空时传一级分类，供后端存储 reason_category_id
      reason_category_id:       item.reason_id ? null : (item.reason_category_id || null),
      custom_reason:            item.custom_reason || '',
      model_id:                 item.model_id || null,
      shipping_material_alias:  item.shipping_material_alias || '',
      aftersale_material_alias: item.aftersale_material_alias || '',
      involved_products:        [],
      notes:                    '',
    }))

    // 提前收集自定义原因（确认后 contentItems 会被清空）
    const customToSave = contentItems.value
      .filter(item => !item.reason_id && item.custom_reason.trim())
      .map(item => ({
        name:        item.custom_reason.trim(),
        category_id: item.reason_category_id || null,
      }))

    const res = await http.post('/api/aftersale/cases', {
      ecommerce_order_no: currentOrder.value.ecommerce_order_no,
      products:           currentOrder.value.products,
      seller_remark:      currentOrder.value.seller_remark,
      buyer_remark:       currentOrder.value.buyer_remark,
      shipped_date:       aftersaleDate.value,
      purchase_date:      purchaseDate.value || null,
      city:               currentOrder.value.city || null,
      district:           currentOrder.value.district || null,
      operator:           currentOrder.value.operator,
      channel_name:       currentOrder.value.channel_name,
      province:           currentOrder.value.province,
      reasons,
      assigned_models:     [],
      shipping_materials:  [],
      aftersale_materials: [],
    })
    if (res.success) {
      ElMessage.success('已确认')
      removeCurrentFromList()
      emit('case-confirmed')
      // 将自定义原因异步写入原因库（重名自动跳过）
      if (customToSave.length) saveCustomReasonsToLib(customToSave)
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

// 将自定义原因列表逐条写入原因库，写入后刷新选项
async function saveCustomReasonsToLib(items) {
  let savedCount = 0
  for (const item of items) {
    const res = await http.post('/api/aftersale/reasons', item)
    if (res.success) savedCount++
    // 重名（已存在）直接跳过，不报错
  }
  if (savedCount > 0) loadReasonOptions()
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
          <el-tooltip content="原因库" placement="top">
            <button class="btn-icon" title="管理原因库" @click="showReasonLib = true">
              <el-icon><Setting /></el-icon>
            </button>
          </el-tooltip>
        </div>
      </div>

      <div v-loading="loadingList" class="order-list">
        <div
          v-for="order in orders"
          :key="order.ecommerce_order_no"
          class="order-card"
          :class="{ active: currentOrder?.ecommerce_order_no === order.ecommerce_order_no }"
          @click="selectOrder(order)"
        >
          <div class="order-no">{{ order.ecommerce_order_no }}</div>
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

        <div ref="sentinel" class="load-sentinel">
          <span v-if="loadingMore" class="load-more-hint">加载中…</span>
          <span v-else-if="!hasMore && orders.length > 0" class="load-more-hint">已全部加载</span>
        </div>

        <div v-if="!loadingList && orders.length === 0" class="queue-empty">
          暂无待处理订单
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

          <!-- 发货物料（只读） -->
          <section class="case-section">
            <div class="section-title">发货物料</div>
            <div class="products-grid">
              <div
                v-for="item in resolvedProducts"
                :key="item.code"
                class="product-chip"
                :title="`${item.code} ${item.name}`"
              >
                <span class="p-code">{{ item.code }}</span>
                <span class="p-name">{{ item.name }}</span>
                <span class="p-qty">×{{ item.quantity }}</span>
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
            <div class="date-field">
              <span class="date-label">购买日期</span>
              <el-date-picker
                v-model="purchaseDate"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="根据备注填写购买日期"
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
                  v-model="item.shipping_material_alias"
                  placeholder="选择发货物料简称"
                  clearable
                  filterable
                  allow-create
                  style="width:100%"
                >
                  <el-option
                    v-for="opt in shippingAliasOptions"
                    :key="opt.id"
                    :value="opt.name"
                    :label="opt.name"
                  />
                </el-select>
              </div>

              <!-- 售后物料简称 -->
              <div class="item-row">
                <span class="item-label">售后物料简称</span>
                <el-select
                  v-model="item.aftersale_material_alias"
                  placeholder="选择出问题的物料简称"
                  clearable
                  filterable
                  allow-create
                  style="width:100%"
                >
                  <el-option
                    v-for="opt in returnAliasOptions"
                    :key="opt.id"
                    :value="opt.name"
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
                  <!-- 二级原因 -->
                  <el-select
                    v-model="item.reason_id"
                    placeholder="具体原因"
                    clearable
                    filterable
                    :disabled="!item.reason_category_id"
                    class="reason-select"
                  >
                    <el-option
                      v-for="r in reasonOptionsForItem(item)"
                      :key="r.value"
                      :value="r.value"
                      :label="r.label"
                    />
                  </el-select>
                  <span class="or-text">或</span>
                  <el-input
                    v-model="item.custom_reason"
                    placeholder="自定义原因"
                    class="custom-reason-input"
                  />
                </div>
              </div>
            </div>
          </section>

          <!-- 产品匹配依据面板 -->
          <section v-if="matchDebug" class="case-section match-debug-section">
            <div class="section-title match-debug-title" @click="showMatchDebug = !showMatchDebug">
              <span>产品匹配依据</span>
              <el-icon class="toggle-icon" :class="{ 'is-expanded': showMatchDebug }">
                <ArrowDown />
              </el-icon>
            </div>

            <div v-if="showMatchDebug" class="match-debug-body">

              <!-- 匹配来源 -->
              <div class="debug-row">
                <span class="debug-key">来源</span>
                <span
                  class="source-badge"
                  :class="matchDebug.source === 'api' ? 'src-api' : matchDebug.source === 'text' ? 'src-text' : 'src-none'"
                >
                  {{ matchDebug.source === 'api' ? '产品代码 / 历史工单' : matchDebug.source === 'text' ? '文本相似度匹配' : '未找到匹配' }}
                </span>
              </div>

              <!-- 参与匹配的文本 -->
              <div v-if="matchDebug.text" class="debug-row debug-row--top">
                <span class="debug-key">匹配文本</span>
                <span class="debug-text-val">{{ matchDebug.text }}</span>
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

              <!-- 发货物料简称匹配 -->
              <div v-if="matchDebug.alias_value || matchDebug.shipping_alias_candidates?.length" class="debug-row debug-row--top">
                <span class="debug-key">发货简称</span>
                <div class="candidates-list">
                  <!-- 已采纳的简称 -->
                  <div v-if="matchDebug.alias_value" class="debug-result" style="margin-bottom:4px">
                    <span class="result-model">{{ matchDebug.alias_value }}</span>
                    <span class="source-badge" :class="matchDebug.alias_source === 'library' ? 'src-api' : 'src-text'">
                      {{ matchDebug.alias_source === 'library' ? '简称库' : '历史工单' }}
                    </span>
                  </div>
                  <!-- 候选列表 -->
                  <div
                    v-for="(c, i) in matchDebug.shipping_alias_candidates"
                    :key="c.id"
                    class="candidate-item alias-candidate"
                    :class="{ 'is-best': i === 0 && !matchDebug.alias_value }"
                    @click="applyShippingAlias(c.name)"
                    title="点击应用"
                  >
                    <span class="cand-rank">{{ i + 1 }}</span>
                    <span class="cand-path">{{ c.name }}</span>
                    <span class="cand-matched-hint">{{ c.matched_codes.join('、') }}</span>
                    <div class="cand-bar-wrap">
                      <div class="cand-bar" :style="{ width: `${Math.round(c.score * 100)}%` }" />
                    </div>
                    <span class="cand-score">{{ Math.round(c.score * 100) }}</span>
                  </div>
                </div>
              </div>

              <!-- 售后物料简称匹配 -->
              <div v-if="matchDebug.aftersale_alias_value || matchDebug.return_alias_candidates?.length" class="debug-row debug-row--top">
                <span class="debug-key">售后简称</span>
                <div class="candidates-list">
                  <!-- 已采纳的简称 -->
                  <div v-if="matchDebug.aftersale_alias_value" class="debug-result" style="margin-bottom:4px">
                    <span class="result-model">{{ matchDebug.aftersale_alias_value }}</span>
                    <span class="source-badge src-text">历史工单</span>
                  </div>
                  <!-- 候选列表 -->
                  <div
                    v-for="(c, i) in matchDebug.return_alias_candidates"
                    :key="c.id"
                    class="candidate-item alias-candidate"
                    :class="{ 'is-best': i === 0 && !matchDebug.aftersale_alias_value }"
                    @click="applyReturnAlias(c.name)"
                    title="点击应用"
                  >
                    <span class="cand-rank">{{ i + 1 }}</span>
                    <span class="cand-path">{{ c.name }}</span>
                    <span class="cand-matched-hint">{{ c.matched_keywords.join('、') }}</span>
                    <div class="cand-bar-wrap">
                      <div class="cand-bar" :style="{ width: `${Math.round(c.score * 100)}%` }" />
                    </div>
                    <span class="cand-score">{{ Math.round(c.score * 100) }}</span>
                  </div>
                </div>
              </div>

              <!-- 售后原因匹配 -->
              <div v-if="matchDebug.suggested_reason_id || matchDebug.reason_candidates?.length" class="debug-row debug-row--top">
                <span class="debug-key">售后原因</span>
                <div class="candidates-list">
                  <!-- 历史工单最频繁原因（仅当与 reason_candidates 不重复时显示）-->
                  <div
                    v-if="matchDebug.suggested_reason_id && !matchDebug.reason_candidates?.find(c => c.reason_id === matchDebug.suggested_reason_id)"
                    class="debug-result" style="margin-bottom:4px"
                  >
                    <span class="result-path">
                      {{ resolveReasonName(matchDebug.suggested_reason_id, matchDebug.suggested_category_id).category_name }}
                      <span class="path-sep">›</span>
                      <span class="result-model">{{ resolveReasonName(matchDebug.suggested_reason_id, matchDebug.suggested_category_id).reason_name }}</span>
                    </span>
                    <span class="source-badge src-text">历史工单</span>
                  </div>
                  <!-- 候选列表（auto-match 返回，含 keyword/history 两种来源）-->
                  <div
                    v-for="(c, i) in matchDebug.reason_candidates"
                    :key="c.reason_id"
                    class="candidate-item alias-candidate"
                    :class="{ 'is-best': i === 0 }"
                    @click="applyReasonCandidate(c)"
                    title="点击应用"
                  >
                    <span class="cand-rank">{{ i + 1 }}</span>
                    <span class="cand-path">
                      <span v-if="c.category_name" class="cand-cat">{{ c.category_name }} › </span>{{ c.name }}
                    </span>
                    <span class="source-badge" :class="c.source === 'keyword' ? 'src-api' : 'src-text'" style="flex-shrink:0">
                      {{ c.source === 'keyword' ? '关键词' : '历史' }}
                    </span>
                    <div class="cand-bar-wrap">
                      <div class="cand-bar" :style="{ width: `${Math.round(c.confidence * 100)}%` }" />
                    </div>
                    <span class="cand-score">{{ Math.round(c.confidence * 100) }}</span>
                  </div>
                </div>
              </div>

              <!-- 无匹配提示 -->
              <div v-if="!matchDebug.source && !matchDebug.alias_value" class="debug-no-match">
                买家留言和商家备注中未找到与产品库相似的内容，请手动选择型号
              </div>
              <div v-else-if="!matchDebug.source" class="debug-no-match">
                未找到型号匹配，请手动选择
              </div>

            </div>
          </section>

        </div><!-- /case-body -->

        <!-- 底部操作栏 -->
        <div v-if="canEditAftersale" class="case-footer">
          <el-button :loading="ignoring" @click="ignoreCase">忽略</el-button>
          <el-button type="primary" :loading="saving" @click="confirmCase">确认</el-button>
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
  margin-bottom: 4px;
}
.order-meta { font-size: 11px; color: var(--text-muted); display: flex; gap: 4px; }
.sep { color: var(--border); }

.queue-empty {
  text-align: center; padding: 40px 0;
  font-size: 13px; color: var(--text-muted);
}
.load-sentinel {
  height: 32px; display: flex;
  align-items: center; justify-content: center;
}
.load-more-hint { font-size: 11px; color: var(--text-muted); }

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
.p-code { font-weight: 600; color: var(--text-primary); }
.p-name { color: var(--text-secondary); }
.p-qty  { color: var(--accent); font-weight: 600; }

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

.reason-select { width: 150px; flex-shrink: 0; }
.or-text { font-size: 12px; color: var(--text-muted); flex-shrink: 0; }
.custom-reason-input { flex: 1; min-width: 0; }

/* 产品匹配置信度外框 */
.product-selects.conf-low :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #d05a3c !important;
}
.product-selects.conf-medium :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #e09050 !important;
}

/* ── 产品匹配依据面板 ──────────────────────────────── */
.match-debug-section { margin-top: 4px; }

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
