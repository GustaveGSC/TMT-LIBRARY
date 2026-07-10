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

// 取消导入
const currentTaskId = ref('')
const isCancelling  = ref(false)

// 跳过记录弹窗（发货行去重）
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
    loading.value       = false
    isCancelling.value  = false
    currentTaskId.value = ''
  }
}
</script>

<template>
  <div class="return-import">

    <div class="import-header">
      <div class="import-header-left">
        <div class="import-title">导入财务清单</div>
        <div class="import-sub">支持 .xlsx / .xls / .csv 格式，正数量行写入发货记录，负数量行写入销退记录，售后组行自动过滤</div>
      </div>
    </div>

    <!-- 文件选择区 -->
    <div
      class="file-zone"
      :class="{ selected: fileName, disabled: loading }"
      @click="!loading && fileInput.click()"
    >
      <input
        ref="fileInput"
        type="file"
        accept=".xlsx,.xls,.csv"
        style="display:none"
        @change="onFileChange"
      />
      <div v-if="!fileName" class="file-zone-hint">
        <div class="file-zone-icon">📂</div>
        <div>点击选择文件</div>
        <div class="file-zone-ext">.xlsx / .xls / .csv</div>
      </div>
      <div v-else class="file-zone-name">
        <svg class="file-icon-excel" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="24" height="24" rx="4" fill="#1D6F42"/>
          <path d="M13 3H7a1 1 0 00-1 1v16a1 1 0 001 1h10a1 1 0 001-1V9l-5-6z" fill="#fff" fill-opacity=".15"/>
          <path d="M13 3v6h5" stroke="#fff" stroke-opacity=".5" stroke-width="1" fill="none"/>
          <text x="4" y="19" font-size="7.5" font-weight="700" fill="#fff" font-family="Arial,sans-serif">XLS</text>
        </svg>
        <span class="file-name-text">{{ fileName }}</span>
        <span class="file-change">点击更换</span>
      </div>
    </div>

    <!-- 导入 / 取消 按钮 -->
    <div class="btn-row">
      <button class="import-btn" :disabled="!file || loading" @click="doImport">
        {{ loading ? '导入中…' : '开始导入' }}
      </button>
      <button v-if="loading" class="cancel-btn" :disabled="isCancelling" @click="cancelImport">
        {{ isCancelling ? '中止中…' : '中止导入' }}
      </button>
    </div>

    <!-- 进度条 -->
    <div v-if="loading || (progress > 0 && progress < 100 && !result)" class="progress-wrap">
      <div class="progress-bar-bg">
        <div class="progress-bar-fill" :style="{ width: progress + '%' }"></div>
      </div>
      <div class="progress-info">
        <span class="progress-phase">{{ phaseLabel }}</span>
        <span v-if="phaseDetail" class="progress-detail">{{ phaseDetail }}</span>
        <span class="progress-pct">{{ progress }}%</span>
      </div>
    </div>

    <!-- 结果卡片 -->
    <div v-if="result" class="result-wrap">
      <div class="result-title">导入完成</div>
      <div class="result-cards">
        <div class="result-card">
          <div class="rc-val">{{ result.total }}</div>
          <div class="rc-lbl">文件总行数</div>
        </div>
        <div class="result-card accent">
          <div class="rc-val">{{ result.inserted }}</div>
          <div class="rc-lbl">新增发货记录</div>
        </div>
        <div class="result-card accent">
          <div class="rc-val">{{ result.inserted_returns }}</div>
          <div class="rc-lbl">新增销退记录</div>
        </div>
        <div
          :class="['result-card', result.skipped > 0 && 'clickable']"
          @click="result.skipped > 0 && (skippedRows = result.skipped_rows, showSkippedDialog = true)"
        >
          <div class="rc-val">{{ result.skipped }}</div>
          <div class="rc-lbl">{{ result.skipped > 0 ? '跳过重复 ›' : '跳过重复' }}</div>
        </div>
        <div class="result-card">
          <div class="rc-val">{{ result.aftersale_filtered }}</div>
          <div class="rc-lbl">售后组过滤</div>
        </div>
      </div>
    </div>

    <!-- 跳过重复弹窗 -->
    <el-dialog v-model="showSkippedDialog" title="已跳过的重复发货记录" width="600px" :close-on-click-modal="false">
      <el-table :data="skippedRows" size="small" border max-height="420">
        <el-table-column prop="ecommerce_order_no" label="平台订单号" min-width="180" show-overflow-tooltip />
        <el-table-column prop="product_code"       label="品号"       width="130" />
        <el-table-column prop="shipped_date"       label="日期"       width="100" align="center" />
        <el-table-column prop="quantity"           label="数量"       width="80"  align="right" />
      </el-table>
      <template #footer>
        <el-button @click="showSkippedDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 错误弹窗 -->
    <el-dialog v-model="showErrorDialog" title="导入失败" width="480px" :close-on-click-modal="false">
      <div class="error-dialog-body">{{ errorMessage }}</div>
      <template #footer>
        <el-button type="primary" @click="showErrorDialog = false">确定</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<style scoped>
