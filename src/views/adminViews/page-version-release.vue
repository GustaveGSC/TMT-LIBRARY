<!-- ─────────────────────────────────────────
  页面：page-version-release
  功能：版本发布（管理员），左侧表单可滚动，
        右侧历史版本最新一条展开其余折叠
───────────────────────────────────────── -->

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import WindowControls from '@/components/common/WindowControls.vue'

// ── 路由 ──────────────────────────────────
const router = useRouter()

// ── 表单状态 ──────────────────────────────
const form          = ref({ version: '', description: '' })
const uploadedFile  = ref(null)
const uploadedYml   = ref(null)
const isDragging    = ref(false)
const isDraggingYml = ref(false)
const fileInput     = ref(null)
const ymlInput      = ref(null)

// 文件大小格式化
const fileSizeText = computed(() => {
  if (!uploadedFile.value) return ''
  const s = uploadedFile.value.size
  if (s > 1024 * 1024) return `${(s / 1024 / 1024).toFixed(1)} MB`
  return `${(s / 1024).toFixed(0)} KB`
})

// 表单校验
const formValid = computed(() =>
  form.value.version.trim() && uploadedFile.value && uploadedYml.value
)

// ── 文件选择 ──────────────────────────────
function triggerFilePick() { fileInput.value?.click() }
function triggerYmlPick()  { ymlInput.value?.click() }

function handleFileChange(e)  { uploadedFile.value = e.target.files?.[0] || null }
function handleYmlChange(e)   { uploadedYml.value  = e.target.files?.[0] || null }
function handleDrop(e)        { isDragging.value = false;    uploadedFile.value = e.dataTransfer.files?.[0] || null }
function handleYmlDrop(e)     { isDraggingYml.value = false; uploadedYml.value  = e.dataTransfer.files?.[0] || null }

// ── 上传发布 ──────────────────────────────
const uploading     = ref(false)
const uploadPercent = ref(0)
const uploadStage   = ref('')

async function handleSubmit() {
  if (!formValid.value) return
  uploading.value     = true
  uploadPercent.value = 0

  try {
    // Step 1：上传安装包
    uploadStage.value = '上传安装包...'
    const exeForm = new FormData()
    exeForm.append('file', uploadedFile.value)
    exeForm.append('type', 'installer')
    const exeRes = await http.post('/api/version/upload', exeForm, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        uploadPercent.value = Math.floor((e.loaded / e.total) * 60)
      }
    })
    if (!exeRes.success) throw new Error(exeRes.message || '安装包上传失败')
    const downloadUrl = exeRes.data.url

    // Step 2：上传 latest.yml
    uploadStage.value   = '上传 latest.yml...'
    uploadPercent.value = 65
    const ymlForm = new FormData()
    ymlForm.append('file', uploadedYml.value)
    ymlForm.append('type', 'yml')
    const ymlRes = await http.post('/api/version/upload', ymlForm, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        uploadPercent.value = 65 + Math.floor((e.loaded / e.total) * 20)
      }
    })
    if (!ymlRes.success) throw new Error(ymlRes.message || 'yml 上传失败')

    // Step 3：写入数据库
    uploadStage.value   = '发布版本信息...'
    uploadPercent.value = 90
    const pubRes = await http.post('/api/version/', {
      version:      form.value.version.trim(),
      description:  form.value.description.trim(),
      download_url: downloadUrl,
    })
    if (!pubRes.success) throw new Error(pubRes.message || '发布失败')

    uploadPercent.value = 100
    ElMessage.success(`版本 ${form.value.version} 发布成功`)

    // 重置表单
    form.value         = { version: '', description: '' }
    uploadedFile.value = null
    uploadedYml.value  = null
    loadHistory()

  } catch (e) {
    ElMessage.error(e.message || '发布失败，请重试')
  } finally {
    uploading.value = false
  }
}

// ── 历史版本 ──────────────────────────────
const history        = ref([])
const historyLoading = ref(false)
const historyExpanded = ref(false)  // 是否展开全部历史

