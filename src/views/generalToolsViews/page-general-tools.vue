<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, watch, onBeforeUnmount, onMounted } from 'vue'
import WindowControls from '@/components/common/WindowControls.vue'
import { useRouter, useRoute } from 'vue-router'
import { VideoPlay, CopyDocument, Back, Folder, ArrowRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { isElectron } from '@/utils/platform'

// ── 路由 ──────────────────────────────────────────
const router = useRouter()
const route  = useRoute()

onMounted(() => {
  const tool = route.query.tool
  if (tool) activeTab.value = tool
})

// ── 响应式状态 ────────────────────────────────────
const activeTab   = ref('video-compress')
const showGuide   = ref(true)

// 视频文件信息
const inputFile     = ref('')
const fileDir       = ref('')
const fileSize      = ref(0)
const videoDuration = ref(0)
const videoWidth    = ref(0)
const videoHeight   = ref(0)

// 压缩参数（可选）
const compressEnabled = ref(true)
const crf             = ref(28)
const preset          = ref('fast')
const videoCodec      = ref('libx264')
const resolution      = ref('keep')
const audioBitrate    = ref('aac128')
const extraArgs       = ref('')

// 封面生成（可选）
const generateCover  = ref(false)
const coverTime      = ref(0)
const videoObjectUrl = ref('')
const coverVideoRef  = ref(null)

// ── 常量 ──────────────────────────────────────────
const PRESETS = [
  { value: 'ultrafast', label: 'ultrafast（最快，文件较大）' },
  { value: 'superfast', label: 'superfast' },
  { value: 'veryfast',  label: 'veryfast' },
  { value: 'faster',    label: 'faster' },
  { value: 'fast',      label: 'fast（推荐）' },
  { value: 'medium',    label: 'medium（均衡）' },
  { value: 'slow',      label: 'slow（更小，更慢）' },
]

const RESOLUTIONS = [
  { value: 'keep',  label: '保持原始分辨率' },
  { value: '1920',  label: '1080p（宽度 1920）' },
  { value: '1280',  label: '720p（宽度 1280）' },
  { value: '854',   label: '480p（宽度 854）' },
  { value: 'half',  label: '缩小一半' },
]

const AUDIO_OPTIONS = [
  { value: 'aac128', label: 'AAC 128k（推荐）' },
  { value: 'aac192', label: 'AAC 192k（高质量）' },
  { value: 'copy',   label: '保留原始音轨' },
  { value: 'none',   label: '去除音频' },
]

// ── 计算属性 ──────────────────────────────────────

const targetWidth = computed(() => {
  if (resolution.value === 'keep') return videoWidth.value
  if (resolution.value === 'half') return Math.round(videoWidth.value / 2)
  return Number(resolution.value)
})

const targetHeight = computed(() => {
  if (!videoWidth.value || !videoHeight.value) return 0
  if (resolution.value === 'keep') return videoHeight.value
  const ratio = videoHeight.value / videoWidth.value
  return Math.round(targetWidth.value * ratio)
})

// 预估压缩后文件大小
const sizeEstimate = computed(() => {
  if (!compressEnabled.value) return null
  if (!fileSize.value || !videoDuration.value || videoDuration.value < 1) return null

  const dur = videoDuration.value
  const w   = targetWidth.value  || videoWidth.value  || 1920
  const h   = targetHeight.value || videoHeight.value || 1080
  const pixels = w * h

  const BASE_KBPS  = 3000
  const BASE_PIX   = 1920 * 1080
  let videoBitrate = BASE_KBPS * (pixels / BASE_PIX) * Math.pow(2, (23 - crf.value) / 6)
  if (videoCodec.value === 'libx265') videoBitrate *= 0.55

  let audioBitrateKbps = 0
  if (audioBitrate.value === 'aac128') audioBitrateKbps = 128
  else if (audioBitrate.value === 'aac192') audioBitrateKbps = 192
  else if (audioBitrate.value === 'copy') audioBitrateKbps = 192

  const totalBitrate   = videoBitrate + audioBitrateKbps
  const estimatedBytes = (totalBitrate * 1000 / 8) * dur

  const lo = estimatedBytes * 0.6
  const hi = estimatedBytes * 1.6

  const fmt = (b) => {
    if (b >= 1024 * 1024 * 1024) return (b / 1024 / 1024 / 1024).toFixed(1) + ' GB'
    if (b >= 1024 * 1024) return (b / 1024 / 1024).toFixed(0) + ' MB'
    return (b / 1024).toFixed(0) + ' KB'
  }

  const ratio = Math.round((1 - estimatedBytes / fileSize.value) * 100)

  return {
    lo: fmt(lo),
    hi: fmt(hi),
    mid: fmt(estimatedBytes),
    ratio: Math.max(0, Math.min(95, ratio)),
    original: fmt(fileSize.value),
  }
})

const crfLabel = computed(() => {
  if (crf.value <= 20) return '高质量，文件较大'
  if (crf.value <= 26) return '较高质量'
  if (crf.value <= 30) return '均衡（推荐）'
  if (crf.value <= 36) return '较低质量，文件较小'
  return '低质量，文件很小'
})

// 构建压缩部分（不含 cd）
function buildCompressPart(input) {
  const dot    = input.lastIndexOf('.')
  const base   = dot > 0 ? input.slice(0, dot) : input
  const ext    = dot > 0 ? input.slice(dot)    : '.mp4'
  const output = `压缩-${base}${ext}`

  const parts = ['ffmpeg', `-i "${input}"`]

  if (resolution.value === 'half') {
    parts.push('-vf "scale=iw/2:ih/2"')
  } else if (resolution.value !== 'keep') {
    parts.push(`-vf "scale=${resolution.value}:-2"`)
  }

  parts.push(`-vcodec ${videoCodec.value}`, `-crf ${crf.value}`, `-preset ${preset.value}`)

  if (audioBitrate.value === 'none') {
    parts.push('-an')
  } else if (audioBitrate.value === 'copy') {
    parts.push('-acodec copy')
  } else {
    const b = audioBitrate.value === 'aac128' ? '128k' : '192k'
    parts.push(`-acodec aac -b:a ${b}`)
  }

  parts.push('-movflags +faststart')
  if (extraArgs.value.trim()) parts.push(extraArgs.value.trim())
  parts.push(`"${output}"`)

  return parts.join(' ')
}

// 构建封面部分（不含 cd）
function buildCoverPart(input) {
  const dot  = input.lastIndexOf('.')
  const base = dot > 0 ? input.slice(0, dot) : input
  const ts   = fmtFFmpeg(coverTime.value)
  return `ffmpeg -ss ${ts} -i "${input}" -vframes 1 -q:v 2 "封面-${base}.png"`
}

// 合并命令
const combinedCommand = computed(() => {
  if (!inputFile.value) return ''
  if (!compressEnabled.value && !generateCover.value) return ''

  const input = inputFile.value
  const dir   = fileDir.value.trim()

  const cmdParts = []
  if (compressEnabled.value) cmdParts.push(buildCompressPart(input))
  if (generateCover.value)   cmdParts.push(buildCoverPart(input))

  if (!dir) return cmdParts.join(' && ')

  const isWin = /^[A-Za-z]:/.test(dir)
  const cd    = isWin ? `cd /d "${dir}"` : `cd "${dir}"`
  return `${cd} && ${cmdParts.join(' && ')}`
})

// 拖动滑块时更新视频预览帧
watch(coverTime, (t) => {
  if (coverVideoRef.value) coverVideoRef.value.currentTime = t
})

onBeforeUnmount(() => {
  if (videoObjectUrl.value) URL.revokeObjectURL(videoObjectUrl.value)
})

// ── 方法 ──────────────────────────────────────────

function pickFile() {
  const input = document.createElement('input')
  input.type   = 'file'
  input.accept = 'video/*'
  input.onchange = (e) => {
    const file = e.target.files[0]
    if (!file) return

    inputFile.value     = file.name
    fileSize.value      = file.size
    videoDuration.value = 0
    videoWidth.value    = 0
    videoHeight.value   = 0
    coverTime.value     = 0

    if (videoObjectUrl.value) URL.revokeObjectURL(videoObjectUrl.value)
    videoObjectUrl.value = URL.createObjectURL(file)

    if (file.path && file.path !== file.name) {
      const sep     = file.path.includes('\\') ? '\\' : '/'
      const lastSep = file.path.lastIndexOf(sep)
      if (lastSep > 0) fileDir.value = file.path.slice(0, lastSep)
    }

    const blobUrl = URL.createObjectURL(file)
    const vid = document.createElement('video')
    vid.preload = 'metadata'
    vid.src     = blobUrl
    vid.onloadedmetadata = () => {
      videoDuration.value = vid.duration
      videoWidth.value    = vid.videoWidth
      videoHeight.value   = vid.videoHeight
      URL.revokeObjectURL(blobUrl)
    }
    vid.onerror = () => URL.revokeObjectURL(blobUrl)
  }
  input.click()
}

async function pickDirectory() {
  if (isElectron && window.electronAPI?.showOpenDialog) {
    const result = await window.electronAPI.showOpenDialog({
      properties: ['openDirectory'],
      title: '选择视频文件所在目录',
    })
    if (!result.canceled && result.filePaths?.[0]) {
      fileDir.value = result.filePaths[0]
    }
  }
}

function fmtDisplay(secs) {
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = Math.floor(secs % 60)
  return h > 0
    ? `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
    : `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
}

function fmtFFmpeg(secs) {
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = Math.floor(secs % 60)
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
}

function _execCopy(text) {
  const el = document.createElement('textarea')
  el.value = text
  el.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none'
  document.body.appendChild(el)
  el.focus(); el.select()
  try { document.execCommand('copy') } catch { /* ignore */ }
  document.body.removeChild(el)
}

function copyText(text) {
  if (!text) return
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).catch(() => _execCopy(text))
  } else {
    _execCopy(text)
  }
  ElMessage.success('命令已复制，去终端粘贴运行')
}
</script>

