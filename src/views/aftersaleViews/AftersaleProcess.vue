<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Setting } from '@element-plus/icons-vue'
import http from '@/api/http.js'
import { usePermission } from '@/composables/usePermission.js'
import AftersaleReasonLib from './AftersaleReasonLib.vue'
import AftersaleProductAlias from './AftersaleProductAlias.vue'

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
const loadingList = ref(false)   // 初次加载
const loadingMore = ref(false)   // 懒加载追加
const hasMore     = computed(() => orders.value.length < totalOrders.value)

// 懒加载哨兵元素
const sentinel    = ref(null)
let   observer    = null

// 当前工单
const currentOrder  = ref(null)
const autoMatches   = ref([])
const loadingMatch  = ref(false)
const saving        = ref(false)
const ignoring      = ref(false)

// 原因分配行（当前工单的编辑状态）
// [{reason_id, reason_name, custom_reason, involved_products: [], notes}]
const reasonRows    = ref([])

// 原因库弹窗
const showReasonLib   = ref(false)
// 物料简称弹窗
const showAliasLib    = ref(false)
// 物料简称列表
const productAliases  = ref([])   // [{id, alias, product_codes:[]}]

// 售后产品分配 ─ 品类树（el-cascader 数据源）
const categoryTree    = ref([])
const cascaderOpts    = computed(() => categoryTree.value.map(cat => ({
  value:    cat.id,
  label:    cat.name,
  children: (cat.series || []).map(s => ({
    value:    s.id,
    label:    s.name,
    children: (s.models || []).map(m => ({
      value: m.id,
      label: `${m.code} ${m.name}`,
    })),
  })),
})))

// 当前工单的三项分配（编辑态）
// selectedModelPaths: [[cat_id, series_id, model_id], ...] — cascader 多选值
const selectedModelPaths  = ref([])
const shippingMaterials   = ref([])   // string[] — 发货物料分配
const aftersaleMaterials  = ref([])   // [{code, name, quantity}] — 售后物料分配

// 售后物料新行输入
const amCodeInput     = ref('')
const amSuggestions   = ref([])
let   amSuggestTimer  = null
// 原因选项分组（从后端加载）
// [{category_id, category_name, reasons:[{id, name, ...}]}]
const reasonGroups  = ref([])
// 扁平化原因列表（用于 id→name 查找）
const reasonOptions = computed(() => reasonGroups.value.flatMap(g => g.reasons))

// ── 生命周期 ──────────────────────────────────────
onMounted(() => {
  loadOrders()
  loadReasonOptions()
  loadAliases()
  loadCategoryTree()
  initObserver()
})

onUnmounted(() => {
  observer?.disconnect()
})

// ── 方法 ──────────────────────────────────────────

// 初始化 IntersectionObserver，监听哨兵元素进入视口时追加加载
// 使用 watchEffect 确保 sentinel DOM 元素就绪后再开始观察
import { watchEffect } from 'vue'
function initObserver() {
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && hasMore.value && !loadingMore.value) {
        loadMore()
      }
    },
    { threshold: 0.1 }
  )
  // sentinel ref 在 onMounted 后已绑定
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
      // 自动选第一条
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

// 加载品类树（供售后产品分配 cascader 使用，缓存即可，不随订单变化）
async function loadCategoryTree() {
  const res = await http.get('/api/category/tree')
  if (res.success) categoryTree.value = res.data
}

// 加载物料简称
async function loadAliases() {
  const res = await http.get('/api/aftersale/product-aliases')
  if (res.success) productAliases.value = res.data
}

/**
 * 解析订单物料：将能匹配别名的产品组合并为别名，剩余产品单独显示。
 * 返回 [{type:'alias', alias, codes:[...]}, {type:'product', code, name, quantity}]
 * 按别名包含代码数量降序尝试（优先匹配更大的组），每个代码只归属一个别名。
 */
