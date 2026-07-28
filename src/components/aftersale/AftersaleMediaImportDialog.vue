<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http.js'
import MediaViewer from '@/components/common/MediaViewer.vue'

// ── Props / Emits ──────────────────────────────────
const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'imported'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

// ── 常量 ──────────────────────────────────────────
const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'webp'])
const VIDEO_EXTS  = new Set(['mp4', 'mov', 'webm'])
const ORDER_NO_RE = /^[A-Za-z0-9_-]{1,100}$/
// 需与后端 AFTERSALE_MEDIA_UPLOAD_LIMIT（默认 500MB）保持一致；后端仍是最终校验方，
// 这里只是提前拦截，避免用户等上传大半才收到失败提示
const MAX_FILE_SIZE = 500 * 1024 * 1024

// ── 响应式状态 ────────────────────────────────────
const step          = ref('pick')     // pick | confirm | uploading | done
const skippedCount  = ref(0)          // 已跳过的不支持类型/超限文件数
const groups        = ref([])         // [{ orderNo, files: File[], existing, mode, invalid }]
const uploading      = ref(false)
const uploadResults  = ref([])        // [{ orderNo, success, message, progress }]
const folderInput    = ref(null)
const isDragOver      = ref(false)
const viewerVisible   = ref(false)
const viewerItems     = ref([])

function extOf(name) {
  const idx = name.lastIndexOf('.')
  return idx === -1 ? '' : name.slice(idx + 1).toLowerCase()
}

function isMediaFile(name) {
  const ext = extOf(name)
  return IMAGE_EXTS.has(ext) || VIDEO_EXTS.has(ext)
}

// ── 合并新解析出的文件到现有分组（支持多次选择/拖入多个文件夹） ──
function mergeIntoGroups(byOrder, skipped) {
  skippedCount.value += skipped
  const existingByOrder = new Map(groups.value.map(g => [g.orderNo, g]))
  for (const [orderNo, files] of byOrder) {
    if (existingByOrder.has(orderNo)) {
      existingByOrder.get(orderNo).files.push(...files)
    } else {
      existingByOrder.set(orderNo, {
        orderNo, files, existing: { exists: false, count: 0, files: [] },
        mode: 'append', invalid: !ORDER_NO_RE.test(orderNo),
      })
    }
  }
  return [...existingByOrder.values()]
}

async function refreshPrecheck(list) {
  const validOrderNos = list.filter(g => !g.invalid).map(g => g.orderNo)
  if (!validOrderNos.length) return list
  try {
    const res = await http.post('/api/aftersale/media/precheck', { order_nos: validOrderNos })
    if (res.success) {
      for (const g of list) {
        if (res.data[g.orderNo]) g.existing = res.data[g.orderNo]
      }
    }
  } catch { /* 预检失败时仍允许继续，冲突信息缺失按无冲突处理 */ }
  return list
}

// ── 文件夹选择（点击，可重复调用累加） ───────────────
function openFolderPicker() { folderInput.value?.click() }

async function onFolderSelected(e) {
  const fileList = Array.from(e.target.files || [])
  e.target.value = ''   // 允许重复选择同一/另一文件夹
  await addFiles(fileList.map(f => ({ file: f, relativePath: f.webkitRelativePath || f.name })))
}

// ── 拖拽多个文件夹（一次可拖入多个顶层文件夹，逐个递归读取） ──
function onDragOver(e) { e.preventDefault(); isDragOver.value = true }
function onDragLeave() { isDragOver.value = false }

async function onDrop(e) {
  e.preventDefault()
  isDragOver.value = false
  const items = e.dataTransfer?.items
  if (!items?.length) return
  const entries = [...items].map(it => it.webkitGetAsEntry?.()).filter(Boolean)
  const collected = []
  await Promise.all(entries.map(entry => walkEntry(entry, '', collected)))
  await addFiles(collected)
}

function walkEntry(entry, prefix, collected) {
  return new Promise((resolve) => {
    if (entry.isFile) {
      entry.file((file) => {
        collected.push({ file, relativePath: prefix + entry.name })
        resolve()
      }, resolve)
    } else if (entry.isDirectory) {
      const reader = entry.createReader()
      const readAll = () => reader.readEntries(async (subEntries) => {
        if (!subEntries.length) return resolve()
        await Promise.all(subEntries.map(sub => walkEntry(sub, prefix + entry.name + '/', collected)))
        readAll()   // readEntries 可能不会一次返回全部，需循环读取直到空
      }, resolve)
      readAll()
    } else {
      resolve()
    }
  })
}

