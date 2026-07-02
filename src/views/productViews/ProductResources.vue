<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useProductResources } from '@/composables/useProductResources'
import { usePermission } from '@/composables/usePermission'
import {
  Plus, Edit, Delete, Search, Setting, Document, VideoPlay, Link, Picture,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

// ── 权限 ──────────────────────────────────────────
const { isAdmin, canEditProduct } = usePermission()

// ── composable（无参：资料库页面模式）────────────
const {
  types, typesLoading, loadTypes, createType, updateType, deleteType,
  resources, resourcesTotal, resourcesLoading, resourcesFilter,
  loadResources, createResource, updateResource, deleteResource, setResourceTags, setResourceModels,
  uploading, uploadPercent, uploadFile, cancelUpload, resetUploadState,
} = useProductResources()

// ── 品类/系列/型号级联（el-cascader）────────────
import http from '@/api/http'
const categoryTree = ref([])

async function loadCategoryTree() {
  if (categoryTree.value.length) return
  const res = await http.get('/api/category/tree')
  if (res.success) categoryTree.value = res.data || []
}

// el-cascader options 格式
const cascaderOptions = computed(() =>
  categoryTree.value.map(cat => ({
    value: cat.id, label: cat.name,
    children: (cat.series || []).map(ser => ({
      value: ser.id, label: ser.name,
      children: (ser.models || []).map(m => ({
        value: m.id, label: m.model_code + (m.name ? ' ' + m.name : ''),
      })),
    })),
  }))
)

// cascader v-model：路径数组 [[catId, seriesId, modelId], ...]
const cascaderModelValue = ref([])

// model_ids → cascader paths
function modelIdsToPaths(modelIds) {
  const paths = []
  for (const cat of categoryTree.value) {
    for (const ser of cat.series || []) {
      for (const m of ser.models || []) {
        if (modelIds.includes(m.id)) paths.push([cat.id, ser.id, m.id])
      }
    }
  }
  return paths
}

function onCascaderChange(paths) {
  cascaderModelValue.value = paths
  resourceForm.value.model_ids = (paths || []).map(p => p[p.length - 1])
}

// 选中型号的 chip 列表（在选择框外展示）
const selectedModelChips = computed(() => {
  const ids = new Set(resourceForm.value.model_ids || [])
  const chips = []
  for (const cat of categoryTree.value)
    for (const ser of cat.series || [])
      for (const m of ser.models || [])
        if (ids.has(m.id)) chips.push({ id: m.id, code: m.model_code, name: m.name })
  return chips
})

const cascaderPlaceholder = computed(() =>
  cascaderModelValue.value.length
    ? `已选 ${cascaderModelValue.value.length} 个型号，点击修改`
    : '选择型号后，该型号的产品将自动包含此资料'
)

function removeModelChip(modelId) {
  resourceForm.value.model_ids = resourceForm.value.model_ids.filter(id => id !== modelId)
  cascaderModelValue.value = modelIdsToPaths(resourceForm.value.model_ids)
}

// ── 标签分类（用于资料关联标签选择器）────────────
const tagCategories   = ref([])   // [{id, name, color, tags:[{id,name}]}]
const tagOptionsFlat  = ref([])   // 未分类标签
const tagSearchQuery  = ref('')
const collapsedTagCats = ref(new Set())

// 所有标签的扁平列表（含分类标签 + 未分类），用于条件构建器查 id→{id,name}
const allTagsFlat = computed(() => {
  const result = []
  for (const cat of tagCategories.value) result.push(...(cat.tags || []))
  result.push(...tagOptionsFlat.value)
  return result
})

function findTagById(id) {
  return allTagsFlat.value.find(t => t.id === id) || { id, name: `#${id}` }
}

async function loadAllTags() {
  // 每次弹窗打开都重新加载，确保新增标签能立即出现
  const [catRes, tagRes] = await Promise.all([
    http.get('/api/product/tags/categories/'),
    http.get('/api/product/tags'),
  ])
  if (catRes.success) tagCategories.value = catRes.data || []
  if (tagRes.success) tagOptionsFlat.value = (tagRes.data || []).filter(t => !t.category_id)
}

// ── 标签条件构建器 ──────────────────────────────
// conditionTree: 根组 { op: 'AND'|'OR', items: [...] }
// 根级 item: { type:'tag', id, name, not } | { type:'group', op, items:[TagItem] }
// TagItem（组内）: { type:'tag', id, name, not }
const conditionTree = ref({ op: 'AND', items: [] })
const conditionMode = ref(false)

function enterConditionMode() {
  const currentTags = (resourceForm.value.tag_ids || []).map(id => {
    const t = findTagById(id)
    return { type: 'tag', id, name: t.name, not: false }
  })
  conditionTree.value = { op: 'AND', items: currentTags }
  conditionMode.value = true
}

function exitConditionMode() {
  const validItems = conditionTree.value.items.filter(i => i.type === 'tag' || (i.type === 'group' && i.items.length))
  const tagCondition = validItems.length
    ? { op: conditionTree.value.op, items: validItems.map(_serializeItem) }
    : null
  resourceForm.value.tag_ids = tagCondition ? [...new Set(_extractTagIds(tagCondition))] : []
  conditionMode.value = false
  conditionTree.value = { op: 'AND', items: [] }
  closeTagPopover()
}

function addSubGroup() {
  conditionTree.value.items.push({ type: 'group', op: 'OR', items: [] })
}

function removeRootItem(idx) {
  conditionTree.value.items.splice(idx, 1)
}

function removeGroupItem(groupIdx, tagIdx) {
  const group = conditionTree.value.items[groupIdx]
  if (group && group.type === 'group') {
    group.items.splice(tagIdx, 1)
    if (group.items.length === 0) conditionTree.value.items.splice(groupIdx, 1)
  }
}

// 标签 popover（单例，共享于根级和子组）
const popoverTarget  = ref(null)   // null | 'root' | number（子组索引）
const popoverVisible = ref(false)
const popoverTagSearch = ref('')

const popoverFilteredGroups = computed(() => {
  const q = popoverTagSearch.value.trim().toLowerCase()
  return tagCategories.value.map(cat => ({
    ...cat,
    filteredTags: (cat.tags || []).filter(t => !q || t.name.toLowerCase().includes(q)),
  })).filter(cat => cat.filteredTags.length)
})
const popoverFilteredUncategorized = computed(() => {
  const q = popoverTagSearch.value.trim().toLowerCase()
  return tagOptionsFlat.value.filter(t => !q || t.name.toLowerCase().includes(q))
})

function openTagPopover(target) {
  if (popoverVisible.value && popoverTarget.value === target) {
    closeTagPopover()
    return
  }
  popoverTarget.value = target
  popoverTagSearch.value = ''
  popoverVisible.value = true
}

function closeTagPopover(target = null) {
  if (target !== null && popoverTarget.value !== target) return
  popoverVisible.value = false
  popoverTarget.value = null
  popoverTagSearch.value = ''
}

function addTagToTarget(tag) {
  const item = { type: 'tag', id: tag.id, name: tag.name, not: false }
  if (popoverTarget.value === 'root') {
    if (!conditionTree.value.items.find(i => i.type === 'tag' && i.id === tag.id))
      conditionTree.value.items.push(item)
  } else if (typeof popoverTarget.value === 'number') {
    const group = conditionTree.value.items[popoverTarget.value]
    if (group && group.type === 'group' && !group.items.find(t => t.id === tag.id))
      group.items.push(item)
  }
  closeTagPopover()
}

function onDocumentClick(e) {
  if (!popoverVisible.value) return
  const target = e.target
  if (!(target instanceof Element)) return
  if (target.closest('.tag-popover') || target.closest('.cond-add-tag-btn')) return
  closeTagPopover()
}

// 序列化 conditionTree → API 格式 { op, items } 或 null
function _serializeItem(item) {
  if (item.type === 'tag') return item.not ? { tag_id: item.id, not: true } : { tag_id: item.id }
  return { op: item.op, items: item.items.map(t => t.not ? { tag_id: t.id, not: true } : { tag_id: t.id }) }
}
function _extractTagIds(node) {
  if ('tag_id' in node) return [node.tag_id]
  return (node.items || []).flatMap(_extractTagIds)
}

// 反序列化 API 格式 → conditionTree（兼容旧 OR-of-AND 列表格式）
function _deserializeItem(node) {
  if ('tag_id' in node) {
    const t = findTagById(node.tag_id)
    return { type: 'tag', id: node.tag_id, name: t.name, not: !!node.not }
  }
  return {
    type: 'group', op: node.op || 'AND',
    items: (node.items || []).map(i => {
      const t = findTagById(i.tag_id || i)
      return { type: 'tag', id: i.tag_id || i, name: t.name, not: !!i.not }
    })
  }
}

function initConditionTreeFromApi(tag_condition) {
  if (!tag_condition) { conditionTree.value = { op: 'AND', items: [] }; conditionMode.value = false; return }
  conditionMode.value = true
  if (Array.isArray(tag_condition)) {
    // 旧 OR-of-AND 格式 → 转为树
    if (tag_condition.length === 1) {
      conditionTree.value = {
        op: 'AND',
        items: tag_condition[0].map(id => { const t = findTagById(id); return { type: 'tag', id, name: t.name, not: false } })
      }
    } else {
      conditionTree.value = {
        op: 'OR',
        items: tag_condition.map(group => ({
          type: 'group', op: 'AND',
          items: group.map(id => { const t = findTagById(id); return { type: 'tag', id, name: t.name, not: false } })
        }))
      }
    }
  } else if (typeof tag_condition === 'object' && tag_condition.op) {
    conditionTree.value = { op: tag_condition.op || 'AND', items: (tag_condition.items || []).map(_deserializeItem) }
  }
}

// 计算提交用的 tag_ids 和 tag_condition
const computedTagPayload = computed(() => {
  if (!conditionMode.value) {
    return { tag_ids: resourceForm.value.tag_ids || [], tag_condition: null }
  }
  const validItems = conditionTree.value.items.filter(i => i.type === 'tag' || (i.type === 'group' && i.items.length))
  if (!validItems.length) return { tag_ids: [], tag_condition: null }
  const tag_condition = { op: conditionTree.value.op, items: validItems.map(_serializeItem) }
  const tag_ids = [...new Set(_extractTagIds(tag_condition))]
  return { tag_ids, tag_condition }
})

// 实时逻辑公式
function _formulaItem(item) {
  if (item.type === 'tag') {
    const label = `"${item.name}"`
    return item.not ? `NOT ${label}` : label
  }
  if (item.type === 'group') {
    const parts = item.items.map(t => t.not ? `NOT "${t.name}"` : `"${t.name}"`)
    if (!parts.length) return null
    const inner = parts.join(` ${item.op} `)
    return parts.length > 1 ? `(${inner})` : inner
  }
  return null
}
const conditionFormula = computed(() => {
  if (!conditionMode.value) return ''
  const validItems = conditionTree.value.items.filter(i => i.type === 'tag' || (i.type === 'group' && i.items.length))
  if (!validItems.length) return ''
  const parts = validItems.map(_formulaItem).filter(Boolean)
  return parts.length > 1 ? parts.join(` ${conditionTree.value.op} `) : (parts[0] || '')
})

function isTagCatCollapsed(id) { return collapsedTagCats.value.has(id) }
function toggleTagCat(id) {
  if (collapsedTagCats.value.has(id)) collapsedTagCats.value.delete(id)
  else collapsedTagCats.value.add(id)
}

const filteredTagGroups = computed(() => {
  const q = tagSearchQuery.value.trim().toLowerCase()
  return tagCategories.value.map(cat => ({
    ...cat,
    filteredTags: (cat.tags || []).filter(t => !q || t.name.toLowerCase().includes(q)),
  })).filter(cat => cat.filteredTags.length)
})
const filteredUncategorizedTags = computed(() => {
  const q = tagSearchQuery.value.trim().toLowerCase()
  return tagOptionsFlat.value.filter(t => !q || t.name.toLowerCase().includes(q))
})

// ── 类型筛选 ──────────────────────────────────────
const activeTypeId = ref(null)

function selectType(typeId) {
  activeTypeId.value = typeId
  // 0 表示"未分类"，传特殊值让后端过滤 type_id IS NULL
  loadResources({ type_id: typeId === 0 ? 'none' : typeId, page: 1 })
}

// ── 搜索 ──────────────────────────────────────────
const searchText = ref('')
let searchTimer = null
function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => loadResources({ search: searchText.value, page: 1 }), 300)
}

