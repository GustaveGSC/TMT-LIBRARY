<script setup>
// ── 导入 ──────────────────────────────────────────
// 研发 BOM 多层结构表（物料BOM 页与物料卡片共用）。
// 数据来自后端展开好的树：[{ id, drawing, erp_code, name, spec, category, qty, unit, children? }]
defineProps({
  rows:       { type: Array,  default: () => [] },
  height:     { type: [String, Number], default: undefined },
  maxHeight:  { type: [String, Number], default: undefined },
  expandAll:  { type: Boolean, default: true },
  emptyText:  { type: String,  default: '暂无 BOM 数据' },
})
// 点击 ERP 编码：由上层决定打开哪个物料卡片
const emit = defineEmits(['open-code'])

// ── 方法 ──────────────────────────────────────────
function formatQty(q) {
  if (q == null) return ''
  return Number.isInteger(q) ? String(q) : String(+Number(q).toFixed(4))
}
</script>

<template>
  <el-table
    class="bom-tree"
    :data="rows"
    row-key="id"
    :tree-props="{ children: 'children' }"
    :default-expand-all="expandAll"
    :height="height"
    :max-height="maxHeight"
    size="small"
    border
    :empty-text="emptyText"
  >
    <el-table-column label="研发编码" min-width="190">
      <template #default="{ row }">
        <span class="bt-drawing mono">{{ row.drawing }}</span>
        <span v-if="row.children?.length" class="bt-sub">{{ row.children.length }}</span>
      </template>
    </el-table-column>
    <el-table-column label="ERP 编码" width="150">
      <template #default="{ row }">
        <span v-if="row.erp_code" class="bt-erp mono" title="点击查看物料卡片"
              @click.stop="emit('open-code', row.erp_code)">{{ row.erp_code }}</span>
        <span v-else class="bt-none" title="ERP 物料表里没有对应编码">未匹配</span>
      </template>
    </el-table-column>
    <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip />
    <el-table-column prop="spec" label="规格" min-width="160" show-overflow-tooltip />
    <el-table-column prop="category" label="类别" width="90" show-overflow-tooltip />
    <el-table-column label="数量" width="70" align="right">
      <template #default="{ row }">{{ formatQty(row.qty) }}</template>
    </el-table-column>
    <el-table-column prop="unit" label="单位" width="60" align="center" />
  </el-table>
</template>

<style scoped>
.mono { font-family: 'SF Mono', Consolas, 'Microsoft YaHei UI', monospace; }
.bt-drawing { font-size: 12px; font-weight: 600; color: #2c2420; }
.bt-sub {
  margin-left: 6px; padding: 0 5px; border-radius: 8px;
  font-size: 10px; line-height: 15px; display: inline-block;
  color: #4a8fc0; background: rgba(74,143,192,0.12);
}
.bt-erp { font-size: 12px; color: #3a3028; cursor: pointer; }
.bt-erp:hover { color: var(--accent); text-decoration: underline; }
.bt-none { font-size: 11px; color: var(--text-muted); }
</style>