<template>
  <div class="page-wrapper">
    <WindowControls :confirm-close="true" confirm-text="确认退出两平米软件库？" />

    <!-- 顶部栏 -->
    <div class="top-bar">
      <el-button link @click="router.push('/index')" style="color:#6b5e4e;padding:0 4px">
        <el-icon><Back /></el-icon> 返回
      </el-button>
      <span class="page-title">通用工具</span>
      <div style="flex:1" />
      <el-button
        link
        style="color:#8a7a6a;font-size:12px;padding:0 4px"
        @click="showGuide = !showGuide"
      >
        {{ showGuide ? '隐藏说明' : '显示说明' }}
        <el-icon style="margin-left:2px"><ArrowRight /></el-icon>
      </el-button>
    </div>

    <div class="page-body">
      <!-- 左侧工具列表 -->
      <div class="sidebar">
        <div
          class="sidebar-item"
          :class="{ active: activeTab === 'video-compress' }"
          @click="activeTab = 'video-compress'"
        >
          <el-icon><VideoPlay /></el-icon>
          <span>视频压缩</span>
        </div>
      </div>

      <!-- 操作区（左） -->
      <div class="work-area" v-if="activeTab === 'video-compress'">

        <!-- 选择文件 -->
        <div class="section">
          <div class="section-label">选择视频文件</div>
          <div class="file-picker" @click="pickFile">
            <el-icon style="font-size:22px;color:#c4883a"><VideoPlay /></el-icon>
            <div style="flex:1;min-width:0">
              <div v-if="inputFile" class="file-name">{{ inputFile }}</div>
              <div v-else style="color:#8a7a6a;font-size:14px">点击选择视频文件…</div>
              <div v-if="inputFile && videoWidth" style="font-size:12px;color:#8a7a6a;margin-top:2px">
                {{ videoWidth }}×{{ videoHeight }}
                · {{ videoDuration ? (videoDuration / 60).toFixed(1) + ' 分钟' : '' }}
                · {{ sizeEstimate?.original || '' }}
              </div>
            </div>
          </div>
        </div>

        <!-- 文件目录（选填，在压缩参数之外） -->
        <div class="section" v-if="inputFile">
          <div class="section-label">文件目录</div>
          <div class="param-row" style="margin:0">
            <el-input v-model="fileDir" placeholder="视频所在目录路径（选填，用于生成 cd 切换路径命令）" style="flex:1" />
            <el-button v-if="isElectron" @click="pickDirectory" style="flex-shrink:0">
              <el-icon><Folder /></el-icon> 浏览
            </el-button>
          </div>
        </div>

        <!-- 压缩视频（可选） -->
        <div class="section" v-if="inputFile">
          <div class="section-label toggle-label">
            压缩视频
            <el-switch v-model="compressEnabled" />
          </div>
          <div v-if="compressEnabled" class="params-grid">

            <!-- 分辨率 -->
            <div class="param-row">
              <label class="param-label">分辨率</label>
              <el-select v-model="resolution" style="flex:1">
                <el-option v-for="o in RESOLUTIONS" :key="o.value" :value="o.value" :label="o.label" />
              </el-select>
              <span v-if="targetWidth && resolution !== 'keep'" style="font-size:12px;color:#8a7a6a;white-space:nowrap">
                → {{ targetWidth }}×{{ targetHeight }}
              </span>
            </div>

            <!-- CRF 画质 -->
            <div class="param-row param-row-col">
              <div style="display:flex;align-items:center;gap:6px;width:100%">
                <label class="param-label" style="min-width:unset">画质 / CRF：<b>{{ crf }}</b></label>
                <span class="crf-hint">{{ crfLabel }}</span>
              </div>
              <div style="display:flex;align-items:center;gap:8px;width:100%">
                <span class="range-label">18 高质量</span>
                <el-slider v-model="crf" :min="18" :max="51" :step="1" style="flex:1" />
                <span class="range-label">51 低质量</span>
              </div>
            </div>

            <!-- 编码预设 -->
            <div class="param-row">
              <label class="param-label">编码预设</label>
              <el-select v-model="preset" style="flex:1">
                <el-option v-for="o in PRESETS" :key="o.value" :value="o.value" :label="o.label" />
              </el-select>
            </div>

            <!-- 视频编码器 -->
            <div class="param-row">
              <label class="param-label">视频编码</label>
              <el-radio-group v-model="videoCodec">
                <el-radio value="libx264">H.264（兼容性最好）</el-radio>
                <el-radio value="libx265">H.265（更小，较慢）</el-radio>
              </el-radio-group>
            </div>

            <!-- 音频 -->
            <div class="param-row">
              <label class="param-label">音频</label>
              <el-select v-model="audioBitrate" style="flex:1">
                <el-option v-for="o in AUDIO_OPTIONS" :key="o.value" :value="o.value" :label="o.label" />
              </el-select>
            </div>

            <!-- 额外参数 -->
            <div class="param-row">
              <label class="param-label">额外参数</label>
              <el-input v-model="extraArgs" placeholder="-ss 00:00:10 -t 60  （截取片段等）" style="flex:1" />
            </div>

            <!-- 预估大小（在压缩参数内部） -->
            <div v-if="sizeEstimate" class="size-estimate-box">
              <div class="size-row">
                <span class="size-label">原始大小</span>
                <span class="size-val">{{ sizeEstimate.original }}</span>
              </div>
              <div class="size-arrow">↓ 约减少 {{ sizeEstimate.ratio }}%</div>
              <div class="size-row">
                <span class="size-label">预估输出</span>
                <span class="size-val size-val-out">{{ sizeEstimate.lo }} ~ {{ sizeEstimate.hi }}</span>
              </div>
              <div class="size-note">预估基于典型视频码率，实际大小因内容差异较大</div>
            </div>

          </div>
        </div>

        <!-- 生成封面（可选） -->
        <div class="section" v-if="inputFile">
          <div class="section-label toggle-label">
            生成封面
            <el-switch v-model="generateCover" />
          </div>
          <div v-if="generateCover" class="cover-box">
            <video
              ref="coverVideoRef"
              :src="videoObjectUrl"
              class="cover-video"
              preload="auto"
              muted
              playsinline
            />
            <div class="cover-controls">
              <span class="cover-time">{{ fmtDisplay(coverTime) }}</span>
              <el-slider
                v-model="coverTime"
                :min="0"
                :max="videoDuration || 1"
                :step="0.1"
                style="flex:1"
              />
              <span class="cover-time">{{ fmtDisplay(videoDuration) }}</span>
            </div>
            <div class="cover-hint">拖动滑块选取封面帧，输出：封面-{{ inputFile.replace(/\.[^.]+$/, '') }}.png</div>
          </div>
        </div>

        <!-- 生成命令 -->
        <div class="section" v-if="combinedCommand">
          <div class="section-label">生成命令</div>
          <div class="command-box">
            <pre class="command-text">{{ combinedCommand }}</pre>
            <el-button type="primary" class="copy-btn" @click="copyText(combinedCommand)">
              <el-icon><CopyDocument /></el-icon> 复制
            </el-button>
          </div>
          <div class="command-tip" v-if="!fileDir">
            提示：填写文件目录后，命令会自动包含 cd 切换路径
          </div>
        </div>
      </div>

      <!-- 说明区（右），可隐藏 -->
      <div class="guide-area" v-if="activeTab === 'video-compress' && showGuide">
        <div class="guide-title">使用说明</div>

        <div class="guide-block">
          <div class="guide-step-title">① 安装 FFmpeg</div>
          <div class="guide-os">Windows</div>
          <div class="guide-desc">以管理员身份打开命令提示符，运行：</div>
          <pre class="guide-code">winget install Gyan.FFmpeg</pre>
          <div class="guide-desc" style="margin-top:4px">安装后重新打开终端即可使用。</div>
          <div class="guide-os" style="margin-top:10px">macOS</div>
          <div class="guide-desc">需先安装 Homebrew，然后运行：</div>
          <pre class="guide-code">brew install ffmpeg</pre>
        </div>

        <div class="guide-block">
          <div class="guide-step-title">② 打开终端</div>
          <div class="guide-os">Windows</div>
          <div class="guide-desc">在文件夹地址栏输入 <code>cmd</code> 回车，可直接在该目录打开终端。</div>
          <div class="guide-os" style="margin-top:8px">macOS</div>
          <div class="guide-desc">将文件夹拖入终端窗口，或使用 <code>cd</code> 切换目录。</div>
        </div>

        <div class="guide-block">
          <div class="guide-step-title">③ 粘贴命令运行</div>
          <div class="guide-desc">复制左侧生成的命令，粘贴到终端后回车。压缩完成后输出文件出现在同一目录。</div>
        </div>

        <div class="guide-block">
          <div class="guide-step-title">压缩参数说明</div>
          <table class="param-table">
            <tr><th>参数</th><th>含义</th></tr>
            <tr><td>CRF</td><td>画质控制，18 最高质量，28 均衡，51 最低质量</td></tr>
            <tr><td>preset</td><td>编码速度，越慢文件越小，fast 是平衡点</td></tr>
            <tr><td>H.264</td><td>兼容性最佳，手机/微信均可播放</td></tr>
            <tr><td>H.265</td><td>同画质约小 40%，部分旧设备不支持</td></tr>
            <tr><td>+faststart</td><td>网络播放时可边下边看</td></tr>
          </table>
          <div class="guide-desc" style="margin-top:8px">输出文件名自动命名为 <code>压缩-原文件名</code>，存放于相同目录。</div>
        </div>

        <div class="guide-block">
          <div class="guide-step-title">生成封面说明</div>
          <div class="guide-desc">拖动时间轴选取任意帧作为封面，生成命令会提取该帧并输出为：</div>
          <pre class="guide-code">封面-原文件名.png</pre>
          <div class="guide-desc" style="margin-top:4px">封面文件存放于与视频相同的目录。如同时开启压缩视频，两条命令将合并为一行，用 <code>&&</code> 连接，依次执行。</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── 整体布局 ── */