// ── 管理类型弹窗 ──────────────────────────────────
const typeManageVisible = ref(false)
const typeFormVisible   = ref(false)
const typeForm          = ref({ name: '', sort_order: 0 })
const editingTypeId     = ref(null)

function openTypeCreate() {
  editingTypeId.value = null
  typeForm.value = { name: '', sort_order: types.value.length * 10 }
  typeFormVisible.value = true
}
function openTypeEdit(t) {
  editingTypeId.value = t.id
  typeForm.value = { name: t.name, sort_order: t.sort_order }
  typeFormVisible.value = true
}
async function submitType() {
  if (editingTypeId.value) {
    await updateType(editingTypeId.value, typeForm.value)
  } else {
    await createType(typeForm.value.name, typeForm.value.sort_order)
  }
  typeFormVisible.value = false
}

// ── 新建/编辑资料弹窗 ────────────────────────────
const resourceDialogVisible = ref(false)
const resourceDialogTitle   = ref('新建资料')
const editingResourceId     = ref(null)
const resourceForm          = ref({
  title: '', type_id: null, url: '', source: 'external',
  file_type: 'link', storage_key: null, original_filename: null, description: '',
  tag_ids: [], model_ids: [],
})

// 视频压缩体积记录
const videoSizeInfo    = ref(null)   // { before, after } 单位字节
const pendingFile      = ref(null)   // 待上传的 File 对象（选文件后暂存，保存时才上传）
const pendingCoverFile = ref(null)   // 待上传的封面图片（仅视频资料可选）
const coverPreviewUrl  = ref('')     // 封面本地预览 Object URL

function formatSize(bytes) {
  if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB'
  return (bytes / 1024).toFixed(0) + ' KB'
}

const FILE_TYPE_OPTIONS = [
  { value: 'pdf',   label: 'PDF 文档' },
  { value: 'image', label: '图片' },
  { value: 'video', label: '视频链接' },
  { value: 'link',  label: '外部链接' },
  { value: 'other', label: '其他' },
]

const uploadInputRef = ref(null)
const uploadMode     = ref('link')   // 'link' | 'file'

