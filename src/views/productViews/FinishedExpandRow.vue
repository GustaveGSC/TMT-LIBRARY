<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, reactive, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import http from '@/api/http'
import { usePermission } from '@/composables/usePermission'
import { ZoomIn, EditPen, Plus, Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFinishedStore } from '@/stores/product/finished'
import { usePackagedStore } from '@/stores/product/packaged'
import GEditTagList from '@/components/common/GEditTagList.vue'
import modelTipImg from '@/assets/images/image_model_tip.png'
import { useFinishedImage } from '@/composables/useFinishedImage'
import { useFinishedParams, GROUP_DEFS } from '@/composables/useFinishedParams'

// ── Props ─────────────────────────────────────────
const props = defineProps({
  row:     { type: Object,   required: true },
  plain:   { type: Boolean,  default: false  }, // true 时去掉外层容器样式（用于 dialog）
  onClose: { type: Function, default: null   }, // plain 模式下关闭回调
})

// ── Emits ─────────────────────────────────────────
const emit = defineEmits(['saved'])

// ── 权限 ──────────────────────────────────────────
const { canEditProduct, canViewShipping } = usePermission()

// ── 响应式状态 ────────────────────────────────────
const editing      = ref(false)
const saving       = ref(false)
const initializing = ref(false)  // startEdit 初始化期间，跳过联动 watch
const moreMenuVisible = ref(false)  // ··· 更多菜单开关

// ── 图片 / 裁剪（see useFinishedImage）────────────
const {
  imgHover, imgPreview, addMenuVisible,
  localCoverImage, savedCoverImage,
  cropDialogVisible, cropImgSrc, cropImgRef, cropSquare,
  initCropper, applyCrop, closeCropDialog,
  previewImage, editImage, addImageFromUpload, addImageFromExisting, deleteImage,
} = useFinishedImage(props)
const editForm = reactive({
  name: '', name_en: '', status: '',
  listed_yymm: '', delisted_yymm: '',
  market: '',
  market_domestic: false,
  market_foreign:  false,
  category_name:  '',
  series_code:    '',
  series_name:    '',
  model_code:     '',
  packaged_tags: [],    // 产成品清单（{value: code, state: 'original'|'added'|'deleted'} 数组）
  // state 语义：original=编辑开始时已在清单里，added=本次新增，deleted=标记删除
  tag_names:      [],   // 标签名称数组
})

// 编辑开始时的原始产成品 codes（用于 saveEdit 做对比，不依赖 state）
const originalPackagedCodes = ref(new Set())
// 编辑开始时已关联的标签名集合（用于区分新增 vs 原有）
const originalTagNames = ref(new Set())

// ── 折叠分组 ──────────────────────────────────────
const openSec = reactive({})
function isSec(key) { return !!openSec[key] }

// ── 发货数据图表 ──────────────────────────────────
const shippingChartEl      = ref(null)   // DOM 节点
const shippingChartLoading = ref(false)
const shippingLoaded       = ref(false)
const shippingMonthly      = ref([])     // [{ month, shipped, returned, actual }]
let   shippingChartInst    = null

async function loadShippingMonthly() {
  if (!canViewShipping || shippingLoaded.value) return
  shippingChartLoading.value = true
  try {
    const res = await http.get(`/api/shipping/product/${props.row.code}/monthly`)
    if (res.success) {
      shippingMonthly.value      = res.data || []
      shippingLoaded.value       = true
      shippingChartLoading.value = false  // 先关 loading，让 chart div 渲染出来
      await nextTick()                    // 等 DOM 更新
      initShippingChart()
    }
  } finally {
    shippingChartLoading.value = false
  }
}

function initShippingChart() {
  if (!shippingChartEl.value) return
  if (!shippingChartInst) {
    shippingChartInst = echarts.init(shippingChartEl.value, null, { renderer: 'canvas' })
  }
  const data   = shippingMonthly.value
  const months = data.map(d => d.month)
  const actual = data.map(d => d.actual)

  shippingChartInst.setOption({
    grid:    { top: 12, right: 12, bottom: 40, left: 44, containLabel: false },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter(params) {
        const p = params[0]
        return `<div style="font-size:12px;color:#3a3028">${p.axisValue}</div>
                <div style="font-size:12px;margin-top:2px">净发货：<b>${p.value}</b></div>`
      },
    },
    xAxis: {
      type: 'category',
      data: months,
      axisLabel: { fontSize: 10, color: '#8a7a6a', rotate: months.length > 18 ? 45 : 0 },
      axisLine:  { lineStyle: { color: '#e0d4c0' } },
      axisTick:  { show: false },
    },
    yAxis: {
      type:        'value',
      minInterval: 1,
      axisLabel:   { fontSize: 10, color: '#8a7a6a' },
      splitLine:   { lineStyle: { color: '#f0ebe0' } },
    },
    series: [{
      type: 'bar',
      data: actual,
      barMaxWidth: 18,
      itemStyle: { color: '#c4883a', borderRadius: [3, 3, 0, 0] },
    }],
  }, true)
}

onBeforeUnmount(() => {
  shippingChartInst?.dispose()
  shippingChartInst = null
})

// ── 生命周期 badge（始终显示）────────────────────
function lc(row) {
  if (row.listed_yymm && row.delisted_yymm) return { label: '已退市', cls: 'lc-out' }
  if (row.listed_yymm)                       return { label: '上市中',  cls: 'lc-on'  }
  return { label: '未知状态', cls: 'lc-unknown' }
}

// ── 编辑 ──────────────────────────────────────────

// ── 复制 / 粘贴 ───────────────────────────────

// 复制当前卡片参数到系统剪切板（仅查看模式可用）
async function copyCard() {
  moreMenuVisible.value = false
  const d = props.row
  const payload = {
    __type:        'tmt-finished-card',
    name:          (d.status === 'recorded' && d.model_name) ? d.model_name : (d.name || ''),
    name_en:       d.name_en       || '',
    market:        d.market        || '',
    category_name: d.category_name || '',
    series_code:   d.series_code   || '',
    series_name:   d.series_name   || '',
    model_code:    d.model_code    || '',
    listed_yymm:   d.listed_yymm   || '',
    delisted_yymm: d.delisted_yymm || '',
    status:        d.status        || 'unrecorded',
    packaged_codes: (d.packaged_list || []).map(p => p?.code ?? p),
    tag_names:     (d.tags || []).map(t => t.name),
    cover_image:   localCoverImage.value || d.cover_image || '',
    params:        paramsData.value,
  }
  try {
    await navigator.clipboard.writeText(JSON.stringify(payload))
    ElMessage.success('已复制卡片参数')
  } catch {
    ElMessage.error('复制失败，请检查权限')
  }
}

// 将剪切板参数粘贴到编辑表单（仅编辑模式可用）
async function pasteCard() {
  moreMenuVisible.value = false
  try {
    const text = await navigator.clipboard.readText()
    const payload = JSON.parse(text)
    if (payload.__type !== 'tmt-finished-card') {
      ElMessage.warning('剪切板内容格式不匹配')
      return
    }
    // 确保候选数据已加载
    await Promise.all([ensurePackagedOptionsLoaded(), ensureTagOptionsLoaded()])
    initializing.value = true
    Object.assign(editForm, {
      name:            payload.name          || '',
      name_en:         payload.name_en       || '',
      status:          payload.status        || 'unrecorded',
      listed_yymm:     payload.listed_yymm   || '',
      delisted_yymm:   payload.delisted_yymm || '',
      market:          payload.market        || '',
      market_domestic: payload.market === 'domestic' || payload.market === 'both',
      market_foreign:  payload.market === 'foreign'  || payload.market === 'both',
      category_name:   payload.category_name || '',
      series_code:     payload.series_code   || '',
      series_name:     payload.series_name   || '',
      model_code:      payload.model_code    || '',
      packaged_tags:   (payload.packaged_codes || []).map(code => ({
        value: code,
        state: originalPackagedCodes.value.has(code) ? 'original' : 'added',
      })),
    })
    // 粘贴封面图片（OSS URL 或清空）
    localCoverImage.value = payload.cover_image || ''
    await nextTick()
    initializing.value = false
    editForm.tag_names = payload.tag_names || []
    // 粘贴参数（按 key_id 匹配当前键名库）
    if (payload.params) {
      GROUP_DEFS.forEach(g => {
        const items = payload.params[g.key] || []
        const validKeys = new Set((paramKeys.value[g.key] || []).map(k => k.id))
        editParams[g.key] = items
          .filter(p => validKeys.has(p.key_id))
          .map(p => ({ key_id: p.key_id, key_name: p.key_name, value: p.value }))
      })
    }
    ElMessage.success('已粘贴卡片参数')
  } catch (e) {
    if (e instanceof SyntaxError) {
      ElMessage.warning('剪切板内容不是有效的卡片数据')
    } else {
      ElMessage.error('粘贴失败')
    }
  }
}

