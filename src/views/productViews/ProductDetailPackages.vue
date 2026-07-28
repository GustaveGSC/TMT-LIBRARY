<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Folder, Search, Close, Edit, Delete } from '@element-plus/icons-vue'
import http from '@/api/http'
import { usePermission } from '@/composables/usePermission'
import { useCategoryTree } from '@/composables/useCategoryTree'
import MediaViewer from '@/components/common/MediaViewer.vue'

// ── 权限 ──────────────────────────────────────────
const { canEditProduct } = usePermission()

// ── 品类/系列/型号级联（复用产品库全局缓存） ──────
const { categoryTree, loadCategoryTreeOnce } = useCategoryTree()
const cascaderOptions = computed(() =>
  categoryTree.value.map(cat => ({
    value: cat.id, label: cat.name,
    children: (cat.series || []).map(ser => ({
      value: ser.id, label: ser.name,
      children: (ser.models || []).map(m => ({
        value: m.id, label: m.model_code + (m.name ? ' ' + m.name : ''),
      })),
    })),
  })),
)
function modelIdsToPaths(modelIds) {
  const paths = []
  for (const cat of categoryTree.value)
    for (const ser of cat.series || [])
      for (const m of ser.models || [])
        if (modelIds.includes(m.id)) paths.push([cat.id, ser.id, m.id])
  return paths
}

// ── 标签（简单多选，OR 语义：产品带任一标签即匹配）──
const allTags = ref([])
async function loadAllTags() {
  const res = await http.get('/api/product/tags')
  if (res.success) allTags.value = res.data || []
}

// ── 包列表 ──────────────────────────────────────────
const packages     = ref([])
const packagesTotal = ref(0)
const packagesLoading = ref(false)
const search = ref('')
let searchTimer = null
function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(loadPackages, 300)
}

async function loadPackages() {
  packagesLoading.value = true
  try {
    const res = await http.get('/api/product-detail-packages', { params: { search: search.value || undefined, size: 100 } })
    if (res.success) { packages.value = res.data.items; packagesTotal.value = res.data.total }
  } finally {
    packagesLoading.value = false
  }
}

async function createPackage() {
  try {
    const { value: name } = await ElMessageBox.prompt('包名称', '新建产品详情包', {
      confirmButtonText: '创建', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
    })
    const res = await http.post('/api/product-detail-packages', { name })
    if (res.success) { ElMessage.success('已创建'); await loadPackages(); openDetail(res.data) }
    else ElMessage.error(res.message || '创建失败')
  } catch { /* 用户取消 */ }
}

// ── 包详情弹窗 ──────────────────────────────────────
const detailVisible = ref(false)
const detailPackage = ref(null)
const detailMedia   = ref([])
const detailNameEdit = ref('')
const detailCascaderValue = ref([])
const detailTagIds  = ref([])
const detailSaving  = ref(false)

async function openDetail(pkg) {
  await Promise.all([loadCategoryTreeOnce(), allTags.value.length ? Promise.resolve() : loadAllTags()])
  detailPackage.value = pkg
  detailNameEdit.value = pkg.name
  detailCascaderValue.value = modelIdsToPaths(pkg.model_ids || [])
  detailTagIds.value = pkg.tag_ids || []
  detailVisible.value = true
  await refreshDetailMedia()
}

async function refreshDetailMedia() {
  if (!detailPackage.value) return
  const res = await http.get(`/api/product-detail-packages/${detailPackage.value.id}`)
  if (res.success) detailMedia.value = res.data.media || []
}

async function saveDetailName() {
  if (!detailNameEdit.value.trim()) { ElMessage.warning('名称不能为空'); return }
  const res = await http.put(`/api/product-detail-packages/${detailPackage.value.id}`, { name: detailNameEdit.value.trim() })
  if (res.success) { ElMessage.success('已保存'); detailPackage.value.name = res.data.name; await loadPackages() }
  else ElMessage.error(res.message || '保存失败')
}

