<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

// ── 响应式状态 ────────────────────────────────────
const lastReturnDate = ref('')   // 数据库中最新的销退日期

const file      = ref(null)
const fileName  = ref('')
const loading   = ref(false)
const result    = ref(null)   // { total, negative_count, unmatched, inserted, skipped, merged_away, ... }
const fileInput = ref(null)

// 进度状态
const progress      = ref(0)
const phaseLabel    = ref('')
const phaseDetail   = ref('')

// 取消导入
const currentTaskId = ref('')
const isCancelling  = ref(false)

// 跳过记录弹窗
const showSkippedDialog  = ref(false)
const skippedRows        = ref([])

// 文件内合并弹窗
const showMergedDialog = ref(false)
const mergedRows       = ref([])

// 无匹配订单弹窗
const showUnmatchedDialog = ref(false)
const unmatchedRows       = ref([])

// 错误弹窗
const showErrorDialog = ref(false)
const errorMessage    = ref('')

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  await refreshStats()
})

// ── 方法 ──────────────────────────────────────────

async function refreshStats() {
  try {
    const res = await http.get('/api/shipping/stats')
    if (res.success) lastReturnDate.value = res.data.last_return_date || ''
  } catch {}
}

// 错误用 dialog 展示，不自动消失
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

// 根据进度事件更新进度条与阶段文字
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
      progress.value    = data.total
        ? 35 + Math.round((data.current / data.total) * 20)
        : 35
      break
    case 'inserted':
      phaseLabel.value  = '数据写入完成'
      phaseDetail.value = `新增 ${data.inserted} 条，跳过 ${data.skipped} 条`
      progress.value    = 55
      break
    case 'resolving': {
      const pct = data.total > 0 ? Math.round((data.current / data.total) * 100) : 0
      phaseLabel.value  = '正在重算成品组合...'
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
    // Step 1：上传文件，获取 task_id
    const form = new FormData()
    form.append('file', file.value)
    const res = await http.post('/api/shipping/import/return', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (!res.success) { showError(res.message || '上传失败'); return }

    currentTaskId.value = res.data.task_id
    progress.value = 5

    // Step 2：订阅 SSE 进度流
    await new Promise((resolve, reject) => {
      const es = new EventSource(`http://127.0.0.1:8765/api/shipping/import/progress/${currentTaskId.value}`)

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
      ElMessage.info('导入已中止，已回滚')
    } else if (result.value) {
      ElMessage.success('导入成功')
      // 有跳过或无匹配记录则弹出明细
      if (result.value.skipped_rows?.length) {
        skippedRows.value       = result.value.skipped_rows
        showSkippedDialog.value = true
      }
      mergedRows.value    = result.value.merged_away_rows || []
      unmatchedRows.value = result.value.unmatched_rows   || []
      await refreshStats()
    }
  } catch (e) {
    showError(e.message || '导入失败')
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
        <div class="import-title">导入销退清单</div>
        <div class="import-sub">支持 .xlsx / .xls / .csv 格式，仅处理数量为负数的行，按订单号与发货记录匹配</div>
      </div>
      <div v-if="lastReturnDate && !loading" class="last-date-badge">
        <span class="last-date-label">当前销退截至</span>
        <span class="last-date-sep">·</span>
        <span class="last-date-value">{{ lastReturnDate }}</span>
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
        <!-- Excel SVG 图标 -->
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
        <div class="result-card">
          <div class="rc-val">{{ result.negative_count }}</div>
          <div class="rc-lbl">销退行数</div>
        </div>
        <div
          :class="['result-card', result.unmatched > 0 && 'clickable']"
          @click="result.unmatched > 0 && (showUnmatchedDialog = true)"
        >
          <div class="rc-val">{{ result.unmatched }}</div>
          <div class="rc-lbl">{{ result.unmatched > 0 ? '无匹配订单 ›' : '无匹配订单' }}</div>
        </div>
        <div class="result-card accent">
          <div class="rc-val">{{ result.inserted }}</div>
          <div class="rc-lbl">新增记录</div>
        </div>
        <div
          :class="['result-card', result.skipped > 0 && 'clickable']"
          @click="result.skipped > 0 && (showSkippedDialog = true)"
        >
          <div class="rc-val">{{ result.skipped }}</div>
          <div class="rc-lbl">{{ result.skipped > 0 ? '跳过重复 ›' : '跳过重复' }}</div>
        </div>
        <div
          v-if="result.merged_away > 0"
          class="result-card clickable"
          @click="showMergedDialog = true"
        >
          <div class="rc-val">{{ result.merged_away }}</div>
          <div class="rc-lbl">文件内合并 ›</div>
        </div>
      </div>
      <div v-if="result.inserted > 0" class="result-hint">
        已自动重新计算受影响订单的成品组合净数量
      </div>
    </div>

    <!-- 错误弹窗 -->
    <el-dialog
      v-model="showErrorDialog"
      title="导入失败"
      width="480px"
      :close-on-click-modal="false"
    >
      <div class="error-dialog-body">{{ errorMessage }}</div>
      <template #footer>
        <el-button type="primary" @click="showErrorDialog = false">确定</el-button>
      </template>
    </el-dialog>

    <!-- 无匹配订单弹窗 -->
    <el-dialog
      v-model="showUnmatchedDialog"
      title="以下销退行在发货记录中找不到对应订单，已忽略"
      width="700px"
      :close-on-click-modal="false"
    >
      <el-table :data="unmatchedRows" size="small" border max-height="420">
        <el-table-column prop="ecommerce_order_no" label="平台订单"    min-width="160" show-overflow-tooltip />
        <el-table-column prop="shipped_date"       label="交易日期"    width="100" align="center" />
        <el-table-column prop="product_code"       label="品号"        min-width="130" show-overflow-tooltip />
        <el-table-column prop="quantity"           label="数量"        width="80"  align="right" />
        <el-table-column prop="warehouse_name"     label="仓库"        min-width="120" show-overflow-tooltip />
      </el-table>
      <template #footer>
        <span style="font-size:12px; color:var(--text-muted); margin-right:auto;">
          共 {{ unmatchedRows.length }} 条
        </span>
        <el-button @click="showUnmatchedDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 文件内合并弹窗 -->
    <el-dialog
      v-model="showMergedDialog"
      title="文件内合并消除的行（数量已累加到对应行）"
      width="700px"
      :close-on-click-modal="false"
    >
      <el-table :data="mergedRows" size="small" border max-height="460">
        <el-table-column prop="ecommerce_order_no" label="平台订单"    min-width="160" show-overflow-tooltip />
        <el-table-column prop="shipped_date"       label="交易日期"    width="100" align="center" />
        <el-table-column prop="product_code"       label="品号"        min-width="130" show-overflow-tooltip />
        <el-table-column prop="quantity"           label="数量"        width="80"  align="right" />
        <el-table-column prop="warehouse_name"     label="仓库"        min-width="120" show-overflow-tooltip />
      </el-table>
      <template #footer>
        <span style="font-size:12px; color:var(--text-muted); margin-right:auto;">
          共 {{ mergedRows.length }} 条
        </span>
        <el-button @click="showMergedDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 跳过记录弹窗 -->
    <el-dialog
      v-model="showSkippedDialog"
      title="以下记录已存在于数据库，已跳过"
      width="700px"
      :close-on-click-modal="false"
    >
      <el-table :data="skippedRows" size="small" border max-height="420">
        <el-table-column prop="ecommerce_order_no" label="平台订单"    min-width="160" show-overflow-tooltip />
        <el-table-column prop="shipped_date"       label="交易日期"    width="100" align="center" />
        <el-table-column prop="product_code"       label="品号"        min-width="130" show-overflow-tooltip />
        <el-table-column prop="quantity"           label="数量"        width="80"  align="right" />
        <el-table-column prop="warehouse_name"     label="仓库"        min-width="120" show-overflow-tooltip />
      </el-table>
      <template #footer>
        <span style="font-size:12px; color:var(--text-muted); margin-right:auto;">
          共 {{ skippedRows.length }} 条
        </span>
        <el-button @click="showSkippedDialog = false">关闭</el-button>
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

.last-date-badge {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  gap: 8px;
  padding: 7px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 20px;
}
.last-date-label {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
}
.last-date-sep {
  font-size: 12px;
  color: var(--border);
}
.last-date-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--accent);
  font-family: monospace;
  letter-spacing: 0.04em;
}

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
  margin-bottom: 12px;
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

.result-hint { font-size: 12px; color: var(--text-muted); }

.error-dialog-body {
  font-size: 13px; color: var(--text-primary);
  line-height: 1.7; word-break: break-all;
  max-height: 300px; overflow-y: auto;
}
</style>
