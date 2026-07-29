<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Folder, Search, ArrowLeft, Delete, Edit, Check, Close } from '@element-plus/icons-vue'
import http from '@/api/http'
import { usePermission } from '@/composables/usePermission'
import { useCategoryTree } from '@/composables/useCategoryTree'
import { useFinishedStore } from '@/stores/product'
import MediaViewer from '@/components/common/MediaViewer.vue'

const finishedStore = useFinishedStore()

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
// checkStrictly 模式下，勾选路径可以停在品类/系列/型号任意一级，需要把三个维度的
// id 各自还原成对应深度的路径，再合并成级联组件的回显值
function scopeIdsToPaths({ categoryIds = [], seriesIds = [], modelIds = [] }) {
  const paths = []
  for (const cat of categoryTree.value) {
    if (categoryIds.includes(cat.id)) paths.push([cat.id])
    for (const ser of cat.series || []) {
      if (seriesIds.includes(ser.id)) paths.push([cat.id, ser.id])
      for (const m of ser.models || [])
        if (modelIds.includes(m.id)) paths.push([cat.id, ser.id, m.id])
    }
  }
  return paths
}

// ── 标签（简单多选，OR 语义：产品带任一标签即匹配）──
// 候选面板复用产品库表格「筛选标签」的分类可折叠样式，数据源共享同一个 store
const tagOptions    = computed(() => finishedStore.tagOptions)
const tagCategories = computed(() => finishedStore.tagCategories)
const tagSearchQuery = ref('')
function onTagFilterMethod(q) { tagSearchQuery.value = q }
function onTagSelectClose()   { tagSearchQuery.value = '' }
// 集合记录"已展开"的分类，默认全部折叠（与产品库「筛选标签」一致）
const collapsedTagCats = ref(new Set())
function toggleTagCat(id) {
  const s = new Set(collapsedTagCats.value)
  s.has(id) ? s.delete(id) : s.add(id)
  collapsedTagCats.value = s
}
function isTagCatCollapsed(id) {
  if (tagSearchQuery.value.trim()) return false
  return !collapsedTagCats.value.has(id)
}
const filteredTagGroups = computed(() => {
  const q = tagSearchQuery.value.trim().toLowerCase()
  return tagCategories.value
    .map(cat => ({ ...cat, filteredTags: (cat.tags || []).filter(t => !q || t.name.toLowerCase().includes(q)) }))
    .filter(g => g.filteredTags.length > 0)
})
const filteredUncategorizedTags = computed(() => {
  const q = tagSearchQuery.value.trim().toLowerCase()
  return tagOptions.value.filter(t => !t.category_id && (!q || t.name.toLowerCase().includes(q)))
})

// ── 文件夹列表 ────────────────────────────────────────
const folders      = ref([])
const foldersTotal  = ref(0)
const foldersLoading = ref(false)
const search = ref('')
let searchTimer = null
function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(loadFolders, 300)
}

async function loadFolders() {
  foldersLoading.value = true
  try {
    const res = await http.get('/api/product-detail-packages', { params: { search: search.value || undefined, size: 100 } })
    if (res.success) { folders.value = res.data.items; foldersTotal.value = res.data.total }
  } finally {
    foldersLoading.value = false
  }
}

async function createFolder() {
  try {
    const { value: name } = await ElMessageBox.prompt('文件夹名称', '新建产品详情文件夹', {
      confirmButtonText: '创建', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
    })
    const res = await http.post('/api/product-detail-packages', { name })
    if (res.success) { ElMessage.success('已创建'); await loadFolders(); openFolder(res.data) }
    else ElMessage.error(res.message || '创建失败')
  } catch { /* 用户取消 */ }
}

// ── 打开文件夹（双击进入，原地切换视图，不是弹窗）─────
const insideFolder = ref(false)   // false=文件夹网格视图，true=文件夹内部视图
const activeFolder = ref(null)
const activeMedia   = ref([])
const nameEdit      = ref('')
const cascaderValue  = ref([])
const tagIds         = ref([])
const scopeSaving    = ref(false)

async function openFolder(folder) {
  await Promise.all([loadCategoryTreeOnce(), finishedStore.loadTagOptions()])
  activeFolder.value = folder
  nameEdit.value = folder.name
  cascaderValue.value = scopeIdsToPaths({
    categoryIds: folder.category_ids || [], seriesIds: folder.series_ids || [], modelIds: folder.model_ids || [],
  })
  tagIds.value = folder.tag_ids || []
  scopeEditing.value = false
  insideFolder.value = true
  await refreshActiveMedia()
}

