<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import WindowControls    from '@/components/common/WindowControls.vue'
import ShippingDashboard from './ShippingDashboard.vue'
import ShippingTable     from './ShippingTable.vue'

// ── 路由 ──────────────────────────────────────────
const router = useRouter()

// ── 响应式状态 ────────────────────────────────────
const activeTab = ref('chart') // 'chart' | 'data'

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
        <div class="title-divider"></div>
        <nav class="top-nav">
          <button class="nav-item" :class="{ active: activeTab === 'chart' }" @click="activeTab = 'chart'">图表</button>
          <button class="nav-item" :class="{ active: activeTab === 'data' }"  @click="activeTab = 'data'">数据</button>
        </nav>
      </div>
    </header>

    <!-- ── 主内容区 ────────────────────────────── -->
    <main class="main-content">
      <ShippingDashboard v-show="activeTab === 'chart'" />
      <ShippingTable     v-show="activeTab === 'data'" />
    </main>

  </div>
</template>

<style scoped>
.shipping-page {
  width: 100vw; height: 100vh;
  background: var(--bg);
  display: flex; flex-direction: column;
  overflow: hidden;
}

/* 顶部栏（与 page-product.vue 保持一致） */
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

/* 顶部 Tab 导航（与 page-product.vue 风格一致） */
.top-nav { display: flex; align-items: center; gap: 2px; margin-left: 8px; }
.nav-item {
  height: 32px; padding: 0 14px;
  border: none; border-radius: 7px;
  background: transparent; color: var(--text-muted);
  font-size: 13px; font-family: var(--font-family);
  cursor: pointer; transition: all 0.15s;
  position: relative;
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

.main-content {
  flex: 1; overflow: hidden;
  display: flex; flex-direction: column;
}

</style>
