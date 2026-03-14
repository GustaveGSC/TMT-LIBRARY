<template>
  <el-dialog
    v-model="visible"
    :title="isForce ? '发现新版本（必须更新）' : '发现新版本'"
    :width="420"
    :close-on-click-modal="!isForce"
    :close-on-press-escape="!isForce"
    :show-close="!isForce"
    class="update-dialog"
    align-center
  >
    <!-- 版本信息 -->
    <div class="update-header">
      <div class="update-version-row">
        <span class="update-label">最新版本</span>
        <span class="update-version">{{ latestVersion }}</span>
      </div>
      <div class="update-version-row">
        <span class="update-label">当前版本</span>
        <span class="update-current">{{ currentVersion }}</span>
      </div>
      <div v-if="releaseDate" class="update-version-row">
        <span class="update-label">发布日期</span>
        <span class="update-current">{{ releaseDate }}</span>
      </div>
    </div>

    <!-- 更新说明 -->
    <div v-if="description" class="update-desc-wrap">
      <div class="update-desc-title">更新内容</div>
      <div class="update-desc">{{ description }}</div>
    </div>

    <!-- 进度条 -->
    <div v-if="status === 'downloading'" class="update-progress-wrap">
      <div class="update-progress-header">
        <span>正在下载...</span>
        <span>{{ progress }}%</span>
      </div>
      <el-progress
        :percentage="progress"
        :show-text="false"
        :stroke-width="6"
      />
      <div class="update-progress-speed">{{ speedText }}</div>
    </div>

    <!-- 下载完成提示 -->
    <div v-if="status === 'downloaded'" class="update-ready">
      ✓ 下载完成，点击「立即安装」将自动重启应用完成更新
    </div>

    <!-- 错误提示 -->
    <div v-if="status === 'error'" class="update-error">
      {{ errorMsg }}
    </div>

    <template #footer>
      <div class="update-footer">
        <!-- 未开始下载 -->
        <template v-if="status === 'idle'">
          <el-button v-if="!isForce" @click="handleSkip">稍后再说</el-button>
          <el-button type="primary" @click="handleDownload">立即下载</el-button>
        </template>
        <!-- 下载中 -->
        <template v-else-if="status === 'downloading'">
          <el-button disabled>下载中...</el-button>
        </template>
        <!-- 下载完成 -->
        <template v-else-if="status === 'downloaded'">
          <el-button v-if="!isForce" @click="handleSkip">稍后安装</el-button>
          <el-button type="primary" @click="handleInstall">立即安装</el-button>
        </template>
        <!-- 出错 -->
        <template v-else-if="status === 'error'">
          <el-button v-if="!isForce" @click="handleSkip">关闭</el-button>
          <el-button type="primary" @click="handleDownload">重试</el-button>
        </template>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

// ── 状态 ──────────────────────────────────────────
const visible       = ref(false)
const isForce       = ref(false)
const status        = ref('idle')   // idle | downloading | downloaded | error
const progress      = ref(0)
const speed         = ref(0)
const errorMsg      = ref('')
const latestVersion = ref('')
const currentVersion = ref('')
const releaseDate   = ref('')
const description   = ref('')

const speedText = computed(() => {
  const s = speed.value
  if (s > 1024 * 1024) return `${(s / 1024 / 1024).toFixed(1)} MB/s`
  if (s > 1024)        return `${(s / 1024).toFixed(0)} KB/s`
  return `${s} B/s`
})

// ── updater 事件监听 ──────────────────────────────
function onProgress(data) {
  status.value   = 'downloading'
  progress.value = data.percent
  speed.value    = data.bytesPerSecond
}

function onDownloaded() {
  status.value = 'downloaded'
}

function onError(msg) {
  status.value  = 'error'
  errorMsg.value = msg || '下载失败，请重试'
}

onMounted(() => {
  window.electronAPI?.updater.on('updater:progress',   onProgress)
  window.electronAPI?.updater.on('updater:downloaded', onDownloaded)
  window.electronAPI?.updater.on('updater:error',      onError)
})

onUnmounted(() => {
  window.electronAPI?.updater.off('updater:progress',   onProgress)
  window.electronAPI?.updater.off('updater:downloaded', onDownloaded)
  window.electronAPI?.updater.off('updater:error',      onError)
})

// ── 操作 ──────────────────────────────────────────
async function handleDownload() {
  status.value   = 'downloading'
  progress.value = 0
  await window.electronAPI?.updater.download()
}

async function handleInstall() {
  await window.electronAPI?.updater.install()
}

function handleSkip() {
  visible.value = false
  status.value  = 'idle'
}

// ── 暴露给父组件 ──────────────────────────────────
function open(opts = {}) {
  latestVersion.value  = opts.latestVersion  || ''
  currentVersion.value = opts.currentVersion || ''
  releaseDate.value    = opts.releaseDate    || ''
  description.value    = opts.description   || ''
  isForce.value        = opts.isForce       || false
  status.value         = 'idle'
  progress.value       = 0
  visible.value        = true
}

defineExpose({ open })
</script>

<style>
.update-dialog .el-dialog__header {
  padding: 20px 24px 12px;
  border-bottom: 1px solid var(--border);
}
.update-dialog .el-dialog__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}
.update-dialog .el-dialog__body {
  padding: 20px 24px;
}
.update-dialog .el-dialog__footer {
  padding: 12px 24px 20px;
  border-top: 1px solid var(--border);
}
</style>

<style scoped>
.update-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.update-version-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.update-label {
  font-size: 12px;
  color: var(--text-muted);
  width: 56px;
  flex-shrink: 0;
}

.update-version {
  font-size: 14px;
  font-weight: 600;
  color: var(--accent);
}

.update-current {
  font-size: 13px;
  color: var(--text-secondary);
}

.update-desc-wrap {
  background: var(--accent-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 16px;
}

.update-desc-title {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.08em;
  margin-bottom: 8px;
}

.update-desc {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.7;
  white-space: pre-line;
}

.update-progress-wrap {
  margin-top: 8px;
}

.update-progress-header {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.update-progress-speed {
  font-size: 11px;
  color: var(--text-muted);
  text-align: right;
  margin-top: 5px;
}

.update-ready {
  font-size: 13px;
  color: #2d7a4a;
  background: #f0faf4;
  border: 1px solid #a8dbb8;
  border-radius: 8px;
  padding: 10px 14px;
  margin-top: 8px;
}

.update-error {
  font-size: 13px;
  color: #c04030;
  background: #fff4f2;
  border: 1px solid #f0b0a0;
  border-radius: 8px;
  padding: 10px 14px;
  margin-top: 8px;
}

.update-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>