function openResourceCreate() {
  editingResourceId.value = null
  resourceDialogTitle.value = '新建资料'
  resourceForm.value = { title: '', type_id: null, url: '', source: 'external', file_type: 'link', storage_key: null, cover_storage_key: null, original_filename: null, description: '', tag_ids: [], model_ids: [] }
  cascaderModelValue.value = []
  conditionMode.value = false
  conditionTree.value = { op: 'AND', items: [] }
  uploadMode.value = 'link'
  pendingFile.value = null
  pendingCoverFile.value = null
  if (coverPreviewUrl.value) { URL.revokeObjectURL(coverPreviewUrl.value); coverPreviewUrl.value = '' }
  loadAllTags(); loadCategoryTree()
  resourceDialogVisible.value = true
}
async function openResourceEdit(r) {
  editingResourceId.value = r.id
  resourceDialogTitle.value = '编辑资料'
  resourceForm.value = {
    title: r.title, type_id: r.type_id, url: r.url, source: r.source,
    file_type: r.file_type, storage_key: r.storage_key,
    cover_storage_key: r.cover_storage_key || null,
    original_filename: r.original_filename, description: r.description || '',
    tag_ids: (r.tags || []).map(t => t.id),
    model_ids: r.model_ids || [],
  }
  uploadMode.value = r.source === 'oss' ? 'file' : 'link'
  pendingFile.value = null
  pendingCoverFile.value = null
  if (coverPreviewUrl.value) { URL.revokeObjectURL(coverPreviewUrl.value); coverPreviewUrl.value = '' }
  if (r.cover_url) coverPreviewUrl.value = r.cover_url
  await Promise.all([loadAllTags(), loadCategoryTree()])
  cascaderModelValue.value = modelIdsToPaths(resourceForm.value.model_ids)
  // 初始化条件构建器：若有 tag_condition 则进入构建器模式
  initConditionTreeFromApi(r.tag_condition)
  resourceDialogVisible.value = true
}

async function pickFile() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pdf,.png,.jpg,.jpeg,.webp,.mp4,.mov,.webm'
  input.onchange = (e) => {
    const file = e.target.files[0]
    if (!file) return
    // 只暂存文件，不上传，保存时才上传
    pendingFile.value   = file
    videoSizeInfo.value = null
    // 根据扩展名预填 file_type
    const ext = file.name.split('.').pop().toLowerCase()
    const typeMap = { pdf: 'pdf', png: 'image', jpg: 'image', jpeg: 'image', webp: 'image', mp4: 'video', mov: 'video', webm: 'video' }
    resourceForm.value.original_filename = file.name
    resourceForm.value.file_type         = typeMap[ext] || 'other'
    resourceForm.value.url               = ''   // 清空旧 url，保存后才有
    resourceForm.value.storage_key       = null
    resourceForm.value.source            = 'oss'
  }
  input.click()
}

function pickCoverFile() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.png,.jpg,.jpeg,.webp'
  input.onchange = (e) => {
    const file = e.target.files[0]
    if (!file) return
    pendingCoverFile.value = file
    if (coverPreviewUrl.value) URL.revokeObjectURL(coverPreviewUrl.value)
    coverPreviewUrl.value = URL.createObjectURL(file)
    // 清空已存储的旧封面 key（保存时会重新上传）
    resourceForm.value.cover_storage_key = null
  }
  input.click()
}

function removeCover() {
  pendingCoverFile.value = null
  if (coverPreviewUrl.value) { URL.revokeObjectURL(coverPreviewUrl.value); coverPreviewUrl.value = '' }
  resourceForm.value.cover_storage_key = null
}

async function submitResource() {
  if (!resourceForm.value.title.trim()) { ElMessage.warning('请填写标题'); return }
  if (!resourceForm.value.type_id) { ElMessage.warning('请选择资料类型'); return }

  // 上传模式且有待上传文件 → 先上传，再写数据库
  if (uploadMode.value === 'file' && pendingFile.value) {
    const result = await uploadFile(pendingFile.value)
    if (!result) return   // 上传失败，uploadFile 内已弹提示
    resourceForm.value.url               = result.url
    resourceForm.value.storage_key       = result.storage_key
    resourceForm.value.file_type         = result.file_type
    resourceForm.value.original_filename = result.original_filename
    resourceForm.value.source            = 'oss'
    pendingFile.value = null
  }

  // 若有待上传封面（视频资料可选）
  if (pendingCoverFile.value) {
    const coverResult = await uploadFile(pendingCoverFile.value)
    if (!coverResult) return
    resourceForm.value.cover_storage_key = coverResult.storage_key
    pendingCoverFile.value = null
  }

  // 上传文件模式但没有待上传文件（编辑时未换文件）
  if (uploadMode.value === 'file' && !resourceForm.value.url) {
    ElMessage.warning('请先选择文件'); return
  }

  const payload = { ...resourceForm.value }
  if (uploadMode.value === 'link') {
    payload.source      = 'external'
    payload.storage_key = null
    // 根据 url 后缀推断 file_type
    if (!payload.file_type || payload.file_type === 'link') {
      const ext = (payload.url || '').split('.').pop().toLowerCase()
      if (ext === 'pdf') payload.file_type = 'pdf'
      else if (['png','jpg','jpeg','webp'].includes(ext)) payload.file_type = 'image'
      else if (['mp4','mov','webm'].includes(ext)) payload.file_type = 'video'
      else payload.file_type = 'link'
    }
  }
  const { tag_ids: tagIds, tag_condition: tagCondition } = computedTagPayload.value
  const modelIds = payload.model_ids || []
  delete payload.tag_ids
  delete payload.model_ids

  let success, newId
  if (editingResourceId.value) {
    success = await updateResource(editingResourceId.value, payload)
    newId   = editingResourceId.value
  } else {
    const r = await createResource(payload)
    success = !!r
    newId   = r?.id
  }
  if (success && newId) {
    await Promise.all([
      setResourceTags(newId, tagIds, tagCondition),
      setResourceModels(newId, modelIds),
    ])
    resourceDialogVisible.value = false
    // 新建时跳到该资料所属的类型 tab；编辑时保持当前 tab
    const targetTypeId = payload.type_id || null
    if (!editingResourceId.value && targetTypeId) {
      activeTypeId.value = targetTypeId
      loadResources({ type_id: targetTypeId, page: 1 })
    } else {
      loadResources()
    }
  }
}

// ── 分页 ──────────────────────────────────────────
function onPageChange(page) { loadResources({ page }) }

// ── file_type 图标 ────────────────────────────────
function fileTypeIcon(type) {
  return { pdf: Document, video: VideoPlay, image: Picture, link: Link }[type] || Document
}
function fileTypeLabel(type) {
  return { pdf: 'PDF', image: '图片', video: '视频', link: '链接', other: '其他' }[type] || type
}
function fileTypeBgColor(type) {
  return { pdf: '#e8f0fe', image: '#e8f5e9', video: '#fce4ec', link: '#fff3e0', other: '#f3e5f5' }[type] || '#f5f0e8'
}
function fileTypeIconColor(type) {
  return { pdf: '#1565c0', image: '#2e7d32', video: '#c62828', link: '#e65100', other: '#6a1b9a' }[type] || '#c4883a'
}

// ── 预览弹窗 ──────────────────────────────────────
const previewVisible  = ref(false)
const previewResource = ref(null)
const videoSrc        = ref('')   // 视频播放器 src（签名 URL）

async function openPreview(r) {
  previewResource.value = r
  videoSrc.value        = ''
  previewVisible.value  = true
  if (r.file_type === 'video') {
    videoSrc.value = await getSignedUrl(r, 'inline') || ''
  }
}

function onPreviewClose() {
  videoSrc.value = ''   // 停止后台缓冲
}