async function onCascaderChange(paths) {
  detailCascaderValue.value = paths
  const modelIds = (paths || []).map(p => p[p.length - 1])
  detailSaving.value = true
  try {
    const res = await http.put(`/api/product-detail-packages/${detailPackage.value.id}/models`, { model_ids: modelIds })
    if (!res.success) ElMessage.error(res.message || '设置型号范围失败')
  } finally {
    detailSaving.value = false
  }
}

async function onTagIdsChange(tagIds) {
  detailTagIds.value = tagIds
  detailSaving.value = true
  try {
    const res = await http.put(`/api/product-detail-packages/${detailPackage.value.id}/tags`, {
      tag_ids: tagIds, tag_condition: tagIds.length ? { op: 'OR', items: tagIds.map(id => ({ tag_id: id })) } : null,
    })
    if (!res.success) ElMessage.error(res.message || '设置标签范围失败')
  } finally {
    detailSaving.value = false
  }
}

async function deletePackage(pkg) {
  try {
    await ElMessageBox.confirm(`确认删除包「${pkg.name}」？包内全部图片/视频将一并删除，此操作不可撤销。`, '删除确认', { type: 'warning' })
  } catch { return }
  const res = await http.delete(`/api/product-detail-packages/${pkg.id}`)
  if (res.success) {
    ElMessage.success('已删除')
    if (detailPackage.value?.id === pkg.id) detailVisible.value = false
    await loadPackages()
  } else {
    ElMessage.error(res.message || '删除失败')
  }
}

// ── 拖拽/选择上传 ────────────────────────────────────
const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'webp'])
const VIDEO_EXTS  = new Set(['mp4', 'mov', 'webm'])
const isDragOver = ref(false)
const uploading  = ref(false)
const uploadDone = ref(0)
const uploadTotal = ref(0)
const fileInput = ref(null)

function extOf(name) {
  const idx = name.lastIndexOf('.')
  return idx === -1 ? '' : name.slice(idx + 1).toLowerCase()
}
function isMediaFile(name) {
  const ext = extOf(name)
  return IMAGE_EXTS.has(ext) || VIDEO_EXTS.has(ext)
}

function openFilePicker() { fileInput.value?.click() }
function onFileInputChange(e) {
  const files = Array.from(e.target.files || [])
  e.target.value = ''
  uploadFiles(files)
}
function onDragOver(e) { e.preventDefault(); isDragOver.value = true }
function onDragLeave() { isDragOver.value = false }
function onDrop(e) {
  e.preventDefault()
  isDragOver.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  uploadFiles(files)
}

async function uploadFiles(files) {
  const valid = files.filter(f => isMediaFile(f.name))
  const skipped = files.length - valid.length
  if (skipped) ElMessage.warning(`已跳过 ${skipped} 个不支持的文件（仅支持图片/视频）`)
  if (!valid.length) return

  uploading.value = true
  uploadDone.value = 0
  uploadTotal.value = valid.length
  try {
    const presignRes = await http.post(`/api/product-detail-packages/${detailPackage.value.id}/media/presign`, {
      files: valid.map(f => ({ ext: extOf(f.name), file_size: f.size, original_filename: f.name })),
    })
    if (!presignRes.success) { ElMessage.error(presignRes.message || '获取上传签名失败'); return }
    const items = presignRes.data.items
    const confirmed = []
    for (let i = 0; i < items.length; i++) {
      const item = items[i]
      try {
        const putRes = await fetch(item.presign_url, { method: 'PUT', headers: item.required_headers, body: valid[i] })
        if (!putRes.ok) throw new Error('上传失败')
        confirmed.push({ storage_key: item.storage_key, original_filename: item.original_filename, file_size: item.file_size })
      } catch { /* 单个文件失败跳过，不中断整批 */ }
      uploadDone.value++
    }
    if (confirmed.length) {
      const confirmRes = await http.post(`/api/product-detail-packages/${detailPackage.value.id}/media/confirm`, { files: confirmed })
      if (confirmRes.success) {
        detailMedia.value = [...detailMedia.value, ...confirmRes.data]
        await loadPackages()
      } else {
        ElMessage.error(confirmRes.message || '确认上传失败')
      }
    }
    if (confirmed.length < valid.length) {
      ElMessage.warning(`成功 ${confirmed.length} 个，失败 ${valid.length - confirmed.length} 个`)
    } else {
      ElMessage.success(`已上传 ${confirmed.length} 个文件`)
    }
  } finally {
    uploading.value = false
  }
}

