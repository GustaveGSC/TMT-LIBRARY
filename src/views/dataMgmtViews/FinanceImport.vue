<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import http, { getBaseURL } from '@/api/http'

// ── 响应式状态 ────────────────────────────────────
const file      = ref(null)
const fileName  = ref('')
const loading   = ref(false)
const result    = ref(null)
const fileInput = ref(null)

// 进度状态
const progress      = ref(0)
const phaseLabel    = ref('')
const phaseDetail   = ref('')

// 取消
const currentTaskId = ref('')
const isCancelling  = ref(false)

// 跳过记录弹窗
const showSkippedDialog = ref(false)
const skippedRows       = ref([])

// 错误弹窗
const showErrorDialog = ref(false)
const errorMessage    = ref('')

// ── 方法 ──────────────────────────────────────────
function showError(msg) {
  errorMessage.value    = msg || '未知错误'
  showErrorDialog.value = true
  progress.value        = 0
}

async function cancelImport() {
  if (!currentTaskId.value || isCancelling.value) return
  isCancelling.value = true
  try {
    await http.post(`/api/shipping/import/cancel/${currentTaskId.value}`)
  } catch {}
}

function onFileChange(e) {
  const f = e.target.files?.[0]
  if (!f) return
  const name = f.name.toLowerCase()
  if (!['.xlsx', '.xls', '.csv'].some(ext => name.endsWith(ext))) {
    ElMessage.warning('仅支持 .xlsx / .xls / .csv 格式')
    return
  }
  file.value        = f
  fileName.value    = f.name
  result.value      = null
  progress.value    = 0
  phaseLabel.value  = ''
  phaseDetail.value = ''
  e.target.value    = ''
}

function handleEvent(data) {
  switch (data.step) {
    case 'parsing':
      phaseLabel.value  = '正在解析文件...'
      phaseDetail.value = ''
      progress.value    = 8
      break
    case 'parsed':
      phaseLabel.value  = '文件解析完成'
      phaseDetail.value = `共 ${data.total} 行数据`
      progress.value    = 25
      break
    case 'inserting':
      phaseLabel.value  = '正在写入数据库...'
      phaseDetail.value = data.total ? `${data.current} / ${data.total} 条` : ''
      progress.value    = data.total ? 35 + Math.round((data.current / data.total) * 20) : 35
      break
    case 'inserted':
      phaseLabel.value  = '数据写入完成'
      phaseDetail.value = `新增发货 ${data.inserted} 条，新增销退 ${data.inserted_returns} 条`
      progress.value    = 55
      break
    case 'resolving': {
      const pct = data.total > 0 ? Math.round((data.current / data.total) * 100) : 0
      phaseLabel.value  = '正在匹配成品组合...'
      phaseDetail.value = `${data.current} / ${data.total} 个订单`
      progress.value    = 55 + Math.round(pct * 0.42)
      break
    }
    case 'done':
      phaseLabel.value  = '导入完成'
      phaseDetail.value = ''
      progress.value    = 100
      break
  }
}