// 获取 OSS 签名 URL（inline 预览 / attachment 下载）
async function getSignedUrl(r, disposition = 'inline') {
  if (!r) return null
  if (!r.storage_key) return r.url   // 外部链接直接返回
  try {
    const res = await http.get(`/api/resources/${r.id}/signed-url`, { params: { disposition } })
    return res.success ? res.data.url : r.url
  } catch { return r.url }
}

async function openInTab(r) {
  const win = window.open('', '_blank')   // 同步开空标签，保住用户手势
  const url = await getSignedUrl(r, 'inline')
  if (!url) { win?.close(); return }

  // PDF/图片：fetch → Blob URL（同源），Chrome 直接用内置阅读器渲染
  if (r.file_type === 'pdf' || r.file_type === 'image') {
    try {
      const resp = await fetch(url)
      const blob = await resp.blob()
      const blobUrl = URL.createObjectURL(blob)
      if (win) {
        win.location.href = blobUrl
        setTimeout(() => URL.revokeObjectURL(blobUrl), 120_000)
      }
      return
    } catch { /* 失败降级到直接打开 */ }
  }
  if (win) win.location.href = url
}

async function shareResource(r) {
  if (!r) return
  let url
  try {
    const res = await http.get(`/api/resources/${r.id}/share`)
    url = res.success ? res.data.url : null
  } catch { url = null }
  if (!url) { ElMessage.error('生成分享链接失败'); return }
  copyText(url)
  const tip = r.file_type === 'video' || r.file_type === 'image'
    ? '分享链接已复制，有效期 7 天，可在微信直接查看'
    : '分享链接已复制，有效期 7 天，在浏览器打开可预览'
  ElMessage.success(tip)
}

function copyText(text) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).catch(() => _execCopy(text))
  } else {
    _execCopy(text)
  }
}
function _execCopy(text) {
  const el = document.createElement('textarea')
  el.value = text
  el.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none'
  document.body.appendChild(el)
  el.focus(); el.select()
  try { document.execCommand('copy') } catch { /* ignore */ }
  document.body.removeChild(el)
}

async function downloadResource(r) {
  const url = await getSignedUrl(r, 'attachment')
  if (!url) return
  const a = document.createElement('a')
  a.href = url
  a.download = r.original_filename || r.title || 'download'
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

// ── 资料弹窗关闭清理 ──────────────────────────────
function onResourceDialogClose() {
  closeTagPopover()
  resetUploadState()
  videoSizeInfo.value = null
  pendingFile.value = null
  pendingCoverFile.value = null
  if (coverPreviewUrl.value) {
    URL.revokeObjectURL(coverPreviewUrl.value)
    coverPreviewUrl.value = ''
  }
}

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  document.addEventListener('click', onDocumentClick)
  await loadTypes()
  // 默认选中第一个类型
  const first = types.value[0]
  if (first) {
    activeTypeId.value = first.id
    loadResources({ type_id: first.id })
  } else {
    loadResources()
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
})
</script>

