<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import http from '@/api/http'

// ── 步骤状态 ──────────────────────────────────────
// 'idle' | 'previewing' | 'preview_done' | 'importing' | 'done' | 'error'
const step = ref('idle')

// ── 文件 ──────────────────────────────────────────
const selectedFile = ref(null)
const fileInputRef = ref(null)

// ── 预览数据 ──────────────────────────────────────
const previewTotal  = ref(0)
const previewSample = ref([])

// ── 导入结果 ──────────────────────────────────────
const importResult = ref(null)

// ── 错误信息 ──────────────────────────────────────
const errorMsg = ref('')

// ── 选择文件 ──────────────────────────────────────
function triggerPicker() {
  fileInputRef.value?.click()
}

function onFileChange(e) {
  const file = e.target.files?.[0]
  if (!file) return
  selectedFile.value = file
  // 重置状态
  step.value         = 'idle'
  previewSample.value = []
  previewTotal.value  = 0
  importResult.value  = null
  errorMsg.value      = ''
}

// ── 预览 ──────────────────────────────────────────
async function handlePreview() {
  if (!selectedFile.value) return
  step.value     = 'previewing'
  errorMsg.value = ''

  const form = new FormData()
  form.append('file', selectedFile.value)

  try {
    const res = await http.post('/api/product/import/preview', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (res.success) {
      previewTotal.value  = res.data.total
      previewSample.value = res.data.sample
      step.value = 'preview_done'
    } else {
      errorMsg.value = res.message || '预览失败'
      step.value = 'error'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
    step.value = 'error'
  }
}

// ── 正式导入 ──────────────────────────────────────
async function handleImport() {
  if (!selectedFile.value) return
  step.value     = 'importing'
  errorMsg.value = ''

  const form = new FormData()
  form.append('file', selectedFile.value)

  try {
    const res = await http.post('/api/product/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (res.success) {
      importResult.value = res.data
      step.value = 'done'
    } else {
      errorMsg.value = res.message || '导入失败'
      step.value = 'error'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
    step.value = 'error'
  }
}

// ── 重置 ──────────────────────────────────────────
function handleReset() {
  selectedFile.value  = null
  previewSample.value = []
  previewTotal.value  = 0
  importResult.value  = null
  errorMsg.value      = ''
  step.value          = 'idle'
  if (fileInputRef.value) fileInputRef.value.value = ''
}
</script>

<template>
  <div class="product-import">

    <!-- 上传区 -->
    <div
      class="upload-area"
      :class="{ 'has-file': selectedFile }"
      @click="triggerPicker"
    >
      <input
        ref="fileInputRef"
        type="file"
        accept=".xlsx,.xls"
        class="file-input"
        @change="onFileChange"
      />

      <!-- 未选择文件 -->
      <div v-if="!selectedFile" class="upload-placeholder">
        <svg class="upload-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
        </svg>
        <div class="upload-hint">点击选择 Excel 文件</div>
        <div class="upload-hint-sub">支持 .xlsx / .xls 格式</div>
      </div>

      <!-- 已选择文件 -->
      <div v-else class="upload-file-info" @click.stop="triggerPicker">
        <svg class="file-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
          <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
        </svg>
        <div>
          <div class="file-name">{{ selectedFile.name }}</div>
          <div class="file-size">{{ (selectedFile.size / 1024).toFixed(1) }} KB</div>
        </div>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="action-row" @click.stop>
      <button
        v-if="selectedFile && step !== 'done'"
        class="btn btn-secondary"
        :disabled="step === 'previewing' || step === 'importing'"
        @click.stop="handlePreview"
      >
        {{ step === 'previewing' ? '解析中...' : '预览数据' }}
      </button>
      <button
        v-if="step === 'preview_done'"
        class="btn btn-primary"
        :disabled="step === 'importing'"
        @click.stop="handleImport"
      >
        {{ step === 'importing' ? '导入中...' : '确认导入' }}
      </button>
      <button
        v-if="step === 'done' || step === 'error'"
        class="btn btn-secondary"
        @click.stop="handleReset"
      >
        重新导入
      </button>
    </div>

    <!-- 预览表格 -->
    <div v-if="step === 'preview_done'" class="preview-section">
      <div class="section-header">
        <span class="section-label">数据预览</span>
        <span class="section-sub">共 {{ previewTotal }} 行，以下为前 5 行样本</span>
      </div>
      <div class="preview-table">
        <div class="pt-head">
          <div class="pt-col col-code">品号</div>
          <div class="pt-col col-name">品名（含规格）</div>
          <div class="pt-col col-group">群组编码</div>
          <div class="pt-col col-group">群组名称</div>
        </div>
        <div v-for="(row, i) in previewSample" :key="i" class="pt-row">
          <div class="pt-col col-code">
            <span class="code-tag">{{ row.code }}</span>
          </div>
          <div class="pt-col col-name">
            {{ row.name }}{{ row.spec ? ' ' + row.spec : '' }}
          </div>
          <div class="pt-col col-group">{{ row.group_code }}</div>
          <div class="pt-col col-group">{{ row.group_name }}</div>
        </div>
      </div>
    </div>

    <!-- 导入结果 -->
    <div v-if="step === 'done' && importResult" class="result-section">
      <div class="section-header">
        <span class="section-label">导入完成</span>
      </div>
      <div class="result-grid">
        <div class="result-card">
          <div class="result-val">{{ importResult.total }}</div>
          <div class="result-label">Excel 总行数</div>
        </div>
        <div class="result-card success">
          <div class="result-val success-val">{{ importResult.inserted }}</div>
          <div class="result-label">成功导入</div>
        </div>
        <div class="result-card neutral">
          <div class="result-val neutral-val">{{ importResult.skipped_dup }}</div>
          <div class="result-label">已存在跳过</div>
        </div>
        <div class="result-card neutral">
          <div class="result-val neutral-val">{{ importResult.skipped_invalid }}</div>
          <div class="result-label">数据缺失跳过</div>
        </div>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="step === 'error'" class="error-bar">
      <el-icon><WarningFilled /></el-icon>
      <span>{{ errorMsg }}</span>
    </div>

  </div>
</template>

<style scoped>
.product-import {
  flex: 1; overflow-y: auto;
  padding: 4px 0 8px;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}
.product-import::-webkit-scrollbar { width: 4px; }
.product-import::-webkit-scrollbar-track { background: transparent; }
.product-import::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.import-title { font-size: 20px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.import-sub   { font-size: 13px; color: var(--text-muted); margin-bottom: 24px; }

/* ── 上传区 ───────────────────────────────────── */
.upload-area {
  width: 100%;
  border: 1.5px dashed var(--border);
  border-radius: 14px; padding: 28px 32px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.2s;
  background: var(--bg-card); min-height: 110px;
}
.upload-area:hover      { border-color: var(--accent); background: var(--accent-bg); }
.upload-area.has-file   { border-style: solid; border-color: var(--accent); }
.file-input             { display: none; }

.upload-placeholder {
  display: flex; flex-direction: column;
  align-items: center; gap: 8px;
}
.upload-svg  { width: 32px; height: 32px; color: var(--text-muted); }
.upload-hint { font-size: 14px; font-weight: 500; color: var(--text-primary); }
.upload-hint-sub { font-size: 12px; color: var(--text-muted); }

.upload-file-info {
  display: flex; align-items: center; gap: 14px;
}
.file-svg  { width: 28px; height: 28px; color: var(--accent); flex-shrink: 0; }
.file-name { font-size: 14px; font-weight: 500; color: var(--text-primary); margin-bottom: 2px; }
.file-size { font-size: 12px; color: var(--text-muted); }

/* ── 操作按钮 ─────────────────────────────────── */
.action-row { display: flex; gap: 10px; margin-top: 16px; }

.btn {
  padding: 7px 20px; border-radius: 8px;
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.2s; border: none;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-secondary {
  background: var(--bg-card); border: 1px solid var(--border);
  color: var(--text-primary);
}
.btn-secondary:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }

.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover:not(:disabled) { filter: brightness(1.1); }

/* ── section header ───────────────────────────── */
.section-header {
  display: flex; align-items: baseline; gap: 10px; margin-bottom: 10px;
}
.section-label { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.section-sub   { font-size: 12px; color: var(--text-muted); }

/* ── 预览表格 ─────────────────────────────────── */
.preview-section { margin-top: 28px; max-width: 780px; }

.preview-table {
  border: 1px solid var(--border);
  border-radius: 10px; overflow: hidden;
}
.pt-head {
  display: flex; align-items: center; height: 34px;
  background: rgba(255,255,255,0.8);
  border-bottom: 1px solid var(--border);
  padding: 0 16px;
}
.pt-col {
  font-size: 12px; color: var(--text-muted); font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  padding-right: 12px;
}
.col-code  { width: 140px; flex-shrink: 0; }
.col-name  { flex: 1; min-width: 0; }
.col-group { width: 120px; flex-shrink: 0; }

.pt-row {
  display: flex; align-items: center; height: 40px;
  padding: 0 16px; border-bottom: 1px solid var(--border);
  font-size: 12px; color: var(--text-primary);
  transition: background 0.15s;
}
.pt-row:last-child { border-bottom: none; }
.pt-row:hover { background: rgba(196,136,58,0.03); }

.code-tag {
  font-family: monospace; font-size: 11px;
  color: var(--accent); background: var(--accent-bg);
  border: 1px solid var(--border); border-radius: 4px;
  padding: 1px 5px;
}

/* ── 导入结果 ─────────────────────────────────── */
.result-section { margin-top: 28px; }

.result-grid { display: flex; gap: 12px; }

.result-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 12px; padding: 16px 22px; min-width: 110px;
}
.result-card.success { border-color: rgba(76,175,80,0.3); background: rgba(76,175,80,0.04); }
.result-card.neutral { background: var(--bg); }

.result-val     { font-size: 28px; font-weight: 700; color: var(--accent); margin-bottom: 4px; letter-spacing: -0.02em; }
.success-val    { color: #4caf50; }
.neutral-val    { color: var(--text-muted); }
.result-label   { font-size: 11px; color: var(--text-muted); }

/* ── 错误提示 ─────────────────────────────────── */
.error-bar {
  display: flex; align-items: center; gap: 8px;
  margin-top: 16px; padding: 10px 16px;
  background: rgba(208,90,60,0.06);
  border: 1px solid rgba(208,90,60,0.2);
  border-radius: 8px; color: #d05a3c; font-size: 13px;
  max-width: 480px;
}
</style>