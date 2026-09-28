<script setup>
// ── 导入 ──────────────────────────────────────────
// 计价依据选择：不手动选日期，而是选「最新价格」或某一次采购导入（订单号 + 价格日期）。
// v-model 仍是计价日期字符串（YYYY-MM-DD；'' = 最新价格），后端按这个日期取当天或之前最近的价格现算。
import { ref, watch, onMounted } from 'vue'
import http from '@/api/http'

const props = defineProps({
  modelValue: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'change'])

// ── 响应式状态 ────────────────────────────────────
const batches  = ref([])    // [{ id, order_no, price_date, price_count }]，日期新→旧
const selected = ref('')    // '' = 最新价格；否则是批次 id（同一天可能有多个订单，所以不用日期当 value）

// ── 方法 ──────────────────────────────────────────
async function load() {
  try {
    const res = await http.get('/api/material/price-batches')
    if (res.success) batches.value = res.data || []
  } catch { /* 拿不到批次就只能按最新价格计算 */ }
}

function onChange(id) {
  const batch = batches.value.find(b => b.id === id)
  const date = batch ? batch.price_date : ''
  emit('update:modelValue', date)
  emit('change', date)
}

// 外部改了计价日期（如重新打开弹窗时清空、返回时恢复）：下拉框跟着对齐
function syncFromValue() {
  const date = props.modelValue || ''
  if (!date) { selected.value = ''; return }
  const current = batches.value.find(b => b.id === selected.value)
  if (current?.price_date !== date) {
    selected.value = batches.value.find(b => b.price_date === date)?.id ?? ''
  }
}
watch(() => props.modelValue, syncFromValue)

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => { await load(); syncFromValue() })
</script>

<template>
  <el-select
    v-model="selected" size="small" class="price-batch-select"
    placeholder="计价：最新价格" @change="onChange"
  >
    <el-option label="计价：最新价格" value="" />
    <el-option
      v-for="b in batches" :key="b.id" :value="b.id"
      :label="`计价：${b.order_no || '（无订单号）'} · ${b.price_date}`"
    >
      <span class="pb-order">{{ b.order_no || '（无订单号）' }}</span>
      <span class="pb-date">{{ b.price_date }}</span>
    </el-option>
  </el-select>
</template>

<style scoped>
.price-batch-select { width: 310px; }
.pb-order { font-family: 'SF Mono', Consolas, 'Microsoft YaHei UI', monospace; font-size: 12px; margin-right: 10px; }
.pb-date { float: right; font-size: 12px; color: #8a7a6a; }
</style>