// ── 媒体查看/删除 ────────────────────────────────────
const viewerVisible = ref(false)
const viewerIndex   = ref(0)
const viewerItems = computed(() => detailMedia.value.map(m => ({
  id: m.id, file_type: m.file_type, oss_url: m.oss_url, original_filename: m.original_filename,
})))
function openViewer(mediaId) {
  viewerIndex.value = Math.max(0, detailMedia.value.findIndex(m => m.id === mediaId))
  viewerVisible.value = true
}
async function deleteMedia(item) {
  const res = await http.delete(`/api/product-detail-packages/${detailPackage.value.id}/media/${item.id}`)
  if (!res.success) { ElMessage.error(res.message || '删除失败'); return false }
  detailMedia.value = detailMedia.value.filter(m => m.id !== item.id)
  await loadPackages()
  return true
}

onMounted(() => { loadPackages(); loadAllTags(); loadCategoryTreeOnce() })
</script>

<template>
  <div class="pkg-page">
    <!-- 工具栏 -->
    <div class="pkg-toolbar">
      <el-input v-model="search" placeholder="搜索包名称…" :prefix-icon="Search" clearable style="width:260px" @input="onSearchInput" />
      <el-button v-if="canEditProduct" type="primary" :icon="Plus" @click="createPackage">新建包</el-button>
    </div>

    <!-- 文件夹网格 -->
    <div v-loading="packagesLoading" class="pkg-grid">
      <div v-if="!packagesLoading && !packages.length" class="pkg-empty">暂无产品详情包</div>
      <div v-for="pkg in packages" :key="pkg.id" class="pkg-card" @click="openDetail(pkg)">
        <div class="pkg-icon-wrap">
          <el-icon class="pkg-folder-icon"><Folder /></el-icon>
          <img v-if="pkg.cover_thumbnail" :src="pkg.cover_thumbnail" class="pkg-cover-overlay" />
        </div>
        <div class="pkg-name" :title="pkg.name">{{ pkg.name }}</div>
        <div class="pkg-meta">{{ pkg.media_count }} 个文件</div>
      </div>
    </div>

    <!-- 包详情弹窗 -->
    <el-dialog v-model="detailVisible" width="720" align-center destroy-on-close>
      <template #header>
        <div class="pkg-detail-hd">
          <el-input v-model="detailNameEdit" size="small" style="width:260px" :disabled="!canEditProduct" @blur="saveDetailName" @keyup.enter="saveDetailName" />
          <el-button v-if="canEditProduct" size="small" type="danger" plain :icon="Delete" @click="deletePackage(detailPackage)">删除包</el-button>
        </div>
      </template>

      <div v-if="canEditProduct" class="pkg-scope">
        <div class="pkg-scope-row">
          <span class="pkg-scope-lbl">适用型号</span>
          <el-cascader
            :model-value="detailCascaderValue" :options="cascaderOptions" multiple
            filterable clearable collapse-tags collapse-tags-tooltip
            placeholder="选择型号，该型号产品自动展示此包" style="flex:1"
            @change="onCascaderChange"
          />
        </div>
        <div class="pkg-scope-row">
          <span class="pkg-scope-lbl">适用标签</span>
          <el-select
            :model-value="detailTagIds" multiple filterable clearable
            placeholder="带任一标签的产品自动展示此包" style="flex:1"
            @change="onTagIdsChange"
          >
            <el-option v-for="t in allTags" :key="t.id" :value="t.id" :label="t.name" />
          </el-select>
        </div>
      </div>

      <!-- 拖拽上传区 -->
      <div
        v-if="canEditProduct"
        class="pkg-dropzone" :class="{ 'pkg-dropzone--over': isDragOver }"
        @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop" @click="openFilePicker"
      >
        <input ref="fileInput" type="file" multiple accept=".png,.jpg,.jpeg,.webp,.mp4,.mov,.webm" style="display:none" @change="onFileInputChange" />
        <span v-if="!uploading">拖拽图片/视频到此处，或点击选择文件（支持多选）</span>
        <span v-else>上传中… {{ uploadDone }}/{{ uploadTotal }}</span>
      </div>

      <!-- 媒体网格 -->
      <div class="pkg-media-grid">
        <div v-if="!detailMedia.length" class="pkg-empty">包内暂无图片/视频</div>
        <div v-for="m in detailMedia" :key="m.id" class="pkg-media-card" @click="openViewer(m.id)">
          <img v-if="m.file_type === 'image'" :src="m.oss_url" class="pkg-media-thumb" loading="lazy" />
          <video v-else :src="m.oss_url" class="pkg-media-thumb" preload="metadata" muted />
        </div>
      </div>
    </el-dialog>

    <MediaViewer
      v-model="viewerVisible" :items="viewerItems" :initial-index="viewerIndex"
      :delete-handler="canEditProduct ? deleteMedia : null"
    />
  </div>
