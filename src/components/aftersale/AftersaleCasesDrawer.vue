<script setup>
import { ref, computed } from 'vue'
import AftersaleCasesTable from './AftersaleCasesTable.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  filter:     { type: Object,  default: () => ({}) },
  title:      { type: String,  default: '相关售后数据' },
})
const emit = defineEmits(['update:modelValue'])

const tableRef        = ref(null)
const exportLoading   = ref(false)

// 合并外部筛选（图表上下文） + 固定 status
const drawerFilter = computed(() => ({ status: 'confirmed', ...props.filter }))

function handleClose() { emit('update:modelValue', false) }

function onOpened() {
  tableRef.value?.initSort?.()
}

// 在新标签页打开当前表格
function openInNewTab() {
  const f = btoa(JSON.stringify(drawerFilter.value))
  const title = encodeURIComponent(props.title)
  const url = `${location.origin}${location.pathname}#/aftersale/cases?f=${f}&title=${title}`
  window.open(url, '_blank')
}
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    direction="rtl"
    size="80%"
    :before-close="handleClose"
    class="cases-drawer"
    @opened="onOpened"
  >
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ title }}</span>
        <span class="drawer-total">共 {{ tableRef?.total ?? 0 }} 条</span>
        <el-button size="small" class="btn-newtab" title="在新标签页中打开" @click="openInNewTab">↗ 新标签页</el-button>
        <el-button
          size="small"
          :loading="exportLoading"
          class="btn-export"
          @click="tableRef?.exportData()"
        >导出</el-button>
      </div>
    </template>

    <AftersaleCasesTable
      v-if="modelValue"
      ref="tableRef"
      :filter="drawerFilter"
      :reset-filters-on-change="true"
      style="height:100%"
      @update:exportLoading="exportLoading = $event"
    />
  </el-drawer>
</template>

<style scoped>
.drawer-header { display: flex; align-items: center; gap: 10px; flex: 1; }
.drawer-title  { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.drawer-total  {
  font-size: 12px; color: var(--text-muted);
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 10px; padding: 1px 8px;
}
.btn-newtab { margin-left: auto; }
.btn-export { margin-right: 8px; }
</style>