.return-import {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.import-header {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.import-header-left { flex: 1; min-width: 0; }
.import-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.import-sub   { font-size: 12px; color: var(--text-muted); }

/* 文件选择区 */
.file-zone {
  border: 1.5px dashed var(--border);
  border-radius: 12px;
  padding: 0 24px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: all 0.18s;
  background: var(--bg);
  height: 100px;
  flex-shrink: 0;
}
.file-zone:hover:not(.disabled) { border-color: var(--accent); background: rgba(196,136,58,0.03); }
.file-zone.selected { border-style: solid; border-color: var(--accent); }
.file-zone.disabled { opacity: 0.5; cursor: not-allowed; }

.file-zone-hint {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  color: var(--text-muted); font-size: 13px;
}
.file-zone-icon { font-size: 32px; }
.file-zone-ext  { font-size: 11px; opacity: 0.6; }

.file-zone-name {
  display: flex; align-items: center; gap: 10px;
  width: 100%;
}
.file-icon-excel { width: 32px; height: 32px; flex-shrink: 0; }
.file-name-text  { flex: 1; font-size: 13px; color: var(--text-primary); word-break: break-all; }
.file-change     { font-size: 11px; color: var(--text-muted); flex-shrink: 0; white-space: nowrap; }

/* 按钮行 */
.btn-row {
  display: flex; gap: 10px;
}

.import-btn {
  flex: 1;
  padding: 11px 0;
  background: var(--accent); color: #fff;
  border: none; border-radius: 8px;
  font-size: 13px; font-weight: 500; font-family: inherit;
  cursor: pointer; transition: background 0.18s;
}
.import-btn:hover:not(:disabled) { background: var(--accent-hover); }
.import-btn:disabled { opacity: 0.45; cursor: not-allowed; }

.cancel-btn {
  padding: 11px 18px;
  background: transparent;
  color: #c06030; border: 1px solid #c06030;
  border-radius: 8px;
  font-size: 13px; font-weight: 500; font-family: inherit;
  cursor: pointer; transition: all 0.18s; white-space: nowrap;
}
.cancel-btn:hover:not(:disabled) { background: rgba(192,96,48,0.06); }
.cancel-btn:disabled { opacity: 0.45; cursor: not-allowed; }

/* 进度条 */
.progress-wrap {
  display: flex; flex-direction: column; gap: 8px;
}
.progress-bar-bg {
  height: 6px;
  background: var(--border);
  border-radius: 3px;
  overflow: hidden;
}
.progress-bar-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 3px;
  transition: width 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
.progress-info {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px;
}
.progress-phase  { color: var(--text-primary); font-weight: 500; }
.progress-detail { color: var(--text-muted); flex: 1; }
.progress-pct    { color: var(--text-muted); margin-left: auto; font-family: monospace; }

/* 结果 */
.result-wrap {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}
.result-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 14px; }
.result-cards {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
}
.result-card {
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 10px; text-align: center;
}
.result-card.accent   { border-color: rgba(196,136,58,0.3); }
.result-card.clickable { cursor: pointer; transition: border-color 0.15s, box-shadow 0.15s; }
.result-card.clickable:hover { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(196,136,58,0.12); }
.rc-val { font-size: 28px; font-weight: 700; color: var(--text-primary); }
.result-card.accent .rc-val { color: var(--accent); }
.rc-lbl { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

.error-dialog-body {
  font-size: 13px; color: var(--text-primary);
  line-height: 1.7; word-break: break-all;
  max-height: 300px; overflow-y: auto;
}
</style>
