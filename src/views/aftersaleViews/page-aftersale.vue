<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import WindowControls      from '@/components/common/WindowControls.vue'
import AftersaleProcess    from './AftersaleProcess.vue'
import AftersaleDashboard  from './AftersaleDashboard.vue'
import AftersaleTable      from './AftersaleTable.vue'
import http                from '@/api/http.js'

// ── 路由 ──────────────────────────────────────────
const router = useRouter()

// ── 响应式状态 ────────────────────────────────────
const activeTab    = ref('process')   // 'process' | 'chart' | 'data'
const pendingCount = ref(0)

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  window.electronAPI?.maximizeApp?.()
  await loadPendingCount()
})

// ── 方法 ──────────────────────────────────────────
function handleBack() {
  window.electronAPI?.unmaximizeApp?.()
  router.back()
}

async function loadPendingCount() {
  const res = await http.get('/api/aftersale/pending/count')
  if (res.success) pendingCount.value = res.data.count
}

// 处理工单确认后更新待处理数
function onCaseConfirmed() {
  loadPendingCount()
}
</script>

<template>
  <div class="aftersale-page">
    <WindowControls :confirm-close="true" confirm-text="确认退出两平米软件库？" />

    <!-- ── 顶部导航栏 ──────────────────────────── -->
    <header class="top-bar">
      <div class="top-left">
        <button class="btn-back" title="返回" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <span class="page-title">售后数据</span>
        <div class="title-divider"></div>
        <nav class="top-nav">
          <button
            class="nav-item"
            :class="{ active: activeTab === 'process' }"
            @click="activeTab = 'process'"
          >
            待处理
            <span v-if="pendingCount > 0" class="pending-badge">{{ pendingCount }}</span>
          </button>
          <button class="nav-item" :class="{ active: activeTab === 'chart' }" @click="activeTab = 'chart'">图表</button>
          <button class="nav-item" :class="{ active: activeTab === 'data' }"  @click="activeTab = 'data'">数据</button>
        </nav>
      </div>
    </header>

    <!-- ── 主内容区 ────────────────────────────── -->
    <main class="main-content">
      <AftersaleProcess
        v-show="activeTab === 'process'"
        @case-confirmed="onCaseConfirmed"
      />
      <AftersaleDashboard v-show="activeTab === 'chart'" />
      <AftersaleTable     v-show="activeTab === 'data'" />
    </main>

  </div>
</template>

<style scoped>
.aftersale-page {
  width: 100vw; height: 100vh;
  background: var(--bg);
  display: flex; flex-direction: column;
  overflow: hidden;
}

/* 顶部栏（与 page-shipping.vue 保持一致） */
.top-bar {
  height: 50px; display: flex; align-items: center;
  padding: 0 14px;
  background: rgba(255,255,255,0.65);
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(12px);
  flex-shrink: 0; z-index: 10;
}
.top-left { display: flex; align-items: center; gap: 8px; }
.btn-back {
  width: 30px; height: 30px;
  border: 1px solid var(--border); border-radius: 7px;
  background: transparent; color: var(--text-muted);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
}
.btn-back:hover { background: var(--bg-card); color: var(--text-primary); }
.page-title { font-size: 14px; font-weight: 600; color: var(--text-primary); letter-spacing: 0.05em; }
.title-divider { width: 1px; height: 16px; background: var(--border); margin-left: 8px; }

.top-nav { display: flex; align-items: center; gap: 2px; margin-left: 8px; }
.nav-item {
  height: 32px; padding: 0 14px;
  border: none; border-radius: 7px;
  background: transparent; color: var(--text-muted);
  font-size: 13px; font-family: var(--font-family);
  cursor: pointer; transition: all 0.15s;
  position: relative;
  display: flex; align-items: center; gap: 6px;
}
.nav-item:hover { color: var(--text-primary); background: var(--bg); }
.nav-item.active {
  color: var(--accent);
  font-weight: 600;
  background: transparent;
}
.nav-item.active::after {
  content: '';
  position: absolute; bottom: 2px; left: 14px; right: 14px;
  height: 2px; border-radius: 1px;
  background: var(--accent);
}

/* 待处理角标 */
.pending-badge {
  min-width: 16px; height: 16px; padding: 0 4px;
  background: #e05050; color: #fff;
  font-size: 10px; font-weight: 700; line-height: 16px;
  border-radius: 8px; text-align: center;
}

.main-content {
  flex: 1; overflow: hidden;
  display: flex; flex-direction: column;
}
</style>