async function doImport() {
  if (!file.value) { ElMessage.warning('请先选择文件'); return }
  loading.value       = true
  isCancelling.value  = false
  currentTaskId.value = ''
  result.value        = null
  progress.value      = 0
  phaseLabel.value    = '上传文件...'
  phaseDetail.value   = ''

  let wasCancelled = false
  try {
    const form = new FormData()
    form.append('file', file.value)
    const res = await http.post('/api/shipping/import/finance', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (!res.success) { showError(res.message || '上传失败'); return }

    currentTaskId.value = res.data.task_id
    progress.value = 5

    await new Promise((resolve, reject) => {
      const es = new EventSource(`${getBaseURL()}/api/shipping/import/progress/${currentTaskId.value}`)

      es.onmessage = (event) => {
        const data = JSON.parse(event.data)
        handleEvent(data)
        if (data.step === 'done') {
          result.value = data.data
          es.close()
          resolve()
        } else if (data.step === 'cancelled') {
          wasCancelled = true
          es.close()
          resolve()
        } else if (data.step === 'error') {
          es.close()
          reject(new Error(data.message || '导入失败'))
        }
      }

      es.onerror = () => { es.close(); reject(new Error('SSE 连接中断，请重试')) }
    })

    if (wasCancelled) {
      ElMessage.info('导入已中止')
      progress.value    = 0
      phaseLabel.value  = ''
      phaseDetail.value = ''
    }
  } catch (e) {
    showError(e.message)
  } finally {
    loading.value = false
    currentTaskId.value = ''
  }
}
</script>

<template>
  <div class="finance-import">
    <!-- 文件拖放区 -->
    <div
      class="drop-zone"
      @click="fileInput.click()"
      @dragover.prevent
      @drop.prevent="e => { const f = e.dataTransfer.files?.[0]; if (f) { file = f; fileName = f.name; result = null; progress = 0 } }"
    >
      <template v-if="!fileName">
        <el-icon style="font-size:32px;color:#c4883a"><Upload /></el-icon>
        <div class="drop-hint">点击或拖拽上传财务清单</div>
        <div class="drop-sub">支持 .xlsx / .xls / .csv</div>
      </template>
      <template v-else>
        <div class="file-name">{{ fileName }}</div>
      </template>
    </div>
    <input ref="fileInput" type="file" accept=".xlsx,.xls,.csv" style="display:none" @change="onFileChange" />

    <!-- 操作按钮 -->
    <div class="btn-row">
      <el-button type="primary" :loading="loading" :disabled="!file" @click="doImport">
        开始导入
      </el-button>
      <el-button v-if="loading" :disabled="isCancelling" @click="cancelImport">
        {{ isCancelling ? '正在中止...' : '中止导入' }}
      </el-button>
    </div>

    <!-- 进度条 -->
    <div v-if="progress > 0 && progress < 100" class="progress-wrap">
      <el-progress :percentage="progress" :show-text="false" />
      <div class="phase-label">{{ phaseLabel }}</div>
      <div v-if="phaseDetail" class="phase-detail">{{ phaseDetail }}</div>
    </div>

    <!-- 结果卡片 -->
    <div v-if="result" class="result-cards">
      <div class="card">
        <div class="card-val">{{ result.total }}</div>
        <div class="card-label">文件总行数</div>
      </div>
      <div class="card accent">
        <div class="card-val">{{ result.inserted }}</div>
        <div class="card-label">新增发货记录</div>
      </div>
      <div class="card accent">
        <div class="card-val">{{ result.inserted_returns }}</div>
        <div class="card-label">新增销退记录</div>
      </div>
      <div
        class="card"
        :class="{ clickable: result.skipped > 0 }"
        @click="result.skipped > 0 && (skippedRows = result.skipped_rows, showSkippedDialog = true)"
      >
        <div class="card-val">{{ result.skipped }}</div>
        <div class="card-label">跳过重复</div>
      </div>
      <div class="card">
        <div class="card-val">{{ result.aftersale_filtered }}</div>
        <div class="card-label">售后组过滤</div>
      </div>
    </div>

    <!-- 跳过重复弹窗 -->
    <el-dialog v-model="showSkippedDialog" title="跳过的重复发货记录" width="600px" append-to-body>
      <el-table :data="skippedRows" size="small" max-height="400">
        <el-table-column prop="ecommerce_order_no" label="平台订单号" min-width="180" />
        <el-table-column prop="product_code" label="品号" width="130" />
        <el-table-column prop="shipped_date" label="日期" width="100" />
        <el-table-column prop="quantity" label="数量" width="80" align="right" />
      </el-table>
    </el-dialog>

    <!-- 错误弹窗 -->
    <el-dialog v-model="showErrorDialog" title="导入失败" width="480px" append-to-body>
      <pre class="error-pre">{{ errorMessage }}</pre>
      <template #footer>
        <el-button type="primary" @click="showErrorDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.finance-import {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.drop-zone {
  border: 2px dashed #e0d4c0;
  border-radius: 10px;
  padding: 28px 16px;
  text-align: center;
  cursor: pointer;
  background: #faf7f2;
  transition: border-color .2s;
  min-height: 100px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.drop-zone:hover { border-color: #c4883a; }
.drop-hint { color: #3a3028; font-size: 14px; font-weight: 500; }
.drop-sub  { color: #8a7a6a; font-size: 12px; }
.file-name { color: #c4883a; font-size: 13px; word-break: break-all; }
.btn-row { display: flex; gap: 8px; }
.progress-wrap { display: flex; flex-direction: column; gap: 4px; }
.phase-label  { font-size: 13px; color: #3a3028; }
.phase-detail { font-size: 12px; color: #8a7a6a; }
.result-cards {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
}
.card {
  background: #fff;
  border: 1px solid #e0d4c0;
  border-radius: 10px;
  padding: 12px 8px;
  text-align: center;
}
.card.accent .card-val { color: #c4883a; }
.card.clickable { cursor: pointer; }
.card.clickable:hover { border-color: #c4883a; }
.card-val   { font-size: 22px; font-weight: 600; color: #2c2420; }
.card-label { font-size: 12px; color: #6b5e4e; margin-top: 4px; }
.error-pre {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 13px;
  color: #c0392b;
  background: #fdf3f3;
  padding: 12px;
  border-radius: 8px;
}
</style>