function backToGrid() {
  insideFolder.value = false
  activeFolder.value = null
  activeMedia.value = []
}

async function refreshActiveMedia() {
  if (!activeFolder.value) return
  const res = await http.get(`/api/product-detail-packages/${activeFolder.value.id}`)
  if (res.success) activeMedia.value = res.data.media || []
}

async function saveName() {
  if (!nameEdit.value.trim()) { ElMessage.warning('名称不能为空'); return }
  const res = await http.put(`/api/product-detail-packages/${activeFolder.value.id}`, { name: nameEdit.value.trim() })
  if (res.success) { ElMessage.success('已保存'); activeFolder.value.name = res.data.name; await loadFolders() }
  else ElMessage.error(res.message || '保存失败')
}

// 适用范围整体走"编辑/确认/取消"：非编辑状态下级联/标签都禁用，点「编辑」才能改；
// 「确认」一次性保存型号/系列/品类/标签四项；「取消」丢弃改动，回退到编辑前的快照
const scopeEditing  = ref(false)
let scopeSnapshot   = null
function startScopeEdit() {
  scopeSnapshot = { cascaderValue: [...cascaderValue.value], tagIds: [...tagIds.value] }
  scopeEditing.value = true
}
function cancelScopeEdit() {
  if (scopeSnapshot) { cascaderValue.value = scopeSnapshot.cascaderValue; tagIds.value = scopeSnapshot.tagIds }
  scopeSnapshot = null
  scopeEditing.value = false
}
function onCascaderChange(paths) {
  cascaderValue.value = paths
}
function onTagIdsChange(ids) {
  tagIds.value = ids
}
async function confirmScopeEdit() {
  // checkStrictly 下路径深度即代表所选层级：1=品类，2=系列，3=型号
  const categoryIds = (cascaderValue.value || []).filter(p => p.length === 1).map(p => p[0])
  const seriesIds   = (cascaderValue.value || []).filter(p => p.length === 2).map(p => p[1])
  const modelIds    = (cascaderValue.value || []).filter(p => p.length === 3).map(p => p[2])
  scopeSaving.value = true
  try {
    const [modelRes, seriesRes, categoryRes, tagRes] = await Promise.all([
      http.put(`/api/product-detail-packages/${activeFolder.value.id}/models`, { model_ids: modelIds }),
      http.put(`/api/product-detail-packages/${activeFolder.value.id}/series`, { series_ids: seriesIds }),
      http.put(`/api/product-detail-packages/${activeFolder.value.id}/categories`, { category_ids: categoryIds }),
      http.put(`/api/product-detail-packages/${activeFolder.value.id}/tags`, {
        tag_ids: tagIds.value,
        tag_condition: tagIds.value.length ? { op: 'OR', items: tagIds.value.map(id => ({ tag_id: id })) } : null,
      }),
    ])
    const failed = [modelRes, seriesRes, categoryRes, tagRes].find(r => !r.success)
    if (failed) { ElMessage.error(failed.message || '设置适用范围失败'); return }
    activeFolder.value.model_ids    = modelIds
    activeFolder.value.series_ids   = seriesIds
    activeFolder.value.category_ids = categoryIds
    activeFolder.value.tag_ids      = tagIds.value
    ElMessage.success('已保存')
    scopeSnapshot = null
    scopeEditing.value = false
  } finally {
    scopeSaving.value = false
  }
}

async function deleteFolder(folder) {
  try {
    await ElMessageBox.confirm(`确认删除文件夹「${folder.name}」？文件夹内全部图片/视频将一并删除，此操作不可撤销。`, '删除确认', { type: 'warning' })
  } catch { return }
  const res = await http.delete(`/api/product-detail-packages/${folder.id}`)
  if (res.success) {
    ElMessage.success('已删除')
    if (activeFolder.value?.id === folder.id) backToGrid()
    await loadFolders()
  } else {
    ElMessage.error(res.message || '删除失败')
  }
}

