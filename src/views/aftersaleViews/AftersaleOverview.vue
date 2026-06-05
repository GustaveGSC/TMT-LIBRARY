<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import http from '@/api/http.js'

// ── 响应式状态 ────────────────────────────────────
const loading = ref(false)
const stats   = ref(null)

// ── 生命周期 ──────────────────────────────────────
onMounted(loadStats)

// ── 方法 ──────────────────────────────────────────
async function loadStats() {
  loading.value = true
  const res = await http.get('/api/aftersale/stats')
  if (res.success) stats.value = res.data
  loading.value = false
}

// 当前年月字符串，用于标题
function currentMonthLabel() {
  const now = new Date()
  return `${now.getMonth() + 1}月`
}

// 暴露给父组件刷新
defineExpose({ refresh: loadStats })
</script>

<template>
  <div class="overview-wrap">
    <div v-if="loading && !stats" class="loading-state">加载中…</div>

    <template v-else-if="stats">
      <!-- ── 统计卡片 ──────────────────────────── -->
      <div class="stat-grid">
        <div class="stat-card" :class="{ warn: stats.pending > 0 }">
          <div class="stat-label">待处理</div>
          <div class="stat-value" :class="{ 'warn-val': stats.pending > 0 }">
            {{ stats.pending }}
          </div>
          <div class="stat-hint" v-if="stats.pending > 0">有工单待确认</div>
          <div class="stat-hint good" v-else>全部已处理</div>
        </div>

        <div class="stat-card">
          <div class="stat-label">{{ currentMonthLabel() }}售后量</div>
          <div class="stat-value">{{ stats.this_month }}</div>
          <div class="stat-hint">按售后日期统计</div>
        </div>

        <div class="stat-card">
          <div class="stat-label">累计已处理</div>
          <div class="stat-value">{{ stats.confirmed }}</div>
          <div class="stat-hint">共 {{ stats.total }} 条记录</div>
        </div>

        <div class="stat-card muted">
          <div class="stat-label">已忽略</div>
          <div class="stat-value muted-val">{{ stats.ignored }}</div>
        </div>
      </div>

    </template>

    <div v-else class="loading-state">暂无数据</div>
  </div>
</template>

<style scoped>
.overview-wrap {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
.overview-wrap::-webkit-scrollbar { width: 4px; }
.overview-wrap::-webkit-scrollbar-track { background: transparent; }
.overview-wrap::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.loading-state {
  color: var(--text-muted);
  font-size: 13px;
  padding: 40px 0;
  text-align: center;
}

/* ── 统计卡片 ── */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 28px;
}
.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px 16px;
  transition: box-shadow 0.2s;
}
.stat-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.06); }
.stat-card.warn  { border-color: rgba(208,90,60,0.3); background: rgba(208,90,60,0.03); }
.stat-card.muted { background: rgba(0,0,0,0.015); }

.stat-label { font-size: 12px; color: var(--text-muted); margin-bottom: 10px; }
.stat-value {
  font-size: 36px; font-weight: 700;
  color: var(--accent);
  letter-spacing: -0.02em;
  line-height: 1;
}
.stat-value.warn-val  { color: #d05a3c; }
.stat-value.muted-val { color: var(--text-muted); font-size: 28px; }

.stat-hint      { font-size: 11px; color: var(--text-aux); margin-top: 8px; }
.stat-hint.good { color: #5a9e6e; }

/* ── 移动端 ── */
@media (max-width: 768px) {
  .overview-wrap { padding: 16px; }
  .stat-grid { grid-template-columns: repeat(2, 1fr); gap: 10px; }
  .stat-value { font-size: 28px; }
}
</style>