function resolveProducts(products) {
  if (!products?.length) return []
  const codeSet  = new Set(products.map(p => p.code))
  const usedCodes = new Set()
  const result    = []

  // 按品号数量从多到少排序，优先匹配更大的组
  const sortedAliases = [...productAliases.value].sort(
    (a, b) => b.product_codes.length - a.product_codes.length
  )
  for (const a of sortedAliases) {
    const codes = a.product_codes
    if (!codes.length) continue
    // 别名中的所有品号都在订单里，且没有被其他别名占用
    if (codes.every(c => codeSet.has(c) && !usedCodes.has(c))) {
      codes.forEach(c => usedCodes.add(c))
      result.push({ type: 'alias', alias: a.alias, codes })
    }
  }

  // 剩余未匹配的单品
  for (const p of products) {
    if (!usedCodes.has(p.code)) {
      result.push({ type: 'product', ...p })
    }
  }
  return result
}

/**
 * 当前工单的「涉及产品」选择项：
 * - 匹配到的别名（选后存 alias 名称）
 * - 未被别名覆盖的单品（选后存 product_code）
 */
const involvedOptions = computed(() => {
  if (!currentOrder.value) return []
  const resolved = resolveProducts(currentOrder.value.products)
  return resolved.map(item =>
    item.type === 'alias'
      ? { value: item.alias, label: `${item.alias}（${item.codes.join('、')}）`, isAlias: true }
      : { value: item.code, label: `${item.code} ${item.name}`, isAlias: false }
  )
})

// 加载原因选项（按分类分组）
async function loadReasonOptions() {
  const res = await http.get('/api/aftersale/reasons')
  if (res.success) {
    reasonGroups.value = res.data
  }
}

// 选中某个待处理订单
async function selectOrder(order) {
  currentOrder.value       = order
  reasonRows.value         = []
  autoMatches.value        = []
  selectedModelPaths.value = []
  shippingMaterials.value  = []
  aftersaleMaterials.value = []
  if (order?.seller_remark) {
    triggerAutoMatch(order.seller_remark)
  }
}

// 自动匹配
async function triggerAutoMatch(text) {
  if (!text) return
  loadingMatch.value = true
  try {
    const res = await http.post('/api/aftersale/auto-match', { text })
    if (res.success) autoMatches.value = res.data
  } finally {
    loadingMatch.value = false
  }
}

// 点击建议芯片：添加到 reasonRows
function applyMatch(match) {
  // 已存在则不重复添加
  if (reasonRows.value.some(r => r.reason_id === match.reason_id)) return
  reasonRows.value.push({
    reason_id:         match.reason_id,
    reason_name:       match.name,
    custom_reason:     '',
    involved_products: [],
    notes:             '',
  })
}

// 添加空白原因行
function addReasonRow() {
  reasonRows.value.push({
    reason_id:         null,
    reason_name:       '',
    custom_reason:     '',
    involved_products: [],
    notes:             '',
  })
}

// 删除原因行
function removeReasonRow(idx) {
  reasonRows.value.splice(idx, 1)
}

// 原因下拉选中
function onReasonSelect(idx, reasonId) {
  const opt = reasonOptions.value.find(r => r.id === reasonId)
  if (opt) {
    reasonRows.value[idx].reason_id   = opt.id
    reasonRows.value[idx].reason_name = opt.name
  }
}

