<script setup>
import { ref, computed } from 'vue'
import { usePermission } from '@/composables/usePermission'
import AftersaleCasesTable from '@/components/aftersale/AftersaleCasesTable.vue'

const tableRef    = ref(null)
const dateRange   = ref([])
const noSalesMode = ref('all')  // 'all' | 'exclude'

const { can } = usePermission()

// 把工具栏状态合并为 filter prop 传给表格
const tableFilter = computed(() => ({
  status:                  'confirmed',
  date_start:              dateRange.value?.[0] || undefined,
  date_end:                dateRange.value?.[1] || undefined,
  exclude_no_sales_series: noSalesMode.value === 'exclude' || undefined,
}))

defineExpose({ refresh: () => tableRef.value?.refresh() })
</script>

<template>
  <div class="table-page">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-date-picker
        v-model="dateRange"
        type="daterange" size="small" range-separator="~"
        start-placeholder="售后日期起" end-placeholder="售后日期止"
        value-format="YYYY-MM-DD" style="width:230px"
      />
      <el-radio-group v-model="noSalesMode" size="small">
        <el-radio value="all">所有数据</el-radio>
        <el-radio value="exclude">不记录当前未销售产品数据</el-radio>
      </el-radio-group>
      <el-button
        v-if="can('aftersale:export')"
        size="small"
        :loading="tableRef?.exportLoading"
        class="export-btn"
        @click="tableRef?.exportData()"
      >导出</el-button>
    </div>

    <!-- 共享表格组件 -->
    <AftersaleCasesTable
      ref="tableRef"
      :filter="tableFilter"
      style="flex:1; overflow:hidden"
    />
  </div>
</template>

<style scoped>
.table-page {
  flex: 1; display: flex; flex-direction: column;
  overflow: hidden; padding: 12px 16px;
}
.toolbar {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 10px; flex-wrap: wrap; flex-shrink: 0;
}
.export-btn {
  background: var(--accent); color: #fff; border: none; border-radius: 8px;
}
.export-btn:hover { background: var(--accent-hover); }
</style>
