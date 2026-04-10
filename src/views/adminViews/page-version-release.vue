<!-- ─────────────────────────────────────────
  页面：page-version-release
  功能：版本发布（管理员），支持 Windows + macOS 双包上传
───────────────────────────────────────── -->

<script setup>
// ── 导入 ──────────────────────────────────
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import axios from 'axios'

// 上传专用实例：不设 timeout，大文件传输时间不可预测
const uploadHttp = axios.create({ timeout: 0, baseURL: 'http://127.0.0.1:8765' })
import WindowControls from '@/components/common/WindowControls.vue'

// ── 路由 ──────────────────────────────────
const router = useRouter()

// ── 表单状态 ──────────────────────────────
const form = ref({ version: '', description: '' })

// Windows 文件
const winFile   = ref(null)
const winYml    = ref(null)
const winInput  = ref(null)
const winYmlInput = ref(null)
const isDraggingWin    = ref(false)
const isDraggingWinYml = ref(false)

// macOS 文件
const macFile   = ref(null)
const macYml    = ref(null)
const macInput  = ref(null)
const macYmlInput = ref(null)
const isDraggingMac    = ref(false)
const isDraggingMacYml = ref(false)

// ── 计算属性 ──────────────────────────────
// Windows 平台完整：安装包 + yml 都选了
const winReady = computed(() => !!(winFile.value && winYml.value))
// macOS 平台完整：安装包 + yml 都选了
const macReady = computed(() => !!(macFile.value && macYml.value))
// 表单可提交：版本号填写 + 至少一个平台完整
const formValid = computed(() =>
  form.value.version.trim() && (winReady.value || macReady.value)
)

function sizeText(f) {
  if (!f) return ''
  const s = f.size
  if (s > 1024 * 1024) return `${(s / 1024 / 1024).toFixed(1)} MB`
  return `${(s / 1024).toFixed(0)} KB`
}

// ── 文件选择 ──────────────────────────────
function pickWin()    { winInput.value?.click() }
function pickWinYml() { winYmlInput.value?.click() }
function pickMac()    { macInput.value?.click() }
function pickMacYml() { macYmlInput.value?.click() }

function onWinFile(e)    { winFile.value   = e.target.files?.[0] || null; e.target.value = '' }
function onWinYml(e)     { winYml.value    = e.target.files?.[0] || null; e.target.value = '' }
function onMacFile(e)    { macFile.value   = e.target.files?.[0] || null; e.target.value = '' }
function onMacYml(e)     { macYml.value    = e.target.files?.[0] || null; e.target.value = '' }

function dropWin(e)    { isDraggingWin.value    = false; winFile.value  = e.dataTransfer.files?.[0] || null }
function dropWinYml(e) { isDraggingWinYml.value = false; winYml.value   = e.dataTransfer.files?.[0] || null }
function dropMac(e)    { isDraggingMac.value    = false; macFile.value  = e.dataTransfer.files?.[0] || null }
function dropMacYml(e) { isDraggingMacYml.value = false; macYml.value   = e.dataTransfer.files?.[0] || null }

// ── 上传发布 ──────────────────────────────
const uploading     = ref(false)
const uploadPercent = ref(0)
const uploadStage   = ref('')

// 上传单个文件到 OSS，返回 URL；progress 回调接收 0~1
async function uploadToOss(file, onProgress) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('type', 'installer')
  const res = await uploadHttp.post('/api/version/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: e => onProgress(e.loaded / e.total),
  })
  const data = res.data
  if (!data.success) throw new Error(data.message || '上传失败')
  return data.data.url
}

