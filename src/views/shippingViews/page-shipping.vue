<script setup>
// ── 导入 ──────────────────────────────────────────
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, HomeFilled } from '@element-plus/icons-vue'
import WindowControls from '@/components/common/WindowControls.vue'
import { usePermission } from '@/composables/usePermission'
import AppBottomBar from '@/components/common/AppBottomBar.vue'

// ── 路由 ──────────────────────────────────────────
const route  = useRoute()
const router = useRouter()
const { canEditShipping } = usePermission()

const ALL_NAV_ITEMS = [
  { path: '/shipping',             label: '分析看板' },
  { path: '/shipping/orders',      label: '订单明细' },
  { path: '/shipping/imports',     label: '数据接入',  editOnly: true },
  { path: '/shipping/settings',    label: '规则设置',  editOnly: true },
  { path: '/shipping/maintenance', label: '数据维护',  editOnly: true },
]
// 数据接入/规则设置/数据维护只对有编辑权限的用户可见，viewer 看不到入口
const NAV_ITEMS = computed(() =>
  ALL_NAV_ITEMS.filter(item => !item.editOnly || canEditShipping)
)

// ── 生命周期 ──────────────────────────────────────
onMounted(() => {
  window.electronAPI?.maximizeApp?.()
})

// ── 方法 ──────────────────────────────────────────
function handleBack() {
  window.electronAPI?.unmaximizeApp?.()
  router.push('/index')
}

// 返回主页：本页 handleBack 本身就回 /index，这里保持独立函数便于两者行为各自调整
function handleHome() {
  window.electronAPI?.unmaximizeApp?.()
  router.push('/index')
}

function isActive(navPath) {
  // /shipping 本身是精确匹配（分析看板），其余子路径用前缀匹配保持刷新/深层链接下的高亮
  return navPath === '/shipping' ? route.path === '/shipping' : route.path.startsWith(navPath)
}

function goTo(navPath) {
  if (!isActive(navPath)) router.push(navPath)
}
</script>

<template>
  <div class="shipping-page">
    <WindowControls :confirm-close="true" confirm-text="确认退出两平米资料站？" />

    <!-- ── 顶部导航栏 ──────────────────────────── -->
    <header class="top-bar">
      <div class="top-left">
        <button class="btn-home" title="返回主页" @click="handleHome">
          <el-icon><HomeFilled /></el-icon>
        </button>
        <button class="btn-back" title="返回" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <span class="page-title">发货数据</span>
        <div class="title-divider"></div>
      </div>
      <nav class="top-nav" data-testid="shipping-nav">
        <button
          v-for="item in NAV_ITEMS"
          :key="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
          @click="goTo(item.path)"
        >
          {{ item.label }}
        </button>
      </nav>
    </header>

    <!-- ── 主内容区（子路由懒加载挂载）─────────────── -->
    <main class="main-content">
      <router-view />
    </main>

    <AppBottomBar />
  </div>
</template>

<style scoped>
.shipping-page {
  width: 100vw; height: 100vh;
  height: 100dvh; /* 动态视口高度，排除移动端浏览器地址栏/导航栏 */
  background: var(--bg);
  display: flex; flex-direction: column;
  overflow: hidden;
}

/* 顶部栏 */
.top-bar {
  height: 50px; display: flex; align-items: center;
  padding: 0 14px;
  background: rgba(255,255,255,0.65);
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(12px);
  flex-shrink: 0; z-index: 10;
  overflow: hidden;
}
.top-left { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.btn-back, .btn-home {
  width: 30px; height: 30px;
  border: 1px solid var(--border); border-radius: 7px;
  background: transparent; color: var(--text-muted);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
}
.btn-back:hover, .btn-home:hover { background: var(--bg-card); color: var(--text-primary); }
.page-title { font-size: 14px; font-weight: 600; color: var(--text-primary); letter-spacing: 0.05em; white-space: nowrap; }
.title-divider { width: 1px; height: 16px; background: var(--border); margin-left: 8px; flex-shrink: 0; }

/* 顶部导航：窄屏下允许横向滚动，不挤压标题/返回按钮 */
.top-nav {
  display: flex; align-items: center; gap: 2px;
  margin-left: 8px;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
}
.nav-item {
  height: 32px; padding: 0 14px;
  border: none; border-radius: 7px;
  background: transparent; color: var(--text-muted);
  font-size: 13px; font-family: var(--font-family);
  cursor: pointer; transition: all 0.15s;
  position: relative;
  white-space: nowrap; flex-shrink: 0;
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

/* ── 移动端响应式（≤768px） ──────────────────── */
@media (max-width: 768px) {
  .top-bar { height: 44px; padding: 0 10px; }
  .page-title { font-size: 13px; }
  .nav-item { padding: 0 10px; font-size: 12px; }
}
</style>