.page-wrapper {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #ede8dc;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'PingFang SC', sans-serif;
  overflow: hidden;
}

.top-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px 6px;
  flex-shrink: 0;
}

.page-title { font-size: 17px; font-weight: 700; color: #3a3028; }

.page-body { flex: 1; display: flex; overflow: hidden; }

/* ── 工具列表侧边栏 ── */
.sidebar {
  width: 130px;
  flex-shrink: 0;
  padding: 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-right: 1px solid #e0d4c0;
  overflow-y: auto;
}

.sidebar-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border-radius: 10px;
  cursor: pointer;
  font-size: 13px;
  color: #6b5e4e;
  transition: background .15s;
}
.sidebar-item:hover  { background: #e8e0d0; }
.sidebar-item.active { background: #c4883a; color: #fff; }

/* ── 操作区（左） ── */
.work-area {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 16px 20px 24px;
  border-right: 1px solid #e0d4c0;
  scrollbar-width: thin;
  scrollbar-color: #d4c8b0 transparent;
}
.work-area::-webkit-scrollbar { width: 4px; }
.work-area::-webkit-scrollbar-track { background: transparent; }
.work-area::-webkit-scrollbar-thumb { background: #d4c8b0; border-radius: 2px; }

/* ── 说明区（右） ── */
.guide-area {
  width: 340px;
  flex-shrink: 0;
  overflow-y: auto;
  padding: 16px 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  scrollbar-width: thin;
  scrollbar-color: #d4c8b0 transparent;
}
.guide-area::-webkit-scrollbar { width: 4px; }
.guide-area::-webkit-scrollbar-track { background: transparent; }
.guide-area::-webkit-scrollbar-thumb { background: #d4c8b0; border-radius: 2px; }

.guide-title {
  font-size: 13px;
  font-weight: 700;
  color: #6b5e4e;
  letter-spacing: .04em;
  text-transform: uppercase;
  margin-bottom: 0;
}

/* ── Section ── */
.section { margin-bottom: 18px; }

.section-label {
  font-size: 12px;
  font-weight: 700;
  color: #6b5e4e;
  text-transform: uppercase;
  letter-spacing: .04em;
  margin-bottom: 8px;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ── 文件选择框 ── */
.file-picker {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: #fff;
  border: 2px dashed #e0d4c0;
  border-radius: 12px;
  cursor: pointer;
  transition: border-color .15s;
}
.file-picker:hover { border-color: #c4883a; }
.file-name { font-size: 14px; font-weight: 600; color: #3a3028; word-break: break-all; }

/* ── 参数行 ── */
.params-grid { display: flex; flex-direction: column; gap: 10px; }

.param-row {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #fff;
  border: 1px solid #e0d4c0;
  border-radius: 10px;
  padding: 9px 12px;
}
.param-row-col { flex-direction: column; align-items: flex-start; gap: 8px; }

.param-label {
  font-size: 13px;
  font-weight: 600;
  color: #3a3028;
  white-space: nowrap;
  min-width: 80px;
}

.crf-hint { font-size: 12px; color: #c4883a; }
.range-label { font-size: 11px; color: #8a7a6a; white-space: nowrap; }

/* ── 预估大小（在 params-grid 内） ── */
.size-estimate-box {
  background: #faf7f2;
  border: 1px solid #e0d4c0;
  border-radius: 10px;
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.size-row { display: flex; align-items: center; gap: 10px; }
.size-label { font-size: 12px; color: #6b5e4e; min-width: 60px; }
.size-val { font-size: 14px; font-weight: 600; color: #3a3028; }
.size-val-out { color: #c4883a; }
.size-arrow { font-size: 12px; color: #8a7a6a; padding-left: 70px; }
.size-note { font-size: 11px; color: #aaa; margin-top: 2px; }

/* ── 命令框 ── */
.command-box {
  background: #1e1a15;
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.command-text {
  flex: 1;
  margin: 0;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 12.5px;
  color: #e8dfc8;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.6;
}
.copy-btn { flex-shrink: 0; background: #c4883a; border-color: #c4883a; }
.copy-btn:hover { background: #e09050; border-color: #e09050; }
.command-tip { margin-top: 5px; font-size: 12px; color: #8a7a6a; }

/* ── 说明区内容 ── */
.guide-block {
  background: #fff;
  border: 1px solid #e0d4c0;
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.guide-step-title { font-size: 13px; font-weight: 700; color: #3a3028; margin-bottom: 2px; }

.guide-os {
  font-size: 11px;
  font-weight: 700;
  color: #c4883a;
  text-transform: uppercase;
  letter-spacing: .05em;
  margin-top: 4px;
}

.guide-desc { font-size: 12px; color: #6b5e4e; line-height: 1.5; }

.guide-code {
  margin: 2px 0 0;
  background: #f5f0e8;
  border-radius: 6px;
  padding: 6px 10px;
  font-family: 'Consolas', monospace;
  font-size: 12px;
  color: #3a3028;
  white-space: pre-wrap;
  word-break: break-all;
}

.guide-desc code {
  background: #f5f0e8;
  border-radius: 4px;
  padding: 1px 5px;
  font-family: 'Consolas', monospace;
  font-size: 11px;
  color: #c4883a;
}

.param-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin-top: 4px;
}
.param-table th, .param-table td {
  padding: 5px 8px;
  text-align: left;
  border-bottom: 1px solid #f0e8d8;
  color: #3a3028;
}
.param-table th { color: #6b5e4e; font-weight: 600; background: #faf7f2; }
.param-table td:first-child { font-family: 'Consolas', monospace; color: #c4883a; white-space: nowrap; font-size: 11px; }

/* ── 封面生成 ── */
.cover-box {
  background: #fff;
  border: 1px solid #e0d4c0;
  border-radius: 10px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cover-video {
  width: 100%;
  max-height: 260px;
  object-fit: contain;
  background: #111;
  border-radius: 8px;
  display: block;
}

.cover-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.cover-time {
  font-size: 12px;
  font-family: 'Consolas', monospace;
  color: #6b5e4e;
  white-space: nowrap;
  min-width: 38px;
}

.cover-hint {
  font-size: 12px;
  color: #8a7a6a;
}

/* ── 手机适配 ── */
@media (max-width: 768px) {
  .sidebar  { width: 100px; }
  .guide-area { display: none; }
}
</style>
