<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http.js'

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

// ── 响应式状态 ────────────────────────────────────
const step         = ref('pick')     // pick | confirm | uploading | done
const skippedCount = ref(0)          // 已跳过的不支持文件数/非法订单号数
const groups       = ref([])         // [{ orderNo, files: File[], existing, mode, invalid }]
const uploading     = ref(false)
const uploadResults = ref([])        // [{ orderNo, success, message }]
const folderInput   = ref(null)

// ── 文件夹选择 & 分组解析 ───────────────────────────
function openFolderPicker() { folderInput.value?.click() }

function extOf(name) {
  const idx = name.lastIndexOf('.')
  return idx === -1 ? '' : name.slice(idx + 1).toLowerCase()
}

async function onFolderSelected(e) {
  const fileList = Array.from(e.target.files || [])
  e.target.value = ''   // 允许重复选择同一文件夹
  if (!fileList.length) return

  const byOrder = new Map()
  let skipped = 0
  for (const file of fileList) {
    const parts = (file.webkitRelativePath || file.name).split('/')
    // 2段：直接选中单个订单文件夹（第一段是订单号）；3段以上：父文件夹套订单子文件夹（取第二段）
    let orderNo
    if (parts.length <= 1) continue
    if (parts.length === 2) orderNo = parts[0]
    else orderNo = parts[1]

    const ext = extOf(file.name)
    if (!IMAGE_EXTS.has(ext) && !VIDEO_EXTS.has(ext)) { skipped++; continue }

    if (!byOrder.has(orderNo)) byOrder.set(orderNo, [])
    byOrder.get(orderNo).push(file)
  }
  skippedCount.value = skipped

  const orderNos = [...byOrder.keys()]
  if (!orderNos.length) {
    ElMessage.warning('未识别到任何图片/视频文件，请检查文件夹结构')
    return
  }

  const validOrderNos = orderNos.filter(o => ORDER_NO_RE.test(o))
  const invalidOrderNos = orderNos.filter(o => !ORDER_NO_RE.test(o))

  let existingMap = {}
  if (validOrderNos.length) {
    try {
      const res = await http.post('/api/aftersale/media/precheck', { order_nos: validOrderNos })
      if (res.success) existingMap = res.data
    } catch { /* 预检失败时仍允许继续，冲突信息缺失按无冲突处理 */ }
  }

  groups.value = [
    ...validOrderNos.map(orderNo => ({
      orderNo,
      files: byOrder.get(orderNo),
      existing: existingMap[orderNo] || { exists: false, count: 0, files: [] },
      mode: existingMap[orderNo]?.exists ? 'append' : 'append',
      invalid: false,
    })),
    ...invalidOrderNos.map(orderNo => ({
      orderNo, files: byOrder.get(orderNo), existing: { exists: false, count: 0, files: [] },
      mode: 'skip', invalid: true,
    })),
  ]
  step.value = 'confirm'
}

function setAllMode(mode) {
  groups.value.forEach(g => { if (!g.invalid) g.mode = mode })
}

// ── 上传执行 ──────────────────────────────────────
async function startImport() {
  const targets = groups.value.filter(g => !g.invalid && g.mode !== 'skip')
  if (!targets.length) {
    ElMessage.warning('没有需要导入的订单')
    return
  }
  step.value = 'uploading'
  uploading.value = true
  uploadResults.value = targets.map(g => ({ orderNo: g.orderNo, success: null, message: '' }))

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
      for (let j = 0; j < items.length; j++) {
        const item = items[j]
        const putRes = await fetch(item.presign_url, {
          method: 'PUT', headers: item.required_headers, body: g.files[j],
        })
        if (!putRes.ok) throw new Error(`文件 ${g.files[j].name} 上传失败`)
      }

      const confirmRes = await http.post('/api/aftersale/media/confirm', { session_token })
      if (!confirmRes.success) throw new Error(confirmRes.message || '确认导入失败')

      uploadResults.value[i] = { orderNo: g.orderNo, success: true, message: `已导入 ${items.length} 个文件` }
    } catch (err) {
      uploadResults.value[i] = { orderNo: g.orderNo, success: false, message: err.message || '导入失败' }
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

const successCount = computed(() => uploadResults.value.filter(r => r.success).length)
const failCount    = computed(() => uploadResults.value.filter(r => r.success === false).length)
</script>

<template>
  <el-dialog
    v-model="visible"
    title="导入售后图片/视频"
    width="640px"
    append-to-body
    destroy-on-close
    @close="reset"
  >
    <!-- 第一步：选择文件夹 -->
    <div v-if="step === 'pick'" class="import-pick">
      <p class="hint">
        选择一个文件夹：文件夹本身以订单号命名（内部直接放图片/视频），或选择一个父文件夹，
        其内的每个子文件夹分别以订单号命名。
      </p>
      <input
        ref="folderInput" type="file" webkitdirectory multiple
        style="display:none" @change="onFolderSelected"
      />
      <el-button type="primary" @click="openFolderPicker">选择文件夹</el-button>
    </div>

    <!-- 第二步：冲突确认 -->
    <div v-else-if="step === 'confirm'" class="import-confirm">
      <p v-if="skippedCount" class="hint hint-warn">已跳过 {{ skippedCount }} 个不支持的文件（仅支持图片/视频）</p>
      <div class="batch-actions">
        <el-button size="small" @click="setAllMode('append')">全部设为追加</el-button>
        <el-button size="small" @click="setAllMode('replace')">全部设为替换</el-button>
        <el-button size="small" @click="setAllMode('skip')">全部跳过</el-button>
      </div>
      <el-table :data="groups" size="small" max-height="360" border>
        <el-table-column label="订单号" min-width="160">
          <template #default="{ row }">
            <span :class="{ 'order-invalid': row.invalid }">{{ row.orderNo }}</span>
            <el-tag v-if="row.invalid" type="danger" size="small" style="margin-left:6px">订单号含非法字符</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="已有文件" width="90">
          <template #default="{ row }">{{ row.existing.count }}</template>
        </el-table-column>
        <el-table-column label="本次导入" width="90">
          <template #default="{ row }">{{ row.files.length }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-radio-group v-if="!row.invalid" v-model="row.mode" size="small">
              <el-radio-button value="append">追加</el-radio-button>
              <el-radio-button value="replace">替换</el-radio-button>
              <el-radio-button value="skip">跳过</el-radio-button>
            </el-radio-group>
            <span v-else class="text-muted">已跳过</span>
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
      <el-table :data="uploadResults" size="small" max-height="360" border>
        <el-table-column label="订单号" prop="orderNo" min-width="160" />
        <el-table-column label="状态" min-width="200">
          <template #default="{ row }">
            <span v-if="row.success === null" class="text-muted">等待中…</span>
            <span v-else-if="row.success" class="text-success">{{ row.message }}</span>
            <span v-else class="text-danger">{{ row.message }}</span>
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
  </el-dialog>
</template>

<style scoped>
.hint { color: var(--text-secondary); font-size: 13px; margin-bottom: 12px; }
.hint-warn { color: #b8860b; }
.batch-actions { display: flex; gap: 8px; margin-bottom: 10px; }
.order-invalid { color: #c0392b; }
.text-muted { color: var(--text-muted); }
.text-success { color: #2e7d32; }
.text-danger { color: #c0392b; }
.dialog-footer { display: flex; justify-content: flex-end; gap: 10px; margin-top: 14px; }
</style>
