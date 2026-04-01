<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import http from '@/api/http.js'

// ── 响应式状态 ────────────────────────────────────

// 筛选
const dateRange    = ref([])
const channels     = ref([])          // 渠道多选
const provinces    = ref([])          // 省份多选
const reasonCatId  = ref(null)        // 原因一级分类筛选（id）

// 图表维度 tab
const groupBy      = ref('reason')    // 'reason' | 'channel' | 'province' | 'month'
const chartType    = ref('bar')       // 'bar' | 'pie'（月度维度用折线）

// 图表数据
const chartData    = ref(null)
const loading      = ref(false)

// 筛选选项（来自后端）
const optChannels  = ref([])
const optProvinces = ref([])
const optCats      = ref([])

// 摘要统计
const stats        = ref(null)

// ECharts 实例
let chartInst      = null
const chartEl      = ref(null)

// 维度配置
const GROUP_TABS = [
  { key: 'reason',   label: '原因分布' },
  { key: 'channel',  label: '渠道分布' },
  { key: 'province', label: '地域分布' },
  { key: 'month',    label: '时间趋势' },
]

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  await loadOptions()
  await loadStats()
  await loadChart()
  initChart()
})

onBeforeUnmount(() => {
  chartInst?.dispose()
})

// ── Watch ─────────────────────────────────────────
watch([dateRange, channels, provinces, reasonCatId, groupBy], async () => {
  await loadChart()
  renderChart()
})

watch(chartType, () => renderChart())

// ── 方法 ──────────────────────────────────────────

async function loadOptions() {
  const res = await http.get('/api/aftersale/chart-options')
  if (res.success) {
    optChannels.value  = res.data.channels
    optProvinces.value = res.data.provinces
    optCats.value      = res.data.categories
  }
}

async function loadStats() {
  const res = await http.get('/api/aftersale/stats')
  if (res.success) stats.value = res.data
}

async function loadChart() {
  loading.value = true
  try {
    const body = {
      group_by:   groupBy.value,
      date_start: dateRange.value?.[0] || undefined,
      date_end:   dateRange.value?.[1] || undefined,
      channel_names: channels.value.length ? channels.value : undefined,
      provinces:    provinces.value.length ? provinces.value : undefined,
      category_id:  reasonCatId.value || undefined,
    }
    const res = await http.post('/api/aftersale/chart-data', body)
    if (res.success) chartData.value = res.data
  } finally {
    loading.value = false
  }
}

function initChart() {
  if (!chartEl.value) return
  chartInst = echarts.init(chartEl.value, null, { renderer: 'canvas' })
  renderChart()

  const ro = new ResizeObserver(() => chartInst?.resize())
  ro.observe(chartEl.value)
}

function renderChart() {
  if (!chartInst || !chartData.value) return
  const items = chartData.value.items || []

  let option
  if (groupBy.value === 'month') {
    option = buildLineOption(items)
  } else if (chartType.value === 'pie') {
    option = buildPieOption(items)
  } else {
    option = buildBarOption(items)
  }

  chartInst.setOption(option, true)
}

function buildBarOption(items) {
  const names  = items.map(i => i.name)
  const values = items.map(i => i.value)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 60, right: 20, top: 20, bottom: 60 },
    xAxis: {
      type: 'category', data: names,
      axisLabel: { interval: 0, rotate: names.length > 8 ? 30 : 0, fontSize: 11 },
    },
    yAxis: { type: 'value', name: '件数' },
    series: [{
      type: 'bar',
      data: values,
      itemStyle: { color: '#c4883a', borderRadius: [3, 3, 0, 0] },
      emphasis: { itemStyle: { color: '#e09050' } },
      label: { show: true, position: 'top', fontSize: 11, color: '#6b5e4e' },
    }],
  }
}

function buildPieOption(items) {
  const COLORS = ['#c4883a', '#4a8fc0', '#6ab47a', '#9c6fba', '#e07070', '#70aacc', '#e0a040', '#7abcaa']
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical', right: 10, top: 'center', type: 'scroll', textStyle: { fontSize: 11 } },
    series: [{
      type: 'pie',
      radius: ['35%', '65%'],
      center: ['40%', '50%'],
      data: items.map((i, idx) => ({
        name: i.name,
        value: i.value,
        itemStyle: { color: COLORS[idx % COLORS.length] },
      })),
      label: { fontSize: 11 },
      emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.2)' } },
    }],
  }
}

