<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import WindowControls  from '@/components/common/WindowControls.vue'
import DataImport      from './DataImport.vue'
import OperatorConfig  from './OperatorConfig.vue'

// ── 路由 ──────────────────────────────────────────
const router = useRouter()

// ── 当前页面 ──────────────────────────────────────
const activePage = ref('import')

// ── 重新计算成品组合 ────────────────────────────────
const resolving       = ref(false)
const resolveProgress = ref('')   // "123 / 4567 个订单"

const navItems = [
  {
    key: 'import',
    label: '导入数据',
    svg: 'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4 M17 8l-5-5-5 5 M12 3v12',
  },
  {
    key: 'operator',
    label: '操作人配置',
    svg: 'M7 7a3 3 0 100-6 3 3 0 000 6 M1 21v-1a6 6 0 0112 0v1 M15 6h7 M15 10h6 M15 14h4',
  },
]

// ── 生命周期 ──────────────────────────────────────
onMounted(() => {
  window.electronAPI?.maximizeApp?.()
})

// ── 方法 ──────────────────────────────────────────
function handleBack() {
  window.electronAPI?.unmaximizeApp?.()
  router.back()
}

async function handleResolveAll() {
  if (resolving.value) return
  resolving.value    = true
  resolveProgress.value = ''
  try {
    const res = await http.post('/api/shipping/resolve-all')
    if (!res.success) { ElMessage.error(res.message || '启动失败'); return }
    const taskId = res.data.task_id

    await new Promise((resolve, reject) => {
      const es = new EventSource(`http://127.0.0.1:8765/api/shipping/import/progress/${taskId}`)
      es.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.step === 'resolving') {
          resolveProgress.value = data.total ? `${data.current} / ${data.total} 个订单` : ''
        } else if (data.step === 'done') {
          es.close()
          ElMessage.success(`成品组合重新计算完成，共处理 ${data.data.resolved} 个订单`)
          resolve()
        } else if (data.step === 'error') {
          es.close()
          ElMessage.error(data.message || '计算失败')
          reject()
        }
      }
      es.onerror = () => { es.close(); reject() }
    })
  } catch {
    // ElMessage 已在内部处理
  } finally {
    resolving.value       = false
    resolveProgress.value = ''
  }
}
</script>

<template>
  <div class="data-mgmt-page">
    <WindowControls :confirm-close="true" confirm-text="确认退出两平米软件库？" />

    <!-- ── 顶部导航栏 ──────────────────────────── -->
    <header class="top-bar">
      <div class="top-left">
        <button class="btn-back" title="返回" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <span class="page-title">数据管理</span>
        <div class="title-divider"></div>
      </div>

      <nav class="top-nav">
        <button
          v-for="item in navItems"
          :key="item.key"
          class="nav-item"
          :class="{ active: activePage === item.key }"
          @click="activePage = item.key"
        >
          <svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path :d="item.svg" />
          </svg>
          <span>{{ item.label }}</span>
          <span v-if="activePage === item.key" class="nav-indicator"></span>
        </button>
      </nav>

      <div class="top-right">
        <button class="btn-resolve" :class="{ resolving }" :disabled="resolving" @click="handleResolveAll">
          <svg v-if="!resolving" class="resolve-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
          <span v-if="!resolving">重新计算成品组合</span>
          <span v-else class="resolve-spin">↻</span>
          <span v-if="resolving && resolveProgress" class="resolve-progress">{{ resolveProgress }}</span>
          <span v-else-if="resolving">计算中…</span>
        </button>
      </div>
    </header>

    <!-- ── 主内容区 ────────────────────────────── -->
    <main class="main-content">
      <div class="content-body">
        <DataImport    v-show="activePage === 'import'"   />
        <OperatorConfig v-show="activePage === 'operator'" />
      </div>
    </main>

  </div>
</template>

<style scoped>
.data-mgmt-page {
  width: 100vw; height: 100vh;
  background: var(--bg);
  display: flex; flex-direction: column;
  overflow: hidden;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ── 顶部栏 ───────────────────────────────────── */
.top-bar {
  height: 50px; display: flex; align-items: center;
  padding: 0 84px 0 14px;
  background: rgba(255,255,255,0.65);
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(12px);
  flex-shrink: 0; z-index: 10;
}
.top-left { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.btn-back {
  width: 30px; height: 30px;
  border: 1px solid var(--border); border-radius: 7px;
  background: transparent; color: var(--text-muted);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
}
.btn-back:hover { background: var(--bg-card); color: var(--text-primary); }
.page-title    { font-size: 14px; font-weight: 600; color: var(--text-primary); letter-spacing: 0.05em; }
.title-divider { width: 1px; height: 16px; background: var(--border); margin-left: 8px; }

.top-nav { display: flex; align-items: center; gap: 2px; flex: 1; padding: 0 8px; }
.nav-item {
  position: relative;
  display: flex; align-items: center; gap: 6px;
  padding: 6px 14px; border: none; border-radius: 7px;
  background: transparent; color: var(--text-muted);
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.18s; white-space: nowrap;
}
.nav-item:hover { background: rgba(196,136,58,0.07); color: var(--text-primary); }
.nav-item.active { color: var(--accent); font-weight: 600; background: transparent; }
.nav-svg { width: 15px; height: 15px; flex-shrink: 0; }
.nav-indicator {
  position: absolute; bottom: -9px; left: 50%;
  transform: translateX(-50%);
  width: 20px; height: 2px;
  background: var(--accent); border-radius: 1px;
}

.top-right { display: flex; align-items: center; flex-shrink: 0; }

.btn-resolve {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--border); border-radius: 7px;
  background: transparent; color: var(--text-muted);
  font-size: 12px; font-family: inherit;
  cursor: pointer; transition: all 0.18s; white-space: nowrap;
}
.btn-resolve:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.btn-resolve:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-resolve.resolving { border-color: rgba(196,136,58,0.4); color: var(--accent); }
.resolve-icon { width: 13px; height: 13px; flex-shrink: 0; }
.resolve-spin { display: inline-block; animation: spin 0.8s linear infinite; font-size: 14px; }
.resolve-progress { color: var(--text-muted); font-size: 11px; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── 主内容区 ─────────────────────────────────── */
.main-content {
  flex: 1; overflow: hidden;
  display: flex; flex-direction: column;
}
.content-body {
  flex: 1; overflow-y: auto;
  padding: 36px 48px;
}
.content-body::-webkit-scrollbar { width: 4px; }
.content-body::-webkit-scrollbar-track { background: transparent; }
.content-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
</style>
