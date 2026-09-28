<script setup>
// ── 导入 ──────────────────────────────────────────
// 物料价格趋势：按价格日期画出该物料每一条价格记录；有研发 BOM 的部件画「按 BOM 计算」的成本（按采购订单逐单重算，
// 来自 /calc-price，不存库），并在右侧纵轴画「已计价比例」——成本突然跳高时能看出是不是覆盖率同时跳了。
import { ref, watch, nextTick, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  modelValue:  { type: Boolean, default: false },
  title:       { type: String,  default: '' },
  // 价格记录：[{ price_date, unit_price, order_no, source, supplier_name }]
  prices:      { type: Array,   default: () => [] },
  // 按 BOM 计算的成本历史（按订单）：[{ date, order_no, unit_price, priced, total, related }]
  calcHistory: { type: Array,   default: () => [] },
  titlePrefix: { type: String,  default: '价格趋势' },
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
      lineStyle: { color: '#4a8fc0', width: 2 }, itemStyle: { color: '#4a8fc0' },
    })
    // 已计价比例（右轴 0~100%）
    const cover = calc.filter(p => p.raw.total).map(p => ({
      value: [p.value[0], Math.round(p.raw.priced / p.raw.total * 100)], raw: p.raw, isCover: true,
    }))
    if (cover.length) {
      series.push({
        name: '已计价比例', type: 'line', step: 'end', yAxisIndex: 1, data: cover, symbolSize: 5,
        lineStyle: { color: '#8a7a6a', width: 1.5, type: 'dashed' }, itemStyle: { color: '#8a7a6a' },
      })
    }
  }
  const hasCover = series.some(s => s.yAxisIndex === 1)
  chart.setOption({
    grid: { left: 70, right: hasCover ? 60 : 30, top: 40, bottom: 40 },
    legend: { top: 4, data: series.map(s => s.name) },
    tooltip: {
      trigger: 'item',
      formatter: p => {
        const raw = p.data.raw || {}
        if (p.data.isCover) {
          return `已计价比例<br/>${p.value[0]}　<b>${p.value[1]}%</b>（${raw.priced}/${raw.total} 种原材料）`
        }
        const lines = [`${p.seriesName}<br/>${p.value[0]}　<b>${money(p.value[1])}</b>`]
        if (raw.related === true) lines.push('本产品订单')
        if (raw.related === false) lines.push('共用物料变价')
        if (raw.order_no) lines.push(`订单号：${raw.order_no}`)
        if (raw.supplier_name) lines.push(`供应商：${raw.supplier_name}`)
        if (raw.total) lines.push(`已计价 ${raw.priced}/${raw.total} 种原材料`)
        return lines.join('<br/>')
      },
    },
    xAxis: { type: 'time', axisLabel: { formatter: '{yyyy}-{MM}-{dd}' } },
    yAxis: [
      { type: 'value', scale: true, axisLabel: { formatter: v => '¥' + v } },
      ...(hasCover ? [{ type: 'value', min: 0, max: 100, splitLine: { show: false },
                        axisLabel: { formatter: v => v + '%' } }] : []),
    ],
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
    :title="`${titlePrefix} · ${title}`"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="onClosed"
  >
    <div v-if="!pricePoints().length && !calcPoints().length" class="pt-empty">
      还没有带日期的价格，无法画出趋势
    </div>
    <div v-else ref="chartEl" class="pt-chart"></div>
    <div class="pt-tip">价格记录按价格日期排列（没有日期的记录不在图上）；「按 BOM 计算」按采购订单逐单重算，虚线是已计价比例（右轴）。</div>
  </el-dialog>
</template>

<style scoped>
.pt-chart { width: 100%; height: 380px; }
.pt-empty { padding: 60px 0; text-align: center; color: #8a7a6a; font-size: 13px; }
.pt-tip { margin-top: 6px; font-size: 12px; color: #8a7a6a; }
</style>