function buildLineOption(items) {
  // 月度趋势：X 轴为月份，折线图
  const months = items.map(i => i.name).sort()
  const valMap = Object.fromEntries(items.map(i => [i.name, i.value]))
  const values = months.map(m => valMap[m] || 0)
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 20, bottom: 60 },
    xAxis: {
      type: 'category', data: months,
      axisLabel: { fontSize: 11 },
    },
    yAxis: { type: 'value', name: '件数' },
    series: [{
      type: 'line',
      data: values,
      smooth: true,
      symbol: 'circle', symbolSize: 6,
      lineStyle: { color: '#c4883a', width: 2 },
      itemStyle: { color: '#c4883a' },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: 'rgba(196,136,58,0.3)' },
          { offset: 1, color: 'rgba(196,136,58,0.02)' },
        ] } },
      label: { show: values.length <= 18, position: 'top', fontSize: 11, color: '#6b5e4e' },
    }],
  }
}

function resetFilters() {
  dateRange.value = []
  channels.value  = []
  provinces.value = []
  reasonCatId.value = null
}
</script>

<template>
  <div class="dashboard-wrap">
    <!-- ── 左侧筛选面板 ────────────────────────── -->
    <aside class="filter-panel">
      <div class="filter-title">筛选</div>

      <div class="filter-section">
        <div class="filter-label">日期范围</div>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          size="small"
          range-separator="~"
          start-placeholder="开始"
          end-placeholder="结束"
          value-format="YYYY-MM-DD"
          style="width:100%"
        />
      </div>

      <div class="filter-section">
        <div class="filter-label">渠道</div>
        <el-select
          v-model="channels"
          multiple
          filterable
          clearable
          size="small"
          placeholder="全部渠道"
          style="width:100%"
        >
          <el-option v-for="c in optChannels" :key="c" :value="c" :label="c" />
        </el-select>
      </div>

      <div class="filter-section">
        <div class="filter-label">省份</div>
        <el-select
          v-model="provinces"
          multiple
          filterable
          clearable
          size="small"
          placeholder="全部省份"
          style="width:100%"
        >
          <el-option v-for="p in optProvinces" :key="p" :value="p" :label="p" />
        </el-select>
      </div>

      <div class="filter-section">
        <div class="filter-label">原因分类</div>
        <el-select
          v-model="reasonCatId"
          clearable
          size="small"
          placeholder="全部分类"
          style="width:100%"
        >
          <el-option
            v-for="c in optCats"
            :key="c.id"
            :value="c.id"
            :label="c.name"
          />
        </el-select>
      </div>

      <el-button size="small" style="width:100%;margin-top:8px" @click="resetFilters">重置筛选</el-button>

      <!-- 摘要统计 -->
      <div v-if="stats" class="stats-card">
        <div class="stat-item">
          <span class="stat-val">{{ stats.pending }}</span>
          <span class="stat-lbl">待处理</span>
        </div>
        <div class="stat-item">
          <span class="stat-val accent">{{ stats.confirmed }}</span>
          <span class="stat-lbl">已处理</span>
        </div>
        <div class="stat-item">
          <span class="stat-val muted">{{ stats.ignored }}</span>
          <span class="stat-lbl">已忽略</span>
        </div>
      </div>

      <!-- Top 原因 -->
      <div v-if="stats?.top_reasons?.length" class="top-reasons">
        <div class="filter-label" style="margin-top:12px">常见原因 Top5</div>
        <div
          v-for="(r, i) in stats.top_reasons"
          :key="r.name"
          class="top-reason-item"
        >
          <span class="top-rank" :class="`rank-${i+1}`">{{ i + 1 }}</span>
          <span class="top-name">{{ r.name }}</span>
          <span class="top-count">{{ r.use_count }}</span>
        </div>
      </div>
    </aside>

    <!-- ── 右侧图表区 ──────────────────────────── -->
    <div class="chart-area">
      <!-- 维度 Tab + 图表类型 -->
      <div class="chart-toolbar">
        <div class="group-tabs">
          <button
            v-for="tab in GROUP_TABS"
            :key="tab.key"
            class="group-tab"
            :class="{ active: groupBy === tab.key }"
            @click="groupBy = tab.key"
          >{{ tab.label }}</button>
        </div>

        <!-- 图表类型（月度时隐藏） -->
        <div v-if="groupBy !== 'month'" class="chart-type-btns">
          <button
            class="type-btn"
            :class="{ active: chartType === 'bar' }"
            title="柱图"
            @click="chartType = 'bar'"
          >柱</button>
          <button
            class="type-btn"
            :class="{ active: chartType === 'pie' }"
            title="饼图"
            @click="chartType = 'pie'"
          >饼</button>
        </div>
      </div>

      <!-- 图表容器 -->
      <div v-loading="loading" class="chart-container">
        <div v-if="chartData?.items?.length === 0 && !loading" class="chart-empty">
          暂无数据
        </div>
        <div ref="chartEl" class="echart-el"></div>
      </div>

      <!-- 数据明细（前10条） -->
      <div v-if="chartData?.items?.length" class="data-table">
        <div class="data-table-header">
          <span class="col-name">{{ groupBy === 'reason' ? '原因' : groupBy === 'channel' ? '渠道' : groupBy === 'province' ? '省份' : '月份' }}</span>
          <span class="col-val">件数</span>
          <span class="col-pct">占比</span>
        </div>
        <div
          v-for="item in chartData.items.slice(0, 10)"
          :key="item.name"
          class="data-row"
        >
          <span class="col-name">{{ item.name }}</span>
          <span class="col-val">{{ item.value }}</span>
          <span class="col-pct">{{ chartData.summary.total ? Math.round(item.value / chartData.summary.total * 100) : 0 }}%</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard-wrap {
  flex: 1; display: flex; overflow: hidden;
}