async function markIgnored() {
  try {
    await ElMessageBox.confirm(
      `确认将「${props.row.code}」标记为无需录入？`,
      '无需录入',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }
  saving.value = true
  try {
    const res = await http.post('/api/product/finished', { code: props.row.code, status: 'ignored' })
    if (res.success) {
      emit('saved')
    } else {
      ElMessage.error(res.message || '操作失败')
    }
  } finally {
    saving.value = false
  }
}

async function startEdit() {
  moreMenuVisible.value = false
  const d = props.row
  const domestic = d.market === 'domestic' || d.market === 'both'
  const foreign  = d.market === 'foreign'  || d.market === 'both'
  // 先加载候选库，再判断每个 code 的初始状态
  await Promise.all([
    ensurePackagedOptionsLoaded(),
    ensureTagOptionsLoaded(),
    ensureParamKeysLoaded(),
    loadParams(d.id),
  ])
  const initialCodes = (d.packaged_list || []).map(p => p?.code ?? p)
  originalPackagedCodes.value = new Set(initialCodes)
  originalTagNames.value = new Set((d.tags || []).map(t => t.name))
  // 初始化期间暂停联动 watch，避免 series/model 字段被清空
  initializing.value = true
  const initialTagNames = (d.tags || []).map(t => t.name)
  Object.assign(editForm, {
    name:            d.model_name    || d.name || '',
    name_en:         d.name_en       || '',
    status:          d.status        || 'unrecorded',
    listed_yymm:     d.listed_yymm   || '',
    delisted_yymm:   d.delisted_yymm || '',
    market:          d.market        || '',
    market_domestic: domestic,
    market_foreign:  foreign,
    category_name:   d.category_name || '',
    series_code:     d.series_code   || '',
    series_name:     d.series_name   || '',
    model_code:      d.model_code    || '',
    packaged_tags: initialCodes.map(code => ({
      value: code,
      state: 'original',
    })),
    tag_names: [],   // 先置空，等 el-select 挂载完再赋值
  })
  savedCoverImage.value = localCoverImage.value
  // 初始化参数编辑态并保留快照
  syncEditParamsFromData()
  originalParamsSnapshot.value = JSON.stringify(paramsData.value)
  paramsEditing.value = true
  editing.value = true
  await nextTick()       // 等待 el-select 挂载 + watch 队列执行完毕
  initializing.value = false
  // el-select 挂载后再赋值，确保其内部 options 已注册，能正确识别已有标签
  editForm.tag_names = initialTagNames
  // 若参数区已展开，初始化拖拽
  if (isSec('params')) initSortables()
}
function cancelEdit() {
  moreMenuVisible.value = false
  localCoverImage.value = savedCoverImage.value
  // 从快照恢复参数编辑态
  if (originalParamsSnapshot.value) {
    paramsData.value = JSON.parse(originalParamsSnapshot.value)
    syncEditParamsFromData()
  }
  paramsEditing.value = false
  editing.value = false
}

// market checkbox → market 字段
function resolveMarket() {
  const d = editForm.market_domestic
  const f = editForm.market_foreign
  if (d && f)  return 'both'
  if (d)       return 'domestic'
  if (f)       return 'foreign'
  return ''
}

async function saveEdit() {
  saving.value = true
  try {
    // ── 图片处理：上传新图 / 清除旧图 ──────────────
    let coverImageValue = undefined   // undefined = 不变，null = 清除，string = 新 OSS URL
    if (localCoverImage.value.startsWith('data:')) {
      // 有新裁剪图（base64）→ 上传到 OSS
      const uploadRes = await http.post('/api/product/finished/cover-image', {
        code:     props.row.code,
        data_url: localCoverImage.value,
      })
      if (uploadRes.success) {
        coverImageValue = uploadRes.data.url
        localCoverImage.value = coverImageValue   // 本地替换为 OSS URL，避免重复上传
      } else {
        ElMessage.error(uploadRes.message || '图片上传失败')
        return
      }
    } else if (localCoverImage.value === '' && savedCoverImage.value !== '') {
      // 图片被删除
      coverImageValue = null
    } else if (localCoverImage.value && localCoverImage.value !== (props.row.cover_image || '')) {
      // 粘贴了来自其他卡片的 OSS URL，直接使用
      coverImageValue = localCoverImage.value
    }

    const body = {
      code:          props.row.code,
      name:          editForm.name,
      name_en:       editForm.name_en,
      status:        editForm.status,
      listed_yymm:   editForm.listed_yymm  || null,
      delisted_yymm: editForm.delisted_yymm || null,
      market:        resolveMarket(),
      category_name: editForm.category_name || null,
      series_code:   editForm.series_code   || null,
      series_name:   editForm.series_name   || null,
      model_code:    editForm.model_code    || null,
    }
    // 仅当图片有变化时才携带 cover_image 字段
    if (coverImageValue !== undefined) body.cover_image = coverImageValue

    const res = await http.post('/api/product/finished', body)
    if (!res.success) {
      ElMessage.error(res.message || '保存失败，请重试')
      return
    }
    if (res.success) {
      // 新记录用返回的 id，已有记录用 props.row.id
      const finishedId = res.data?.id ?? props.row.id

      // ── 产成品清单同步（与原始 codes 对比增删）──
      const activeCodes = new Set(editForm.packaged_tags.filter(t => t.state !== 'deleted').map(t => t.value))
      const toRemove = [...originalPackagedCodes.value].filter(c => !activeCodes.has(c))
      const toAdd    = [...activeCodes].filter(c => !originalPackagedCodes.value.has(c))
      for (const code of toRemove) {
        const pid = packagedStore.map[code]?.id
        if (pid) await http.delete(`/api/product/finished/${finishedId}/packaged/${pid}`)
      }
      for (const code of toAdd) {
        const pid = packagedStore.map[code]?.id
        if (pid) await http.post(`/api/product/finished/${finishedId}/packaged/${pid}`)
      }

      // ── 标签同步（与原始 tag 名称对比增删）──
      const activeTagNames = editForm.tag_names.filter(n => n)
      const toRemoveTags   = [...originalTagNames.value].filter(n => !activeTagNames.includes(n))
      const toAddTags      = activeTagNames.filter(n => !originalTagNames.value.has(n))
      for (const name of toAddTags) {
        // 若 tag 不在选项库中，先创建
        let tag = tagOptions.value.find(t => t.name === name)
        if (!tag) {
          const createRes = await http.post('/api/product/tags/', { name, color: '#c4883a' })
          if (createRes.success) {
            tag = createRes.data
            tagOptions.value.push(tag)   // 更新本地缓存
          }
        }
        if (tag?.id) await http.post(`/api/product/tags/finished/${finishedId}/${tag.id}`)
      }
      for (const name of toRemoveTags) {
        const tag = tagOptions.value.find(t => t.name === name)
        if (tag?.id) await http.delete(`/api/product/tags/finished/${finishedId}/${tag.id}`)
      }

      // ── 参数保存（委托给 useFinishedParams）─────────
      await saveParamsFor(finishedId)

      moreMenuVisible.value = false
      paramsEditing.value = false
      editing.value = false
      ElMessage.success('保存完成')
      emit('saved')
    }
  } finally {
    saving.value = false
  }
}

// ── Autocomplete 候选 ─────────────────────────────
const finishedStore  = useFinishedStore()
const packagedStore  = usePackagedStore()

// 中文名称：使用与表格显示一致的 effective name
// （recorded 且有 model_name → 用 model_name，否则用 import 的 name）
function suggestName(query, cb) {
  const q = (query || '').trim().toLowerCase()
  const seen = new Set()
  const result = []
  for (const row of finishedStore.rawItems) {
    const effective = (row.status === 'recorded' && row.model_name) ? row.model_name : (row.name || '')
    if (!effective) continue
    const lower = effective.toLowerCase()
    if (q && !lower.includes(q)) continue
    if (seen.has(lower)) continue
    seen.add(lower)
    result.push({ value: effective })
    if (result.length >= 20) break
  }
  cb(result)
}
// 英文名称：从 rawItems 本地匹配
function suggestNameEn(query, cb) {
  const list = query
    ? finishedStore.getSuggestions('name_en', query)
    : finishedStore.getTopSuggestions('name_en')
  cb(list.map(v => ({ value: v })))
}

// ── 产成品候选选项（懒加载）──────────────────────
const packagedOptions = ref([])   // [{code, name}]
const packagedLoaded  = ref(false)
async function ensurePackagedOptionsLoaded() {
  if (packagedLoaded.value) return
  try {
    const res = await http.get('/api/product/packaged/candidates/all')
    if (res.success) { packagedOptions.value = res.data || []; packagedLoaded.value = true }
  } catch {}
}

// ── 标签选项（懒加载）────────────────────────────
const tagOptions = ref([])   // [{id, name, color}]
const tagsLoaded = ref(false)
async function ensureTagOptionsLoaded() {
  if (tagsLoaded.value) return
  try {
    const res = await http.get('/api/product/tags/')
    if (res.success) { tagOptions.value = res.data || []; tagsLoaded.value = true }
  } catch {}
}

// 判断标签名是否在 finished 原有关联里（不在则为本次新增）
function isExistingTag(name) {
  return originalTagNames.value.has(name)
}

// ── 编辑模式：根据产成品清单实时计算体积/毛重/净重 ──────────
function sumPackaged(field) {
  const active = editForm.packaged_tags.filter(t => t.state !== 'deleted')
  const total = active.reduce((acc, t) => {
    const val = packagedStore.map[t.value]?.[field]
    return acc + (val != null ? Number(val) : 0)
  }, 0)
  return total > 0 ? parseFloat(total.toFixed(3)) : null
}
const editVolume      = computed(() => sumPackaged('volume'))
const editGrossWeight = computed(() => sumPackaged('gross_weight'))
const editNetWeight   = computed(() => sumPackaged('net_weight'))

// ── 分类树（编辑时懒加载）────────────────────────
const categoryTree = ref([])
const treeLoaded   = ref(false)
async function ensureTreeLoaded() {
  if (treeLoaded.value) return
  try {
    const res = await http.get('/api/category/tree')
    if (res.success) { categoryTree.value = res.data || []; treeLoaded.value = true }
  } catch {}
}

// 当前选中的品类/系列对象（用于过滤下级候选）
const selectedCategoryObj = computed(() =>
  categoryTree.value.find(c => c.name === editForm.category_name) ?? null
)
const selectedSeriesObj = computed(() =>
  (selectedCategoryObj.value?.series || []).find(s => s.code === editForm.series_code) ?? null
)

// 字段是否禁用
const seriesDisabled     = computed(() => !editForm.category_name)
const seriesNameReadonly = computed(() => !!selectedSeriesObj.value)
const modelDisabled      = computed(() => !editForm.series_code)

// 品类变化 → 清空下级（初始化期间跳过）
watch(() => editForm.category_name, () => {
  if (initializing.value) return
  editForm.series_code = ''
  editForm.series_name = ''
  editForm.model_code  = ''
})

// 系列编码变化 → 自动填充系列名称 / 清空型号（初始化期间跳过）
watch(() => editForm.series_code, (code) => {
  if (initializing.value) return
  editForm.model_code = ''
  if (!code) {
    editForm.series_name = ''
  } else {
    const match = (selectedCategoryObj.value?.series || []).find(s => s.code === code)
    if (match) editForm.series_name = match.name
  }
})

// 品类候选
async function suggestCategory(query, cb) {
  await ensureTreeLoaded()
  const list = categoryTree.value.filter(c => !query || c.name.includes(query))
  cb(list.map(c => ({ value: c.name })))
}

// 系列编码候选（限当前品类下，若品类不在树中则显示全部）
async function suggestSeriesCode(query, cb) {
  await ensureTreeLoaded()
  const series = selectedCategoryObj.value
    ? (selectedCategoryObj.value.series || [])
    : categoryTree.value.flatMap(c => c.series || [])
  cb(series.filter(s => !query || s.code.includes(query)).map(s => ({ value: s.code })))
}

// 系列名称候选（同上）
async function suggestSeriesName(query, cb) {
  await ensureTreeLoaded()
  const series = selectedCategoryObj.value
    ? (selectedCategoryObj.value.series || [])
    : categoryTree.value.flatMap(c => c.series || [])
  cb(series.filter(s => !query || s.name.includes(query)).map(s => ({ value: s.name })))
}

// 型号简码候选（限当前系列下，若系列不在树中则显示全部）
async function suggestModelCode(query, cb) {
  await ensureTreeLoaded()
  const models = selectedSeriesObj.value
    ? (selectedSeriesObj.value.models || [])
    : categoryTree.value.flatMap(c => (c.series || []).flatMap(s => s.models || []))
  cb(models.filter(m => !query || (m.model_code || '').includes(query)).map(m => ({ value: m.model_code })))
}

// ── 表单校验 ──────────────────────────────────────
const validations = computed(() => {
  if (!editing.value) return {}
  const errs = {}
  const code = props.row.code

  // 中文名称：必填（model_name 无需唯一性约束）
  const name = editForm.name.trim()
  if (!name) {
    errs.name = '中文名称不能为空'
  }

  // 英文名称：外贸时必填；有值时唯一
  const nameEn = editForm.name_en.trim()
  if (editForm.market_foreign && !nameEn) {
    errs.name_en = '勾选外贸时英文名称不能为空'
  } else if (nameEn && finishedStore.rawItems.some(r => r.code !== code && r.name_en === nameEn)) {
    errs.name_en = '与其他成品英文名称重复'
  }

  // 品类编码：必填
  if (!editForm.category_name.trim()) errs.category_name = '品类编码不能为空'

  // 系列编码：必填
  if (!editForm.series_code.trim()) errs.series_code = '系列编码不能为空'

  // 系列名称：必填
  if (!editForm.series_name.trim()) errs.series_name = '系列名称不能为空'

  // 型号简码：必填 + 唯一
  const mc = editForm.model_code.trim()
  if (!mc) {
    errs.model_code = '型号简码不能为空'
  } else if (finishedStore.rawItems.some(r => r.code !== code && r.model_code === mc)) {
    errs.model_code = '与其他成品型号简码重复'
  }

  // 产成品清单：非空 + 无 not-in-library
  const active = editForm.packaged_tags.filter(t => t.state !== 'deleted')
  if (active.length === 0) {
    errs.packaged_tags = '产成品清单不能为空'
  } else if (active.some(t => !packagedStore.map[t.value])) {
    errs.packaged_tags = '清单中存在未入库的产成品，请移除后再提交'
  }

  return errs
})
const formValid = computed(() => Object.keys(validations.value).length === 0)

// ── 参数（see useFinishedParams）─────────────────
const {
  paramsData, paramsLoaded, editParams, originalParamsSnapshot,
  paramsEditing, paramsSaving, paramKeys,
  paramAddDialog, sortableRefs,
  openParamAdd, ensureParamKeysLoaded, availableKeyOptions,
  addParamItem, removeParamItem, restoreParamItem,
  loadParams, syncEditParamsFromData, initSortables,
  startParamsEdit, cancelParamsEdit,
  saveParamsFor, saveParamsOnly,
} = useFinishedParams(props)

// ── 折叠分组（params 区首次展开时懒加载）─────────
function toggleSec(key) {
  openSec[key] = !openSec[key]
  if (key === 'params' && openSec[key] && !paramsLoaded.value && props.row.id) {
    loadParams(props.row.id)
  }
  if (key === 'data' && openSec[key]) {
    loadShippingMonthly()
  }
}
</script>

<template>
  <div :class="['ec', { 'ec--plain': props.plain }]">

    <!-- ── 大卡片：顶栏 + 图片信息 + 折叠分组 ── -->
    <div class="ec-main">

      <!-- 顶栏：编码 + 生命周期badge + 操作按钮 -->
      <div class="ec-top">
        <span class="ec-code">{{ row.code }}</span>
        <span class="lc-badge" :class="lc(row).cls">{{ lc(row).label }}</span>
        <div class="ec-acts">
          <!-- plain 模式：关闭按钮 -->
          <button v-if="props.plain && props.onClose" class="eb eb-close" title="关闭" @click.stop="props.onClose()">✕</button>
          <template v-if="!props.plain && canEditProduct && !editing">
            <button
              v-if="props.row.status !== 'ignored'"
              class="eb eb-ignore"
              title="标记为无需录入"
              @click.stop="markIgnored"
            >无需录入</button>
            <button class="eb eb-edit" @click.stop="startEdit">✎ 编辑</button>
          </template>
          <template v-else-if="!props.plain && canEditProduct && editing">
            <button class="eb eb-save" :disabled="saving || !formValid" @click.stop="saveEdit">
              {{ saving ? '保存中…' : '✓ 提交' }}
            </button>
            <button class="eb eb-cancel" @click.stop="cancelEdit">× 取消</button>
          </template>
          <!-- ··· 更多菜单（plain 模式隐藏）-->
          <div v-if="!props.plain" class="eb-more-wrap">
            <button class="eb eb-more" @click.stop="moreMenuVisible = !moreMenuVisible">···</button>
            <div v-if="moreMenuVisible" class="eb-more-menu">
              <div
                class="eb-more-item"
                :class="{ 'eb-more-item--disabled': editing }"
                @click.stop="!editing && copyCard()"
              >复制</div>
              <div
                class="eb-more-item"
                :class="{ 'eb-more-item--disabled': !editing }"
                @click.stop="editing && pasteCard()"
              >粘贴</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 图片 + 信息并排 -->
      <div class="ec-row">

        <!-- 图片区 -->
        <div class="ec-img"
          @mouseenter="imgHover = true"
          @mouseleave="imgHover = false; addMenuVisible = false"
        >
          <!-- 有图片 -->
          <template v-if="localCoverImage || row.cover_image">
            <img
              :src="localCoverImage || row.cover_image"
              class="ec-img-photo"
              :class="{ 'ec-img-photo--viewable': !editing }"
              alt="封面图"
              @click="!editing && previewImage()"
            />
          </template>
          <!-- 无图片 -->
          <template v-else>
            <span class="ec-img-ico">🖼</span>
            <span class="ec-img-hint">暂无图片</span>
          </template>

          <!-- 编辑状态遮罩：4个按钮 -->
          <div v-if="editing && imgHover" class="ec-img-overlay ec-img-overlay-edit">
            <!-- 查看 -->
            <button class="ov-btn" :disabled="!localCoverImage && !row.cover_image" @click.stop="previewImage">
              <el-icon><ZoomIn /></el-icon>
            </button>
            <!-- 编辑（裁切） -->
            <button class="ov-btn" :disabled="!localCoverImage && !row.cover_image" @click.stop="editImage">
              <el-icon><EditPen /></el-icon>
            </button>
            <!-- 新增（有子菜单） -->
            <div class="ov-btn-wrap">
              <button class="ov-btn" @click.stop="addMenuVisible = !addMenuVisible">
                <el-icon><Plus /></el-icon>
              </button>
              <div v-if="addMenuVisible" class="ov-submenu">
                <div class="ov-submenu-item" @click.stop="addImageFromUpload">使用新图片</div>
                <div class="ov-submenu-item" @click.stop="addImageFromExisting">使用已有图片</div>
              </div>
            </div>
            <!-- 删除 -->
            <button class="ov-btn ov-btn-danger" :disabled="!localCoverImage && !row.cover_image" @click.stop="deleteImage">
              <el-icon><Delete /></el-icon>
            </button>
          </div>
        </div>

        <!-- 图片预览（teleported 到 body，支持滚轮缩放/旋转） -->
        <el-image-viewer
          v-if="imgPreview && (localCoverImage || row.cover_image)"
          :url-list="[localCoverImage || row.cover_image]"
          :teleported="true"
          @close="imgPreview = false"
        />

        <!-- 信息区：flex列，gap=5px，每行36px -->
        <div class="ec-card">

        <!-- ── 查看模式 ── -->
        <template v-if="!editing">

          <!-- 行1：中文名称 + 内销tag -->
          <div class="eg-row">
            <div class="eg-cell eg-full">
              <span class="eg-lbl">中文名称</span>
              <span class="eg-val">
                <span class="eg-txt">{{ (row.status === 'recorded' && row.model_name) ? row.model_name : (row.name || '—') }}</span>
                <span v-if="row.market === 'domestic' || row.market === 'both'" class="eg-inner-tag eg-tag-domestic">内销</span>
              </span>
            </div>
          </div>

          <!-- 行2：英文名称 + 外贸tag -->
          <div class="eg-row">
            <div class="eg-cell eg-full">
              <span class="eg-lbl">英文名称</span>
              <span class="eg-val">
                <span class="eg-txt">{{ row.name_en || '—' }}</span>
                <span v-if="row.market === 'foreign' || row.market === 'both'" class="eg-inner-tag eg-tag-foreign">外贸</span>
              </span>
            </div>
          </div>

          <!-- 行3：品类 / 系列编码 / 上市年月 -->
          <div class="eg-row">
            <div class="eg-cell"><span class="eg-lbl">品类编码</span><span class="eg-val">{{ row.category_name || '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl">系列编码</span><span class="eg-val eg-mono">{{ row.series_code || '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl eg-lbl-em">上市日期</span><span class="eg-val">{{ row.listed_yymm || '—' }}</span></div>
          </div>

          <!-- 行4：型号简码 / 系列名称 / 退市年月 -->
          <div class="eg-row">
            <div class="eg-cell"><span class="eg-lbl">型号简码</span><span class="eg-val eg-mono">{{ row.model_code || '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl">系列名称</span><span class="eg-val">{{ row.series_name || '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl eg-lbl-em">退市日期</span><span class="eg-val">{{ row.delisted_yymm || '—' }}</span></div>
          </div>

          <!-- 行5：体积 / 毛重 / 净重 -->
          <div class="eg-row">
            <div class="eg-cell"><span class="eg-lbl">体积 (m³)</span><span class="eg-val">{{ row.total_volume ?? '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl">毛重 (kg)</span><span class="eg-val">{{ row.total_gross_weight ?? '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl">净重 (kg)</span><span class="eg-val">{{ row.total_net_weight ?? '—' }}</span></div>
          </div>

          <!-- 行6：产成品清单 -->
          <div class="eg-row">
            <div class="eg-cell eg-full">
              <span class="eg-lbl">产成品清单</span>
              <span class="eg-val">
                <span v-for="c in (row.packaged_list || [])" :key="c" class="pk-tag">{{ c }}</span>
                <span v-if="!row.packaged_list?.length" class="eg-dim">—</span>
              </span>
            </div>
          </div>

          <!-- 行7：标签 -->
          <div class="eg-row">
            <div class="eg-cell eg-full">
              <span class="eg-lbl">标签</span>
              <span class="eg-val">
                <span
                  v-for="tag in (row.tags || [])"
                  :key="tag.id"
                  class="ec-tag"
                  :style="{ background: tag.color + '22', borderColor: tag.color, color: tag.color }"
                >{{ tag.name }}</span>
                <span v-if="!(row.tags || []).length" class="eg-dim">—</span>
              </span>
            </div>
          </div>

        </template>

        <!-- ── 编辑模式 ── -->
        <template v-else-if="canEditProduct">

          <!-- 行1：中文名称 + 内销checkbox -->
          <div class="eg-row eg-row-edit">
            <div class="eg-cell eg-full">
              <el-tooltip :content="validations.name" :disabled="!validations.name" placement="top">
                <span class="eg-lbl eg-lbl-edit" :class="{ 'eg-lbl-error': validations.name }">中文名称</span>
              </el-tooltip>
              <span class="eg-val eg-val-inp">
                <el-autocomplete v-model="editForm.name" :fetch-suggestions="suggestName"
                  placeholder="中文名称" class="ei-auto" clearable />
                <el-checkbox v-model="editForm.market_domestic" class="ei-check">内销</el-checkbox>
              </span>
            </div>
          </div>

          <!-- 行2：英文名称 + 外贸checkbox -->
          <div class="eg-row eg-row-edit">
            <div class="eg-cell eg-full">
              <el-tooltip :content="validations.name_en" :disabled="!validations.name_en" placement="top">
                <span class="eg-lbl eg-lbl-edit" :class="{ 'eg-lbl-error': validations.name_en }">英文名称</span>
              </el-tooltip>
              <span class="eg-val eg-val-inp">
                <el-autocomplete v-model="editForm.name_en" :fetch-suggestions="suggestNameEn"
                  placeholder="英文名称（选填）" class="ei-auto" clearable />
                <el-checkbox v-model="editForm.market_foreign" class="ei-check">外贸</el-checkbox>
              </span>
            </div>
          </div>

          <!-- 行3：品类 / 系列编码 / 上市年月 -->
          <div class="eg-row eg-row-edit">
            <div class="eg-cell eg-cell-edit">
              <el-tooltip :content="validations.category_name" :disabled="!validations.category_name" placement="top">
                <span class="eg-lbl eg-lbl-edit" :class="{ 'eg-lbl-error': validations.category_name }">品类编码</span>
              </el-tooltip>
              <span class="eg-val eg-val-inp">
                <el-autocomplete v-model="editForm.category_name" :fetch-suggestions="suggestCategory"
                  placeholder="品类" class="ei-auto" clearable />
              </span>
            </div>
            <div class="eg-cell eg-cell-edit">
              <el-tooltip :content="validations.series_code" :disabled="!validations.series_code" placement="top">
                <span class="eg-lbl eg-lbl-edit" :class="{ 'eg-lbl-error': validations.series_code }">系列编码</span>
              </el-tooltip>
              <span class="eg-val eg-val-inp">
                <el-autocomplete v-model="editForm.series_code" :fetch-suggestions="suggestSeriesCode"
                  placeholder="系列编码" class="ei-auto" clearable :disabled="seriesDisabled" />
              </span>
            </div>
            <div class="eg-cell eg-cell-edit">
              <span class="eg-lbl eg-lbl-edit">上市日期</span>
              <span class="eg-val eg-val-inp">
                <el-date-picker v-model="editForm.listed_yymm" type="month"
                  format="YYYY-MM" value-format="YYYY-MM" placeholder="上市年月" class="ei-date" />
              </span>
            </div>
          </div>

          <!-- 行4：型号简码 / 系列名称 / 退市年月 -->
          <div class="eg-row eg-row-edit">
            <div class="eg-cell eg-cell-edit">
              <el-tooltip :content="validations.model_code" :disabled="!validations.model_code" placement="top">
                <span class="eg-lbl eg-lbl-edit" :class="{ 'eg-lbl-error': validations.model_code }" style="display:flex;align-items:center;gap:6px;">
                  型号简码
                  <el-popover placement="bottom-start" trigger="click" :width="'auto'" popper-style="padding:8px;">
                    <template #reference>
                      <button class="mc-tip-btn" title="查看型号简码说明" @click.stop>?</button>
                    </template>
                    <img :src="modelTipImg" style="display:block;border-radius:6px;" />
                  </el-popover>
                </span>
              </el-tooltip>
              <span class="eg-val eg-val-inp">
                <el-autocomplete v-model="editForm.model_code" :fetch-suggestions="suggestModelCode"
                  placeholder="型号简码" class="ei-auto" clearable :disabled="modelDisabled" />
              </span>
            </div>
            <div class="eg-cell eg-cell-edit">
              <el-tooltip :content="validations.series_name" :disabled="!validations.series_name" placement="top">
                <span class="eg-lbl eg-lbl-edit" :class="{ 'eg-lbl-error': validations.series_name }">系列名称</span>
              </el-tooltip>
              <span class="eg-val eg-val-inp">
                <el-autocomplete v-model="editForm.series_name" :fetch-suggestions="suggestSeriesName"
                  placeholder="系列名称" class="ei-auto" clearable
                  :disabled="seriesDisabled || seriesNameReadonly" />
              </span>
            </div>
            <div class="eg-cell eg-cell-edit">
              <span class="eg-lbl eg-lbl-edit">退市日期</span>
              <span class="eg-val eg-val-inp">
                <el-date-picker v-model="editForm.delisted_yymm" type="month"
                  format="YYYY-MM" value-format="YYYY-MM" placeholder="退市年月" class="ei-date" />
              </span>
            </div>
          </div>

          <!-- 行5：体积 / 毛重 / 净重（只读，由产成品清单实时计算） -->
          <div class="eg-row">
            <div class="eg-cell"><span class="eg-lbl">体积 (m³)</span><span class="eg-val">{{ editVolume ?? '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl">毛重 (kg)</span><span class="eg-val">{{ editGrossWeight ?? '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl">净重 (kg)</span><span class="eg-val">{{ editNetWeight ?? '—' }}</span></div>
          </div>

          <!-- 行6：产成品清单 → GEditTagList -->
          <div class="eg-row eg-row-edit eg-row-grow">
            <div class="eg-cell eg-full">
              <el-tooltip :content="validations.packaged_tags" :disabled="!validations.packaged_tags" placement="top">
                <span class="eg-lbl eg-lbl-edit" :class="{ 'eg-lbl-error': validations.packaged_tags }" style="align-self: stretch;">产成品清单</span>
              </el-tooltip>
              <span class="eg-val eg-val-inp" style="align-items: flex-start; ">
                <GEditTagList v-model="editForm.packaged_tags" :options="packagedOptions" />
              </span>
            </div>
          </div>

          <!-- 行7：标签 → el-select，最多展示6个，新建标签 type=primary -->
          <div class="eg-row eg-row-edit">
            <div class="eg-cell eg-full">
              <span class="eg-lbl eg-lbl-edit">标签</span>
              <span class="eg-val eg-val-inp">
                <el-select v-model="editForm.tag_names"
                  multiple allow-create filterable placeholder="选择标签" class="ei-sel">
                  <template #tag="{ data }">
                    <el-tag
                      v-for="item in data.slice(0, 6)"
                      :key="item.value"
                      :type="isExistingTag(item.value) ? undefined : 'primary'"
                      size="small" closable
                      @close="editForm.tag_names = editForm.tag_names.filter(n => n !== item.value)"
                    >{{ item.value }}</el-tag>
                    <el-tooltip v-if="data.length > 6" placement="top" effect="light">
                      <template #content>
                        <div class="tag-tip">
                          <el-tag
                            v-for="item in data.slice(6)"
                            :key="item.value"
                            :type="isExistingTag(item.value) ? undefined : 'primary'"
                            size="small" closable
                            @close="editForm.tag_names = editForm.tag_names.filter(n => n !== item.value)"
                          >{{ item.value }}</el-tag>
                        </div>
                      </template>
                      <el-tag type="info" size="small">+{{ data.length - 6 }}</el-tag>
                    </el-tooltip>
                  </template>
                  <el-option
                    v-for="tag in tagOptions"
                    :key="tag.id"
                    :value="tag.name"
                    :label="tag.name" />
                </el-select>
              </span>
            </div>
          </div>

        </template>

      </div><!-- /ec-card -->
      </div><!-- /ec-row -->

      <!-- 折叠分组（参数 / 数据）── -->
      <div class="ec-sections">
        <div class="eg-sec">
          <div class="eg-sec-hd" @click="toggleSec('params')">
            <span class="eg-arr">{{ isSec('params') ? '▾' : '›' }}</span>参数
            <!-- 参数独立编辑按钮：仅在查看模式 + 有权限时显示 -->
            <button
              v-if="isSec('params') && canEditProduct && !editing && !paramsEditing"
              class="param-sec-edit-btn"
              title="编辑参数"
              @click.stop="startParamsEdit"
            >✎ 编辑</button>
          </div>
          <div v-if="isSec('params')" class="eg-sec-bd eg-sec-bd-params">

            <!-- 查看模式 -->
            <template v-if="!paramsEditing">
              <div v-if="!paramsLoaded" class="params-loading">加载中…</div>
              <div v-else class="params-cards">
                <div v-for="g in GROUP_DEFS" :key="g.key" class="param-card">
                  <div class="param-card-hd" :style="{ background: g.bg, color: g.color }">{{ g.label }}</div>
                  <div class="param-card-body">
                    <div v-if="!paramsData[g.key].length" class="param-card-empty">—</div>
                    <div v-for="item in paramsData[g.key]" :key="item.key_id" class="param-item">
                      <span class="param-key-lbl">{{ item.key_name }}</span>
                      <span class="param-val-txt">{{ item.value || '—' }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>

            <!-- 编辑模式（独立或随主行编辑） -->
            <template v-else>
              <div class="params-cards params-cards-edit">
                <div v-for="g in GROUP_DEFS" :key="g.key" class="param-card param-card-edit">
                  <!-- 卡片标题 + 添加按钮 -->
                  <div class="param-card-hd" :style="{ background: g.bg, color: g.color }">
                    <span>{{ g.label }}</span>
                    <button
                      class="param-add-btn"
                      title="添加参数项"
                      :style="{ color: g.color, borderColor: g.color }"
                      @click.stop="openParamAdd(g.key)"
                    >+</button>
                  </div>
                  <!-- 可拖拽列表 -->
                  <div class="param-card-body">
                  <div
                    :ref="el => sortableRefs[g.key] = el"
                    class="param-list"
                  >
                    <div
                      v-for="(item, idx) in editParams[g.key]"
                      :key="item.key_id ?? item.key_name"
                      class="param-item-edit"
                      :class="{ 'param-item-deleted': item.state === 'deleted' }"
                    >
                      <span
                        class="drag-handle"
                        :class="{ 'drag-handle-disabled': item.state === 'deleted' }"
                        :title="item.state === 'deleted' ? '' : '拖动排序'"
                      >⠿</span>
                      <span
                        class="param-key-lbl"
                        :class="{ 'param-key-deleted': item.state === 'deleted' }"
                      >{{ item.key_name }}</span>
                      <input
                        v-model="item.value"
                        class="param-val-input"
                        placeholder="输入值"
                        :disabled="item.state === 'deleted'"
                        @click.stop
                      />
                      <!-- deleted → 撤回按钮；其他 → 删除按钮 -->
                      <button
                        v-if="item.state === 'deleted'"
                        class="param-restore-btn"
                        title="撤回删除"
                        @click.stop="restoreParamItem(g.key, idx)"
                      >↩</button>
                      <button
                        v-else
                        class="param-del-btn"
                        title="移除"
                        @click.stop="removeParamItem(g.key, idx)"
                      >×</button>
                    </div>
                    <div v-if="!editParams[g.key].length" class="param-card-empty">—</div>
                  </div>
                  </div><!-- /param-card-body -->
                </div>
              </div>
              <!-- 独立编辑时的保存/取消按钮 -->
              <div v-if="!editing" class="params-actions">
                <button class="params-action-btn params-action-cancel" @click.stop="cancelParamsEdit">取消</button>
                <button class="params-action-btn params-action-save" :disabled="paramsSaving" @click.stop="saveParamsOnly">
                  {{ paramsSaving ? '保存中…' : '保存参数' }}
                </button>
              </div>

              <!-- 添加参数 dialog（四个分组共用） -->
              <el-dialog
                v-model="paramAddDialog.visible"
                :title="`添加参数 · ${GROUP_DEFS.find(g => g.key === paramAddDialog.groupKey)?.label ?? ''}`"
                width="360px"
                :close-on-click-modal="false"
                append-to-body
                @keydown.enter.stop
              >
                <div style="display:flex;flex-direction:column;gap:14px;padding:4px 0;">
                  <div>
                    <div style="font-size:12px;color:#6b5e4e;margin-bottom:6px;">键名</div>
                    <el-select
                      v-model="paramAddDialog.name"
                      filterable
                      allow-create
                      default-first-option
                      placeholder="选择或输入键名"
                      style="width:100%"
                      clearable
                      @keydown.enter.stop
                    >
                      <el-option
                        v-for="k in availableKeyOptions(paramAddDialog.groupKey)"
                        :key="k.id"
                        :value="k.name"
                        :label="k.name"
                      />
                    </el-select>
                  </div>
                  <div>
                    <div style="font-size:12px;color:#6b5e4e;margin-bottom:6px;">值（可留空）</div>
                    <el-input
                      v-model="paramAddDialog.value"
                      placeholder="输入参数值"
                      clearable
                      @keyup.enter.stop="addParamItem"
                    />
                  </div>
                </div>
                <template #footer>
                  <button class="param-dlg-cancel" @click="paramAddDialog.visible = false">取消</button>
                  <button
                    class="param-dlg-confirm"
                    :disabled="!paramAddDialog.name?.trim()"
                    :style="{ background: GROUP_DEFS.find(g => g.key === paramAddDialog.groupKey)?.color }"
                    @click="addParamItem"
                  >确认添加</button>
                </template>
              </el-dialog>
            </template>

          </div>
        </div>
        <div class="eg-sec">
          <div class="eg-sec-hd" @click="toggleSec('data')">
            <span class="eg-arr">{{ isSec('data') ? '▾' : '›' }}</span>数据
          </div>
          <div v-if="isSec('data')" class="eg-sec-bd eg-sec-bd-data">
            <!-- 发货数据 bar 图 -->
            <div class="data-shipping-card">
              <div class="data-ph-hd">发货数据</div>
              <div class="data-shipping-body">
                <div v-if="shippingChartLoading" class="data-shipping-loading">
                  <div class="data-shipping-spinner"></div>
                </div>
                <div v-else-if="!shippingMonthly.length" class="data-shipping-empty">暂无发货记录</div>
                <div v-else ref="shippingChartEl" class="data-shipping-chart"></div>
                <!-- 无权限遮罩：仅覆盖图表区域 -->
                <div v-if="!canViewShipping" class="data-shipping-mask">
                  <span class="data-shipping-mask-text">无权限</span>
                </div>
              </div>
            </div>
            <!-- 售后数据（待开发） -->
            <div class="data-placeholder-card">
              <div class="data-ph-hd">售后数据</div>
              <div class="data-ph-body">
                <span class="eg-dim">待开发</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 提交遮罩 -->
      <div v-if="saving" class="ec-saving-mask">
        <div class="ec-saving-spinner"></div>
        <span class="ec-saving-text">正在提交…</span>
      </div>

    </div><!-- /ec-main -->

  </div>

  <!-- ── 裁剪弹窗 ──────────────────────────────── -->
  <el-dialog
    v-model="cropDialogVisible"
    title="裁剪图片"
    width="760"
    :close-on-click-modal="false"
    append-to-body
    class="crop-dialog"
    @opened="initCropper"
    @closed="closeCropDialog"
  >
    <!-- 裁剪区域：固定高度，cropperjs 在此区域内渲染 -->
    <div class="crop-wrap">
      <img ref="cropImgRef" :src="cropImgSrc" class="crop-src-img" alt="" />
    </div>
    <!-- 裁剪选项栏 -->
    <div class="crop-controls">
      <label class="crop-square-toggle">
        <el-checkbox v-model="cropSquare" size="small" />
        <span>正方形裁剪</span>
      </label>
      <span class="crop-output-hint">输出尺寸：600 × 600 px</span>
    </div>
    <template #footer>
      <button class="crop-btn crop-btn-cancel" @click="closeCropDialog">取消</button>
      <button class="crop-btn crop-btn-confirm" @click="applyCrop">应用裁剪</button>
    </template>
  </el-dialog>

</template>

<style scoped>
/* ── 展开区外壳 ───────────────────────────────── */
.ec {
  padding: 12px 14px;
  background: #f5f0e8;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ec--plain {
  padding: 0;
  background: transparent;
}

/* ── 顶栏（在 ec-main 内，底部分隔线） ─────────── */
.ec-top {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid #e8ddd0;
}
.ec-code {
  font-size: 15px; font-weight: 700; color: #2c2420;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', monospace;
}
.lc-badge {
  display: inline-block; font-size: 11px; font-weight: 600;
  padding: 2px 7px; border-radius: 3px; border: 1px solid;
}
.lc-on      { color: #389e0d; background: #f6ffed; border-color: #b7eb8f; }
.lc-out     { color: #cf1322; background: #fff1f0; border-color: #ffa39e; }
.lc-unknown { color: #8a7a6a; background: #f5f0e8; border-color: #d4c8b8; }
.ec-acts { margin-left: auto; display: flex; gap: 8px; }
.eb {
  padding: 4px 12px; border-radius: 5px; font-size: 12px;
  cursor: pointer; border: 1px solid; transition: all 0.15s; font-family: inherit;
  background: #fff;
}
.eb-close  { border-color: #ddd5c4; color: #8a7a6a; }
.eb-close:hover { background: #f5f0e8; color: #3a3028; }
.eb-edit        { border-color: #c0d4f0; color: #3a7bc8; }
.eb-edit:hover  { background: #edf4ff; }
.eb-ignore       { border-color: #f0b8b0; color: #c05040; }
.eb-ignore:hover { background: #fff0ee; }
.eb-more   { border-color: #ddd5c4; color: #8a7a6a; letter-spacing: 2px; padding: 4px 8px; }
.eb-more-wrap { position: relative; }
.eb-more-menu {
  position: absolute; top: calc(100% + 4px); right: 0;
  background: #fff; border: 1px solid #e8ddd0;
  border-radius: 7px; overflow: hidden;
  box-shadow: 0 4px 12px rgba(0,0,0,0.12);
  white-space: nowrap; z-index: 50; min-width: 80px;
}
.eb-more-item {
  padding: 8px 16px; font-size: 12px; color: #3a3028;
  cursor: pointer; transition: background 0.12s;
}
.eb-more-item:hover:not(.eb-more-item--disabled) { background: #faf5ee; color: #c4883a; }
.eb-more-item--disabled { color: #c8bfb0; cursor: not-allowed; }
.eb-save   { background: #c4883a; border-color: #c4883a; color: #fff; }
.mc-tip-btn {
  flex-shrink: 0; width: 18px; height: 18px; border-radius: 50%;
  border: 1.5px solid #c4883a; background: #fff7ed;
  color: #c4883a; font-size: 11px; font-weight: 700; line-height: 1;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.15s; padding: 0; font-family: inherit;
}
.mc-tip-btn:hover { background: #c4883a; color: #fff; }
.eb-save:hover:not(:disabled) { background: #b07830; }
.eb-save:disabled { opacity: 0.6; cursor: not-allowed; }
.eb-cancel { border-color: #ffa39e; color: #cf1322; }
.eb-cancel:hover { background: #fff1f0; }

/* ── 大卡片容器 ───────────────────────────────── */
.ec-main {
  position: relative;
  width: 1200px;
  background: #fff;
  border: 1px solid #e8ddd0;
  border-radius: 10px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.ec-row {
  display: flex;
  align-items: flex-start;
  padding: 12px;
  gap: 10px;
}

/* 图片：宽度固定，高度自动跟随信息区（align-self:stretch） */
.ec-img {
  width: 282px;
  flex-shrink: 0;
  align-self: stretch;
  background: #f8f5f0;
  border: 1px solid #e8ddd0;
  border-radius: 8px;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 6px;
  position: relative;   /* 遮罩定位基准 */
  overflow: hidden;
  cursor: default;
}
.ec-img-ico  { font-size: 26px; opacity: 0.2; }
.ec-img-hint { font-size: 11px; color: #c8bfb0; }

/* 图片本体 */
.ec-img-photo {
  width: 100%; height: 100%;
  object-fit: cover;
  display: block;
  border-radius: 8px;
  transition: transform 0.2s ease;
}
.ec-img-photo--viewable {
  cursor: pointer;
}
.ec-img-photo--viewable:hover {
  transform: scale(1.06);
}

/* ── 遮罩（查看 / 编辑两种） ────────────────────── */
.ec-img-overlay {
  position: absolute; inset: 0;
  background: rgba(0,0,0,0.38);
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  gap: 6px;
  cursor: pointer;
  transition: background 0.15s;
}
/* 查看遮罩：居中大图标 */
.ec-img-overlay:not(.ec-img-overlay-edit) {
  flex-direction: column;
}
.ec-img-overlay:not(.ec-img-overlay-edit):hover {
  background: rgba(0,0,0,0.52);
}
.ov-icon  { font-size: 28px; color: #fff; }

/* 编辑遮罩：圆形按钮横排 */
.ec-img-overlay-edit {
  flex-direction: row;
  flex-wrap: nowrap;
  gap: 10px;
  padding: 16px;
  cursor: default;
  align-content: center;
  justify-content: center;
}

/* 遮罩按钮：圆形，无文字 */
.ov-btn {
  display: flex; align-items: center; justify-content: center;
  width: 40px; height: 40px;
  background: rgba(255,255,255,0.18);
  border: 1px solid rgba(255,255,255,0.45);
  border-radius: 50%;
  color: #fff;
  cursor: pointer; transition: background 0.15s, transform 0.12s;
  flex-shrink: 0;
}
.ov-btn:hover:not(:disabled) {
  background: rgba(255,255,255,0.35);
  transform: scale(1.08);
}
.ov-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.ov-btn .el-icon { font-size: 17px; }

.ov-btn-danger:hover:not(:disabled) {
  background: rgba(207,19,34,0.6);
  border-color: rgba(255,120,120,0.7);
}

/* 新增子菜单 */
.ov-btn-wrap { position: relative; }
.ov-submenu {
  position: absolute; bottom: calc(100% + 6px); left: 50%;
  transform: translateX(-50%);
  background: #fff; border: 1px solid #e8ddd0;
  border-radius: 6px; overflow: hidden;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  white-space: nowrap; z-index: 10;
}
.ov-submenu-item {
  padding: 8px 14px; font-size: 12px; color: #3a3028;
  cursor: pointer; transition: background 0.12s;
}
.ov-submenu-item:hover { background: #faf5ee; color: #c4883a; }

/* 信息区：flex列，行间距5px，无统一卡片背景 */
.ec-card {
  flex: 1; min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

/* ── 每一行：36px固定高，白底，有边框圆角 ──────── */
.eg-row {
  display: flex;
  height: 36px;
  flex-shrink: 0;
  box-sizing: border-box;
  background: #fff;
  border: 1px solid #e8ddd0;
  border-radius: 6px;
  overflow: hidden;
}

/* 每行里的格子 */
.eg-cell {
  flex: 1; display: flex; align-items: center;
  border-right: 1px solid #f0e8dc;
  overflow: hidden;
}
.eg-cell-edit {
  border-right: none;
}
.eg-cell:last-child { border-right: none; }
.eg-full { flex: 3; }

/* label 格：100px宽，居中，有右边框 */
.eg-lbl {
  flex-shrink: 0;
  width: 100px;
  font-size: 12px; color: #6b5e4e; font-weight: 600;
  background: #faf7f2;
  border-right: 1px solid #e8ddd0;
  padding: 0 10px;
  align-self: stretch;
  display: flex; align-items: center; justify-content: center;
}
.eg-lbl-em { color: #3a3028; font-weight: 700; }

/* 校验失败时 label 变红 */
.eg-lbl-error { color: #d05a3c !important; }

/* 提交遮罩 */
.ec-saving-mask {
  position: absolute; inset: 0;
  background: rgba(255, 255, 255, 0.72);
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 10px;
  z-index: 10;
  border-radius: 10px;
}
.ec-saving-spinner {
  width: 28px; height: 28px;
  border: 3px solid #e8ddd0;
  border-top-color: #c4883a;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.ec-saving-text {
  font-size: 13px;
  color: #6b5e4e;
}

/* 编辑模式 label：加左/上/下边框（右边框已有） */
.eg-lbl-edit {
  border-left: 1px solid #e8ddd0;
  border-top: 1px solid #e8ddd0;
  border-bottom: 1px solid #e8ddd0;
}

/* value 格（查看） */
.eg-val {
  flex: 1; min-width: 0;
  padding: 0 10px;
  font-size: 13px; color: #2c2420;
  display: flex; align-items: center; gap: 6px;
  overflow: hidden;
}
.eg-txt  { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.eg-mono { font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', monospace; }
.eg-dim  { color: #bbb; font-size: 12px; }

/* market tag */
.eg-inner-tag {
  flex-shrink: 0; font-size: 10px; border: 1px solid; border-radius: 3px; padding: 1px 5px;
}
.eg-tag-domestic { color: #c4883a; border-color: #f5d6a8; background: #fff7ed; }
.eg-tag-foreign  { color: #3a7bc8; border-color: #c5d9f5; background: #edf4ff; }

/* 产成品 tag */
.pk-tag {
  display: inline-block; font-size: 13px; color: #3a7bc8;
  background: #edf4ff; border: 1px solid #c5d9f5;
  border-radius: 4px; padding: 2px 8px; margin-right: 4px; flex-shrink: 0;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', monospace;
}

/* 产品标签 tag（查看模式行7） */
.ec-tag {
  display: inline-block; font-size: 13px; font-weight: 500;
  border: 1px solid; border-radius: 5px;
  padding: 2px 10px; margin-right: 5px; flex-shrink: 0;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif;
}

/* ── 编辑模式行：取消整行外边框和背景 ─────────── */
.eg-row-edit {
  border: none;
  background: transparent;
}
/* 自动高度行（产成品清单等内容可能超过一行）*/
.eg-row-grow {
  height: auto;
  min-height: 36px;
}
.eg-row-edit .eg-lbl {
  border-radius: 6px;
}

/* ── 编辑模式 value 格 ────────────────────────── */
.eg-val-inp {
  padding: 0 6px;
  gap: 6px;
}

/* el-autocomplete：始终显示边框，白色背景 */
.ei-auto { flex: 1; min-width: 0; }
.ei-auto :deep(.el-input__wrapper) {
  height: 26px; padding: 0 8px; border-radius: 4px;
  box-shadow: none !important;
  border: 1px solid #e8ddd0;
  background: #fff;
  transition: border-color 0.15s;
}
.ei-auto :deep(.el-input__wrapper):hover      { border-color: #c4883a; }
.ei-auto :deep(.el-input__wrapper.is-focus)   { border-color: #c4883a !important; }
.ei-auto :deep(.el-input__inner) { height: 24px; font-size: 13px; color: #2c2420; background: #fff; }

/* el-date-picker：始终显示边框，白色背景 */
.ei-date { flex: 1; min-width: 0; }
.ei-date :deep(.el-input__wrapper) {
  height: 26px; padding: 0 8px; border-radius: 4px;
  box-shadow: none !important;
  border: 1px solid #e8ddd0;
  background: #fff;
  transition: border-color 0.15s;
}
.ei-date :deep(.el-input__wrapper):hover      { border-color: #c4883a; }
.ei-date :deep(.el-input__wrapper.is-focus)   { border-color: #c4883a !important; }
.ei-date :deep(.el-input__inner) { height: 24px; font-size: 13px; color: #2c2420; background: #fff; }

/* el-select（多选，行6/7）：始终显示边框，高度与 autocomplete 一致 */
.ei-sel { flex: 1; min-width: 0; }
.ei-sel :deep(.el-select__wrapper) {
  height: 32px; min-height: 32px; padding: 0 8px; border-radius: 4px;
  box-shadow: none !important;
  border: 1px solid #e8ddd0;
  background: #fff;
  transition: border-color 0.15s;
}
.ei-sel :deep(.el-select__wrapper):hover      { border-color: #c4883a; }
.ei-sel :deep(.el-select__wrapper.is-focused) { border-color: #c4883a; box-shadow: none !important; }
.ei-sel :deep(.el-select__placeholder),
.ei-sel :deep(.el-select__input)              { font-size: 13px; }
.ei-sel :deep(.el-select__tags-text)          { font-size: 12px; }
.ei-sel :deep(.el-tag:first-child)            { margin-left: 2px; }

/* tooltip 内的 tag 列表 */
.tag-tip { display: flex; flex-wrap: wrap; gap: 4px; max-width: 240px; }

/* checkbox */
.ei-check { flex-shrink: 0; margin-left: auto; }
.ei-check :deep(.el-checkbox__label) { font-size: 12px; color: #6b5e4e; padding-left: 4px; }

/* ── 折叠分组区（在 ec-main 内，顶部分隔线） ── */
.ec-sections {
  border-top: 1px solid #e8ddd0;
}
.eg-sec { border-top: 1px solid #f0e8dc; }
.eg-sec:first-child { border-top: none; }
.eg-sec-hd {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 12px; cursor: pointer;
  font-size: 12px; color: #6b5e4e; font-weight: 600;
  user-select: none; transition: background 0.15s;
}
.eg-sec-hd:hover { background: #faf5ee; }
.eg-arr { color: #aaa; width: 12px; font-size: 11px; }
.eg-sec-bd { padding: 8px 12px 10px 30px; }

/* ── 裁剪弹窗 ────────────────────────────────── */
/* 去除 dialog body 内边距，让 cropperjs 铺满 */
:global(.crop-dialog .el-dialog__body) {
  padding: 0 !important;
}

/* 裁剪容器：固定高度，cropperjs 在此布局 */
.crop-wrap {
  height: 460px;
  background: #1a1a1a;
  /* 不加 overflow:hidden，cropperjs 自己管理 */
}
/* 初始图片样式，cropperjs 初始化后会接管 */
.crop-src-img {
  display: block;
  max-width: 100%;
}

/* 裁剪选项栏 */
.crop-controls {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px;
  border-top: 1px solid #f0e8dc;
  background: #faf7f2;
}
.crop-square-toggle {
  display: flex; align-items: center; gap: 6px;
  cursor: pointer; font-size: 13px; color: #3a3028;
}
.crop-output-hint { font-size: 12px; color: #aaa; }

/* 底部按钮 */
.crop-btn {
  padding: 6px 20px; border-radius: 7px;
  font-size: 13px; font-family: inherit; cursor: pointer;
  border: 1px solid #e0d4c0; transition: all 0.15s;
}
.crop-btn-cancel  { background: #fff; color: #6b5e4e; }
.crop-btn-cancel:hover { background: #f5f0e8; }
.crop-btn-confirm { background: #c4883a; color: #fff; border-color: #c4883a; margin-left: 8px; }
.crop-btn-confirm:hover { background: #e09050; border-color: #e09050; }

/* ── 参数区 ───────────────────────────────────── */
.eg-sec-bd-params { padding: 12px 14px; }
.eg-sec-bd-data   { padding: 12px 14px; display: flex; gap: 12px; }
.data-placeholder-card {
  flex: 1; border: 1px solid #e8ddd0; border-radius: 10px; overflow: hidden;
}
.data-shipping-card {
  flex: 2; border: 1px solid #e8ddd0; border-radius: 10px; overflow: hidden;
}
.data-ph-hd {
  padding: 7px 12px; font-size: 12px; font-weight: 600;
  background: #f5f0e8; color: #8a7a6a;
  border-bottom: 1px solid #e8ddd0;
}
.data-ph-body {
  padding: 20px 12px; display: flex; align-items: center; justify-content: center;
}
.data-shipping-body {
  padding: 8px 4px; height: 180px;
  display: flex; align-items: center; justify-content: center;
  position: relative;
}
.data-shipping-chart { width: 100%; height: 100%; }
.data-shipping-loading {
  display: flex; align-items: center; justify-content: center;
  width: 100%; height: 100%;
}
.data-shipping-spinner {
  width: 22px; height: 22px;
  border: 2px solid #e8ddd0;
  border-top-color: #c4883a;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
.data-shipping-empty  { font-size: 12px; color: #bbb; }
.data-shipping-mask {
  position: absolute; inset: 0;
  background: rgba(200, 200, 200, 0.25);
  backdrop-filter: blur(4px);
  border-radius: 0 0 10px 10px;
  display: flex; align-items: center; justify-content: center;
}
.data-shipping-mask-text {
  font-size: 12px; color: #6b6b6b;
  background: rgba(255,255,255,0.6);
  border: 1px solid rgba(200,200,200,0.6);
  border-radius: 6px;
  padding: 3px 12px;
}
.params-loading { font-size: 12px; color: #bbb; }

/* 参数区头部编辑按钮 */
.param-sec-edit-btn {
  margin-left: auto; padding: 2px 9px; border-radius: 4px;
  border: 1px solid #c0d4f0; background: transparent; color: #3a7bc8;
  font-size: 11px; font-family: inherit; cursor: pointer; transition: all 0.15s;
}
.param-sec-edit-btn:hover { background: #edf4ff; }

/* 独立编辑时底部操作按钮 */
.params-actions {
  display: flex; justify-content: flex-end; gap: 8px; margin-top: 10px;
}
.params-action-btn {
  padding: 5px 16px; border-radius: 6px; font-size: 12px;
  font-family: inherit; cursor: pointer; border: 1px solid; transition: all 0.15s;
}
.params-action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.params-action-cancel { border-color: #e8ddd0; background: #fff; color: #6b5e4e; }
.params-action-cancel:hover:not(:disabled) { background: #f5f0e8; }
.params-action-save { border-color: #c4883a; background: #c4883a; color: #fff; }
.params-action-save:hover:not(:disabled) { background: #e09050; border-color: #e09050; }

.params-cards {
  display: flex; gap: 10px;
}
.param-card {
  flex: 1; min-width: 0;
  background: #fff; border: 1px solid #e8ddd0;
  border-radius: 10px;
  overflow: hidden;
  display: flex; flex-direction: column;
}
.param-card-hd {
  font-size: 12px; font-weight: 600;
  padding: 7px 12px;
  display: flex; align-items: center; justify-content: space-between;
  flex-shrink: 0;
}
.param-card-body { padding: 8px 12px; flex: 1; }
.param-card-empty { font-size: 12px; color: #ccc; padding: 4px 0; }
.param-item {
  display: flex; gap: 6px; align-items: baseline;
  padding: 4px 0; border-bottom: 1px solid #f5f0e8; font-size: 12px;
}
.param-item:last-child { border-bottom: none; }
.param-key-lbl { color: #6b5e4e; flex-shrink: 0; }
.param-val-txt { color: #2c2420; flex: 1; text-align: right; }

/* 编辑模式 */
.param-card-edit { background: #faf7f2; }
.param-list { display: flex; flex-direction: column; gap: 4px; }
.param-item-edit {
  display: flex; align-items: center; gap: 5px;
  padding: 3px 0;
}
.drag-handle {
  color: #c0b8ac; cursor: grab; font-size: 13px; flex-shrink: 0;
  user-select: none; line-height: 1;
}
.drag-handle:active { cursor: grabbing; }
.param-val-input {
  flex: 1; min-width: 0; height: 26px; padding: 0 6px;
  border: 1px solid #e0d4c0; border-radius: 5px;
  background: #fff; color: #2c2420;
  font-size: 12px; font-family: inherit;
  outline: none; transition: border-color 0.15s;
}
.param-val-input:focus { border-color: #c4883a; }
.param-del-btn {
  width: 18px; height: 18px; border-radius: 4px; flex-shrink: 0;
  border: 1px solid #e8ddd0; background: transparent;
  color: #a09080; font-size: 13px; line-height: 1;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.12s; padding: 0;
}
.param-del-btn:hover { background: rgba(208,90,60,0.08); color: #d05a3c; border-color: #ffa39e; }

/* deleted 项样式 */
.param-item-deleted { opacity: 0.7; }
.param-key-deleted  { color: #d05a3c !important; text-decoration: line-through; }
.param-item-deleted .param-val-input { color: #bbb; }
.drag-handle-disabled { cursor: default; opacity: 0.3; pointer-events: none; }

/* 撤回按钮 */
.param-restore-btn {
  width: 18px; height: 18px; border-radius: 4px; flex-shrink: 0;
  border: 1px solid #7ab87a; background: transparent;
  color: #4a9a5a; font-size: 13px; line-height: 1;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.12s; padding: 0;
}
.param-restore-btn:hover { background: rgba(74,154,90,0.1); }

.param-add-btn {
  width: 18px; height: 18px; border-radius: 4px;
  border: 1px solid #ddd5c4; background: transparent;
  color: #8a7a6a; font-size: 14px; line-height: 1;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.12s; padding: 0;
}
.param-add-btn:hover { border-color: #c4883a; color: #c4883a; background: #fff7ed; }
.param-add-confirm {
  width: 100%; padding: 5px 0; border-radius: 5px;
  border: none; background: #c4883a; color: #fff;
  font-size: 12px; font-family: inherit; cursor: pointer;
  transition: background 0.15s;
}
.param-add-confirm:hover:not(:disabled) { background: #e09050; }
.param-add-confirm:disabled { opacity: 0.5; cursor: not-allowed; }

/* 添加参数 dialog 按钮 */
.param-dlg-cancel {
  padding: 6px 18px; border-radius: 6px; border: 1px solid #e0d4c0;
  background: #fff; color: #6b5e4e; font-size: 13px; font-family: inherit;
  cursor: pointer; transition: background 0.15s; margin-right: 8px;
}
.param-dlg-cancel:hover { background: #faf7f2; }
.param-dlg-confirm {
  padding: 6px 18px; border-radius: 6px; border: none;
  color: #fff; font-size: 13px; font-family: inherit;
  cursor: pointer; transition: background 0.15s;
}
.param-dlg-confirm:hover:not(:disabled) { filter: brightness(1.1); }
.param-dlg-confirm:disabled { opacity: 0.5; cursor: not-allowed; }

/* SortableJS 拖拽占位样式 */
.sortable-ghost { opacity: 0.4; border: 1px dashed #c4883a !important; border-radius: 5px; }
.sortable-chosen { background: #fff7ed; }

</style>