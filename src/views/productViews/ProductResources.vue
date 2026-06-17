<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted } from 'vue'
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
  uploading, uploadFile,
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

async function loadAllTags() {
  if (tagCategories.value.length || tagOptionsFlat.value.length) return
  const [catRes, tagRes] = await Promise.all([
    http.get('/api/product/tags/categories/'),
    http.get('/api/product/tags'),
  ])
  if (catRes.success) tagCategories.value = catRes.data || []
  if (tagRes.success) tagOptionsFlat.value = (tagRes.data || []).filter(t => !t.category_id)
}

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
  resourceForm.value = { title: '', type_id: null, url: '', source: 'external', file_type: 'link', storage_key: null, original_filename: null, description: '', tag_ids: [], model_ids: [] }
  cascaderModelValue.value = []
  uploadMode.value = 'link'
  loadAllTags(); loadCategoryTree()
  resourceDialogVisible.value = true
}
async function openResourceEdit(r) {
  editingResourceId.value = r.id
  resourceDialogTitle.value = '编辑资料'
  resourceForm.value = {
    title: r.title, type_id: r.type_id, url: r.url, source: r.source,
    file_type: r.file_type, storage_key: r.storage_key,
    original_filename: r.original_filename, description: r.description || '',
    tag_ids: (r.tags || []).map(t => t.id),
    model_ids: r.model_ids || [],
  }
  uploadMode.value = r.source === 'oss' ? 'file' : 'link'
  await Promise.all([loadAllTags(), loadCategoryTree()])
  cascaderModelValue.value = modelIdsToPaths(resourceForm.value.model_ids)
  resourceDialogVisible.value = true
}

async function pickFile() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pdf,.png,.jpg,.jpeg,.webp'
  input.onchange = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    const result = await uploadFile(file)
    if (result) {
      resourceForm.value.url               = result.url
      resourceForm.value.storage_key       = result.storage_key
      resourceForm.value.file_type         = result.file_type
      resourceForm.value.original_filename = result.original_filename
      resourceForm.value.source            = 'oss'
    }
  }
  input.click()
}

async function submitResource() {
  if (!resourceForm.value.title.trim()) { ElMessage.warning('请填写标题'); return }
  if (!resourceForm.value.type_id) { ElMessage.warning('请选择资料类型'); return }
  const payload = { ...resourceForm.value }
  if (uploadMode.value === 'link') {
    payload.source      = 'external'
    payload.storage_key = null
    // 根据 url 后缀推断 file_type
    if (!payload.file_type || payload.file_type === 'link') {
      const ext = (payload.url || '').split('.').pop().toLowerCase()
      if (ext === 'pdf') payload.file_type = 'pdf'
      else if (['png','jpg','jpeg','webp'].includes(ext)) payload.file_type = 'image'
      else payload.file_type = 'link'
    }
  }
  const tagIds   = payload.tag_ids   || []
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
      setResourceTags(newId, tagIds),
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

function openPreview(r) {
  previewResource.value = r
  previewVisible.value  = true
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

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
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
    <el-dialog v-model="previewVisible" :title="previewResource?.title" width="760" align-center append-to-body>
      <div class="preview-body">
        <img
          v-if="previewResource?.file_type === 'image'"
          :src="previewResource?.url"
          style="max-width:100%;max-height:60vh;object-fit:contain;display:block;margin:0 auto;"
        />
        <div v-else style="text-align:center;padding:50px 0;color:#8a7a6a;font-size:13px;">
          <!-- PDF icon -->
          <div v-if="previewResource?.file_type === 'pdf'" style="display:flex;justify-content:center;margin-bottom:12px;">
            <div class="preview-pdf-icon">
              <div class="preview-pdf-top">PDF</div>
              <div class="preview-pdf-lines"><span></span><span></span><span></span></div>
            </div>
          </div>
          <div v-else style="font-size:40px;margin-bottom:12px;">
            {{ previewResource?.file_type === 'video' ? '🎬' : '🔗' }}
          </div>
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
          <el-button @click="openInTab(previewResource)">在新标签页打开</el-button>
          <el-button type="primary" @click="downloadResource(previewResource)">下载</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- ── 新建/编辑资料弹窗 ──────────────────────── -->
    <el-dialog v-model="resourceDialogVisible" :title="resourceDialogTitle" width="560" align-center :close-on-click-modal="false">
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
            <el-button :loading="uploading" @click="pickFile">选择文件（PDF / 图片）</el-button>
            <span v-if="resourceForm.original_filename" class="upload-filename">{{ resourceForm.original_filename }}</span>
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
        <el-form-item label="关联标签">
          <el-select
            v-model="resourceForm.tag_ids"
            multiple
            placeholder="带该标签的产品将自动包含此资料"
            style="width:100%"
            :filter-method="q => tagSearchQuery = q"
            filterable
          >
            <!-- 分类标签 -->
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
            <!-- 未分类标签 -->
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
  object-fit: cover; display: block;
}
.card-icon-wrap {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  font-size: 40px;
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
.upload-area     { display: flex; align-items: center; gap: 10px; }
.upload-filename { font-size: 12px; color: var(--text-muted); }

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
</style>
