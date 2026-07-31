<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, HomeFilled } from '@element-plus/icons-vue'
import { PhListDashes, PhBarcode } from '@phosphor-icons/vue'
import WindowControls from '@/components/common/WindowControls.vue'
import AppBottomBar from '@/components/common/AppBottomBar.vue'
import MaterialItemsPanel from '@/components/material/MaterialItemsPanel.vue'
import GroupCategoryConfig from '@/components/material/GroupCategoryConfig.vue'
import CodePrefixRules from '@/components/material/CodePrefixRules.vue'

// ── 路由 ──────────────────────────────────────────
const router = useRouter()

// ── 响应式状态 ────────────────────────────────────
const activeTab = ref('items')
const ruleTab   = ref('group')   // group 分组默认大类 / prefix 前缀例外规则

// 已挂载过的 tab，避免切走后重新拉数据；与产品库 mountedTabs 的做法一致
const mountedTabs = ref({ items: true, rules: false })

// ── Tab 定义 ──────────────────────────────────────
const tabs = [
  { key: 'items', label: '物料清单', icon: PhListDashes },
  { key: 'rules', label: '编码规则', icon: PhBarcode },
]

// ── 生命周期 ──────────────────────────────────────
onMounted(() => { window.electronAPI?.maximizeApp?.() })

// ── 方法 ──────────────────────────────────────────
function switchTab(key) {
  activeTab.value = key
  mountedTabs.value[key] = true
}

function handleBack() {
  window.electronAPI?.unmaximizeApp?.()
  router.back()
}

// 返回主页：与 handleBack 区别是不依赖浏览历史，始终回到 /index
function handleHome() {
  window.electronAPI?.unmaximizeApp?.()
  router.push('/index')
}
</script>

<template>
  <div class="material-page">
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
        <span class="page-title">物料库</span>
        <div class="title-divider"></div>
        <nav class="top-nav">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="nav-item"
            :class="{ active: activeTab === tab.key }"
            @click="switchTab(tab.key)"
          >
            <component :is="tab.icon" :size="15" weight="duotone" />
            {{ tab.label }}
          </button>
        </nav>
      </div>
    </header>

    <!-- ── 主内容区 ────────────────────────────── -->
    <main class="main-content">

      <!-- 物料清单 -->
      <div v-if="mountedTabs.items" v-show="activeTab === 'items'" class="tab-panel">
        <MaterialItemsPanel />
      </div>

      <!-- 编码规则：分组默认大类 + 前缀例外规则 -->
      <div v-if="mountedTabs.rules" v-show="activeTab === 'rules'" class="tab-panel">
        <div class="sub-tabs">
          <button class="sub-tab" :class="{ active: ruleTab === 'group' }"
                  @click="ruleTab = 'group'">分组默认大类</button>
          <button class="sub-tab" :class="{ active: ruleTab === 'prefix' }"
                  @click="ruleTab = 'prefix'">前缀例外规则</button>
        </div>
        <div class="sub-panel">
          <GroupCategoryConfig v-show="ruleTab === 'group'" />
          <CodePrefixRules v-show="ruleTab === 'prefix'" />
        </div>
      </div>

    </main>
    <AppBottomBar />
  </div>
</template>

<style scoped>
.material-page {
  width: 100vw; height: 100vh;
  background: var(--bg);
  display: flex; flex-direction: column;
  overflow: hidden;
}

/* ── 顶部栏（与其他页面一致）── */
.top-bar {
  height: 46px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 18px;
  background: rgba(255,255,255,0.5);
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(12px);
  box-sizing: border-box;
}
.top-left { display: flex; align-items: center; gap: 8px; }

.btn-back, .btn-home {
  width: 30px; height: 30px;
  border: 1px solid var(--border); border-radius: 7px;
  background: transparent; color: var(--text-muted);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
}
.btn-back:hover, .btn-home:hover { background: var(--bg-card); color: var(--text-primary); }
.page-title { font-size: 14px; font-weight: 600; color: var(--text-primary); letter-spacing: 0.05em; }
.title-divider { width: 1px; height: 16px; background: var(--border); margin-left: 8px; }

.top-nav { display: flex; align-items: center; gap: 2px; margin-left: 8px; }
.nav-item {
  height: 32px; padding: 0 14px;
  display: flex; align-items: center; gap: 6px;
  border: none; border-radius: 7px;
  background: transparent; color: var(--text-muted);
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.2s;
}
.nav-item:hover { background: var(--accent-bg); color: var(--accent); }
.nav-item.active { background: var(--accent-bg); color: var(--accent); font-weight: 600; }

/* ── 主内容 ───────────────────────────────────── */
.main-content {
  flex: 1; min-height: 0;
  padding: 14px 18px;
  overflow: hidden;
  display: flex; flex-direction: column;
}
.tab-panel { flex: 1; min-height: 0; display: flex; flex-direction: column; }

/* ── 子 tab ───────────────────────────────────── */
.sub-tabs { display: flex; gap: 6px; margin-bottom: 12px; flex-shrink: 0; }
.sub-tab {
  padding: 5px 16px; border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--bg-card); color: var(--text-muted);
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
}
.sub-tab:hover { border-color: var(--accent); color: var(--accent); }
.sub-tab.active { background: var(--accent-bg); border-color: var(--accent); color: var(--accent); font-weight: 600; }
.sub-panel { flex: 1; min-height: 0; overflow-y: auto; }
.sub-panel::-webkit-scrollbar { width: 4px; }
.sub-panel::-webkit-scrollbar-track { background: transparent; }
.sub-panel::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
</style>
