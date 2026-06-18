<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import http from '@/api/http'
import appIcon from '@/assets/app-icon.png'

// ── 响应式状态 ────────────────────────────────────
const router      = useRouter()
const loading     = ref(true)
const latest      = ref(null)
const history     = ref([])
const expanded    = ref(false)

// ── 计算属性 ──────────────────────────────────────
const olderVersions = computed(() => history.value.slice(1))

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  try {
    const [latestRes, listRes] = await Promise.all([
      http.get('/api/version/latest'),
      http.get('/api/version/list'),
    ])
    if (latestRes.success && latestRes.data) latest.value = latestRes.data
    if (listRes.success && listRes.data)    history.value = listRes.data
  } catch { }
  finally { loading.value = false }
})

// ── 方法 ──────────────────────────────────────────
function handleDownload() {
  if (latest.value?.download_url) {
    window.open(latest.value.download_url, '_blank')
  }
}
</script>

<template>
  <div class="download-page">
    <div class="bg-circle bg-circle-1"></div>
    <div class="bg-circle bg-circle-2"></div>

    <div class="card">

      <div v-if="loading" class="loading">加载中...</div>

      <template v-else>
        <!-- 头部：icon + 名称 + 版本 -->
        <div class="app-header">
          <img :src="appIcon" class="app-icon" alt="icon" />
          <div class="app-name">两平米资料站</div>
          <div class="app-version">v{{ latest?.version || '-' }}</div>
          <div class="app-desc">桌面端 · Windows</div>
        </div>

        <!-- 最新更新说明 -->
        <div class="release-notes">
          <div class="notes-label">最新更新说明</div>
          <div class="notes-body">{{ latest?.description || '暂无更新说明' }}</div>
        </div>

        <!-- 下载按钮 -->
        <button
          class="btn-download"
          :disabled="!latest?.download_url"
          @click="handleDownload"
        >
          下载桌面版
        </button>

        <!-- 历史版本 -->
        <div v-if="olderVersions.length" class="history-section">
          <div class="history-toggle" @click="expanded = !expanded">
            历史更新记录
            <span class="toggle-arrow" :class="{ open: expanded }">›</span>
          </div>

          <div class="history-list" :class="{ 'is-expanded': expanded }">
            <div v-for="v in olderVersions" :key="v.id" class="history-item">
              <div class="history-item-header">
                <span class="history-version">v{{ v.version }}</span>
                <span class="history-date">{{ v.created_at }}</span>
              </div>
              <div class="history-desc">{{ v.description || '暂无说明' }}</div>
            </div>
          </div>
        </div>

        <!-- 底部链接 -->
        <div class="footer-link" @click="router.push('/login')">进入 Web 版 →</div>

      </template>
    </div>
  </div>
</template>

<style scoped>
.download-page {
  width: 100vw;
  min-height: 100vh;
  background: var(--bg);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 16px;
  box-sizing: border-box;
  position: relative;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'PingFang SC', sans-serif;
}

.bg-circle { position: fixed; border-radius: 50%; pointer-events: none; }
.bg-circle-1 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(196,136,58,0.09) 0%, transparent 70%);
  top: -120px; right: -80px;
}
.bg-circle-2 {
  width: 360px; height: 360px;
  background: radial-gradient(circle, rgba(160,100,40,0.06) 0%, transparent 70%);
  bottom: 60px; left: -60px;
}

.card {
  position: relative; z-index: 1;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 40px 44px;
  width: 100%;
  max-width: 360px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.08);
  box-sizing: border-box;
}

.loading {
  font-size: 13px;
  color: var(--text-muted);
  padding: 24px 0;
}

/* 头部 */
.app-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.app-icon {
  width: 96px;
  height: 96px;
  border-radius: 24px;
  object-fit: contain;
  box-shadow: 0 4px 20px rgba(196,136,58,0.18);
}

.app-name {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 0.04em;
}

.app-version {
  font-size: 13px;
  font-family: monospace;
  color: var(--accent);
  background: rgba(196,136,58,0.1);
  border: 1px solid rgba(196,136,58,0.2);
  border-radius: 6px;
  padding: 2px 10px;
}

.app-desc {
  font-size: 12px;
  color: var(--text-muted);
}

/* 更新说明 */
.release-notes {
  width: 100%;
  background: var(--accent-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
}

.notes-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0.08em;
  margin-bottom: 8px;
}

.notes-body {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
  white-space: pre-line;
}

/* 下载按钮 */
.btn-download {
  width: 100%;
  padding: 12px 0;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  letter-spacing: 0.05em;
  transition: background 0.18s, transform 0.1s;
}
.btn-download:hover:not(:disabled) { background: #b8782e; }
.btn-download:active:not(:disabled) { transform: scale(0.98); }
.btn-download:disabled { opacity: 0.4; cursor: not-allowed; }

/* 历史版本 */
.history-section {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}

.history-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 16px;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.2s, background 0.2s;
  user-select: none;
}
.history-toggle:hover { color: var(--accent); background: rgba(196,136,58,0.04); }

.toggle-arrow {
  font-size: 16px;
  transition: transform 0.2s;
  line-height: 1;
}
.toggle-arrow.open { transform: rotate(90deg); }

.history-list {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.3s ease;
}

.history-list.is-expanded {
  max-height: 240px;
  overflow-y: auto;
  border-top: 1px solid var(--border);
}

.history-list::-webkit-scrollbar { width: 4px; }
.history-list::-webkit-scrollbar-track { background: transparent; }
.history-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

.history-item {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.history-item:last-child { border-bottom: none; }

.history-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 5px;
}

.history-version {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  font-family: monospace;
}

.history-date {
  font-size: 11px;
  color: var(--text-muted);
}

.history-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
  white-space: pre-line;
}


/* 底部链接 */
.footer-link {
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.2s;
}
.footer-link:hover { color: var(--accent); }
</style>