// ── 汇总解析结果、按订单号分组、跳过不支持/超限文件 ──
async function addFiles(entries) {
  if (!entries.length) return
  const byOrder = new Map()
  let skipped = 0
  for (const { file, relativePath } of entries) {
    const parts = relativePath.split('/')
    let orderNo
    if (parts.length <= 1) continue
    if (parts.length === 2) orderNo = parts[0]
    else orderNo = parts[1]

    if (!isMediaFile(file.name) || file.size > MAX_FILE_SIZE) { skipped++; continue }
    if (!byOrder.has(orderNo)) byOrder.set(orderNo, [])
    byOrder.get(orderNo).push(file)
  }
  if (!byOrder.size && !skipped) return
  if (!byOrder.size) {
    ElMessage.warning('未识别到任何图片/视频文件，请检查文件夹结构')
    return
  }
  groups.value = await refreshPrecheck(mergeIntoGroups(byOrder, skipped))
  step.value = 'confirm'
}

function setAllMode(mode) {
  groups.value.forEach(g => { if (!g.invalid) g.mode = mode })
}

function removeGroup(orderNo) {
  groups.value = groups.value.filter(g => g.orderNo !== orderNo)
}

function viewExisting(group) {
  viewerItems.value = group.existing.files.map(f => ({
    id: f.id, file_type: f.file_type, oss_url: f.oss_url, original_filename: f.original_filename,
  }))
  viewerVisible.value = true
}

// ── 上传执行（带进度）──────────────────────────────
function putWithProgress(url, headers, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', url)
    Object.entries(headers || {}).forEach(([k, v]) => xhr.setRequestHeader(k, v))
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total) }
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300) ? resolve() : reject(new Error(`上传失败 (${xhr.status})`))
    xhr.onerror = () => reject(new Error('网络错误，上传失败'))
    xhr.send(file)
  })
}

async function startImport() {
  const targets = groups.value.filter(g => !g.invalid && g.mode !== 'skip')
  if (!targets.length) {
    ElMessage.warning('没有需要导入的订单')
    return
  }
  step.value = 'uploading'
  uploading.value = true
  uploadResults.value = targets.map(g => ({ orderNo: g.orderNo, success: null, message: '', progress: 0 }))

  // 逐订单串行处理，避免几十个订单同时并发压垮单 worker
  for (let i = 0; i < targets.length; i++) {
    const g = targets[i]
    try {
      const presignRes = await http.post('/api/aftersale/media/presign', {
        order_no: g.orderNo,
        mode: g.mode,
        files: g.files.map(f => ({ ext: extOf(f.name), file_size: f.size, original_filename: f.name })),
      })
      if (!presignRes.success) throw new Error(presignRes.message || '获取上传签名失败')

      const { session_token, items } = presignRes.data
      const totalBytes = g.files.reduce((sum, f) => sum + f.size, 0) || 1
      const perFileUploaded = new Array(items.length).fill(0)
      const updateProgress = () => {
        const uploaded = perFileUploaded.reduce((a, b) => a + b, 0)
        uploadResults.value[i].progress = Math.min(100, Math.round((uploaded / totalBytes) * 100))
      }
      for (let j = 0; j < items.length; j++) {
        const item = items[j]
        await putWithProgress(item.presign_url, item.required_headers, g.files[j], (ratio) => {
          perFileUploaded[j] = ratio * g.files[j].size
          updateProgress()
        })
        perFileUploaded[j] = g.files[j].size
        updateProgress()
      }

      const confirmRes = await http.post('/api/aftersale/media/confirm', { session_token })
      if (!confirmRes.success) throw new Error(confirmRes.message || '确认导入失败')

      uploadResults.value[i] = { ...uploadResults.value[i], success: true, message: `已导入 ${items.length} 个文件`, progress: 100 }
    } catch (err) {
      uploadResults.value[i] = { ...uploadResults.value[i], success: false, message: err.message || '导入失败' }
    }
  }

  uploading.value = false
  step.value = 'done'
  emit('imported')
}

function retryFailed() {
  const failedOrderNos = new Set(uploadResults.value.filter(r => !r.success).map(r => r.orderNo))
  groups.value = groups.value.filter(g => failedOrderNos.has(g.orderNo))
  step.value = 'confirm'
}

function reset() {
  step.value = 'pick'
  groups.value = []
  uploadResults.value = []
  skippedCount.value = 0
}

function close() {
  visible.value = false
  reset()
}

const successCount   = computed(() => uploadResults.value.filter(r => r.success).length)
const failCount      = computed(() => uploadResults.value.filter(r => r.success === false).length)
const overallProgress = computed(() => {
  if (!uploadResults.value.length) return 0
  const sum = uploadResults.value.reduce((acc, r) => acc + (r.success === false ? 100 : (r.progress || 0)), 0)
  return Math.round(sum / uploadResults.value.length)
})
</script>

