<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import http from '@/api/http'
import WindowControls from '@/components/common/WindowControls.vue'

// ── 路由 ──────────────────────────────────────────
const router = useRouter()

// ── DAU 图表 ──────────────────────────────────────
const dauChartEl  = ref(null)
const dauLoading  = ref(false)
const dauDays     = ref(30)       // 30 / 60 / 90
const dauData     = ref([])       // [{date, count}]
let   dauChartInst = null

// ── 账号统计表 ────────────────────────────────────
const statsLoading = ref(false)
const userStats    = ref([])      // [{username, display_name, total, success_count, failed_count, last_login_at, identity_type}]

// ── 计算属性 ──────────────────────────────────────
const totalUsers   = computed(() => new Set(userStats.value.map(r => r.username)).size)
const totalLogins  = computed(() => userStats.value.reduce((s, r) => s + r.total, 0))
const dauPeak      = computed(() => dauData.value.reduce((m, r) => Math.max(m, r.count), 0))

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  await Promise.all([loadDau(), loadUserStats()])
})

onBeforeUnmount(() => {
  dauChartInst?.dispose()
  dauChartInst = null
})

// ── 方法 ──────────────────────────────────────────
async function loadDau() {
  dauLoading.value = true
  try {
    const res = await http.get('/api/account/login-stats/dau', { params: { days: dauDays.value } })
    if (res.success) {
      dauData.value    = res.data || []
      dauLoading.value = false   // 先关 loading，让图表 DOM 渲染出来
      await nextTick()
      initDauChart()
    } else {
      ElMessage.error(res.message || '加载日活数据失败')
      dauLoading.value = false
    }
  } catch {
    ElMessage.error('网络错误')
    dauLoading.value = false
  }
}

async function changeDays(d) {
  dauDays.value = d
  await loadDau()
}

function initDauChart() {
  if (!dauChartEl.value) return
  if (!dauChartInst) {
    dauChartInst = echarts.init(dauChartEl.value, null, { renderer: 'canvas' })
  }

  // 填充缺失日期（无登录的天显示 0）
  const allDates = []
  const countMap = Object.fromEntries(dauData.value.map(r => [r.date, r.count]))
  const end   = new Date()
  const start = new Date()
  start.setDate(end.getDate() - dauDays.value + 1)
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    const key = d.toISOString().slice(0, 10)
    allDates.push({ date: key, count: countMap[key] ?? 0 })
  }

  const dates  = allDates.map(r => r.date.slice(5))   // MM-DD
  const counts = allDates.map(r => r.count)

  dauChartInst.setOption({
    grid:    { top: 16, right: 16, bottom: 36, left: 36, containLabel: false },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter(params) {
        const p = params[0]
        return `<div style="font-size:12px;color:#3a3028">${allDates[p.dataIndex]?.date}</div>
                <div style="font-size:12px;margin-top:2px">日活用户：<b>${p.value}</b></div>`
      },
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        fontSize: 10, color: '#8a7a6a',
        interval: dauDays.value <= 30 ? 'auto' : Math.floor(dauDays.value / 15),
      },
      axisLine: { lineStyle: { color: '#e0d4c0' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value', minInterval: 1,
      axisLabel: { fontSize: 10, color: '#8a7a6a' },
      splitLine: { lineStyle: { color: '#f0ebe0' } },
    },
    series: [{
      type: 'bar',
      data: counts,
      barMaxWidth: 20,
      itemStyle: { color: '#c4883a', borderRadius: [3, 3, 0, 0] },
    }],
  }, true)
}

async function loadUserStats() {
  statsLoading.value = true
  try {
    const res = await http.get('/api/account/login-stats/users')
    if (res.success) {
      userStats.value = res.data || []
    } else {
      ElMessage.error(res.message || '加载账号统计失败')
    }
  } catch {
    ElMessage.error('网络错误')
  } finally {
    statsLoading.value = false
  }
}

