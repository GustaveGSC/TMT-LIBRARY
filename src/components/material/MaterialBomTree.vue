<script setup>
// ── 导入 ──────────────────────────────────────────
// 研发 BOM 多层结构表（物料BOM 页与物料卡片共用）。
// 数据来自后端展开好的树：[{ id, drawing, erp_code, name, spec, category, qty, unit, children? }]
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  rows:       { type: Array,  default: () => [] },
  height:     { type: [String, Number], default: undefined },
  maxHeight:  { type: [String, Number], default: undefined },
  expandAll:  { type: Boolean, default: true },
  emptyText:  { type: String,  default: '暂无 BOM 数据' },
  // 筛选词（编码/名称，不区分大小写）：命中的行连同它的上级链路保留，其余隐藏
  keyword:    { type: String,  default: '' },
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

const kw = computed(() => (props.keyword || '').trim().toLowerCase())

function isHit(node) {
  const k = kw.value
  if (!k) return false
  return [node.drawing, node.erp_code, node.name]
    .some(v => v && String(v).toLowerCase().includes(k))
}

// 筛选后的树：序号在筛选前已生成，所以筛选后仍是原层级编号，便于对照原表
const filtered = computed(() => {
  if (!kw.value) return { rows: numberedRows.value, hits: 0 }
  let hits = 0
  const walk = nodes => nodes.reduce((acc, node) => {
    const children = node.children ? walk(node.children) : []
    const hit = isHit(node)
    if (hit) hits++
    if (hit || children.length) {
      acc.push({ ...node, _hit: hit, ...(node.children ? { children } : {}) })
    }
    return acc
  }, [])
  const rows = walk(numberedRows.value)
  return { rows, hits }
})

// 命中行浅色高亮，上级链路行保持原样
function rowClass({ row }) { return row._hit ? 'bt-hit-row' : '' }

// ── 一键展开/收起 ─────────────────────────────────
// 数据变化（换 BOM、改筛选词）后 el-table 按 default-expand-all 重新决定展开，状态跟着复位
const tableRef = ref(null)
const allExpanded = ref(props.expandAll)
watch(() => filtered.value.rows, () => { allExpanded.value = props.expandAll })

function setAllExpanded(expanded) {
  const walk = rows => rows.forEach(r => {
    if (r.children?.length) {
      tableRef.value?.toggleRowExpansion(r, expanded)
      walk(r.children)
    }
  })
  walk(filtered.value.rows)
  allExpanded.value = expanded
}

function toggleAll() {
  nextTick(() => setAllExpanded(!allExpanded.value))
}

// 有下级的行才需要展开/收起按键
const hasNested = computed(() => filtered.value.rows.some(r => r.children?.length))

defineExpose({
  matchCount: computed(() => filtered.value.hits),
  allExpanded, hasNested, toggleAll, setAllExpanded,
})

// ── 方法 ──────────────────────────────────────────
function formatQty(q) {
  if (q == null) return ''
  return Number.isInteger(q) ? String(q) : String(+Number(q).toFixed(4))
}
</script>

<template>
  <el-table
    ref="tableRef"
    class="bom-tree"
    :data="filtered.rows"
    row-key="id"
    :tree-props="{ children: 'children' }"
    :default-expand-all="expandAll"
    :height="height"
    :max-height="maxHeight"
    size="small"
    border
    :empty-text="emptyText"
    :row-class-name="rowClass"
  >
    <!-- 序号列承载树的展开箭头与缩进，层级一目了然 -->
    <el-table-column label="序号" width="120">
      <template #default="{ row }">
        <span class="bt-seq mono">{{ row._seq }}</span>
        <span v-if="row.children?.length" class="bt-sub" title="下级数量">{{ row.children.length }}</span>
      </template>
    </el-table-column>
    <!-- 图纸编码：研发 BOM 里的完整编码（成品/产成品带 -A01 这类完整版本） -->
    <el-table-column label="图纸编码" width="150">
      <template #default="{ row }">
        <span class="bt-drawing mono">{{ row.drawing }}</span>
      </template>
    </el-table-column>
    <!-- ERP 编码：成品/产成品只到 -A；能对应到 ERP 物料时可点开物料卡片，对应不到的显示「未匹配」 -->
    <el-table-column label="ERP编码" width="150">
      <template #default="{ row }">
        <span v-if="row.erp_code" class="bt-erp mono" title="点击查看物料卡片"
              @click.stop="emit('open-code', row.erp_code)">{{ row.erp_code }}</span>
        <span v-else class="bt-none" title="ERP 物料表里没有对应编码">未匹配</span>
      </template>
    </el-table-column>
    <!-- 名称已包含规格，不再单列规格/类别 -->
    <el-table-column prop="name" label="名称" min-width="240" show-overflow-tooltip />
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
.bt-drawing { font-size: 12px; font-weight: 600; color: #2c2420; }
.bt-erp { font-size: 12px; color: #3a3028; cursor: pointer; }
.bt-erp:hover { color: var(--accent); text-decoration: underline; }
.bt-none { font-size: 12px; color: var(--text-muted); }
:deep(.bt-hit-row > td.el-table__cell) { background: #fff6dc !important; }
</style>