<template>
  <div class="resources-page">

    <!-- ── 顶部工具栏 ─────────────────────────────── -->
    <div class="toolbar">
      <div class="search-wrap">
        <el-input
          v-model="searchText"
          placeholder="搜索资料标题…"
          clearable
          :prefix-icon="Search"
          style="width: 220px"
          @input="onSearchInput"
          @clear="() => { searchText = ''; loadResources({ search: '', page: 1 }) }"
        />
      </div>
      <div class="toolbar-right">
        <el-button v-if="isAdmin" :icon="Setting" @click="typeManageVisible = true">管理类型</el-button>
        <el-button v-if="canEditProduct" type="primary" :icon="Plus" @click="openResourceCreate">新建资料</el-button>
      </div>
    </div>

    <!-- ── 主体：类型筛选 + 资料列表 ────────────────── -->
    <div class="body-wrap">

      <!-- 左侧类型筛选栏 -->
      <aside class="type-sidebar">
        <!-- 未分类兜底入口 -->
        <div
          class="type-item type-item--uncat"
          :class="{ active: activeTypeId === 0 }"
          @click="selectType(0)"
        >未分类</div>
        <div
          v-for="t in types"
          :key="t.id"
          class="type-item"
          :class="{ active: activeTypeId === t.id }"
          @click="selectType(t.id)"
        >{{ t.name }}</div>
      </aside>

      <!-- 右侧资料列表 -->
      <div class="resource-list">
        <div v-if="resourcesLoading" class="list-loading">加载中…</div>
        <template v-else>
          <div v-if="!resources.length" class="list-empty">暂无资料</div>
          <div v-else class="resource-cards">
            <div
              v-for="r in resources" :key="r.id"
              class="resource-card"
              @click="openPreview(r)"
            >
              <!-- 预览区 -->
              <div class="card-preview">
                <img
                  v-if="r.file_type === 'image'"
                  :src="r.url"
                  class="card-thumb"
                  loading="lazy"
                />
                <!-- PDF 专属图标 -->
                <div v-else-if="r.file_type === 'pdf'" class="card-icon-wrap" style="background:#fce8e8;">
                  <div class="card-pdf-icon">
                    <div class="card-pdf-top">PDF</div>
                    <div class="card-pdf-lines"><span></span><span></span><span></span></div>
                  </div>
                </div>
                <!-- 视频：有封面用封面图，OSS 视频用缩略帧，否则图标 -->
                <div v-else-if="r.file_type === 'video'" class="card-video-wrap">
                  <img v-if="r.cover_url" :src="r.cover_url" class="card-video-thumb" style="object-fit:contain;background:#000;" />
                  <video v-else-if="r.storage_key" :src="r.url" preload="metadata" muted class="card-video-thumb" />
                  <div v-else class="card-icon-wrap" style="background:#fce4ec;">
                    <el-icon style="color:#c62828;"><VideoPlay /></el-icon>
                  </div>
                  <div class="card-video-play-overlay"><el-icon><VideoPlay /></el-icon></div>
                </div>
                <div
                  v-else
                  class="card-icon-wrap"
                  :style="{ background: fileTypeBgColor(r.file_type) }"
                >
                  <el-icon :style="{ color: fileTypeIconColor(r.file_type) }">
                    <component :is="fileTypeIcon(r.file_type)" />
                  </el-icon>
                </div>
                <span class="card-ft-badge">{{ fileTypeLabel(r.file_type) }}</span>
              </div>
              <!-- 信息区 -->
              <div class="card-info">
                <div class="card-title" :title="r.title">{{ r.title }}</div>
                <div class="card-linked">{{ r.linked_count }} 个产品</div>
              </div>
              <!-- 操作（悬浮展示） -->
              <div v-if="canEditProduct" class="card-actions" @click.stop>
                <el-button size="small" :icon="Edit" circle @click="openResourceEdit(r)" />
                <el-button size="small" :icon="Delete" type="danger" plain circle @click="deleteResource(r.id).then(ok => ok && loadResources())" />
              </div>
            </div>
          </div>

          <!-- 分页 -->
          <div v-if="resourcesTotal > resourcesFilter.size" class="pagination">
            <el-pagination
              small background layout="prev, pager, next"
              :total="resourcesTotal"
              :page-size="resourcesFilter.size"
              :current-page="resourcesFilter.page"
              @current-change="onPageChange"
            />
          </div>
        </template>
      </div>
    </div>

    <!-- ── 管理类型弹窗 ────────────────────────────── -->
    <el-dialog v-model="typeManageVisible" title="管理资料类型" width="480" align-center>
      <div class="type-manage">
        <div v-for="t in types" :key="t.id" class="type-row">
          <span class="type-row-name">{{ t.name }}</span>
          <div class="type-row-actions">
            <el-button size="small" :icon="Edit" @click="openTypeEdit(t)" />
            <el-button size="small" :icon="Delete" type="danger" plain @click="deleteType(t.id)" />
          </div>
        </div>
        <el-button :icon="Plus" style="width:100%;margin-top:10px" @click="openTypeCreate">新增类型</el-button>
      </div>
    </el-dialog>

    <!-- 类型 新增/编辑 弹窗 -->
    <el-dialog v-model="typeFormVisible" :title="editingTypeId ? '编辑类型' : '新增类型'" width="360" align-center>
      <el-form :model="typeForm" label-width="70px">
        <el-form-item label="名称">
          <el-input v-model="typeForm.name" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="typeForm.sort_order" :min="0" style="width:120px" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="typeFormVisible = false">取消</el-button>
        <el-button type="primary" @click="submitType">确定</el-button>
      </template>
    </el-dialog>

    <!-- ── 资料预览弹窗 ─────────────────────────── -->
    <el-dialog v-model="previewVisible" :title="previewResource?.title" width="760" align-center append-to-body @close="onPreviewClose">
      <div class="preview-body">
        <img
          v-if="previewResource?.file_type === 'image'"
          :src="previewResource?.url"
          style="max-width:100%;max-height:60vh;object-fit:contain;display:block;margin:0 auto;"
        />
        <!-- 视频播放器 -->
        <div v-else-if="previewResource?.file_type === 'video'" style="text-align:center;">
          <video
            v-if="videoSrc"
            :src="videoSrc"
            controls
            style="width:100%;max-height:60vh;border-radius:8px;background:#000;"
          />
          <div v-else style="padding:40px 0;color:#8a7a6a;font-size:13px;">加载中…</div>
        </div>
        <div v-else style="text-align:center;padding:50px 0;color:#8a7a6a;font-size:13px;">
          <!-- PDF icon -->
          <div v-if="previewResource?.file_type === 'pdf'" style="display:flex;justify-content:center;margin-bottom:12px;">
            <div class="preview-pdf-icon">
              <div class="preview-pdf-top">PDF</div>
              <div class="preview-pdf-lines"><span></span><span></span><span></span></div>
            </div>
          </div>
          <div v-else style="font-size:40px;margin-bottom:12px;">🔗</div>
          <div style="font-size:14px;color:#3a3028;font-weight:600;margin-bottom:8px;">{{ previewResource?.original_filename || previewResource?.title }}</div>
          <div>该文件类型无法在此处预览，请点击下方按钮操作。</div>
        </div>
        <!-- 备注 -->
        <div v-if="previewResource?.description" class="preview-desc">
          <span class="preview-desc-label">备注：</span>{{ previewResource.description }}
        </div>
      </div>
      <template #footer>
        <div style="display:flex;justify-content:flex-end;gap:8px;">
          <el-button @click="previewVisible = false">关闭</el-button>
          <el-button @click="shareResource(previewResource)">分享链接</el-button>
          <el-button v-if="previewResource?.file_type !== 'video'" @click="openInTab(previewResource)">在新标签页打开</el-button>
          <el-button type="primary" @click="downloadResource(previewResource)">下载</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- ── 新建/编辑资料弹窗 ──────────────────────── -->
    <el-dialog v-model="resourceDialogVisible" :title="resourceDialogTitle" width="560" align-center :close-on-click-modal="false" @close="onResourceDialogClose">
      <el-form :model="resourceForm" label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="resourceForm.title" placeholder="资料名称" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="resourceForm.type_id" placeholder="选择资料类型" clearable style="width:100%">
            <el-option v-for="t in types" :key="t.id" :value="t.id" :label="t.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源">
          <el-radio-group v-model="uploadMode">
            <el-radio value="link">外部链接</el-radio>
            <el-radio value="file">上传文件</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="uploadMode === 'link'" label="链接">
          <el-input v-model="resourceForm.url" placeholder="https://…" />
        </el-form-item>
        <el-form-item v-else label="文件">
          <div class="upload-area">
            <el-button :disabled="uploading" @click="pickFile">选择文件（PDF / 图片 / 视频）</el-button>
            <span v-if="resourceForm.original_filename && !uploading" class="upload-filename">{{ resourceForm.original_filename }}</span>
            <!-- 上传进度 -->
            <div v-if="uploading" class="upload-progress-wrap">
              <div class="upload-progress-label">
                上传中…
                <span class="upload-progress-pct">{{ uploadPercent }}%</span>
                <el-button size="small" type="danger" plain style="margin-left:8px;padding:2px 8px;height:22px;" @click="cancelUpload">取消</el-button>
              </div>
              <div class="upload-progress-bar">
                <div class="upload-progress-fill" :style="{ width: uploadPercent + '%' }" />
              </div>
            </div>
          </div>
        </el-form-item>
        <!-- 封面上传（仅视频 + 上传文件模式） -->
        <el-form-item v-if="uploadMode === 'file' && resourceForm.file_type === 'video'" label="视频封面">
          <div class="cover-upload-area">
            <div v-if="coverPreviewUrl" class="cover-preview-wrap">
              <img :src="coverPreviewUrl" class="cover-preview-img" />
              <el-button size="small" type="danger" plain class="cover-remove-btn" @click="removeCover">移除封面</el-button>
            </div>
            <el-button v-else size="small" @click="pickCoverFile">选择封面图片（可选）</el-button>
            <div v-if="!coverPreviewUrl" class="cover-upload-hint">封面将显示在资料卡片上，支持 PNG / JPG / WEBP</div>
          </div>
        </el-form-item>
        <el-form-item label="文件类型">
          <el-select v-model="resourceForm.file_type" style="width:160px">
            <el-option v-for="o in FILE_TYPE_OPTIONS" :key="o.value" :value="o.value" :label="o.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联型号">
          <div class="model-select-wrap">
            <el-cascader
              class="model-cascader"
              :model-value="cascaderModelValue"
              :options="cascaderOptions"
              :props="{ multiple: true, checkStrictly: false, emitPath: true }"
              :show-all-levels="false"
              :placeholder="cascaderPlaceholder"
              filterable
              clearable
              style="width:100%"
              @change="onCascaderChange"
            />
            <!-- 选中型号展示在外部 -->
            <div v-if="selectedModelChips.length" class="model-chips">
              <div v-for="chip in selectedModelChips" :key="chip.id" class="model-chip">
                <span class="chip-code">{{ chip.code }}</span>
                <span v-if="chip.name" class="chip-name">{{ chip.name }}</span>
                <span class="chip-remove" @click="removeModelChip(chip.id)">×</span>
              </div>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="关联标签" class="tag-form-item">
          <!-- 简单 OR 模式 -->
          <template v-if="!conditionMode">
            <div class="tag-field-wrap">
              <el-select
                v-model="resourceForm.tag_ids"
                multiple
                placeholder="带该标签的产品将自动包含此资料"
                style="flex:1;min-width:0"
                :filter-method="q => tagSearchQuery = q"
                filterable
              >
                <template v-for="cat in filteredTagGroups" :key="cat.id">
                  <el-option :value="`__cat__${cat.id}`" :label="cat.name" disabled class="tag-group-hd"
                    @mousedown.stop.prevent="toggleTagCat(cat.id)">
                    <span class="tag-group-dot" :style="{ background: cat.color }"></span>
                    <span class="tag-group-name">{{ cat.name }}</span>
                    <span class="tag-group-arrow" :class="{ collapsed: isTagCatCollapsed(cat.id) }">▾</span>
                  </el-option>
                  <template v-if="!isTagCatCollapsed(cat.id)">
                    <el-option v-for="tag in cat.filteredTags" :key="tag.id"
                      :value="tag.id" :label="tag.name" class="tag-group-item" />
                  </template>
                </template>
                <template v-if="filteredUncategorizedTags.length">
                  <el-option value="__cat__none" label="未分类" disabled class="tag-group-hd"
                    @mousedown.stop.prevent="toggleTagCat('none')">
                    <span class="tag-group-dot" style="background:#bbb"></span>
                    <span class="tag-group-name">未分类</span>
                    <span class="tag-group-arrow" :class="{ collapsed: isTagCatCollapsed('none') }">▾</span>
                  </el-option>
                  <template v-if="!isTagCatCollapsed('none')">
                    <el-option v-for="tag in filteredUncategorizedTags" :key="tag.id"
                      :value="tag.id" :label="tag.name" class="tag-group-item" />
                  </template>
                </template>
              </el-select>
              <button class="cond-mode-btn" title="配置逻辑条件（AND/OR）" @click.prevent="enterConditionMode">
                条件
              </button>
            </div>
            <div class="tag-field-hint">多个标签之间为 OR（满足任意一个即匹配）</div>
          </template>

          <!-- 条件构建器模式 -->
          <template v-else>
            <div class="cond-builder">
              <div class="cond-builder-hd">
                <span class="cond-builder-title">逻辑条件</span>
                <button class="cond-simple-btn" @click.prevent="exitConditionMode">恢复简单模式</button>
              </div>
              <div v-if="conditionFormula" class="cond-formula">{{ conditionFormula }}</div>

              <!-- 根级 AND/OR 切换（多于1个条件时显示） -->
              <div v-if="conditionTree.items.filter(i=>i.type==='tag'||(i.items&&i.items.length)).length > 1" class="cond-op-row">
                <button :class="['cond-op-btn', { active: conditionTree.op === 'AND' }]" @click.prevent="conditionTree.op = 'AND'">全部满足 (AND)</button>
                <button :class="['cond-op-btn', { active: conditionTree.op === 'OR' }]" @click.prevent="conditionTree.op = 'OR'">满足任一 (OR)</button>
              </div>

              <!-- 条件项列表 -->
              <div v-for="(item, idx) in conditionTree.items" :key="idx" class="cond-item-wrap">
                <!-- 根级标签 chip -->
                <template v-if="item.type === 'tag'">
                  <span class="cond-tag-chip" :class="{ 'is-not': item.not }">
                    <span v-if="item.not" class="cond-not-badge" title="点击取消排除" @click.stop="item.not = false">NOT</span>
                    <span class="cond-tag-text">{{ item.name }}</span>
                    <span class="cond-chip-remove" @click.stop="removeRootItem(idx)">×</span>
                  </span>
                  <span class="cond-not-toggle" :class="{ active: item.not }" title="排除此标签 (NOT)" @click.stop="item.not = !item.not">⊘</span>
                </template>

                <!-- 子条件组 -->
                <div v-else-if="item.type === 'group'" class="cond-subgroup">
                  <div class="cond-subgroup-hd">
                    <button :class="['cond-op-btn cond-op-btn--sm', { active: item.op === 'AND' }]" @click.prevent="item.op = 'AND'">AND</button>
                    <button :class="['cond-op-btn cond-op-btn--sm', { active: item.op === 'OR' }]" @click.prevent="item.op = 'OR'">OR</button>
                    <button class="cond-subgroup-del" @click.prevent="removeRootItem(idx)">删除组 ×</button>
                  </div>
                  <div class="cond-subgroup-body">
                    <span v-for="(tag, ti) in item.items" :key="tag.id" class="cond-group-tag-wrap">
                      <span class="cond-tag-chip" :class="{ 'is-not': tag.not }">
                        <span v-if="tag.not" class="cond-not-badge" title="点击取消排除" @click.stop="tag.not = false">NOT</span>
                        <span class="cond-tag-text">{{ tag.name }}</span>
                        <span class="cond-chip-remove" @click.stop="removeGroupItem(idx, ti)">×</span>
                      </span>
                      <span class="cond-not-toggle" :class="{ active: tag.not }" title="排除此标签 (NOT)" @click.stop="tag.not = !tag.not">⊘</span>
                    </span>
                    <el-popover
                      :visible="popoverVisible && popoverTarget === idx"
                      placement="bottom-start"
                      :width="220"
                      trigger="manual"
                      popper-class="tag-popover"
                    >
                      <template #reference>
                        <span class="cond-add-tag-btn" @click.stop="openTagPopover(idx)">+ 添加标签</span>
                      </template>
                      <div class="tag-pop-search"><el-input v-model="popoverTagSearch" placeholder="搜索标签" size="small" clearable /></div>
                      <div class="tag-pop-list">
                        <template v-for="cat in popoverFilteredGroups" :key="cat.id">
                          <div class="tag-pop-cat">{{ cat.name }}</div>
                          <div v-for="tag in cat.filteredTags" :key="tag.id" class="tag-pop-item" @click="addTagToTarget(tag)">{{ tag.name }}</div>
                        </template>
                        <template v-if="popoverFilteredUncategorized.length">
                          <div class="tag-pop-cat">未分类</div>
                          <div v-for="tag in popoverFilteredUncategorized" :key="tag.id" class="tag-pop-item" @click="addTagToTarget(tag)">{{ tag.name }}</div>
                        </template>
                        <div v-if="!popoverFilteredGroups.length && !popoverFilteredUncategorized.length" class="tag-pop-empty">无匹配标签</div>
                      </div>
                    </el-popover>
                  </div>
                </div>
              </div>

              <!-- 根级操作按钮 -->
              <div class="cond-root-actions">
                <el-popover
                  :visible="popoverVisible && popoverTarget === 'root'"
                  placement="bottom-start"
                  :width="220"
                  trigger="manual"
                  popper-class="tag-popover"
                >
                  <template #reference>
                    <span class="cond-add-tag-btn" @click.stop="openTagPopover('root')">+ 添加标签</span>
                  </template>
                  <div class="tag-pop-search"><el-input v-model="popoverTagSearch" placeholder="搜索标签" size="small" clearable /></div>
                  <div class="tag-pop-list">
                    <template v-for="cat in popoverFilteredGroups" :key="cat.id">
                      <div class="tag-pop-cat">{{ cat.name }}</div>
                      <div v-for="tag in cat.filteredTags" :key="tag.id" class="tag-pop-item" @click="addTagToTarget(tag)">{{ tag.name }}</div>
                    </template>
                    <template v-if="popoverFilteredUncategorized.length">
                      <div class="tag-pop-cat">未分类</div>
                      <div v-for="tag in popoverFilteredUncategorized" :key="tag.id" class="tag-pop-item" @click="addTagToTarget(tag)">{{ tag.name }}</div>
                    </template>
                    <div v-if="!popoverFilteredGroups.length && !popoverFilteredUncategorized.length" class="tag-pop-empty">无匹配标签</div>
                  </div>
                </el-popover>
                <button class="cond-add-group-btn" @click.prevent="addSubGroup">+ 添加子条件组</button>
              </div>
            </div>
          </template>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="resourceForm.description" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resourceDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="uploading" @click="submitResource">保存</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<style scoped>