async function handleSubmit() {
  if (!formValid.value) return
  uploading.value     = true
  uploadPercent.value = 0

  try {
    let winUrl = null
    let macUrl = null

    // 根据实际要上传的步骤数分配进度区间
    const steps = []
    if (winReady.value) steps.push('win_file', 'win_yml')
    if (macReady.value) steps.push('mac_file', 'mac_yml')
    steps.push('publish')
    const stepPct = 95 / (steps.length)
    let basePercent = 0

    // ── Windows 安装包 ──
    if (winReady.value) {
      uploadStage.value = 'Windows 安装包上传中...'
      winUrl = await uploadToOss(winFile.value, p => {
        uploadPercent.value = Math.floor(basePercent + p * stepPct)
      })
      basePercent += stepPct

      // ── Windows latest.yml ──
      uploadStage.value = 'latest.yml 上传中...'
      await uploadToOss(winYml.value, p => {
        uploadPercent.value = Math.floor(basePercent + p * stepPct)
      })
      basePercent += stepPct
    }

    // ── macOS 安装包 ──
    if (macReady.value) {
      uploadStage.value = 'macOS 安装包上传中...'
      macUrl = await uploadToOss(macFile.value, p => {
        uploadPercent.value = Math.floor(basePercent + p * stepPct)
      })
      basePercent += stepPct

      // ── macOS latest-mac.yml ──
      uploadStage.value = 'latest-mac.yml 上传中...'
      await uploadToOss(macYml.value, p => {
        uploadPercent.value = Math.floor(basePercent + p * stepPct)
      })
      basePercent += stepPct
    }

    // ── 写入数据库 ──
    uploadStage.value   = '发布版本信息...'
    uploadPercent.value = 95
    const pubRes = await http.post('/api/version/', {
      version:          form.value.version.trim(),
      description:      form.value.description.trim(),
      download_url:     winUrl,
      mac_download_url: macUrl,
    })
    if (!pubRes.success) throw new Error(pubRes.message || '发布失败')

    uploadPercent.value = 100
    ElMessage.success(`版本 ${form.value.version} 发布成功`)

    // 重置表单
    form.value    = { version: '', description: '' }
    winFile.value = winYml.value = null
    macFile.value = macYml.value = null
    loadHistory()

  } catch (e) {
    ElMessage.error(e.message || '发布失败，请重试')
  } finally {
    uploading.value = false
  }
}

// ── 历史版本 ──────────────────────────────
const history         = ref([])
const historyLoading  = ref(false)
const historyExpanded = ref(false)

const latestVersion = computed(() => history.value[0] || null)
const olderVersions = computed(() => history.value.slice(1))

async function loadHistory() {
  historyLoading.value = true
  try {
    const res = await http.get('/api/version/list')
    if (res.success) history.value = res.data || []
  } catch { }
  finally { historyLoading.value = false }
}

// ── 生命周期 ──────────────────────────────
onMounted(loadHistory)
</script>