/* 左侧筛选 */
.filter-panel {
  width: 210px; flex-shrink: 0;
  border-right: 1px solid var(--border);
  padding: 14px 12px;
  overflow-y: auto;
  background: var(--bg-card);
}
.filter-panel::-webkit-scrollbar { width: 4px; }
.filter-panel::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.filter-title {
  font-size: 12px; font-weight: 600; color: var(--text-secondary);
  letter-spacing: 0.05em; margin-bottom: 12px;
}
.filter-section { margin-bottom: 12px; }
.filter-label {
  font-size: 11px; color: var(--text-muted); margin-bottom: 5px;
}

.stats-card {
  margin-top: 16px;
  background: #faf7f2; border: 1px solid var(--border);
  border-radius: 8px; padding: 10px;
  display: flex; justify-content: space-around;
}
.stat-item {
  display: flex; flex-direction: column;
  align-items: center; gap: 2px;
}
.stat-val {
  font-size: 18px; font-weight: 700; color: var(--text-primary);
}
.stat-val.accent { color: var(--accent); }
.stat-val.muted  { color: var(--text-muted); }
.stat-lbl { font-size: 10px; color: var(--text-muted); }

.top-reasons { margin-top: 4px; }
.top-reason-item {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 0; border-bottom: 1px solid #f0e8d8;
}
.top-rank {
  width: 18px; height: 18px; border-radius: 50%;
  background: var(--border); color: var(--text-muted);
  font-size: 10px; font-weight: 700; text-align: center; line-height: 18px;
  flex-shrink: 0;
}
.rank-1 { background: #c4883a; color: #fff; }
.rank-2 { background: #aaa; color: #fff; }
.rank-3 { background: #b87333; color: #fff; }
.top-name { flex: 1; font-size: 12px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.top-count { font-size: 11px; color: var(--text-muted); flex-shrink: 0; }

/* 右侧图表区 */
.chart-area {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
}

.chart-toolbar {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
  flex-shrink: 0;
}
.group-tabs {
  display: flex; gap: 4px;
}
.group-tab {
  padding: 5px 14px; border-radius: 7px;
  border: 1px solid var(--border); background: transparent;
  color: var(--text-muted); font-size: 12px; cursor: pointer;
  transition: all 0.15s;
}
.group-tab:hover { background: var(--bg); color: var(--text-primary); }
.group-tab.active {
  background: #fff7ed; border-color: var(--accent);
  color: var(--accent); font-weight: 600;
}

.chart-type-btns {
  display: flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden;
}
.type-btn {
  padding: 4px 12px; border: none; background: transparent;
  color: var(--text-muted); font-size: 12px; cursor: pointer;
  transition: all 0.15s;
}
.type-btn:not(:last-child) { border-right: 1px solid var(--border); }
.type-btn.active { background: #fff7ed; color: var(--accent); font-weight: 600; }
.type-btn:hover:not(.active) { background: var(--bg); }

.chart-container {
  flex: 1; position: relative; min-height: 0;
}
.echart-el {
  width: 100%; height: 100%;
}
.chart-empty {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; color: var(--text-muted);
}

/* 数据明细 */
.data-table {
  flex-shrink: 0;
  border-top: 1px solid var(--border);
  max-height: 160px; overflow-y: auto;
}
.data-table::-webkit-scrollbar { width: 4px; }
.data-table::-webkit-scrollbar-thumb { background: var(--border); }

.data-table-header, .data-row {
  display: grid;
  grid-template-columns: 1fr 60px 50px;
  padding: 5px 16px; font-size: 12px;
}
.data-table-header {
  position: sticky; top: 0;
  background: #f5f0e8; font-weight: 600;
  color: var(--text-secondary); border-bottom: 1px solid var(--border);
}
.data-row { color: var(--text-primary); border-bottom: 1px solid #f5f0e8; }
.data-row:hover { background: #faf7f2; }
.col-val, .col-pct { text-align: right; }
</style>