// 最新一条
const latestVersion = computed(() => history.value[0] || null)
// 其余历史（折叠部分）
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

    <!-- 页头（固定） -->
    <div class="page-header">
      <button class="btn-back" @click="router.back()">← 返回</button>
      <h1 class="page-title">发布新版本</h1>
    </div>

    <!-- 主体：左右布局 -->
    <div class="page-body">

      <!-- 左：发布表单（卡片内可滚动） -->
      <div class="form-col">
        <div class="release-card">
          <div class="release-card-body">

          <!-- 版本号 -->
          <div class="field">
            <div class="field-label">版本号 <span class="required">*</span></div>
            <el-input v-model="form.version" placeholder="如 V1.0.1" />
            <div class="field-hint">格式：V主.次.修（如 V1.0.1）；测试版用 Beta 0.0.1</div>
          </div>

          <!-- 更新说明 -->
          <div class="field">
            <div class="field-label">更新说明</div>
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="4"
              placeholder="描述本次更新内容，支持换行..."
            />
          </div>

          <!-- 安装包上传 -->
          <div class="field">
            <div class="field-label">安装包文件 <span class="required">*</span></div>
            <div
              class="upload-area"
              :class="{ 'has-file': uploadedFile, dragging: isDragging }"
              @click="triggerFilePick"
              @dragover.prevent="isDragging = true"
              @dragleave="isDragging = false"
              @drop.prevent="handleDrop"
            >
              <template v-if="!uploadedFile">
                <div class="upload-icon">⬆</div>
                <div class="upload-text">点击或拖拽安装包到这里</div>
                <div class="upload-hint">.exe / .dmg / .AppImage</div>
              </template>
              <template v-else>
                <div class="upload-icon done">✓</div>
                <div class="upload-text">{{ uploadedFile.name }}</div>
                <div class="upload-hint">{{ fileSizeText }}</div>
              </template>
            </div>
            <input ref="fileInput" type="file" accept=".exe,.dmg,.AppImage" style="display:none" @change="handleFileChange" />
          </div>

          <!-- latest.yml 上传 -->
          <div class="field">
            <div class="field-label">latest.yml <span class="required">*</span></div>
            <div
              class="upload-area small"
              :class="{ 'has-file': uploadedYml, dragging: isDraggingYml }"
              @click="triggerYmlPick"
              @dragover.prevent="isDraggingYml = true"
              @dragleave="isDraggingYml = false"
              @drop.prevent="handleYmlDrop"
            >
              <template v-if="!uploadedYml">
                <div class="upload-text">点击选择 latest.yml</div>
                <div class="upload-hint">electron-builder 打包时自动生成</div>
              </template>
              <template v-else>
                <div class="upload-text done">✓ {{ uploadedYml.name }}</div>
              </template>
            </div>
            <input ref="ymlInput" type="file" accept=".yml,.yaml" style="display:none" @change="handleYmlChange" />
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
        </div><!-- release-card-body -->
        </div><!-- release-card -->
      </div><!-- form-col -->

      <!-- 右：历史版本 -->
      <div class="history-col">
        <div class="history-card">
          <div class="history-header">历史版本</div>
          <div class="history-card-body">

          <div v-if="historyLoading" class="history-empty">加载中...</div>
          <div v-else-if="!latestVersion" class="history-empty">暂无历史版本</div>
          <template v-else>

            <!-- 最新版本（默认展开） -->
            <div class="history-item latest">
              <div class="history-item-header">
                <span class="history-version">{{ latestVersion.version }}</span>
                <span class="history-tag">最新</span>
                <span class="history-date">{{ latestVersion.created_at }}</span>
              </div>
              <div class="history-desc">{{ latestVersion.description || '无更新说明' }}</div>
            </div>

            <!-- 其余历史（折叠） -->
            <template v-if="olderVersions.length">
              <transition name="expand">
                <div v-if="historyExpanded" class="history-older">
                  <div
                    v-for="v in olderVersions"
                    :key="v.id"
                    class="history-item"
                  >
                    <div class="history-item-header">
                      <span class="history-version">{{ v.version }}</span>
                      <span class="history-date">{{ v.created_at }}</span>
                    </div>
                    <div class="history-desc">{{ v.description || '无更新说明' }}</div>
                  </div>
                </div>
              </transition>

              <!-- 展开/折叠按钮 -->
              <div class="history-toggle" @click="historyExpanded = !historyExpanded">
                {{ historyExpanded ? '收起历史版本' : `查看更多（${olderVersions.length} 条）` }}
                <span class="toggle-arrow" :class="{ open: historyExpanded }">›</span>
              </div>
            </template>

          </template>
          </div><!-- history-card-body -->
        </div><!-- history-card -->
      </div><!-- history-col -->

    </div>
  </div>
</template>