// ── 拖拽/选择上传（直接在文件夹内部进行，不弹面板）───
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
    const presignRes = await http.post(`/api/product-detail-packages/${activeFolder.value.id}/media/presign`, {
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
      const confirmRes = await http.post(`/api/product-detail-packages/${activeFolder.value.id}/media/confirm`, { files: confirmed })
      if (confirmRes.success) {
        activeMedia.value = [...activeMedia.value, ...confirmRes.data]
        await loadFolders()
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
const viewerItems = computed(() => activeMedia.value.map(m => ({
  id: m.id, file_type: m.file_type, oss_url: m.oss_url, original_filename: m.original_filename,
})))
function openViewer(mediaId) {
  viewerIndex.value = Math.max(0, activeMedia.value.findIndex(m => m.id === mediaId))
  viewerVisible.value = true
}
async function deleteMedia(item) {
  const res = await http.delete(`/api/product-detail-packages/${activeFolder.value.id}/media/${item.id}`)
  if (!res.success) { ElMessage.error(res.message || '删除失败'); return false }
  activeMedia.value = activeMedia.value.filter(m => m.id !== item.id)
  await loadFolders()
  return true
}

onMounted(() => { loadFolders(); finishedStore.loadTagOptions(); loadCategoryTreeOnce() })
</script>

<template>
  <div class="pkg-page">
    <!-- ── 文件夹网格视图 ── -->
    <template v-if="!insideFolder">
      <div class="pkg-toolbar">
        <el-input v-model="search" placeholder="搜索文件夹名称…" :prefix-icon="Search" clearable style="width:260px" @input="onSearchInput" />
        <el-button v-if="canEditProduct" type="primary" :icon="Plus" @click="createFolder">新建文件夹</el-button>
      </div>

      <div v-loading="foldersLoading" class="pkg-grid">
        <div v-if="!foldersLoading && !folders.length" class="pkg-empty">暂无产品详情文件夹</div>
        <div v-for="folder in folders" :key="folder.id" class="pkg-card" @dblclick="openFolder(folder)">
          <div class="pkg-icon-wrap">
            <el-icon class="pkg-folder-icon"><Folder /></el-icon>
          </div>
          <div class="pkg-name" :title="folder.name">{{ folder.name }}</div>
          <div class="pkg-meta">{{ folder.media_count }} 个文件</div>
        </div>
      </div>
    </template>

    <!-- ── 文件夹内部视图（像 Windows 双击进入文件夹一样原地切换，不是弹窗）── -->
    <template v-else>
      <div class="pkg-inside-hd">
        <el-button text :icon="ArrowLeft" @click="backToGrid">返回</el-button>
        <span class="pkg-inside-title">{{ activeFolder?.name }}</span>
        <span class="pkg-inside-count">{{ activeMedia.length }} 个文件</span>
      </div>

      <div class="pkg-inside-body">
        <!-- 左侧：设置面板，常驻显示（名称/适用范围/删除） -->
        <aside v-if="canEditProduct" class="pkg-scope-panel">
          <div class="pkg-set-title">设置</div>

          <div class="pkg-set-section">
            <div class="pkg-scope-lbl">名称</div>
            <el-input
              v-model="nameEdit" size="small" :disabled="!canEditProduct"
              @blur="saveName" @keyup.enter="saveName"
            />
          </div>

          <div class="pkg-set-section pkg-scope-title">
            适用范围
            <div class="pkg-scope-actions">
              <button v-if="!scopeEditing" class="pkg-icon-btn" title="编辑" @click="startScopeEdit">
                <el-icon><Edit /></el-icon>
              </button>
              <template v-else>
                <button class="pkg-icon-btn" title="取消" :disabled="scopeSaving" @click="cancelScopeEdit">
                  <el-icon><Close /></el-icon>
                </button>
                <button class="pkg-icon-btn pkg-icon-btn--ok" title="确认" :disabled="scopeSaving" @click="confirmScopeEdit">
                  <el-icon><Check /></el-icon>
                </button>
              </template>
            </div>
          </div>
          <div class="pkg-scope-field">
            <div class="pkg-scope-lbl">适用品类/系列/型号</div>
            <el-cascader
              :model-value="cascaderValue" :options="cascaderOptions"
              :props="{ multiple: true, checkStrictly: true }"
              :show-all-levels="false" :disabled="!scopeEditing"
              filterable clearable collapse-tags collapse-tags-tooltip size="small"
              placeholder="选择品类/系列/型号" style="width:100%"
              @change="onCascaderChange"
            />
          </div>
          <div class="pkg-scope-field">
            <div class="pkg-scope-lbl">适用标签</div>
            <el-select
              :model-value="tagIds" multiple filterable clearable collapse-tags collapse-tags-tooltip
              size="small" :disabled="!scopeEditing" :filter-method="onTagFilterMethod"
              @visible-change="v => { if (!v) onTagSelectClose() }"
              placeholder="选择标签" style="width:100%" class="pkg-tag-select"
              @change="onTagIdsChange"
            >
              <template v-for="cat in filteredTagGroups" :key="cat.id">
                <el-option :value="`__cat__${cat.id}`" :label="cat.name" disabled class="tag-group-hd"
                  @mousedown.stop.prevent="toggleTagCat(cat.id)">
                  <span class="tag-group-dot" :style="{ background: cat.color }"></span>
                  <span class="tag-group-name">{{ cat.name }}</span>
                  <span class="tag-group-arrow" :class="{ collapsed: isTagCatCollapsed(cat.id) }">▾</span>
                </el-option>
                <!-- v-show 而非 v-if：折叠分类里的标签选项也要保持挂载，否则 el-select 拿不到
                     未展开过的分类下已选中标签的 label，选中项会显示成原始 id 数字 -->
                <el-option v-for="tag in cat.filteredTags" :key="tag.id"
                  v-show="!isTagCatCollapsed(cat.id)"
                  :value="tag.id" :label="tag.name" class="tag-group-item">
                  <span class="tag-item-dot" :style="{ background: tag.color }"></span>
                  <span>{{ tag.name }}</span>
                </el-option>
              </template>
              <template v-if="filteredUncategorizedTags.length">
                <el-option value="__cat__uncategorized" label="未分类" disabled class="tag-group-hd"
                  @mousedown.stop.prevent="toggleTagCat('uncategorized')">
                  <span class="tag-group-dot" style="background:#bbb"></span>
                  <span class="tag-group-name">未分类</span>
                  <span class="tag-group-arrow" :class="{ collapsed: isTagCatCollapsed('uncategorized') }">▾</span>
                </el-option>
                <el-option v-for="tag in filteredUncategorizedTags" :key="tag.id"
                  v-show="!isTagCatCollapsed('uncategorized')"
                  :value="tag.id" :label="tag.name" class="tag-group-item">
                  <span class="tag-item-dot" :style="{ background: tag.color }"></span>
                  <span>{{ tag.name }}</span>
                </el-option>
              </template>
            </el-select>
          </div>
          <div class="pkg-scope-hint">命中所选品类/系列/型号/标签任意一项的产品，会在其详情页自动展示这个文件夹里的图片/视频；勾选品类/系列后，其下新增的型号也会自动生效</div>

          <div class="pkg-set-section pkg-set-danger">
            <el-button size="small" type="danger" plain :icon="Delete" style="width:100%" @click="deleteFolder(activeFolder)">删除文件夹</el-button>
          </div>
        </aside>

        <!-- 右侧：文件区，整个区域都是拖拽上传目标 -->
        <div
          class="pkg-inside-main"
          :class="{ 'pkg-inside-main--over': isDragOver }"
          @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop"
        >
          <input ref="fileInput" type="file" multiple accept=".png,.jpg,.jpeg,.webp,.mp4,.mov,.webm" style="display:none" @change="onFileInputChange" />
          <div v-if="canEditProduct" class="pkg-upload-hint" @click="openFilePicker">
            <span v-if="!uploading">将图片/视频拖到这里上传，或点击此处选择文件（支持多选）</span>
            <span v-else>上传中… {{ uploadDone }}/{{ uploadTotal }}</span>
          </div>

          <div class="pkg-media-grid">
            <div v-if="!activeMedia.length" class="pkg-empty">文件夹内暂无图片/视频</div>
            <div v-for="m in activeMedia" :key="m.id" class="pkg-media-card" @click="openViewer(m.id)">
              <img v-if="m.file_type === 'image'" :src="m.oss_url" class="pkg-media-thumb" loading="lazy" />
              <video v-else :src="m.oss_url" class="pkg-media-thumb" preload="metadata" muted />
            </div>
          </div>

          <div v-if="isDragOver" class="pkg-drop-overlay">松开鼠标上传</div>
        </div>
      </div>
    </template>

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
  cursor: pointer; padding: 8px; border-radius: 10px; transition: background 0.15s; user-select: none;
}
.pkg-card:hover { background: rgba(196,136,58,0.08); }
.pkg-icon-wrap { position: relative; width: 72px; height: 60px; }
.pkg-folder-icon { font-size: 60px; color: #e8b84b; filter: drop-shadow(0 2px 2px rgba(0,0,0,0.15)); }
.pkg-name { font-size: 12px; color: var(--text-primary); text-align: center; max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pkg-meta { font-size: 11px; color: var(--text-muted); }

/* ── 文件夹内部视图 ── */
.pkg-inside-hd { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; flex-shrink: 0; }
.pkg-inside-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.pkg-inside-count { font-size: 12px; color: var(--text-muted); margin-left: auto; }
.pkg-inside-body { flex: 1; display: flex; gap: 16px; overflow: hidden; }

.pkg-scope-panel {
  width: 220px; flex-shrink: 0; background: #fff; border: 1px solid var(--border); border-radius: 12px;
  padding: 14px; display: flex; flex-direction: column; gap: 4px; overflow-y: auto;
}
.pkg-set-title { font-size: 14px; font-weight: 700; color: var(--text-primary); margin-bottom: 6px; }
.pkg-set-section {
  display: flex; flex-direction: column; gap: 4px;
  padding: 12px 0; border-top: 1px solid #f0e8dc;
}
.pkg-set-section:first-of-type { border-top: none; padding-top: 0; }
.pkg-set-danger { border-top: 1px solid #f0e8dc; }
.pkg-scope-title {
  /* flex-direction 必须显式声明 row：本元素同时带 .pkg-set-section（column），
     不覆盖的话按键会被挤到标题下一行 */
  display: flex; flex-direction: row; align-items: center; justify-content: space-between;
  font-size: 13px; font-weight: 600; color: var(--text-primary);
}
.pkg-scope-actions { display: flex; align-items: center; gap: 10px; }
/* 扁平图标按钮：无背景无边框，只有图标本身（参考设计工具属性面板的图标排布） */
.pkg-icon-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; padding: 0;
  background: none; border: none; cursor: pointer;
  color: var(--text-muted); font-size: 15px;
  transition: color 0.15s;
}
.pkg-icon-btn:hover:not(:disabled) { color: var(--accent); }
.pkg-icon-btn--ok:hover:not(:disabled) { color: #4a9a5a; }
.pkg-icon-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.pkg-scope-field { display: flex; flex-direction: column; gap: 4px; }
.pkg-scope-lbl { font-size: 12px; color: var(--text-secondary); }
.pkg-scope-hint { font-size: 11px; color: var(--text-muted); line-height: 1.5; }

.pkg-inside-main {
  flex: 1; position: relative; overflow-y: auto; border: 1px solid var(--border); border-radius: 12px;
  background: #fff; padding: 14px;
}
.pkg-inside-main--over { border-color: var(--accent); }
.pkg-upload-hint {
  border: 2px dashed var(--border); border-radius: 10px; padding: 16px; text-align: center;
  color: var(--text-muted); font-size: 13px; cursor: pointer; margin-bottom: 14px; transition: all 0.15s;
}
.pkg-upload-hint:hover { border-color: var(--accent); color: var(--accent); }
.pkg-drop-overlay {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  background: rgba(196,136,58,0.1); color: var(--accent); font-size: 14px; font-weight: 600;
  border-radius: 12px; pointer-events: none;
}

.pkg-media-grid { display: flex; flex-wrap: wrap; gap: 10px; }
.pkg-media-card {
  width: 120px; aspect-ratio: 4/3; border-radius: 8px; border: 1px solid var(--border);
  overflow: hidden; cursor: pointer; background: #f5f0e8;
}
.pkg-media-thumb { width: 100%; height: 100%; object-fit: contain; background: #fff; display: block; }

/* 适用标签候选面板：与产品库表格「筛选标签」一致的分类可折叠样式。
   不加 :deep() ——el-option 是本组件模板直接渲染的，即使被 Element Plus 传送到 <body>，
   元素本身仍带着 scoped 属性；:deep() 编译成祖先选择器，反而在传送门场景下永远匹配不到。 */
.tag-group-hd.el-select-dropdown__item {
  display: flex !important; align-items: center; gap: 7px;
  padding: 0 12px !important; height: 32px !important;
  background: #faf7f2 !important; cursor: pointer !important;
  color: #3a3028 !important; font-weight: 700 !important;
  font-size: 13px !important; border-top: 1px solid #f0e8dc;
}
.tag-group-hd.el-select-dropdown__item:first-child { border-top: none; }
.tag-group-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.tag-group-name { font-size: 13px; font-weight: 700; color: #3a3028; flex: 1; }
.tag-group-arrow { font-size: 12px; color: #8a7a6a; transition: transform 0.2s; display: inline-block; }
.tag-group-arrow.collapsed { transform: rotate(-90deg); }
.tag-group-item.el-select-dropdown__item {
  padding-left: 24px !important; display: flex !important; align-items: center; gap: 7px;
}
.tag-item-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
</style>