</template>

<style scoped>
.pkg-page { flex: 1; display: flex; flex-direction: column; overflow: hidden; padding: 16px 20px; }
.pkg-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; flex-shrink: 0; }
.pkg-grid {
  flex: 1; overflow-y: auto; display: flex; flex-wrap: wrap; gap: 18px; align-content: flex-start;
}
.pkg-empty { color: var(--text-muted); font-size: 13px; padding: 30px; width: 100%; text-align: center; }
.pkg-card {
  width: 120px; display: flex; flex-direction: column; align-items: center; gap: 4px;
  cursor: pointer; padding: 8px; border-radius: 10px; transition: background 0.15s;
}
.pkg-card:hover { background: rgba(196,136,58,0.08); }
.pkg-icon-wrap { position: relative; width: 72px; height: 60px; }
.pkg-folder-icon { font-size: 60px; color: #e8b84b; filter: drop-shadow(0 2px 2px rgba(0,0,0,0.15)); }
.pkg-cover-overlay {
  position: absolute; left: 14px; top: 20px; width: 44px; height: 32px;
  object-fit: cover; border-radius: 3px; border: 1px solid rgba(255,255,255,0.8);
}
.pkg-name { font-size: 12px; color: var(--text-primary); text-align: center; max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pkg-meta { font-size: 11px; color: var(--text-muted); }

.pkg-detail-hd { display: flex; align-items: center; justify-content: space-between; gap: 10px; width: 100%; padding-right: 24px; }
.pkg-scope { display: flex; flex-direction: column; gap: 10px; margin-bottom: 14px; }
.pkg-scope-row { display: flex; align-items: center; gap: 10px; }
.pkg-scope-lbl { flex-shrink: 0; width: 64px; font-size: 12px; color: var(--text-secondary); }

.pkg-dropzone {
  border: 2px dashed var(--border); border-radius: 10px; padding: 20px; text-align: center;
  color: var(--text-muted); font-size: 13px; cursor: pointer; margin-bottom: 14px; transition: all 0.15s;
}
.pkg-dropzone--over { border-color: var(--accent); background: rgba(196,136,58,0.06); color: var(--accent); }

.pkg-media-grid { display: flex; flex-wrap: wrap; gap: 10px; max-height: 320px; overflow-y: auto; }
.pkg-media-card {
  width: 100px; aspect-ratio: 4/3; border-radius: 8px; border: 1px solid var(--border);
  overflow: hidden; cursor: pointer; background: #f5f0e8;
}
.pkg-media-thumb { width: 100%; height: 100%; object-fit: contain; background: #fff; display: block; }
</style>
