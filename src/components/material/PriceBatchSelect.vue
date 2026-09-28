<script setup>
// ── 导入 ──────────────────────────────────────────
// 计价依据选择：不手动选日期，而是选「最新价格」或某一次采购导入（订单号 + 价格日期）。
// 批次按 年 → 月 → 订单 组织成树，只有「最新价格」和订单可选（年/月只用来展开）。
// v-model 是采购导入批次 id（null = 最新价格）：后端按「该订单导入时」的截止点计价，
// 同一天导入多个订单也能区分（之前只传日期，同日订单结果一样，Codex 审计 #1，2026-09-28）。
import { ref, computed, watch, onMounted } from 'vue'
import http from '@/api/http'

const props = defineProps({
  modelValue: { type: Number, default: null },
})
const emit = defineEmits(['update:modelValue', 'change'])

const LATEST = 'latest'

// ── 响应式状态 ────────────────────────────────────
const batches  = ref([])      // [{ id, order_no, price_date, price_count }]，日期新→旧
const selected = ref(LATEST)  // LATEST 或 'b-<批次 id>'（同一天可能有多个订单，所以不用日期当 value）

// ── 计算属性 ──────────────────────────────────────
// 年 → 月 → 订单；年、月按新→旧排列（批次本身已是新→旧）
const treeData = computed(() => {
  const years = []
  for (const b of batches.value) {
    const [y, m] = b.price_date.split('-')
    let year = years.find(n => n.key === y)
    if (!year) { year = { value: `y-${y}`, key: y, label: `${y}年`, children: [] }; years.push(year) }
    let month = year.children.find(n => n.key === m)
    if (!month) { month = { value: `m-${y}-${m}`, key: m, label: `${Number(m)}月`, children: [] }; year.children.push(month) }
    month.children.push({
      value: `b-${b.id}`, label: `${b.order_no || '（无订单号）'} · ${b.price_date}`,
      order: b.order_no || '（无订单号）', date: b.price_date,
    })
  }
  return [{ value: LATEST, label: '最新价格', isLatest: true }, ...years]
})

// 默认展开最近一年、最近一月，方便直接选最新的订单
const defaultExpanded = computed(() => {
  const first = treeData.value[1]
  return first ? [first.value, first.children[0]?.value].filter(Boolean) : []
})

// ── 方法 ──────────────────────────────────────────
async function load() {
  try {
    const res = await http.get('/api/material/price-batches')
    if (res.success) batches.value = res.data || []
  } catch { /* 拿不到批次就只能按最新价格计算 */ }
}

function onChange(value) {
  const batch = batches.value.find(b => `b-${b.id}` === value)
  const id = batch ? batch.id : null
  emit('update:modelValue', id)
  emit('change', id)
}

// 外部改了批次（如重新打开弹窗时清空、返回时恢复）：选择框跟着对齐
function syncFromValue() {
  const id = props.modelValue
  selected.value = id && batches.value.some(b => b.id === id) ? `b-${id}` : LATEST
}
watch(() => props.modelValue, syncFromValue)

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => { await load(); syncFromValue() })
</script>

<template>
  <div class="price-batch">
    <span class="pb-label">计价</span>
    <!-- 只有叶子（最新价格 / 订单）可选：年、月点击只展开 -->
    <el-tree-select
      v-model="selected"
      :data="treeData"
      :default-expanded-keys="defaultExpanded"
      node-key="value"
      :render-after-expand="false"
      size="small"
      class="pb-select"
      popper-class="price-batch-popper"
      @change="onChange"
    >
      <template #default="{ data }">
        <span v-if="data.isLatest" class="pb-latest">最新价格</span>
        <span v-else-if="data.order" class="pb-node">
          <span class="pb-order">{{ data.order }}</span>
          <span class="pb-date">{{ data.date.slice(5) }}</span>
        </span>
        <span v-else class="pb-group">{{ data.label }}</span>
      </template>
    </el-tree-select>
  </div>
</template>

<style scoped>
.price-batch { display: inline-flex; align-items: center; gap: 6px; }
.pb-label { font-size: 12px; color: #6b5e4e; flex-shrink: 0; }
.pb-select { width: 300px; }
.pb-latest { font-weight: 600; color: #3a3028; }
.pb-group { color: #6b5e4e; }
.pb-node { display: inline-flex; align-items: center; gap: 10px; }
.pb-order { font-family: 'SF Mono', Consolas, 'Microsoft YaHei UI', monospace; font-size: 12px; color: #2c2420; }
.pb-date { font-size: 12px; color: #8a7a6a; }
</style>
