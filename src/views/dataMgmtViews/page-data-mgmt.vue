<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import WindowControls  from '@/components/common/WindowControls.vue'
import DataImport       from './DataImport.vue'
import ReturnImport     from './ReturnImport.vue'
import OperatorConfig   from './OperatorConfig.vue'
import WarehouseConfig  from './WarehouseConfig.vue'

// ── 路由 ──────────────────────────────────────────
const router = useRouter()

// ── 当前页面 ──────────────────────────────────────
const activePage = ref('import')

// ── 刷新全局数据 ────────────────────────────────────
const resolving          = ref(false)
const showResolveConfirm = ref(false)
const showResolveProgress  = ref(false)  // 进度 dialog
const resolveCurrentOrder  = ref(0)      // 当前已处理订单数
const resolveTotalOrders   = ref(0)      // 总订单数
const resolvePrepareMsg    = ref('')     // 准备阶段说明文字
const resolvePrepareCount  = ref(0)      // 准备阶段已加载数量
const resolveSaving        = ref(false)  // 写入阶段
const resolveSaveCurrent   = ref(0)
const resolveSaveTotal     = ref(0)

const navItems = [
  {
    key: 'import',
    label: '导入数据',
    svg: 'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4 M17 8l-5-5-5 5 M12 3v12',
  },
  {
    key: 'config',
    label: '数据配置',
    svg: 'M12 2a4 4 0 100 8 4 4 0 000-8 M2 20a10 10 0 0120 0',
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
  showResolveConfirm.value  = false
  resolving.value           = true
  resolveCurrentOrder.value = 0
  resolveTotalOrders.value  = 0
  resolvePrepareMsg.value   = '正在初始化…'
  showResolveProgress.value = true
  try {
    const res = await http.post('/api/shipping/resolve-all')
    if (!res.success) {
      showResolveProgress.value = false
      ElMessage.error(res.message || '启动失败')
      return
    }
    const taskId = res.data.task_id

    await new Promise((resolve, reject) => {
      const es = new EventSource(`http://127.0.0.1:8765/api/shipping/import/progress/${taskId}`)
      es.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.step === 'preparing') {
          resolvePrepareMsg.value   = data.message  ?? '正在准备数据…'
          resolveTotalOrders.value  = data.total    ?? 0
          resolvePrepareCount.value = data.current  ?? 0
        } else if (data.step === 'resolving') {
          resolvePrepareMsg.value   = ''
          resolveSaving.value       = false
          resolveCurrentOrder.value = data.current ?? 0
          resolveTotalOrders.value  = data.total   ?? 0
        } else if (data.step === 'saving') {
          resolveSaving.value      = true
          resolveSaveCurrent.value = data.current ?? 0
          resolveSaveTotal.value   = data.total   ?? 0
        } else if (data.step === 'done') {
          es.close()
          resolveCurrentOrder.value = data.data.resolved
          resolveTotalOrders.value  = data.data.resolved
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
    resolving.value           = false
    showResolveProgress.value = false
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
        <button class="btn-resolve" :class="{ resolving }" :disabled="resolving" @click="showResolveConfirm = true">
          <svg class="resolve-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
          <span>刷新全局数据</span>
        </button>
      </div>
    </header>

    <!-- ── 刷新全局数据确认弹窗 ───────────────────── -->
    <el-dialog
      v-model="showResolveConfirm"
      title="刷新全局数据"
      width="400px"
      :close-on-click-modal="false"
    >
      <div class="confirm-body">
        将重新计算所有订单的成品组合（含发货数量、销退数量、实际数量），数据量较大时耗时较长，确认继续？
      </div>
      <template #footer>
        <el-button @click="showResolveConfirm = false">取消</el-button>
        <el-button type="primary" @click="handleResolveAll">确认刷新</el-button>
      </template>
    </el-dialog>

    <!-- ── 刷新进度弹窗 ──────────────────────────── -->
    <el-dialog
      v-model="showResolveProgress"
      title="刷新全局数据"
      width="420px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="false"
    >
      <div class="progress-body">
        <!-- 准备阶段：显示分批加载进度 -->
        <template v-if="resolvePrepareMsg">
          <div class="progress-label">
            <span class="progress-prepare-msg">{{ resolvePrepareMsg }}</span>
            <span class="progress-count">
              {{ resolvePrepareCount.toLocaleString() }}
              <span class="progress-sep">/</span>
              {{ resolveTotalOrders > 0 ? resolveTotalOrders.toLocaleString() : '…' }}
            </span>
          </div>
          <el-progress
            :percentage="resolveTotalOrders > 0 ? Math.min(Math.round(resolvePrepareCount / resolveTotalOrders * 100), 99) : 0"
            :stroke-width="10"
            :color="'#c4883a'"
            status=""
          />
        </template>
        <!-- 计算阶段 -->
        <template v-else-if="!resolveSaving">
          <div class="progress-label">
            <span>当前处理订单</span>
            <span class="progress-count">
              {{ resolveCurrentOrder.toLocaleString() }}
              <span class="progress-sep">/</span>
              {{ resolveTotalOrders > 0 ? resolveTotalOrders.toLocaleString() : '…' }}
            </span>
          </div>
          <el-progress
            :percentage="resolveTotalOrders > 0 ? Math.min(Math.round(resolveCurrentOrder / resolveTotalOrders * 100), 99) : 0"
            :stroke-width="10"
            :color="'#c4883a'"
            status=""
          />
        </template>
        <!-- 写入阶段 -->
        <template v-else>
          <div class="progress-label">
            <span>正在写入数据库</span>
            <span class="progress-count">
              {{ resolveSaveCurrent.toLocaleString() }}
              <span class="progress-sep">/</span>
              {{ resolveSaveTotal > 0 ? resolveSaveTotal.toLocaleString() : '…' }}
            </span>
          </div>
          <el-progress
            :percentage="resolveSaveTotal > 0 ? Math.min(Math.round(resolveSaveCurrent / resolveSaveTotal * 100), 100) : 0"
            :stroke-width="10"
            :color="'#c4883a'"
            status=""
          />
        </template>
        <div class="progress-hint">请勿关闭窗口，计算完成后将自动关闭</div>
      </div>
    </el-dialog>

    <!-- ── 主内容区 ────────────────────────────── -->
    <main class="main-content">
      <div class="content-body">
        <div v-show="activePage === 'import'" class="import-layout">
          <DataImport />
          <div class="import-divider"></div>
          <ReturnImport />
        </div>
        <div v-show="activePage === 'config'" class="config-layout">
          <OperatorConfig />
          <div class="import-divider"></div>
          <WarehouseConfig />
        </div>
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
  padding: 0 120px 0 14px;
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

.confirm-body {
  font-size: 13px; color: var(--text-primary); line-height: 1.7;
}

.progress-body {
  padding: 8px 0 4px;
  display: flex; flex-direction: column; gap: 14px;
}
.progress-label {
  display: flex; justify-content: space-between; align-items: baseline;
  font-size: 13px; color: var(--text-muted);
}
.progress-count {
  font-size: 16px; font-weight: 600; color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}
.progress-sep { margin: 0 4px; color: var(--text-muted); font-weight: 400; }
.progress-prepare-msg { font-size: 13px; color: var(--text-primary); }
.progress-count-small { font-size: 12px; color: var(--text-muted); }
.progress-hint {
  font-size: 12px; color: var(--text-muted); text-align: center;
}

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

/* 导入数据双列布局 */
.import-layout {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 0;
  align-items: start;
}
.import-divider {
  width: 1px;
  background: var(--border);
  margin: 0 36px;
  align-self: stretch;
  min-height: 200px;
}

/* 数据配置双列布局（操作人 + 仓库） */
.config-layout {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 0;
  align-items: start;
}
</style>