<template>
  <div class="release-page">
    <WindowControls :confirm-close="true" confirm-text="确认退出两平米软件库？" />

    <!-- 页头 -->
    <div class="page-header">
      <button class="btn-back" @click="router.back()">← 返回</button>
      <h1 class="page-title">发布新版本</h1>
    </div>

    <!-- 主体：左右布局 -->
    <div class="page-body">

      <!-- 左：发布表单 -->
      <div class="form-col">
        <div class="release-card">
          <div class="release-card-body">

            <!-- 版本号 -->
            <div class="field">
              <div class="field-label">版本号 <span class="required">*</span></div>
              <el-input v-model="form.version" placeholder="如 1.0.2" />
              <div class="field-hint">格式：主.次.修（如 1.0.2）；测试版用 Beta 0.0.1</div>
            </div>

            <!-- 更新说明 -->
            <div class="field">
              <div class="field-label">更新说明</div>
              <el-input v-model="form.description" type="textarea" :rows="3" placeholder="描述本次更新内容..." />
            </div>

            <!-- ── Windows 区块 ── -->
            <div class="platform-block" :class="{ ready: winReady }">
              <div class="platform-title">
                <span class="platform-icon">🪟</span>
                <span>Windows</span>
                <span v-if="winReady" class="platform-badge">已就绪</span>
                <span v-else class="platform-badge optional">可选</span>
              </div>

              <!-- Windows 安装包 -->
              <div class="field">
                <div class="field-label">安装包（.exe）</div>
                <div
                  class="upload-area"
                  :class="{ 'has-file': winFile, dragging: isDraggingWin }"
                  @click="pickWin"
                  @dragover.prevent="isDraggingWin = true"
                  @dragleave="isDraggingWin = false"
                  @drop.prevent="dropWin"
                >
                  <template v-if="!winFile">
                    <div class="upload-icon">⬆</div>
                    <div class="upload-text">点击或拖拽 .exe 文件</div>
                  </template>
                  <template v-else>
                    <div class="upload-icon done">✓</div>
                    <div class="upload-text">{{ winFile.name }}</div>
                    <div class="upload-hint">{{ sizeText(winFile) }}</div>
                  </template>
                </div>
                <input ref="winInput" type="file" accept=".exe" style="display:none" @change="onWinFile" />
              </div>

              <!-- latest.yml -->
              <div class="field">
                <div class="field-label">latest.yml</div>
                <div
                  class="upload-area small"
                  :class="{ 'has-file': winYml, dragging: isDraggingWinYml }"
                  @click="pickWinYml"
                  @dragover.prevent="isDraggingWinYml = true"
                  @dragleave="isDraggingWinYml = false"
                  @drop.prevent="dropWinYml"
                >
                  <template v-if="!winYml">
                    <div class="upload-text">点击选择 latest.yml</div>
                  </template>
                  <template v-else>
                    <div class="upload-text done">✓ {{ winYml.name }}</div>
                  </template>
                </div>
                <input ref="winYmlInput" type="file" accept=".yml,.yaml" style="display:none" @change="onWinYml" />
              </div>
            </div>

            <!-- ── macOS 区块 ── -->
            <div class="platform-block" :class="{ ready: macReady }">
              <div class="platform-title">
                <span class="platform-icon">🍎</span>
                <span>macOS</span>
                <span v-if="macReady" class="platform-badge">已就绪</span>
                <span v-else class="platform-badge optional">可选</span>
              </div>

              <!-- macOS 安装包 -->
              <div class="field">
                <div class="field-label">安装包（.dmg）</div>
                <div
                  class="upload-area"
                  :class="{ 'has-file': macFile, dragging: isDraggingMac }"
                  @click="pickMac"
                  @dragover.prevent="isDraggingMac = true"
                  @dragleave="isDraggingMac = false"
                  @drop.prevent="dropMac"
                >
                  <template v-if="!macFile">
                    <div class="upload-icon">⬆</div>
                    <div class="upload-text">点击或拖拽 .dmg 文件</div>
                  </template>
                  <template v-else>
                    <div class="upload-icon done">✓</div>
                    <div class="upload-text">{{ macFile.name }}</div>
                    <div class="upload-hint">{{ sizeText(macFile) }}</div>
                  </template>
                </div>
                <input ref="macInput" type="file" accept=".dmg" style="display:none" @change="onMacFile" />
              </div>

              <!-- latest-mac.yml -->
              <div class="field">
                <div class="field-label">latest-mac.yml</div>
                <div
                  class="upload-area small"
                  :class="{ 'has-file': macYml, dragging: isDraggingMacYml }"
                  @click="pickMacYml"
                  @dragover.prevent="isDraggingMacYml = true"
                  @dragleave="isDraggingMacYml = false"
                  @drop.prevent="dropMacYml"
                >
                  <template v-if="!macYml">
                    <div class="upload-text">点击选择 latest-mac.yml</div>
                  </template>
                  <template v-else>
                    <div class="upload-text done">✓ {{ macYml.name }}</div>
                  </template>
                </div>
                <input ref="macYmlInput" type="file" accept=".yml,.yaml" style="display:none" @change="onMacYml" />
              </div>
            </div>

            <!-- 校验提示 -->
            <div v-if="form.version && !winReady && !macReady" class="validate-hint">
              至少完整填写一个平台（安装包 + yml）
            </div>

            <!-- 上传进度 -->
            <div v-if="uploading" class="upload-progress">
              <div class="upload-progress-header">
                <span>{{ uploadStage }}</span>
                <span>{{ uploadPercent }}%</span>
              </div>
              <el-progress :percentage="uploadPercent" :show-text="false" :stroke-width="6" />
            </div>

            <!-- 发布按钮 -->
            <el-button
              type="primary"
              :loading="uploading"
              :disabled="!formValid"
              style="width:100%;margin-top:8px;"
              @click="handleSubmit"
            >
              {{ uploading ? '发布中...' : '发布版本' }}
            </el-button>

          </div>
        </div>
      </div>

      <!-- 右：历史版本 -->
      <div class="history-col">
        <div class="history-card">
          <div class="history-header">历史版本</div>
          <div class="history-card-body">

            <div v-if="historyLoading" class="history-empty">加载中...</div>
            <div v-else-if="!latestVersion" class="history-empty">暂无历史版本</div>
            <template v-else>

              <!-- 最新版本 -->
              <div class="history-item latest">
                <div class="history-item-header">
                  <span class="history-version">{{ latestVersion.version }}</span>
                  <span class="history-tag">最新</span>
                  <span class="history-date">{{ latestVersion.created_at }}</span>
                </div>
                <div class="history-desc">{{ latestVersion.description || '无更新说明' }}</div>
                <div class="history-links">
                  <a v-if="latestVersion.download_url"     :href="latestVersion.download_url"     class="dl-link">🪟 Windows</a>
                  <a v-if="latestVersion.mac_download_url" :href="latestVersion.mac_download_url" class="dl-link">🍎 macOS</a>
                </div>
              </div>

              <!-- 旧版本（折叠） -->
              <template v-if="olderVersions.length">
                <transition name="expand">
                  <div v-if="historyExpanded" class="history-older">
                    <div v-for="v in olderVersions" :key="v.id" class="history-item">
                      <div class="history-item-header">
                        <span class="history-version">{{ v.version }}</span>
                        <span class="history-date">{{ v.created_at }}</span>
                      </div>
                      <div class="history-desc">{{ v.description || '无更新说明' }}</div>
                      <div class="history-links">
                        <a v-if="v.download_url"     :href="v.download_url"     class="dl-link">🪟 Windows</a>
                        <a v-if="v.mac_download_url" :href="v.mac_download_url" class="dl-link">🍎 macOS</a>
                      </div>
                    </div>
                  </div>
                </transition>
                <div class="history-toggle" @click="historyExpanded = !historyExpanded">
                  {{ historyExpanded ? '收起历史版本' : `查看更多（${olderVersions.length} 条）` }}
                  <span class="toggle-arrow" :class="{ open: historyExpanded }">›</span>
                </div>
              </template>

            </template>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.release-page {
  width: 100vw; height: 100vh;
  background: var(--bg);
  display: flex; flex-direction: column;
  font-family: var(--font-main);
  box-sizing: border-box; overflow: hidden;
}

