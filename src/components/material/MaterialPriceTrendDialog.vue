<script setup>
// ── 导入 ──────────────────────────────────────────
// 物料价格趋势：按价格日期画出该物料每一条价格记录；有研发 BOM 的部件另画「按 BOM 计算」的价格
// （计算价历史来自 /calc-price，本身就是在各价格日期上重算的结果，不存库）。
import { ref, watch, nextTick, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  modelValue:  { type: Boolean, default: false },
  title:       { type: String,  default: '' },
  // 价格记录：[{ price_date, unit_price, order_no, source, supplier_name }]
  prices:      { type: Array,   default: () => [] },
  // 按 BOM 计算的价格历史：[{ date, unit_price, missing }]
  calcHistory: { type: Array,   default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

// ── 响应式状态 ────────────────────────────────────
const chartEl = ref(null)
let chart = null

// ── 方法 ──────────────────────────────────────────
function money(v) {
  return v == null ? '—' : '¥' + String(+Number(v).toFixed(4))
}

// 价格记录按日期升序；没有日期的记录没法放到时间轴上，跳过
function pricePoints() {
  return props.prices
    .filter(p => p.price_date && p.unit_price != null)
    .map(p => ({ value: [p.price_date, Number(p.unit_price)], raw: p }))
    .sort((a, b) => a.value[0].localeCompare(b.value[0]))
}

function calcPoints() {
  return [...props.calcHistory]
    .filter(h => h.date && h.unit_price != null)
    .map(h => ({ value: [h.date, Number(h.unit_price)], raw: h }))
    .sort((a, b) => a.value[0].localeCompare(b.value[0]))
}

function render() {
  if (!chartEl.value) return
  chart = chart || echarts.init(chartEl.value)
  const series = []
  const pts = pricePoints()
  if (pts.length) {
    series.push({
      name: '价格记录', type: 'line', data: pts, symbolSize: 8,
      lineStyle: { color: '#c4883a', width: 2 }, itemStyle: { color: '#c4883a' },
    })
  }
  const calc = calcPoints()
  if (calc.length) {
    series.push({
      name: '按 BOM 计算', type: 'line', step: 'end', data: calc, symbolSize: 7,
      lineStyle: { color: '#4a8fc0', width: 2, type: 'dashed' }, itemStyle: { color: '#4a8fc0' },
    })
  }
  chart.setOption({
    grid: { left: 70, right: 30, top: 40, bottom: 40 },
    legend: { top: 4, data: series.map(s => s.name) },
    tooltip: {
      trigger: 'item',
      formatter: p => {
        const raw = p.data.raw || {}
        const lines = [`${p.seriesName}<br/>${p.value[0]}　<b>${money(p.value[1])}</b>`]
        if (raw.order_no) lines.push(`订单号：${raw.order_no}`)
        if (raw.supplier_name) lines.push(`供应商：${raw.supplier_name}`)
        if (raw.missing) lines.push(`其中 ${raw.missing} 项原材料无价格`)
        return lines.join('<br/>')
      },
    },
    xAxis: { type: 'time', axisLabel: { formatter: '{yyyy}-{MM}-{dd}' } },
    yAxis: { type: 'value', scale: true, axisLabel: { formatter: v => '¥' + v } },
    series,
  }, true)
}

function onResize() { chart?.resize() }

watch(() => props.modelValue, async v => {
  if (!v) return
  await nextTick()
  render()
  window.addEventListener('resize', onResize)
})

function onClosed() {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
}

onBeforeUnmount(onClosed)
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    width="min(900px, 92vw)"
    align-center
    append-to-body
    class="price-trend-dialog"
    :title="`价格趋势 · ${title}`"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="onClosed"
  >
    <div v-if="!pricePoints().length && !calcPoints().length" class="pt-empty">
      还没有带日期的价格，无法画出趋势
    </div>
    <div v-else ref="chartEl" class="pt-chart"></div>
    <div class="pt-tip">价格记录按价格日期排列（没有日期的记录不在图上）；「按 BOM 计算」是在下级各价格日期上重算的结果。</div>
  </el-dialog>
</template>

<style scoped>
.pt-chart { width: 100%; height: 380px; }
.pt-empty { padding: 60px 0; text-align: center; color: #8a7a6a; font-size: 13px; }
.pt-tip { margin-top: 6px; font-size: 12px; color: #8a7a6a; }
</style>