<style scoped>
/* ── 页面基础 ─────────────────────────────── */
.release-page {
  width: 100vw;
  height: 100vh;
  background: var(--bg);
  display: flex;
  flex-direction: column;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  box-sizing: border-box;
  overflow: hidden;
}

/* ── 页头（固定） ─────────────────────────── */
.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px 40px 16px;
  flex-shrink: 0;
}

.btn-back {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 13px;
  color: var(--text-muted);
  cursor: pointer;
  font-family: inherit;
  transition: all 0.2s;
}
.btn-back:hover { border-color: var(--accent); color: var(--accent); }

.page-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.03em;
}

/* ── 主体左右布局 ─────────────────────────── */
.page-body {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  padding: 0 40px 24px;
  overflow: hidden;
  min-height: 0;
}

/* ── 左侧表单列（不滚动，卡片内滚动） ───── */
.form-col {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.release-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: 0 2px 12px var(--shadow);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex: 1;
  min-height: 0;
}

.release-card-body {
  padding: 24px 28px;
  overflow-y: auto;
  flex: 1;
}

/* ── 右侧历史版本列（不滚动，卡片内滚动） ── */
.history-col {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.history-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: 0 2px 12px var(--shadow);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex: 1;
  min-height: 0;
}

.history-card-body {
  overflow-y: auto;
  flex: 1;
}

/* ── 美化滚动条 ───────────────────────────── */
.release-card-body::-webkit-scrollbar,
.history-card-body::-webkit-scrollbar {
  width: 4px;
}
.release-card-body::-webkit-scrollbar-track,
.history-card-body::-webkit-scrollbar-track {
  background: transparent;
}
.release-card-body::-webkit-scrollbar-thumb,
.history-card-body::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 4px;
}
.release-card-body::-webkit-scrollbar-thumb:hover,
.history-card-body::-webkit-scrollbar-thumb:hover {
  background: var(--text-muted);
}

.history-header {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.history-empty {
  font-size: 13px;
  color: var(--text-muted);
  padding: 32px 20px;
  text-align: center;
}

/* ── 历史版本条目 ─────────────────────────── */
.history-item {
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
}
.history-item:last-child { border-bottom: none; }
.history-item.latest { background: var(--accent-bg); }

.history-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.history-version {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
}

.history-tag {
  font-size: 10px;
  background: var(--accent);
  color: #fff;
  border-radius: 4px;
  padding: 1px 6px;
  letter-spacing: 0.05em;
}

.history-date {
  font-size: 11px;
  color: var(--text-muted);
  margin-left: auto;
}

.history-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
  white-space: pre-line;
}

/* ── 折叠历史 ─────────────────────────────── */
.history-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.2s;
  border-top: 1px solid var(--border);
}
.history-toggle:hover { color: var(--accent); }

.toggle-arrow {
  font-size: 14px;
  transition: transform 0.2s;
  line-height: 1;
}
.toggle-arrow.open { transform: rotate(90deg); }

/* ── 表单字段 ─────────────────────────────── */
.field { margin-bottom: 18px; }
.field-label {
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 0.08em;
  margin-bottom: 8px;
}
.required { color: var(--accent); }
.field-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 5px;
  opacity: 0.7;
}

/* ── 上传区域 ─────────────────────────────── */
.upload-area {
  border: 1.5px dashed var(--border);
  border-radius: 12px;
  padding: 28px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--accent-bg);
}
.upload-area:hover, .upload-area.dragging {
  border-color: var(--accent);
  background: rgba(196,136,58,0.04);
}
.upload-area.has-file {
  border-style: solid;
  border-color: var(--accent);
  background: rgba(196,136,58,0.04);
}
.upload-area.small { padding: 14px 20px; }

.upload-icon { font-size: 24px; margin-bottom: 6px; }
.upload-icon.done { color: var(--accent); }
.upload-text { font-size: 13px; color: var(--text-primary); font-weight: 500; margin-bottom: 3px; }
.upload-text.done { color: var(--accent); }
.upload-hint { font-size: 11px; color: var(--text-muted); }

/* ── 上传进度 ─────────────────────────────── */
.upload-progress {
  margin-bottom: 16px;
  background: var(--accent-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 16px;
}
.upload-progress-header {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

/* ── 展开动画 ─────────────────────────────── */
.expand-enter-active, .expand-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}
.expand-enter-from, .expand-leave-to { opacity: 0; max-height: 0; }
.expand-enter-to, .expand-leave-from { opacity: 1; max-height: 1000px; }
</style>