<script setup>
// ── 导入 ──────────────────────────────────────────
// 研发 BOM 多层结构表（物料BOM 页与物料卡片共用）。
// 数据来自后端展开好的树：[{ id, drawing, erp_code, name, spec, category, qty, unit, children? }]
import { computed } from 'vue'

const props = defineProps({
  rows:       { type: Array,  default: () => [] },
  height:     { type: [String, Number], default: undefined },
  maxHeight:  { type: [String, Number], default: undefined },
  expandAll:  { type: Boolean, default: true },
  emptyText:  { type: String,  default: '暂无 BOM 数据' },
})
// 点击编码：由上层决定打开哪个物料卡片
const emit = defineEmits(['open-code'])

// ── 计算属性 ──────────────────────────────────────
// 层级序号：第一层 1、2、3，下级 1.1、1.2、1.2.1……按树中位置生成，不存库
const numberedRows = computed(() => {
  const walk = (nodes, prefix) => nodes.map((node, i) => {
    const seq = prefix ? `${prefix}.${i + 1}` : String(i + 1)
    return {
      ...node, _seq: seq,
      ...(node.children ? { children: walk(node.children, seq) } : {}),
    }
  })
  return walk(props.rows || [], '')
})

// ── 方法 ──────────────────────────────────────────
function formatQty(q) {
  if (q == null) return ''
  return Number.isInteger(q) ? String(q) : String(+Number(q).toFixed(4))
}
</script>

<template>
  <el-table
    class="bom-tree"
    :data="numberedRows"
    row-key="id"
    :tree-props="{ children: 'children' }"
    :default-expand-all="expandAll"
    :height="height"
    :max-height="maxHeight"
    size="small"
    border
    :empty-text="emptyText"
  >
    <!-- 序号列承载树的展开箭头与缩进，层级一目了然 -->
    <el-table-column label="序号" min-width="120">
      <template #default="{ row }">
        <span class="bt-seq mono">{{ row._seq }}</span>
        <span v-if="row.children?.length" class="bt-sub" title="下级数量">{{ row.children.length }}</span>
      </template>
    </el-table-column>
    <!-- 编码：研发编码与 ERP 编码一致，只显示一列；ERP 物料表里没有时显示研发编码并置灰 -->
    <el-table-column label="编码" width="160">
      <template #default="{ row }">
        <span v-if="row.erp_code" class="bt-erp mono" title="点击查看物料卡片"
              @click.stop="emit('open-code', row.erp_code)">{{ row.erp_code }}</span>
        <span v-else class="bt-none mono" title="ERP 物料表里没有对应编码">{{ row.drawing }}</span>
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
.bt-seq { font-size: 12px; font-weight: 600; color: #2c2420; }
.bt-sub {
  margin-left: 6px; padding: 0 5px; border-radius: 8px;
  font-size: 10px; line-height: 15px; display: inline-block;
  color: #4a8fc0; background: rgba(74,143,192,0.12);
}
.bt-erp { font-size: 12px; font-weight: 600; color: #2c2420; cursor: pointer; }
.bt-erp:hover { color: var(--accent); text-decoration: underline; }
.bt-none { font-size: 12px; color: var(--text-muted); }
</style>
