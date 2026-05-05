<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onUnmounted } from 'vue'
import http from '@/api/http.js'

// ── 响应式状态 ────────────────────────────────────
const visible     = ref(false)
const downloading = ref(false)
const progress    = ref(null)   // 下载状态对象
const error       = ref('')

let pollTimer = null

// ── 计算属性 ──────────────────────────────────────
const percent     = computed(() => progress.value?.percent ?? 0)
const currentFile = computed(() => progress.value?.current_file ?? '')
const fileIndex   = computed(() => progress.value?.file_index ?? 0)
const fileTotal   = computed(() => progress.value?.file_total ?? 0)
const isDone      = computed(() => progress.value?.done === true)
const isError     = computed(() => !!progress.value?.error || !!error.value)
const errorMsg    = computed(() => progress.value?.error || error.value)

// ── 生命周期 ──────────────────────────────────────
onUnmounted(() => stopPoll())

// ── 方法 ──────────────────────────────────────────
// 由父组件调用，检测到模型未安装时打开
async function open() {
  visible.value = true
}

async function handleDownload() {
  downloading.value = true
  error.value = ''
  try {
    const res = await http.post('/api/aftersale/model/download')
    if (!res.success) {
      error.value = res.message || '启动下载失败'
      downloading.value = false
      return
    }
    startPoll()
  } catch {
    error.value = '网络错误，请重试'
    downloading.value = false
  }
}

function startPoll() {
  pollTimer = setInterval(async () => {
    try {
      const res = await http.get('/api/aftersale/model/progress')
      if (res.success) {
        progress.value = res.data
        if (res.data.done || res.data.error) {
          stopPoll()
          downloading.value = false
        }
      }
    } catch { /* 网络抖动忽略 */ }
  }, 800)
}

function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

function handleClose() {
  if (downloading.value) return   // 下载中不允许关闭
  visible.value = false
  stopPoll()
  emit('close')
}

function handleDone() {
  visible.value = false
  stopPoll()
  emit('installed')
}

const emit = defineEmits(['close', 'installed'])
defineExpose({ open })
</script>

<template>
  <el-dialog
    v-model="visible"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="!downloading"
    width="420px"
    class="model-dialog"
    @close="handleClose"
  >
    <template #header>
      <div class="dialog-header">
        <span class="dialog-title">语义匹配模型</span>
        <span class="dialog-sub">bge-small-zh-v1.5 · 约 90 MB</span>
      </div>
    </template>

    <div class="dialog-body">
      <!-- 未开始下载 -->
      <template v-if="!downloading && !isDone && !isError">
        <div class="desc-block">
          <div class="desc-icon">🧠</div>
          <div class="desc-text">
            <p>检测到<strong>语义匹配模型</strong>尚未安装。</p>
            <p>安装后，售后工单匹配将增加语义理解能力，可识别描述不规范、关键词缺失的备注内容。</p>
            <p class="desc-hint">模型文件将从云端下载到本地，约 90 MB，下载完成后永久生效。</p>
          </div>
        </div>
        <button class="btn-download" @click="handleDownload">立即下载安装</button>
        <button class="btn-skip" @click="handleClose">暂时跳过</button>
      </template>

      <!-- 下载中 -->
      <template v-else-if="downloading || (progress && !isDone && !isError)">
        <div class="progress-area">
          <div class="progress-label">
            <span>{{ currentFile || '准备中...' }}</span>
            <span class="progress-pct">{{ percent }}%</span>
          </div>
          <div class="progress-bar-wrap">
            <div class="progress-bar-fill" :style="{ width: percent + '%' }"></div>
          </div>
          <div class="progress-sub">
            第 {{ fileIndex }} / {{ fileTotal }} 个文件
          </div>
        </div>
      </template>

      <!-- 下载完成 -->
      <template v-else-if="isDone">
        <div class="result-block success">
          <div class="result-icon">✅</div>
          <div class="result-text">
            <p>模型安装完成！</p>
            <p class="desc-hint">语义匹配已启用，后续工单推荐将更加准确。</p>
          </div>
        </div>
        <button class="btn-download" @click="handleDone">确定</button>
      </template>

      <!-- 下载出错 -->
      <template v-else-if="isError">
        <div class="result-block error">
          <div class="result-icon">❌</div>
          <div class="result-text">
            <p>下载失败</p>
            <p class="desc-hint">{{ errorMsg }}</p>
          </div>
        </div>
        <button class="btn-download" @click="handleDownload">重试</button>
        <button class="btn-skip" @click="handleClose">关闭</button>
      </template>
    </div>
  </el-dialog>
</template>

<style scoped>
.dialog-header {
  display: flex; flex-direction: column; gap: 3px;
}
.dialog-title { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.dialog-sub   { font-size: 11px; color: var(--text-muted); }

.dialog-body { display: flex; flex-direction: column; gap: 14px; padding: 4px 0 8px; }

/* 说明区 */
.desc-block {
  display: flex; gap: 14px; align-items: flex-start;
  background: var(--accent-bg); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px;
}
.desc-icon { font-size: 28px; flex-shrink: 0; }
.desc-text { font-size: 12px; color: var(--text-secondary); line-height: 1.7; }
.desc-text p { margin: 0 0 4px; }
.desc-text strong { color: var(--text-primary); }
.desc-hint { color: var(--text-muted); font-size: 11px; }

/* 按钮 */
.btn-download {
  width: 100%; padding: 11px;
  background: linear-gradient(135deg, var(--accent), var(--accent-hover));
  border: none; border-radius: 10px;
  color: #fff; font-size: 13px; font-family: inherit;
  font-weight: 600; letter-spacing: 0.06em;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(196,136,58,0.28);
  transition: all 0.2s;
}
.btn-download:hover { opacity: 0.9; transform: translateY(-1px); }

.btn-skip {
  width: 100%; padding: 10px;
  background: transparent; border: 1.5px solid var(--border);
  border-radius: 10px; color: var(--text-muted);
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.2s;
}
.btn-skip:hover { border-color: var(--accent); color: var(--accent); }

/* 进度 */
.progress-area {
  background: var(--accent-bg); border: 1px solid var(--border);
  border-radius: 10px; padding: 16px;
  display: flex; flex-direction: column; gap: 8px;
}
.progress-label {
  display: flex; justify-content: space-between;
  font-size: 12px; color: var(--text-secondary);
}
.progress-pct { font-weight: 700; color: var(--accent); }
.progress-bar-wrap {
  height: 6px; background: var(--border); border-radius: 3px; overflow: hidden;
}
.progress-bar-fill {
  height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent-hover));
  border-radius: 3px; transition: width 0.4s ease;
}
.progress-sub { font-size: 11px; color: var(--text-muted); }

/* 结果 */
.result-block {
  display: flex; gap: 14px; align-items: flex-start;
  border-radius: 10px; padding: 14px;
}
.result-block.success { background: rgba(80,160,80,0.06); border: 1px solid rgba(80,160,80,0.2); }
.result-block.error   { background: rgba(200,60,50,0.06); border: 1px solid rgba(200,60,50,0.2); }
.result-icon { font-size: 24px; flex-shrink: 0; }
.result-text { font-size: 12px; line-height: 1.7; color: var(--text-secondary); }
.result-text p { margin: 0 0 4px; }
</style>