// 确认保存当前工单
async function confirmCase() {
  if (!currentOrder.value) return
  if (reasonRows.value.length === 0) {
    ElMessage.warning('请至少添加一条售后原因')
    return
  }
  saving.value = true
  try {
    const reasons = reasonRows.value.map(r => ({
      reason_id:         r.reason_id || null,
      custom_reason:     r.custom_reason || '',
      involved_products: r.involved_products || [],
      notes:             r.notes || '',
    }))
    const res = await http.post('/api/aftersale/cases', {
      ecommerce_order_no:  currentOrder.value.ecommerce_order_no,
      products:            currentOrder.value.products,
      seller_remark:       currentOrder.value.seller_remark,
      buyer_remark:        currentOrder.value.buyer_remark,
      shipped_date:        currentOrder.value.shipped_date,
      operator:            currentOrder.value.operator,
      channel_name:        currentOrder.value.channel_name,
      province:            currentOrder.value.province,
      reasons,
      assigned_models:     buildAssignedModels(selectedModelPaths.value),
      shipping_materials:  shippingMaterials.value,
      aftersale_materials: aftersaleMaterials.value.filter(r => r.code.trim()),
    })
    if (res.success) {
      ElMessage.success('已确认')
      removeCurrentFromList()
      emit('case-confirmed')
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

// 忽略当前工单
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
    const res = await http.post(`/api/aftersale/cases/${encodeURIComponent(currentOrder.value.ecommerce_order_no)}/ignore`)
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
  currentOrder.value       = next
  reasonRows.value         = []
  autoMatches.value        = []
  selectedModelPaths.value = []
  shippingMaterials.value  = []
  aftersaleMaterials.value = []
  if (next?.seller_remark) triggerAutoMatch(next.seller_remark)
}

// 原因库更新后刷新选项
function onReasonLibUpdated() {
  loadReasonOptions()
}

// 物料简称更新后刷新
function onAliasUpdated() {
  loadAliases()
}

/**
 * 将 cascader 选中路径 [[cat_id, series_id, model_id], ...] 转为
 * [{model_id, model_code, model_name, series_name, category_name}]
 */
function buildAssignedModels(paths) {
  const result = []
  for (const [catId, seriesId, modelId] of paths) {
    const cat    = categoryTree.value.find(c => c.id === catId)
    const series = cat?.series?.find(s => s.id === seriesId)
    const model  = series?.models?.find(m => m.id === modelId)
    if (model) {
      result.push({
        model_id:      model.id,
        model_code:    model.model_code,
        model_name:    model.name,
        series_name:   series.name,
        category_name: cat.name,
      })
    }
  }
  return result
}

// ── 售后物料行操作 ──────────────────────────────────────────────────────────

function addAftersaleMaterial() {
  aftersaleMaterials.value.push({ code: '', name: '', quantity: 1 })
}

function removeAftersaleMaterial(idx) {
  aftersaleMaterials.value.splice(idx, 1)
}

// 品号输入防抖建议
function onAmCodeInput(val, idx) {
  clearTimeout(amSuggestTimer)
  if (!val?.trim()) { amSuggestions.value = []; return }
  amSuggestTimer = setTimeout(async () => {
    const res = await http.get('/api/aftersale/product-code-suggestions', { params: { q: val } })
    if (res.success) amSuggestions.value = res.data.map(s => ({ ...s, _idx: idx }))
  }, 300)
}

// 从建议中选中品号（自动填充品名）
function applyAmSuggestion(s) {
  const row = aftersaleMaterials.value[s._idx]
  if (row) { row.code = s.code; row.name = s.name || row.name }
  amSuggestions.value = []
}

// 置信度 bar 宽度
function confBar(conf) {
  return Math.round((conf || 0) * 100) + '%'
}

// 来源标签
function srcLabel(src) {
  return src === 'keyword' ? '关键词' : '历史'
}
</script>

<template>
  <div class="process-wrap">
    <!-- ── 左侧待处理队列 ─────────────────────── -->
    <aside class="order-queue">
      <!-- 队列头 -->
      <div class="queue-header">
        <div class="queue-title">
          待处理
          <span class="queue-count">{{ totalOrders }}</span>
        </div>
        <div class="header-btns">
          <el-tooltip content="物料简称" placement="top">
            <button class="btn-icon" title="管理物料简称" @click="showAliasLib = true">🏷️</button>
          </el-tooltip>
          <el-tooltip content="原因库" placement="top">
            <button class="btn-icon" title="管理原因库" @click="showReasonLib = true">
              <el-icon><Setting /></el-icon>
            </button>
          </el-tooltip>
        </div>
      </div>

      <!-- 订单卡片列表 -->
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

        <!-- 懒加载哨兵 + 加载提示 -->
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
            <span class="meta-item"><span class="meta-label">日期</span>{{ currentOrder.shipped_date || '—' }}</span>
            <span class="meta-item"><span class="meta-label">渠道</span>{{ currentOrder.channel_name || '—' }}</span>
            <span class="meta-item"><span class="meta-label">操作人</span>{{ currentOrder.operator || '—' }}</span>
            <span class="meta-item"><span class="meta-label">省份</span>{{ currentOrder.province || '—' }}</span>
          </div>
        </div>

        <!-- 工单内容（可滚动） -->
        <div class="case-body">
          <!-- 物料列表（别名合并显示） -->
          <section class="case-section">
            <div class="section-title">发货物料</div>
            <div class="products-grid">
              <!-- 匹配到别名的组 -->
              <div
                v-for="item in resolveProducts(currentOrder.products)"
                :key="item.type === 'alias' ? item.alias : item.code"
                class="product-chip"
                :class="{ 'product-chip--alias': item.type === 'alias' }"
                :title="item.type === 'alias' ? `包含：${item.codes.join('、')}` : `${item.code} ${item.name}`"
              >
                <template v-if="item.type === 'alias'">
                  <span class="p-alias-badge">简称</span>
                  <span class="p-alias-name">{{ item.alias }}</span>
                </template>
                <template v-else>
                  <span class="p-code">{{ item.code }}</span>
                  <span class="p-name">{{ item.name }}</span>
                  <span class="p-qty">×{{ item.quantity }}</span>
                </template>
              </div>
            </div>
          </section>

          <!-- 备注区 -->
          <section class="case-section remarks-section">
            <div class="remark-block">
              <div class="remark-label">商家备注（seller_remark）</div>
              <div class="remark-text">{{ currentOrder.seller_remark || '（无）' }}</div>
            </div>
            <div class="remark-block">
              <div class="remark-label">买家留言（buyer_remark）</div>
              <div class="remark-text">{{ currentOrder.buyer_remark || '（无）' }}</div>
            </div>
          </section>

          <!-- ── 售后产品分配 ────────────────────────── -->
          <section class="case-section">
            <div class="section-title">售后产品分配</div>
            <el-cascader
              v-model="selectedModelPaths"
              :options="cascaderOpts"
              :props="{ multiple: true, checkStrictly: false, emitPath: true }"
              placeholder="选择品类 / 系列 / 型号（可多选）"
              filterable
              clearable
              collapse-tags
              collapse-tags-tooltip
              style="width:100%"
            />
          </section>

          <!-- ── 发货物料分配 ────────────────────────── -->
          <section class="case-section">
            <div class="section-title">发货物料分配</div>
            <el-select
              v-model="shippingMaterials"
              multiple
              clearable
              collapse-tags
              collapse-tags-tooltip
              placeholder="选择本次售后涉及的发货物料（可选）"
              style="width:100%"
            >
              <el-option
                v-for="opt in involvedOptions"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              >
                <span v-if="opt.isAlias" class="opt-alias-badge">简称</span>
                <span>{{ opt.label }}</span>
              </el-option>
            </el-select>
          </section>

          <!-- ── 产生售后物料分配 ────────────────────── -->
          <section class="case-section">
            <div class="section-title">
              产生售后物料分配
              <button class="btn-add-reason" @click="addAftersaleMaterial">
                <el-icon><Plus /></el-icon> 添加物料
              </button>
            </div>

            <div v-if="aftersaleMaterials.length === 0" class="reason-empty">
              点击「添加物料」录入本次售后需处理的物料
            </div>

            <div
              v-for="(row, idx) in aftersaleMaterials"
              :key="idx"
              class="am-row"
            >
              <!-- 品号（带建议下拉） -->
              <div class="am-code-wrap">
                <el-input
                  v-model="row.code"
                  placeholder="品号"
                  size="small"
                  class="am-code"
                  @input="(v) => onAmCodeInput(v, idx)"
                />
                <!-- 品号建议列表 -->
                <div
                  v-if="amSuggestions.length && amSuggestions[0]._idx === idx"
                  class="am-suggestions"
                >
                  <div
                    v-for="s in amSuggestions"
                    :key="s.code"
                    class="am-sug-item"
                    @click="applyAmSuggestion(s)"
                  >
                    <span class="sug-code">{{ s.code }}</span>
                    <span class="sug-name">{{ s.name }}</span>
                  </div>
                </div>
              </div>
              <el-input v-model="row.name"     placeholder="品名" size="small" class="am-name" />
              <el-input-number
                v-model="row.quantity"
                :min="1" :step="1"
                size="small"
                controls-position="right"
                class="am-qty"
              />
              <button class="btn-del-reason" title="删除此行" @click="removeAftersaleMaterial(idx)">
                <el-icon><Delete /></el-icon>
              </button>
            </div>
          </section>

          <!-- 自动匹配建议 -->
          <section v-if="autoMatches.length > 0 || loadingMatch" class="case-section">
            <div class="section-title">
              自动匹配建议
              <span v-if="loadingMatch" class="matching-hint">匹配中…</span>
            </div>
            <div class="match-chips">
              <div
                v-for="m in autoMatches"
                :key="m.reason_id"
                class="match-chip"
                :class="{ applied: reasonRows.some(r => r.reason_id === m.reason_id) }"
                :title="`来源：${srcLabel(m.source)}，置信度 ${Math.round(m.confidence * 100)}%`"
                @click="applyMatch(m)"
              >
                <span class="chip-name">{{ m.name }}</span>
                <span class="chip-src">{{ srcLabel(m.source) }}</span>
                <span class="chip-bar-wrap">
                  <span class="chip-bar" :style="{ width: confBar(m.confidence) }"></span>
                </span>
              </div>
            </div>
          </section>

          <!-- 原因分配区 -->
          <section class="case-section">
            <div class="section-title">
              售后原因分配
              <button v-if="canEditAftersale" class="btn-add-reason" @click="addReasonRow">
                <el-icon><Plus /></el-icon> 添加原因
              </button>
            </div>

            <div v-if="reasonRows.length === 0" class="reason-empty">
              点击「添加原因」或直接点击上方匹配建议
            </div>

            <div v-for="(row, idx) in reasonRows" :key="idx" class="reason-row">
              <!-- 原因选择 -->
              <div class="reason-row-top">
                <el-select
                  v-model="row.reason_id"
                  placeholder="选择原因"
                  clearable
                  filterable
                  class="reason-select"
                  @change="(val) => onReasonSelect(idx, val)"
                >
                  <el-option-group
                    v-for="group in reasonGroups"
                    :key="group.category_id"
                    :label="group.category_name"
                  >
                    <el-option
                      v-for="opt in group.reasons"
                      :key="opt.id"
                      :value="opt.id"
                      :label="opt.name"
                    />
                  </el-option-group>
                </el-select>
                <span class="or-text">或</span>
                <el-input
                  v-model="row.custom_reason"
                  placeholder="自定义原因（不选库中原因时填写）"
                  class="custom-reason-input"
                />
                <button class="btn-del-reason" title="删除此行" @click="removeReasonRow(idx)">
                  <el-icon><Delete /></el-icon>
                </button>
              </div>

              <!-- 涉及产品多选（别名+单品） -->
              <div class="reason-row-bottom">
                <span class="sub-label">涉及产品</span>
                <el-select
                  v-model="row.involved_products"
                  multiple
                  clearable
                  placeholder="选择涉及的产品/简称（可选）"
                  class="products-select"
                >
                  <el-option
                    v-for="opt in involvedOptions"
                    :key="opt.value"
                    :value="opt.value"
                    :label="opt.label"
                  >
                    <span v-if="opt.isAlias" class="opt-alias-badge">简称</span>
                    <span>{{ opt.label }}</span>
                  </el-option>
                </el-select>
                <span class="sub-label" style="margin-left:12px">备注</span>
                <el-input
                  v-model="row.notes"
                  placeholder="可选备注"
                  class="notes-input"
                />
              </div>
            </div>
          </section>
        </div><!-- /case-body -->

        <!-- 底部操作栏 -->
        <div class="case-footer" v-if="canEditAftersale">
          <el-button
            :loading="ignoring"
            @click="ignoreCase"
          >忽略</el-button>
          <el-button
            type="primary"
            :loading="saving"
            @click="confirmCase"
          >确认</el-button>
        </div>
      </template>
    </div><!-- /work-area -->

    <!-- 原因库管理弹窗 -->
    <AftersaleReasonLib
      v-model="showReasonLib"
      @updated="onReasonLibUpdated"
    />

    <!-- 物料简称管理弹窗 -->
    <AftersaleProductAlias
      v-model="showAliasLib"
      @updated="onAliasUpdated"
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
  padding: 10px 10px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s;
  margin-bottom: 4px;
}
.order-card:hover {
  background: var(--bg);
  border-color: var(--border);
}
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
.order-meta {
  font-size: 11px; color: var(--text-muted);
  display: flex; gap: 4px;
}
.sep { color: var(--border); }

.queue-empty {
  text-align: center; padding: 40px 0;
  font-size: 13px; color: var(--text-muted);
}

.load-sentinel {
  height: 32px; display: flex;
  align-items: center; justify-content: center;
}
.load-more-hint {
  font-size: 11px; color: var(--text-muted);
}

/* ── 右侧工作区 ────────────────────────────────── */
.work-area {
  flex: 1; display: flex; flex-direction: column;
  overflow: hidden;
}

.work-empty {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px; color: var(--text-muted); font-size: 14px;
}
.work-empty-icon {
  font-size: 36px; color: #6ab47a;
}

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
.case-meta-row {
  display: flex; gap: 20px; flex-wrap: wrap;
}
.meta-item {
  font-size: 12px; color: var(--text-secondary);
}
.meta-label {
  font-size: 11px; color: var(--text-muted);
  margin-right: 4px;
}

/* 工单内容（可滚动） */
.case-body {
  flex: 1; overflow-y: auto; padding: 16px 20px;
}
.case-body::-webkit-scrollbar { width: 4px; }
.case-body::-webkit-scrollbar-track { background: transparent; }
.case-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.case-section {
  margin-bottom: 20px;
}
.section-title {
  font-size: 12px; font-weight: 600; color: var(--text-secondary);
  letter-spacing: 0.05em; margin-bottom: 10px;
  display: flex; align-items: center; gap: 10px;
}
.matching-hint {
  font-size: 11px; font-weight: 400; color: var(--text-muted);
}

/* 物料 */
.products-grid {
  display: flex; flex-wrap: wrap; gap: 6px;
}
.product-chip {
  padding: 4px 10px;
  background: #f5f0e8; border: 1px solid var(--border);
  border-radius: 6px; font-size: 12px;
  display: flex; align-items: center; gap: 6px;
}
.p-code { font-weight: 600; color: var(--text-primary); }
.p-name { color: var(--text-secondary); }
.p-qty  { color: var(--accent); font-weight: 600; }

/* 别名芯片样式 */
.product-chip--alias {
  background: #fff7ed; border-color: var(--accent);
}
.p-alias-badge {
  font-size: 9px; padding: 1px 4px;
  background: var(--accent); color: #fff;
  border-radius: 3px; flex-shrink: 0;
}
.p-alias-name { font-weight: 600; color: var(--accent); }

.opt-alias-badge {
  font-size: 10px; padding: 1px 4px;
  background: var(--accent); color: #fff;
  border-radius: 3px; margin-right: 6px;
}

/* 备注 */
.remarks-section {
  display: flex; gap: 16px;
}
.remark-block {
  flex: 1;
  background: #faf7f2; border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 12px;
}
.remark-label {
  font-size: 11px; color: var(--text-muted); margin-bottom: 6px;
}
.remark-text {
  font-size: 12px; color: var(--text-primary);
  line-height: 1.6; white-space: pre-wrap;
  max-height: 80px; overflow-y: auto;
}
.remark-text::-webkit-scrollbar { width: 3px; }
.remark-text::-webkit-scrollbar-thumb { background: var(--border); }

/* 自动匹配芯片 */
.match-chips {
  display: flex; flex-wrap: wrap; gap: 8px;
}
.match-chip {
  padding: 6px 12px;
  background: #fff; border: 1px solid var(--border);
  border-radius: 20px; cursor: pointer;
  display: flex; align-items: center; gap: 8px;
  transition: all 0.15s; font-size: 12px;
}
.match-chip:hover {
  border-color: var(--accent); background: #fff7ed;
}
.match-chip.applied {
  border-color: var(--accent); background: #fff7ed;
  opacity: 0.6;
}
.chip-name  { font-weight: 600; color: var(--text-primary); }
.chip-src   {
  font-size: 10px; color: #fff;
  background: var(--text-muted); border-radius: 3px;
  padding: 1px 4px;
}
.chip-bar-wrap {
  width: 40px; height: 4px;
  background: var(--border); border-radius: 2px; overflow: hidden;
}
.chip-bar {
  display: block; height: 100%;
  background: var(--accent); border-radius: 2px;
  transition: width 0.3s;
}

/* 原因分配 */
.btn-add-reason {
  padding: 3px 10px;
  border: 1px dashed var(--accent); border-radius: 6px;
  background: transparent; color: var(--accent);
  font-size: 12px; cursor: pointer;
  display: flex; align-items: center; gap: 4px;
  transition: all 0.15s;
}
.btn-add-reason:hover { background: #fff7ed; }

.reason-empty {
  font-size: 12px; color: var(--text-muted);
  padding: 12px 0;
}

.reason-row {
  background: #faf7f2; border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 12px;
  margin-bottom: 10px;
}
.reason-row-top {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 8px;
}
.reason-select  { width: 180px; }
.or-text { font-size: 12px; color: var(--text-muted); flex-shrink: 0; }
.custom-reason-input { flex: 1; }

.btn-del-reason {
  width: 26px; height: 26px; flex-shrink: 0;
  border: 1px solid #f0c0c0; border-radius: 6px;
  background: transparent; color: #d05a3c;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.btn-del-reason:hover { background: #fff0ee; }

.reason-row-bottom {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.sub-label { font-size: 11px; color: var(--text-muted); flex-shrink: 0; }
.products-select { width: 240px; }
.notes-input { flex: 1; }

.opt-category {
  font-size: 10px; color: var(--text-muted);
  margin-right: 6px; background: #f5f0e8;
  padding: 1px 4px; border-radius: 3px;
}

/* 底部操作栏 */
.case-footer {
  padding: 12px 20px;
  border-top: 1px solid var(--border);
  background: rgba(255,255,255,0.7);
  display: flex; justify-content: flex-end; gap: 10px;
  flex-shrink: 0;
}

/* 产生售后物料分配 */
.am-row {
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 6px;
}
.am-code-wrap {
  position: relative; width: 140px; flex-shrink: 0;
}
.am-code { width: 100%; }
.am-name { flex: 1; min-width: 0; }
.am-qty  { width: 100px; flex-shrink: 0; }

.am-suggestions {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 20;
  background: #fff; border: 1px solid var(--border);
  border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  max-height: 150px; overflow-y: auto; margin-top: 2px;
}
.am-sug-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; cursor: pointer; transition: background 0.12s;
}
.am-sug-item:hover { background: #faf7f2; }
.am-sug-item .sug-code {
  font-family: monospace; font-size: 12px;
  font-weight: 600; color: var(--text-primary); flex-shrink: 0;
}
.am-sug-item .sug-name {
  font-size: 11px; color: var(--text-muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
</style>