.page-header {
  display: flex; align-items: center; gap: 16px;
  padding: 24px 40px 16px; flex-shrink: 0;
}
.btn-back {
  background: transparent; border: 1px solid var(--border); border-radius: 8px;
  padding: 6px 14px; font-size: 13px; color: var(--text-muted);
  cursor: pointer; font-family: inherit; transition: all 0.2s;
}
.btn-back:hover { border-color: var(--accent); color: var(--accent); }
.page-title { font-size: 18px; font-weight: 600; color: var(--text-primary); letter-spacing: 0.03em; }

.page-body {
  flex: 1; display: grid; grid-template-columns: 1fr 1fr;
  gap: 20px; padding: 0 40px 24px;
  overflow: hidden; min-height: 0;
}

.form-col, .history-col {
  overflow: hidden; display: flex; flex-direction: column; min-height: 0;
}

.release-card, .history-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 16px; box-shadow: 0 2px 12px var(--shadow);
  display: flex; flex-direction: column; overflow: hidden; flex: 1; min-height: 0;
}

.release-card-body {
  padding: 24px 28px; overflow-y: auto; flex: 1;
}

.history-card-body { overflow-y: auto; flex: 1; }

/* 滚动条 */
.release-card-body::-webkit-scrollbar,
.history-card-body::-webkit-scrollbar  { width: 4px; }
.release-card-body::-webkit-scrollbar-track,
.history-card-body::-webkit-scrollbar-track { background: transparent; }
.release-card-body::-webkit-scrollbar-thumb,
.history-card-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

/* 表单字段 */
.field { margin-bottom: 14px; }
.field-label { font-size: 12px; color: var(--text-muted); letter-spacing: 0.08em; margin-bottom: 7px; }
.required { color: var(--accent); }
.field-hint { font-size: 11px; color: var(--text-muted); margin-top: 5px; opacity: 0.7; }

