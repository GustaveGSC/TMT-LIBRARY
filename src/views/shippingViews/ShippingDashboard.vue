<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import http from '@/api/http'

// ── 响应式状态 ────────────────────────────────────
const stats   = ref(null)    // 统计摘要
const loading = ref(true)

// ECharts
const chartEl   = ref(null)
let   chartInst = null
let   resizeObs = null

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  // 加载统计数据
  try {
    const res = await http.get('/api/shipping/stats')
    if (res.success) stats.value = res.data
  } catch {}
  loading.value = false

  // 初始化图表（占位空图）
  initChart()
})

onUnmounted(() => {
  resizeObs?.disconnect()
  if (chartInst) { chartInst.dispose(); chartInst = null }
})

// ── 方法 ──────────────────────────────────────────

/** 初始化 ResizeObserver，感知容器尺寸后再创建实例 */
function initChart() {
  if (!chartEl.value) return
  resizeObs = new ResizeObserver(() => {
    if (!chartEl.value?.offsetWidth || !chartEl.value?.offsetHeight) return
    if (!chartInst) {
      chartInst = echarts.init(chartEl.value, null, { renderer: 'canvas' })
      renderChart()
    } else {
      chartInst.resize()
    }
  })
  resizeObs.observe(chartEl.value)
}

/** 渲染占位图：空白 + 提示文字 */
function renderChart() {
  if (!chartInst) return
  const FONT = "'Microsoft YaHei UI','Microsoft YaHei','PingFang SC',sans-serif"
  chartInst.setOption({
    backgroundColor: 'transparent',
    graphic: [{
      type: 'group',
      left: 'center',
      top:  'middle',
      children: [
        {
          type: 'text',
          left: 'center',
          top: 0,
          style: {
            text:       '📊',
            textAlign:  'center',
            fontSize:   48,
          },
        },
        {
          type: 'text',
          left: 'center',
          top:  64,
          style: {
            text:       '数据维度待配置',
            textAlign:  'center',
            fontSize:   15,
            fill:       '#8a7a6a',
            fontFamily: FONT,
          },
        },
        {
          type: 'text',
          left: 'center',
          top:  90,
          style: {
            text:       '导入数据后，图表将在此处展示',
            textAlign:  'center',
            fontSize:   12,
            fill:       '#b0a090',
            fontFamily: FONT,
          },
        },
      ],
    }],
  }, { notMerge: true })
}
</script>

<template>
  <div class="dashboard-view">

    <!-- ── 统计卡片 ──────────────────────────────── -->
    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-label">发货记录</div>
        <div class="stat-value">{{ loading ? '…' : (stats?.shipping_total ?? '—') }}</div>
        <div v-if="stats?.last_shipping_import" class="stat-hint">最近导入 {{ stats.last_shipping_import }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">销退记录</div>
        <div class="stat-value">{{ loading ? '…' : (stats?.return_total ?? '—') }}</div>
        <div v-if="stats?.last_return_import" class="stat-hint">最近导入 {{ stats.last_return_import }}</div>
      </div>
      <div class="stat-card accent-card">
        <div class="stat-label">净发货</div>
        <div class="stat-value accent-val">
          {{ loading ? '…' : (stats ? stats.shipping_total - stats.return_total : '—') }}
        </div>
        <div class="stat-hint">发货 - 销退</div>
      </div>
    </div>

    <!-- ── 图表区（占位）──────────────────────────── -->
    <div class="chart-wrap">
      <div ref="chartEl" class="chart-canvas"></div>
    </div>

  </div>
</template>

<style scoped>
.dashboard-view {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 28px 32px 0;
  gap: 20px;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'PingFang SC', sans-serif;
}

/* 统计卡片行 */
.stat-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  flex-shrink: 0;
}
.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px 24px;
  transition: box-shadow 0.2s;
}
.stat-card:hover { box-shadow: 0 4px 16px var(--shadow); }
.accent-card { border-color: rgba(196,136,58,0.3); }

.stat-label { font-size: 12px; color: var(--text-muted); margin-bottom: 10px; }
.stat-value { font-size: 34px; font-weight: 700; color: var(--text-primary); letter-spacing: -0.02em; }
.accent-val { color: var(--accent); }
.stat-hint  { font-size: 11px; color: var(--text-muted); margin-top: 6px; }

/* 图表区 */
.chart-wrap {
  flex: 1;
  min-height: 0;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  margin-bottom: 24px;
}
.chart-canvas {
  width: 100%;
  height: 100%;
}
</style>