<template>
  <el-dialog
    v-model="visible"
    title="导入售后图片/视频"
    width="680px"
    append-to-body
    destroy-on-close
    @close="reset"
  >
    <!-- 第一步：选择/拖拽文件夹 -->
    <div v-if="step === 'pick'" class="import-pick">
      <p class="hint">
        文件夹本身以订单号命名（内部直接放图片/视频），或选择一个父文件夹，其内每个子文件夹分别
        以订单号命名——可一次拖入多个文件夹批量导入，也可以多次点击「选择文件夹」逐个累加。
      </p>
      <div
        class="dropzone" :class="{ 'dropzone-active': isDragOver }"
        @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop"
      >
        <p>将多个订单文件夹拖到此处</p>
        <p class="hint">或</p>
        <input
          ref="folderInput" type="file" webkitdirectory multiple
          style="display:none" @change="onFolderSelected"
        />
        <el-button type="primary" @click="openFolderPicker">选择文件夹</el-button>
      </div>
    </div>

    <!-- 第二步：冲突确认 -->
    <div v-else-if="step === 'confirm'" class="import-confirm">
      <p v-if="skippedCount" class="hint hint-warn">已跳过 {{ skippedCount }} 个文件（不支持的类型或超过 500MB）</p>
      <div class="batch-actions">
        <el-button size="small" @click="openFolderPicker">继续添加文件夹</el-button>
        <el-button size="small" @click="setAllMode('append')">全部设为追加</el-button>
        <el-button size="small" @click="setAllMode('replace')">全部设为替换</el-button>
        <el-button size="small" @click="setAllMode('skip')">全部跳过</el-button>
      </div>
      <input
        ref="folderInput" type="file" webkitdirectory multiple
        style="display:none" @change="onFolderSelected"
      />
      <el-table :data="groups" size="small" max-height="360" border>
        <el-table-column label="订单号" min-width="150">
          <template #default="{ row }">
            <span :class="{ 'order-invalid': row.invalid }">{{ row.orderNo }}</span>
            <el-tag v-if="row.invalid" type="danger" size="small" style="margin-left:6px">订单号含非法字符</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="已有文件" width="110">
          <template #default="{ row }">
            <el-button v-if="row.existing.count" link type="primary" size="small" @click="viewExisting(row)">
              查看 {{ row.existing.count }} 个
            </el-button>
            <span v-else>0</span>
          </template>
        </el-table-column>
        <el-table-column label="本次导入" width="90">
          <template #default="{ row }">{{ row.files.length }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-radio-group v-if="!row.invalid" v-model="row.mode" size="small">
              <el-radio-button value="append">追加</el-radio-button>
              <el-radio-button value="replace">替换</el-radio-button>
              <el-radio-button value="skip">跳过</el-radio-button>
            </el-radio-group>
            <span v-else class="text-muted">已跳过</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeGroup(row.orderNo)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="dialog-footer">
        <el-button @click="step = 'pick'">上一步</el-button>
        <el-button type="primary" @click="startImport">开始导入</el-button>
      </div>
    </div>

    <!-- 第三步：上传进度 -->
    <div v-else-if="step === 'uploading'" class="import-progress">
      <div class="overall-progress">
        <span>总体进度</span>
        <el-progress :percentage="overallProgress" :stroke-width="10" style="flex:1" />
      </div>
      <el-table :data="uploadResults" size="small" max-height="320" border>
        <el-table-column label="订单号" prop="orderNo" min-width="140" />
        <el-table-column label="进度" min-width="220">
          <template #default="{ row }">
            <span v-if="row.success === false" class="text-danger">{{ row.message }}</span>
            <el-progress v-else :percentage="row.progress" :status="row.success ? 'success' : undefined" />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 第四步：完成 -->
    <div v-else class="import-done">
      <p>导入完成：成功 {{ successCount }} 单{{ failCount ? `，失败 ${failCount} 单` : '' }}</p>
      <el-table v-if="failCount" :data="uploadResults.filter(r => !r.success)" size="small" max-height="240" border>
        <el-table-column label="订单号" prop="orderNo" min-width="160" />
        <el-table-column label="失败原因" prop="message" min-width="200" />
      </el-table>
      <div class="dialog-footer">
        <el-button v-if="failCount" @click="retryFailed">仅重试失败项</el-button>
        <el-button type="primary" @click="close">关闭</el-button>
      </div>
    </div>

    <MediaViewer v-model="viewerVisible" :items="viewerItems" />
  </el-dialog>
</template>

<style scoped>
.hint { color: var(--text-secondary); font-size: 13px; margin-bottom: 12px; }
.hint-warn { color: #b8860b; }
.batch-actions { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.order-invalid { color: #c0392b; }
.text-muted { color: var(--text-muted); }
.text-success { color: #2e7d32; }
.text-danger { color: #c0392b; }
.dialog-footer { display: flex; justify-content: flex-end; gap: 10px; margin-top: 14px; }
.dropzone {
  border: 2px dashed var(--border); border-radius: 10px; padding: 36px 16px; text-align: center;
  transition: border-color 0.2s, background 0.2s;
}
.dropzone-active { border-color: var(--accent); background: rgba(196,136,58,0.06); }
.overall-progress { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
</style>
