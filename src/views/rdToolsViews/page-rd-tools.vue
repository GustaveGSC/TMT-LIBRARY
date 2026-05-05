<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import WindowControls from '@/components/common/WindowControls.vue'
import { PhHouseLine, PhArrowsLeftRight, PhClipboardText, PhBell } from '@phosphor-icons/vue'
import EcrForm from '@/components/rdTools/EcrForm.vue'

// ── 路由 ──────────────────────────────────────────
const router = useRouter()

// ── 响应式状态 ────────────────────────────────────
const activeTab = ref('home')

// ── Tab 定义 ──────────────────────────────────────
const tabs = [
  { key: 'home',     label: '主页',          icon: PhHouseLine },
  { key: 'pdm2bom', label: 'PDM转BOM',      icon: PhArrowsLeftRight, coming: true },
  { key: 'ecr',     label: '变更申请单填写', icon: PhClipboardText },
  { key: 'ecn',     label: '变更通知单填写', icon: PhBell,            coming: true },
]

// ── 生命周期 ──────────────────────────────────────
onMounted(() => { window.electronAPI?.maximizeApp?.() })

// ── 方法 ──────────────────────────────────────────
function handleBack() {
  window.electronAPI?.unmaximizeApp?.()
  router.back()
}
</script>

<template>
  <div class="rd-page">
    <WindowControls :confirm-close="true" confirm-text="确认退出两平米软件库？" />

    <!-- ── 顶部导航栏 ──────────────────────────── -->
    <header class="top-bar">
      <div class="top-left">
        <button class="btn-back" title="返回" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <span class="page-title">研发部工具</span>
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
            <div v-if="tab.coming" class="tool-card-badge">即将上线</div>
          </div>
        </div>
      </div>

      <!-- PDM转BOM -->
      <div v-show="activeTab === 'pdm2bom'" class="tab-panel coming-panel">
        <component :is="PhArrowsLeftRight" :size="48" weight="duotone" color="#c4883a" style="opacity:0.4" />
        <div class="coming-title">PDM 转 BOM</div>
        <div class="coming-desc">从 PDM 导出文件自动转换为标准 BOM 格式，功能开发中</div>
      </div>

      <!-- 变更申请单填写 -->
      <div v-show="activeTab === 'ecr'" class="tab-panel ecr-panel">
        <EcrForm />
      </div>

      <!-- 变更通知单填写 -->
      <div v-show="activeTab === 'ecn'" class="tab-panel coming-panel">
        <component :is="PhBell" :size="48" weight="duotone" color="#c4883a" style="opacity:0.4" />
        <div class="coming-title">变更通知单填写</div>
        <div class="coming-desc">ECN 变更通知单填写与导出，功能开发中</div>
      </div>

    </main>
  </div>
</template>

<style scoped>
.rd-page {
  width: 100vw; height: 100vh;
  background: var(--bg);
  display: flex; flex-direction: column;
  overflow: hidden;
}

/* ── 顶部栏（与其他页面一致）── */
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
  height: 32px; padding: 0 13px;
  border: none; border-radius: 7px;
  background: transparent; color: var(--text-muted);
  font-size: 13px; font-family: var(--font-family);
  cursor: pointer; transition: all 0.15s;
  position: relative;
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
.main-content { flex: 1; overflow: hidden; display: flex; flex-direction: column; }

.tab-panel { flex: 1; width: 100%; height: 100%; }

/* 主页：工具卡片网格 */
.home-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.home-grid { display: flex; gap: 24px; }

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

/* 功能开发中占位 */
.coming-panel {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px; padding: 40px;
}
.coming-title {
  font-size: 16px; font-weight: 600;
  color: var(--text-primary); letter-spacing: 0.04em;
  margin-top: 4px;
}
.coming-desc { font-size: 13px; color: var(--text-muted); text-align: center; max-width: 280px; line-height: 1.6; }

.ecr-panel {
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
</style>
