<script setup>
// ── 导入 ──────────────────────────────────────────
import DataImport    from '../dataMgmtViews/DataImport.vue'
import FinanceImport from '../dataMgmtViews/FinanceImport.vue'
</script>

<template>
  <div class="shipping-imports-page">
    <div class="import-layout">
      <div class="import-section">
        <div class="import-section-title">发货数据</div>
        <DataImport />
      </div>
      <div class="import-divider"></div>
      <div class="import-section">
        <div class="import-section-title">财务数据</div>
        <FinanceImport />
      </div>
    </div>
  </div>
</template>

<style scoped>
.shipping-imports-page {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  padding: 24px;
  box-sizing: border-box;
}

.import-layout {
  display: flex;
  gap: 32px;
  max-width: 1200px;
  margin: 0 auto;
}
.import-section { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px; }
.import-section-title {
  font-size: 14px; font-weight: 600; color: var(--text-primary);
  padding-bottom: 8px; border-bottom: 1px solid var(--border);
}
.import-divider { width: 1px; background: var(--border); flex-shrink: 0; }

@media (max-width: 900px) {
  .import-layout { flex-direction: column; }
  .import-divider { width: 100%; height: 1px; }
}
</style>
