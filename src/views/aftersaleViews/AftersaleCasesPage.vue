<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import WindowControls from '@/components/common/WindowControls.vue'
import AftersaleCasesTable from '@/components/aftersale/AftersaleCasesTable.vue'

// ── 路由参数解析 ──────────────────────────────────
const route = useRoute()
const tableRef = ref(null)
const exportLoading = ref(false)

// filter 从 URL query.f（base64 JSON）解析
const filter = computed(() => {
  try {
    const raw = route.query.f
    if (!raw) return { status: 'confirmed' }
    return JSON.parse(atob(raw))
  } catch {
    return { status: 'confirmed' }
  }
})

const title = computed(() => route.query.title ? decodeURIComponent(route.query.title) : '售后数据')
const total = computed(() => tableRef.value?.total ?? 0)

onMounted(() => {
  document.title = title.value + ' · 两平米软件库'
})
</script>

<template>
  <div class="cases-page">
    <WindowControls :confirm-close="true" confirm-text="确认退出两平米软件库？" />

    <!-- 顶部栏 -->
    <div class="page-header">
      <span class="page-title">{{ title }}</span>
      <span class="page-total">共 {{ total }} 条</span>
      <el-button
        size="small"
        :loading="exportLoading"
        class="btn-export"
        @click="tableRef?.exportData()"
      >导出</el-button>
    </div>

    <!-- 表格 -->
    <div class="page-body">
      <AftersaleCasesTable
        ref="tableRef"
        :filter="filter"
        :reset-filters-on-change="false"
        style="height:100%"
        @update:exportLoading="exportLoading = $event"
      />
    </div>
  </div>
</template>

<style scoped>
.cases-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg);
  overflow: hidden;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-card);
  flex-shrink: 0;
}

.page-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.page-total {
  font-size: 12px;
  color: var(--text-muted);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1px 8px;
}

.btn-export {
  margin-left: auto;
}

.page-body {
  flex: 1;
  min-height: 0;
  padding: 12px;
  overflow: hidden;
}
</style>