.resources-page {
  height: 100%;
  display: flex; flex-direction: column;
  overflow: hidden;
}

/* ── 工具栏 ────────────────────────────────── */
.toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.toolbar-right { display: flex; gap: 8px; }

/* ── 主体 ──────────────────────────────────── */
.body-wrap {
  flex: 1; min-height: 0;
  display: flex; overflow: hidden;
}

/* ── 左侧类型栏 ────────────────────────────── */
.type-sidebar {
  width: 140px; flex-shrink: 0;
  border-right: 1px solid var(--border);
  overflow-y: auto;
  padding: 12px 8px;
}
.type-item {
  padding: 7px 12px;
  border-radius: 8px;
  font-size: 13px; color: var(--text-muted);
  cursor: pointer; transition: all 0.15s;
  margin-bottom: 2px;
}
.type-item:hover { background: rgba(196,136,58,0.06); color: var(--text-primary); }
.type-item.active { background: var(--accent-bg); color: var(--accent); font-weight: 500; }
.type-item--uncat { margin-bottom: 8px; border-bottom: 1px solid var(--border); padding-bottom: 10px; color: var(--text-muted); font-size: 12px; }

/* ── 资料列表 ──────────────────────────────── */
.resource-list {
  flex: 1; min-width: 0;
  overflow-y: auto;
  padding: 16px 20px;
}
.list-loading, .list-empty {
  text-align: center; padding: 60px 0;
  font-size: 13px; color: var(--text-muted);
}
/* ── 卡片网格 ──────────────────────────────── */
.resource-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 14px;
}
.resource-card {
  position: relative;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 12px; overflow: hidden;
  cursor: pointer; transition: box-shadow 0.2s, border-color 0.2s;
  display: flex; flex-direction: column;
}
.resource-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.10); border-color: var(--accent); }
/* 预览区 */
.card-preview {
  position: relative;
  width: 100%; aspect-ratio: 4/3;
  background: #f5f0e8;
  overflow: hidden;
  flex-shrink: 0;
}
.card-thumb {
  width: 100%; height: 100%;
  object-fit: contain; display: block;
  background: #fff;
}
.card-icon-wrap {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  font-size: 40px;
}
.card-video-wrap {
  width: 100%; height: 100%;
  position: relative; overflow: hidden;
  background: #000;
}
.card-video-thumb {
  width: 100%; height: 100%;
  object-fit: cover; display: block;
}
.card-video-play-overlay {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.25);
  font-size: 36px; color: #fff;
  pointer-events: none;
}
.card-ft-badge {
  position: absolute; bottom: 6px; left: 6px;
  font-size: 10px; font-weight: 600;
  padding: 2px 6px; border-radius: 4px;
  background: rgba(0,0,0,0.45); color: #fff;
  pointer-events: none;
}
/* 信息区 */
.card-info  { padding: 8px 10px; flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.card-title {
  font-size: 12px; font-weight: 600; color: var(--text-primary);
  margin-bottom: 4px;
  overflow: hidden; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
  line-height: 1.4;
}
.card-linked { font-size: 11px; color: var(--text-muted); }
/* ── PDF 卡片图标 ──────────────────── */
.card-pdf-icon {
  width: 52px; height: 62px;
  background: #e53935; border-radius: 6px;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 4px;
}
.card-pdf-top {
  font-size: 13px; font-weight: 900; color: #fff; letter-spacing: 0.5px;
}
.card-pdf-lines { display: flex; flex-direction: column; gap: 2px; width: 30px; }
.card-pdf-lines span { display: block; height: 2px; border-radius: 1px; background: rgba(255,255,255,0.55); }
/* ── 预览弹窗备注 ──────────────────── */
.preview-desc {
  margin-top: 16px; padding: 10px 14px;
  background: #f5f0e8; border-radius: 8px;
  font-size: 13px; color: var(--text-primary); line-height: 1.6;
}
.preview-desc-label { font-weight: 600; color: var(--text-muted); }
/* ── 预览 PDF 图标 ──────────────────── */
.preview-pdf-icon {
  width: 70px; height: 84px;
  background: #e53935; border-radius: 8px;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 6px;
}
.preview-pdf-top { font-size: 18px; font-weight: 900; color: #fff; letter-spacing: 1px; }
.preview-pdf-lines { display: flex; flex-direction: column; gap: 3px; width: 42px; }
.preview-pdf-lines span { display: block; height: 2.5px; border-radius: 1.5px; background: rgba(255,255,255,0.55); }
/* 操作按钮（悬浮时显示） */
.card-actions {
  position: absolute; top: 6px; right: 6px;
  display: none; flex-direction: column; gap: 4px;
}
.resource-card:hover .card-actions { display: flex; }

.pagination { margin-top: 16px; display: flex; justify-content: center; }

/* ── 类型管理 ──────────────────────────────── */
.type-manage { display: flex; flex-direction: column; gap: 6px; }
.type-row    { display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; border: 1px solid var(--border); border-radius: 8px; }
.type-row-name { font-size: 13px; color: var(--text-primary); }
.type-row-actions { display: flex; gap: 6px; }

/* ── 上传 ──────────────────────────────────── */
.upload-area     { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; }
.upload-filename { font-size: 12px; color: var(--text-muted); }
.upload-progress-wrap { width: 100%; }
.upload-progress-label { display: flex; justify-content: space-between; font-size: 12px; color: #6b5e4e; margin-bottom: 4px; }
.upload-progress-pct { font-weight: 600; color: #c4883a; }
.upload-progress-bar { width: 100%; height: 6px; background: #e0d4c0; border-radius: 3px; overflow: hidden; }
.upload-progress-fill { height: 100%; background: #c4883a; border-radius: 3px; transition: width 0.3s ease; }
.upload-size-info { font-size: 12px; color: #6b5e4e; }
.upload-size-ratio { color: #2e7d32; font-weight: 600; }

/* ── 封面上传 ────────────────────────────────── */
.cover-upload-area { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; }
.cover-upload-hint { font-size: 12px; color: var(--text-muted); }
.cover-preview-wrap { position: relative; display: inline-flex; flex-direction: column; gap: 6px; align-items: flex-start; }
.cover-preview-img { width: 120px; height: 80px; object-fit: cover; border-radius: 8px; border: 1px solid var(--border); display: block; }
.cover-remove-btn { align-self: flex-start; }

/* ── 型号级联选择器 ──────────────────────────── */
.model-select-wrap { width: 100%; display: flex; flex-direction: column; gap: 8px; }
/* 隐藏 cascader 内部已选 tag，只保留输入框 */
:deep(.model-cascader .el-cascader__tags .el-tag) { display: none; }
:deep(.model-cascader .el-cascader__tags) { flex-wrap: nowrap; }
:deep(.model-cascader .el-cascader__search-input) { min-width: 100% !important; }
/* 选中型号的外部 chip 列表 */
.model-chips { display: flex; flex-direction: column; gap: 4px; }
.model-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 8px 2px 10px;
  background: #eef4ff; border: 1px solid #c3d8f8;
  border-radius: 20px; cursor: default;
  align-self: flex-start;
}
.chip-code {
  font-size: 12px; font-weight: 700; color: #2a5caa;
  white-space: nowrap; flex-shrink: 0;
}
.chip-name {
  font-size: 11px; color: #5a7ab8;
  white-space: nowrap;
}
.chip-remove {
  font-size: 13px; line-height: 1; color: #8aabdc;
  cursor: pointer; flex-shrink: 0; margin-left: 2px;
  transition: color 0.15s;
}
.chip-remove:hover { color: #e53935; }

/* ── 标签分类选择器 ─────────────────────────── */
.tag-group-hd {
  display: flex !important; align-items: center; gap: 6px;
  font-size: 11px !important; font-weight: 600 !important;
  color: var(--text-muted) !important; cursor: pointer !important;
  padding: 4px 12px !important;
}
.tag-group-dot  { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.tag-group-name { flex: 1; }
.tag-group-arrow { font-size: 10px; transition: transform 0.2s; }
.tag-group-arrow.collapsed { transform: rotate(-90deg); }
.tag-group-item { padding-left: 28px !important; font-size: 12px !important; }

/* ── 标签字段（简单模式包装）────────────────── */
.tag-field-wrap {
  display: flex; align-items: center; gap: 6px; width: 100%;
}
.tag-field-hint {
  font-size: 11px; color: var(--text-muted); margin-top: 4px;
}
.cond-mode-btn {
  flex-shrink: 0; height: 32px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 7px;
  background: transparent; font-size: 12px; color: var(--text-muted);
  cursor: pointer; white-space: nowrap; transition: all 0.15s;
  font-family: inherit;
}
.cond-mode-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-bg); }

/* ── 关联标签 form-item 标签顶对齐 ─────────── */
:deep(.el-form-item.tag-form-item .el-form-item__label) { align-self: flex-start; padding-top: 6px; }

/* ── 条件构建器 ──────────────────────────────── */
.cond-builder {
  width: 100%;
  border: 1px solid var(--border); border-radius: 10px;
  padding: 10px 12px; background: #faf7f2;
  display: flex; flex-direction: column; gap: 8px;
}
.cond-builder-hd {
  display: flex; align-items: center; justify-content: space-between;
}
.cond-builder-title { font-size: 12px; font-weight: 600; color: #5a4e42; }
.cond-simple-btn {
  font-size: 11px; color: var(--text-muted); background: transparent;
  border: none; cursor: pointer; padding: 0; font-family: inherit;
  text-decoration: underline;
}
.cond-simple-btn:hover { color: var(--accent); }
.cond-formula {
  margin: 4px 0 2px;
  padding: 4px 8px;
  background: rgba(196,136,58,0.07);
  border-left: 2px solid rgba(196,136,58,0.4);
  border-radius: 0 4px 4px 0;
  font-size: 11px; color: #6b4c1e; font-family: monospace;
  word-break: break-all; line-height: 1.6;
}

/* 根级 AND/OR 切换行 */
.cond-op-row { display: flex; gap: 6px; }
.cond-op-btn {
  font-size: 11px; font-weight: 500; padding: 3px 10px; border-radius: 6px;
  border: 1px solid var(--border); background: transparent; color: var(--text-muted);
  cursor: pointer; font-family: inherit; transition: all 0.15s;
}
.cond-op-btn.active { border-color: var(--accent); color: var(--accent); background: var(--accent-bg); font-weight: 600; }
.cond-op-btn--sm { font-size: 10px; padding: 2px 7px; }

/* 条件项 */
.cond-item-wrap { display: flex; }

/* tag chip */
.cond-item-wrap,
.cond-group-tag-wrap {
  display: inline-flex; align-items: center; gap: 2px;
}
.cond-tag-chip {
  display: inline-flex; align-items: center; gap: 2px;
  padding: 1px 6px 1px 6px; border-radius: 4px;
  background: rgba(196,136,58,0.12); border: 1px solid rgba(196,136,58,0.3);
  font-size: 12px; color: #6b4c1e; line-height: 1.6;
  cursor: default;
}
.cond-tag-chip.is-not {
  background: rgba(220,60,50,0.07); border-color: rgba(220,60,50,0.3); color: #9a2a20;
}
.cond-tag-chip.is-not .cond-tag-text { text-decoration: line-through; }
/* NOT badge（仅当 not=true 时显示在 chip 内） */
.cond-not-badge {
  font-size: 9px; font-weight: 700; padding: 0 3px; border-radius: 2px;
  background: rgba(220,60,50,0.15); color: #c84030;
  cursor: pointer; flex-shrink: 0; line-height: 1.4;
}
.cond-not-badge:hover { background: rgba(220,60,50,0.25); }
/* ⊘ 排除切换图标：默认透明，悬停 chip 外容器时显示 */
.cond-not-toggle {
  opacity: 0; pointer-events: none;
  font-size: 13px; color: #c0b0a0; cursor: pointer;
  transition: opacity 0.15s, color 0.15s; flex-shrink: 0; line-height: 1; user-select: none;
}
.cond-item-wrap:hover .cond-not-toggle,
.cond-group-tag-wrap:hover .cond-not-toggle { opacity: 1; pointer-events: auto; }
.cond-not-toggle:hover { color: #c84030; }
.cond-not-toggle.active { opacity: 1; pointer-events: auto; color: #c84030; }
.cond-tag-text { flex: 1; }
.cond-chip-remove {
  cursor: pointer; font-size: 11px; line-height: 1; color: #b08050;
  margin-left: 1px; transition: color 0.15s; flex-shrink: 0;
}
.cond-chip-remove:hover { color: #d05a3c; }

/* 子条件组 */
.cond-subgroup {
  width: 100%; border: 1px solid #e0d4c0; border-radius: 8px;
  background: #fff; overflow: hidden;
}
.cond-subgroup-hd {
  display: flex; align-items: center; gap: 5px;
  padding: 5px 8px; background: #f5f0e8; border-bottom: 1px solid #e8dfd0;
}
.cond-subgroup-del {
  margin-left: auto; font-size: 10px; color: #c06050;
  background: transparent; border: none; cursor: pointer; font-family: inherit;
  padding: 0; transition: color 0.15s;
}
.cond-subgroup-del:hover { color: #e03020; }
.cond-subgroup-body {
  padding: 6px 8px; display: flex; flex-wrap: wrap; gap: 5px; align-items: center;
}

/* 根级操作按钮行 */
.cond-root-actions { display: flex; align-items: center; gap: 8px; margin-top: 2px; }

.cond-add-tag-btn {
  font-size: 12px; color: var(--accent); cursor: pointer;
  padding: 1px 6px; border-radius: 4px;
  border: 1px dashed rgba(196,136,58,0.5);
  transition: all 0.15s; white-space: nowrap; display: inline-flex;
  align-items: center; line-height: 1.6;
}
.cond-add-tag-btn:hover { background: var(--accent-bg); }

.cond-add-group-btn {
  font-size: 11px; color: var(--text-muted);
  background: transparent; border: 1px dashed var(--border);
  border-radius: 6px; padding: 3px 10px; cursor: pointer;
  font-family: inherit; transition: all 0.15s;
}
.cond-add-group-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-bg); }

/* ── 标签 popover 内容 ───────────────────────── */
:global(.tag-popover) { padding: 8px !important; }
.tag-pop-search { margin-bottom: 6px; }
.tag-pop-list { max-height: 200px; overflow-y: auto; }
.tag-pop-list::-webkit-scrollbar { width: 4px; }
.tag-pop-list::-webkit-scrollbar-track { background: transparent; }
.tag-pop-list::-webkit-scrollbar-thumb { background: #e0d4c0; border-radius: 2px; }
.tag-pop-cat {
  font-size: 10px; font-weight: 600; color: var(--text-muted);
  padding: 4px 6px 2px; text-transform: uppercase; letter-spacing: 0.5px;
}
.tag-pop-item {
  padding: 5px 8px; font-size: 12px; color: var(--text-primary);
  border-radius: 5px; cursor: pointer; transition: background 0.1s;
}
.tag-pop-item:hover { background: var(--accent-bg); color: var(--accent); }
.tag-pop-empty { font-size: 12px; color: var(--text-muted); text-align: center; padding: 12px 0; }
</style>
