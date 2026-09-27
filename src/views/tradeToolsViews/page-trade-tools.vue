<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, HomeFilled } from '@element-plus/icons-vue'
import { PhHouseLine, PhSwap } from '@phosphor-icons/vue'
import WindowControls from '@/components/common/WindowControls.vue'
import AppBottomBar from '@/components/common/AppBottomBar.vue'
import ProductModificationPlan from '@/components/tradeTools/ProductModificationPlan.vue'
import { smartBack } from '@/utils/smartBack'

// ── 路由 ──────────────────────────────────────────
const router = useRouter()

// ── 响应式状态 ────────────────────────────────────
const activeTab = ref('home')

// ── Tab 定义（首页"功能"分组 + 顶部导航）─────────────
// 产品改制目前只放方案讨论稿（badge 提示），流程确认可行后再开发功能
const tabs = [
  { key: 'home',         label: '主页',     icon: PhHouseLine },
  { key: 'modification', label: '产品改制', icon: PhSwap, badge: '方案讨论中' },
]

// ── 生命周期 ──────────────────────────────────────
onMounted(() => { window.electronAPI?.maximizeApp?.() })

// ── 方法 ──────────────────────────────────────────
function handleBack() {
  window.electronAPI?.unmaximizeApp?.()
  smartBack(router)
}

// 返回主页：与 handleBack 区别是不依赖浏览历史，始终回到 /index
function handleHome() {
  window.electronAPI?.unmaximizeApp?.()
  router.push('/index')
}
</script>

<template>
  <div class="trade-page">
    <WindowControls :confirm-close="true" confirm-text="确认退出两平米软件库？" />

    <!-- ── 顶部导航栏 ──────────────────────────── -->
    <header class="top-bar">
      <div class="top-left">
        <button class="btn-home" title="返回主页" @click="handleHome">
          <el-icon><HomeFilled /></el-icon>
        </button>
        <button class="btn-back" title="返回" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <span class="page-title">外贸工具</span>
        <div class="title-divider"></div>
        <nav class="top-nav">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="nav-item"
            :class="{ active: activeTab === tab.key }"
            @click="activeTab = tab.key"
          >
            <component :is="tab.icon" :size="15" weight="duotone" />
            {{ tab.label }}
          </button>
        </nav>
      </div>
    </header>

    <!-- ── 主内容区 ────────────────────────────── -->
    <main class="main-content">

      <!-- 主页 -->
      <div v-show="activeTab === 'home'" class="tab-panel home-panel">
        <div class="home-groups">
          <div class="home-group">
            <div class="home-group-label">功能</div>
            <div class="home-grid">
              <div
                v-for="tab in tabs.slice(1)"
                :key="tab.key"
                class="tool-card"
                @click="activeTab = tab.key"
              >
                <div class="tool-card-icon">
                  <component :is="tab.icon" :size="32" weight="duotone" color="#c4883a" />
                </div>
                <div class="tool-card-name">{{ tab.label }}</div>
                <div v-if="tab.badge" class="tool-card-badge">{{ tab.badge }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 产品改制：目前是方案讨论稿 -->
      <div v-show="activeTab === 'modification'" class="tab-panel scroll-panel">
        <ProductModificationPlan />
      </div>

    </main>
    <AppBottomBar />
  </div>
</template>

<style scoped>
.trade-page {
  width: 100vw; height: 100vh;
  background: var(--bg);
  display: flex; flex-direction: column;
  overflow: hidden;
}

/* ── 顶部栏（与研发部工具一致）── */
.top-bar {
  height: 50px; display: flex; align-items: center;
  padding: 0 14px;
  background: rgba(255,255,255,0.65);
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(12px);
  flex-shrink: 0; z-index: 10;
}
.top-left { display: flex; align-items: center; gap: 8px; min-width: 0; }

.btn-back, .btn-home {
  width: 30px; height: 30px; flex-shrink: 0;
  border: 1px solid var(--border); border-radius: 7px;
  background: transparent; color: var(--text-muted);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
}
.btn-back:hover, .btn-home:hover { background: var(--bg-card); color: var(--text-primary); }

.page-title { font-size: 14px; font-weight: 600; color: var(--text-primary); letter-spacing: 0.05em; white-space: nowrap; }
.title-divider { width: 1px; height: 16px; background: var(--border); margin-left: 8px; flex-shrink: 0; }

.top-nav { display: flex; align-items: center; gap: 2px; margin-left: 8px; overflow-x: auto; }
.nav-item {
  height: 32px; padding: 0 13px;
  border: none; border-radius: 7px;
  background: transparent; color: var(--text-muted);
  font-size: 13px; font-family: var(--font-family);
  cursor: pointer; transition: all 0.15s;
  position: relative; white-space: nowrap;
  display: flex; align-items: center; gap: 5px;
}
.nav-item:hover { color: var(--text-primary); background: var(--bg); }
.nav-item.active { color: var(--accent); font-weight: 600; }
.nav-item.active::after {
  content: '';
  position: absolute; bottom: 2px; left: 13px; right: 13px;
  height: 2px; border-radius: 1px;
  background: var(--accent);
}

/* ── 主内容区 ── */
.main-content { flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; }
.tab-panel { flex: 1; width: 100%; min-height: 0; }
.scroll-panel { overflow-y: auto; }
.scroll-panel::-webkit-scrollbar { width: 4px; }
.scroll-panel::-webkit-scrollbar-track { background: transparent; }
.scroll-panel::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* 主页：工具卡片网格 */
.home-panel {
  display: flex; align-items: center; justify-content: center;
  padding: 40px; overflow-y: auto;
}
.home-groups { display: flex; flex-direction: column; gap: 28px; }
.home-group-label {
  font-size: 12px; font-weight: 600; color: var(--text-muted);
  letter-spacing: 0.08em; margin-bottom: 10px; padding-left: 2px;
}
.home-grid { display: flex; gap: 24px; flex-wrap: wrap; }

.tool-card {
  position: relative;
  width: 140px;
  display: flex; flex-direction: column;
  align-items: center; gap: 10px;
  cursor: pointer;
  background: rgba(255,255,255,0.55);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 24px 16px 20px;
  backdrop-filter: blur(8px);
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.tool-card:hover {
  border-color: rgba(196,136,58,0.35);
  box-shadow: 0 8px 24px rgba(196,136,58,0.1);
  transform: translateY(-3px);
}
.tool-card-icon {
  width: 64px; height: 64px; border-radius: 16px;
  display: flex; align-items: center; justify-content: center;
  background: var(--bg-card);
  border: 1.5px solid var(--border);
  box-shadow: 0 4px 12px var(--shadow), inset 0 1px 0 rgba(255,255,255,0.8);
}
.tool-card-name { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.tool-card-badge {
  position: absolute; top: -7px; right: 10px;
  background: var(--accent-bg); border: 1px solid var(--border);
  border-radius: 6px; padding: 2px 7px;
  font-size: 10px; color: var(--text-muted);
}

@media (max-width: 768px) {
  .home-panel { padding: 24px 16px; align-items: flex-start; }
}
</style>