/* 平台区块 */
.platform-block {
  border: 1.5px solid var(--border); border-radius: 12px;
  padding: 14px 16px; margin-bottom: 16px;
  transition: border-color 0.2s;
}
.platform-block.ready { border-color: var(--accent); }

.platform-title {
  display: flex; align-items: center; gap: 7px;
  font-size: 13px; font-weight: 600; color: var(--text-primary);
  margin-bottom: 12px;
}
.platform-icon { font-size: 15px; }
.platform-badge {
  margin-left: auto; font-size: 11px; border-radius: 4px;
  padding: 2px 8px; font-weight: 500;
  background: rgba(196,136,58,0.15); color: var(--accent);
}
.platform-badge.optional { background: var(--accent-bg); color: var(--text-muted); }

/* 上传区域 */
.upload-area {
  border: 1.5px dashed var(--border); border-radius: 10px;
  padding: 20px 16px; text-align: center; cursor: pointer;
  transition: all 0.2s; background: var(--accent-bg);
}
.upload-area:hover, .upload-area.dragging { border-color: var(--accent); background: rgba(196,136,58,0.04); }
.upload-area.has-file { border-style: solid; border-color: var(--accent); background: rgba(196,136,58,0.04); }
.upload-area.small { padding: 10px 16px; }

.upload-icon { font-size: 22px; margin-bottom: 4px; }
.upload-icon.done { color: var(--accent); }
.upload-text { font-size: 13px; color: var(--text-primary); font-weight: 500; margin-bottom: 2px; }
.upload-text.done { color: var(--accent); }
.upload-hint { font-size: 11px; color: var(--text-muted); }

/* 校验提示 */
.validate-hint {
  font-size: 12px; color: #c05040;
  margin-bottom: 12px; text-align: center;
}

/* 上传进度 */
.upload-progress {
  margin-bottom: 16px; background: var(--accent-bg);
  border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px;
}
.upload-progress-header {
  display: flex; justify-content: space-between;
  font-size: 12px; color: var(--text-muted); margin-bottom: 8px;
}

/* 历史版本 */
.history-header {
  font-size: 14px; font-weight: 600; color: var(--text-primary);
  padding: 16px 20px; border-bottom: 1px solid var(--border);
}
.history-empty { font-size: 13px; color: var(--text-muted); padding: 32px 20px; text-align: center; }

.history-item { padding: 14px 20px; border-bottom: 1px solid var(--border); }
.history-item:last-child { border-bottom: none; }
.history-item.latest { background: var(--accent-bg); }

.history-item-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.history-version { font-size: 13px; font-weight: 600; color: var(--accent); }
.history-tag { font-size: 10px; background: var(--accent); color: #fff; border-radius: 4px; padding: 1px 6px; }
.history-date { font-size: 11px; color: var(--text-muted); margin-left: auto; }
.history-desc { font-size: 12px; color: var(--text-secondary); line-height: 1.6; white-space: pre-line; }

.history-links { display: flex; gap: 10px; margin-top: 6px; }
.dl-link {
  font-size: 11px; color: var(--accent); text-decoration: none;
  border: 1px solid var(--border); border-radius: 5px; padding: 2px 8px;
  transition: all 0.15s;
}
.dl-link:hover { border-color: var(--accent); background: rgba(196,136,58,0.06); }

.history-toggle {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 12px; font-size: 12px; color: var(--text-muted);
  cursor: pointer; transition: color 0.2s; border-top: 1px solid var(--border);
}
.history-toggle:hover { color: var(--accent); }
.toggle-arrow { font-size: 14px; transition: transform 0.2s; line-height: 1; }
.toggle-arrow.open { transform: rotate(90deg); }

/* 展开动画 */
.expand-enter-active, .expand-leave-active { transition: all 0.25s ease; overflow: hidden; }
.expand-enter-from, .expand-leave-to { opacity: 0; max-height: 0; }
.expand-enter-to, .expand-leave-from { opacity: 1; max-height: 2000px; }
</style>
