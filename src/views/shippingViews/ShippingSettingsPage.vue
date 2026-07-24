<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import OperatorConfig         from '../dataMgmtViews/OperatorConfig.vue'
import WarehouseConfig        from '../dataMgmtViews/WarehouseConfig.vue'
import EquivalentConfig       from '../dataMgmtViews/EquivalentConfig.vue'
import TagDimensionConfig     from '../dataMgmtViews/TagDimensionConfig.vue'
import FinanceCustomerMapping from '../dataMgmtViews/FinanceCustomerMapping.vue'

// ── 路由 ──────────────────────────────────────────
const route  = useRoute()
const router = useRouter()

// ── Tab 分组 ──────────────────────────────────────
const TAB_GROUPS = [
  {
    label: '来源与口径',
    tabs: [
      { key: 'operator',   label: '操作人分类' },
      { key: 'warehouse',  label: '仓库过滤配置' },
      { key: 'financeMap', label: '客户匹配' },
    ],
  },
  {
    label: '匹配规则',
    tabs: [
      { key: 'equivalent', label: '产成品通用件配置' },
    ],
  },
  {
    label: '分析设置',
    tabs: [
      { key: 'tagDim', label: '标签分析维度' },
    ],
  },
]
const ALL_TAB_KEYS = TAB_GROUPS.flatMap(g => g.tabs.map(t => t.key))

// 用 query.tab 持久化当前 Tab，刷新页面后保持
const activeTab = ref(ALL_TAB_KEYS.includes(route.query.tab) ? route.query.tab : 'operator')

watch(activeTab, (tab) => {
  if (route.query.tab !== tab) {
    router.replace({ query: { ...route.query, tab } })
  }
})
watch(() => route.query.tab, (tab) => {
  if (ALL_TAB_KEYS.includes(tab) && tab !== activeTab.value) {
    activeTab.value = tab
  }
})
</script>

<template>
  <div class="shipping-settings-page">
    <nav class="settings-nav">
      <div v-for="group in TAB_GROUPS" :key="group.label" class="nav-group">
        <div class="nav-group-label">{{ group.label }}</div>
        <button
          v-for="tab in group.tabs"
          :key="tab.key"
          class="nav-tab-item"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>
    </nav>
    <div class="settings-body">
      <OperatorConfig         v-show="activeTab === 'operator'" />
      <WarehouseConfig        v-show="activeTab === 'warehouse'" />
      <FinanceCustomerMapping v-show="activeTab === 'financeMap'" />
      <EquivalentConfig       v-show="activeTab === 'equivalent'" />
      <TagDimensionConfig     v-show="activeTab === 'tagDim'" />
    </div>
  </div>
</template>

<style scoped>
.shipping-settings-page {
  width: 100%; height: 100%;
  display: flex;
  overflow: hidden;
}

.settings-nav {
  width: 180px; flex-shrink: 0;
  padding: 20px 12px;
  border-right: 1px solid var(--border);
  overflow-y: auto;
  display: flex; flex-direction: column; gap: 18px;
}
.nav-group { display: flex; flex-direction: column; gap: 2px; }
.nav-group-label {
  font-size: 11px; color: var(--text-muted); font-weight: 600;
  padding: 4px 10px; letter-spacing: 0.05em;
}
.nav-tab-item {
  text-align: left;
  padding: 8px 10px;
  border: none; border-radius: 7px;
  background: transparent; color: var(--text-muted);
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
  white-space: nowrap;
}
.nav-tab-item:hover { background: rgba(196,136,58,0.07); color: var(--text-primary); }
.nav-tab-item.active { color: #fff; font-weight: 600; background: var(--accent); }

.settings-body {
  flex: 1; min-width: 0;
  overflow-y: auto;
  padding: 24px;
  box-sizing: border-box;
}

/* ── 窄屏：顶部横向可滚动 tab 列表，替代侧边栏 ────── */
@media (max-width: 900px) {
  .shipping-settings-page { flex-direction: column; }
  .settings-nav {
    width: 100%; height: auto;
    flex-direction: row; flex-wrap: nowrap;
    gap: 4px;
    padding: 10px 12px;
    border-right: none; border-bottom: 1px solid var(--border);
    overflow-x: auto; overflow-y: hidden;
  }
  .nav-group { flex-direction: row; align-items: center; flex-shrink: 0; gap: 4px; }
  .nav-group-label { padding: 4px 6px 4px 0; }
  .nav-tab-item { flex-shrink: 0; }
}
</style>
