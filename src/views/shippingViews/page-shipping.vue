<script setup>
// ── 导入 ──────────────────────────────────────────
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import WindowControls    from '@/components/common/WindowControls.vue'
import ShippingDashboard from './ShippingDashboard.vue'

// ── 路由 ──────────────────────────────────────────
const router = useRouter()

// ── 生命周期 ──────────────────────────────────────
onMounted(() => {
  window.electronAPI?.maximizeApp?.()
})

// ── 方法 ──────────────────────────────────────────
function handleBack() {
  window.electronAPI?.unmaximizeApp?.()
  router.back()
}
</script>

<template>
  <div class="shipping-page">
    <WindowControls :confirm-close="true" confirm-text="确认退出两平米软件库？" />

    <!-- ── 顶部导航栏 ──────────────────────────── -->
    <header class="top-bar">
      <div class="top-left">
        <button class="btn-back" title="返回" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <span class="page-title">发货数据</span>
      </div>
    </header>

    <!-- ── 主内容区 ────────────────────────────── -->
    <main class="main-content">
      <ShippingDashboard />
    </main>

  </div>
</template>

<style scoped>
.shipping-page {
  width: 100vw; height: 100vh;
  background: var(--bg);
  display: flex; flex-direction: column;
  overflow: hidden;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

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

.main-content {
  flex: 1; overflow: hidden;
  display: flex; flex-direction: column;
}
</style>