// 格式化时间
function fmtTime(iso) {
  if (!iso) return '—'
  const d   = new Date(iso)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
</script>

<template>
  <div class="log-page">
    <WindowControls :confirm-close="true" confirm-text="确认退出两平米软件库？" />

    <!-- 页头 -->
    <div class="page-header">
      <button class="btn-back" @click="router.back()">← 返回</button>
      <h1 class="page-title">用户分析</h1>
    </div>

    <!-- 概览指标条 -->
    <div class="metrics-bar">
      <div class="metric-card">
        <div class="metric-val">{{ totalUsers }}</div>
        <div class="metric-lbl">累计账号</div>
      </div>
      <div class="metric-card">
        <div class="metric-val">{{ totalLogins }}</div>
        <div class="metric-lbl">总登录次数</div>
      </div>
      <div class="metric-card">
        <div class="metric-val">{{ dauPeak }}</div>
        <div class="metric-lbl">日活峰值</div>
      </div>
      <div class="metric-card">
        <div class="metric-val">{{ dauData.length > 0 ? dauData[dauData.length - 1]?.count ?? 0 : 0 }}</div>
        <div class="metric-lbl">今日活跃</div>
      </div>
    </div>

    <!-- DAU 图表卡片 -->
    <div class="card dau-card">
      <div class="card-hd">
        <span class="card-title">日活用户（DAU）</span>
        <div class="day-tabs">
          <button
            v-for="d in [30, 60, 90]" :key="d"
            :class="['day-tab', { active: dauDays === d }]"
            @click="changeDays(d)"
          >{{ d }}天</button>
        </div>
      </div>
      <div class="dau-chart-wrap">
        <!-- 图表 div 始终保留，避免切换时 ECharts 容器被卸载 -->
        <div ref="dauChartEl" class="dau-chart"></div>
        <div v-if="dauLoading" class="chart-loading-overlay">
          <div class="chart-spinner"></div>
        </div>
      </div>
    </div>

    <!-- 账号统计表卡片 -->
    <div class="card stats-card">
      <div class="card-hd">
        <span class="card-title">账号登录统计</span>
        <span class="card-sub">{{ userStats.length }} 个账号</span>
      </div>
      <el-table
        :data="userStats"
        v-loading="statsLoading"
        height="100%"
        row-key="username"
      >
        <el-table-column label="账号" min-width="160">
          <template #default="{ row }">
            <div class="user-cell">
              <el-tag
                :type="row.identity_type === 'guest' ? 'info' : 'warning'"
                size="small"
                style="margin-right:6px;flex-shrink:0"
              >{{ row.identity_type === 'guest' ? '游客' : '用户' }}</el-tag>
              <span class="user-name">{{ row.username }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="显示名称" min-width="100">
          <template #default="{ row }">{{ row.display_name || '—' }}</template>
        </el-table-column>

        <el-table-column label="总登录" width="80" align="center">
          <template #default="{ row }">
            <span class="count-badge">{{ row.total }}</span>
          </template>
        </el-table-column>

        <el-table-column label="成功" width="70" align="center">
          <template #default="{ row }">
            <span class="count-success">{{ row.success_count }}</span>
          </template>
        </el-table-column>

        <el-table-column label="失败" width="70" align="center">
          <template #default="{ row }">
            <span :class="row.failed_count > 0 ? 'count-failed' : 'count-zero'">{{ row.failed_count }}</span>
          </template>
        </el-table-column>

        <el-table-column label="最后登录" min-width="150">
          <template #default="{ row }">{{ fmtTime(row.last_login_at) }}</template>
        </el-table-column>
      </el-table>
    </div>

  </div>
</template>

<style scoped>
/* ── 页面基础 ─────────────────────────────── */
.log-page {
  width: 100vw; height: 100vh;
  background: var(--bg);
  padding: 24px 32px 16px;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'PingFang SC', sans-serif;
  box-sizing: border-box;
  display: flex; flex-direction: column; gap: 14px;
  overflow: hidden;
}

/* ── 页头 ──────────────────────────────────── */
.page-header {
  display: flex; align-items: center; gap: 16px;
  flex-shrink: 0;
}
.btn-back {
  background: transparent; border: 1px solid var(--border);
  border-radius: 8px; padding: 6px 14px;
  font-size: 13px; color: var(--text-muted);
  cursor: pointer; font-family: inherit; transition: all 0.2s;
}
.btn-back:hover { border-color: var(--accent); color: var(--accent); }
.page-title {
  font-size: 18px; font-weight: 600;
  color: var(--text-primary); letter-spacing: 0.03em;
}

/* ── 概览指标条 ──────────────────────────── */
.metrics-bar {
  display: flex; gap: 12px; flex-shrink: 0;
}
.metric-card {
  flex: 1; background: var(--bg-card);
  border: 1px solid var(--border); border-radius: 12px;
  padding: 12px 16px; text-align: center;
}
.metric-val {
  font-size: 22px; font-weight: 700;
  color: var(--accent); line-height: 1.2;
}
.metric-lbl {
  font-size: 11px; color: var(--text-muted); margin-top: 4px;
}

/* ── 通用卡片 ────────────────────────────── */
.card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 14px; padding: 16px 20px;
  box-shadow: 0 2px 10px var(--shadow);
  display: flex; flex-direction: column;
}
.card-hd {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 12px; flex-shrink: 0;
}
.card-title {
  font-size: 13px; font-weight: 600; color: var(--text-primary);
}
.card-sub {
  font-size: 12px; color: var(--text-muted);
}

/* ── DAU 图表 ────────────────────────────── */
.dau-card { flex-shrink: 0; }
.day-tabs {
  display: flex; gap: 4px; margin-left: auto;
}
.day-tab {
  background: transparent; border: 1px solid var(--border);
  border-radius: 6px; padding: 3px 10px;
  font-size: 12px; color: var(--text-muted);
  cursor: pointer; font-family: inherit; transition: all 0.15s;
}
.day-tab:hover     { border-color: var(--accent); color: var(--accent); }
.day-tab.active    { background: var(--accent); color: #fff; border-color: var(--accent); }
.dau-chart-wrap {
  height: 160px;
  position: relative;
}
.dau-chart { width: 100%; height: 100%; }
.chart-loading-overlay {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,0.6);
  border-radius: 8px;
}
.chart-spinner {
  width: 22px; height: 22px;
  border: 2px solid #e8ddd0; border-top-color: #c4883a;
  border-radius: 50%; animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── 账号统计表 ──────────────────────────── */
.stats-card { flex: 1; min-height: 0; overflow: hidden; }
.stats-card :deep(.el-table) { flex: 1; min-height: 0; }
.stats-card :deep(.el-table__body-wrapper) { overflow-y: auto; }
.stats-card :deep(.el-table th) { background: #f5f0e8; color: #6b5e4e; font-weight: 600; }
.stats-card :deep(.el-table tr:hover td) { background: #faf7f2 !important; }

.user-cell { display: flex; align-items: center; }
.user-name { font-size: 13px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.count-badge  { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.count-success { font-size: 13px; color: #22863a; font-weight: 500; }
.count-failed  { font-size: 13px; color: #c0392b; font-weight: 500; }
.count-zero    { font-size: 13px; color: #bbb; }
</style>
