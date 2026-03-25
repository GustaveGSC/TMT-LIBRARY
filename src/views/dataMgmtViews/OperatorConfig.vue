<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

// ── 响应式状态 ────────────────────────────────────
const operators  = ref([])   // [{ operator, type }]
const loading    = ref(false)
const saving     = ref(false)
const resolving  = ref(false)
const staleCount = ref(0)

// type 选项
const TYPE_OPTIONS = [
  { value: 'shipping',  label: '发货',  color: '#c4883a' },
  { value: 'aftersale', label: '售后',  color: '#4a8fc0' },
  { value: 'unknown',   label: '未分类', color: '#8a7a6a' },
]

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  await loadOperators()
  await loadStats()
})

// ── 方法 ──────────────────────────────────────────

async function loadOperators() {
  loading.value = true
  try {
    const res = await http.get('/api/shipping/operators')
    if (res.success) operators.value = res.data
    else ElMessage.error(res.message)
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const res = await http.get('/api/shipping/stats')
    if (res.success) staleCount.value = res.data.stale_count ?? 0
  } catch {}
}

async function saveClassify() {
  saving.value = true
  try {
    const res = await http.post('/api/shipping/operators/classify', operators.value)
    if (res.success) {
      ElMessage.success('保存成功')
    } else {
      ElMessage.error(res.message)
    }
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function resolveStale() {
  resolving.value = true
  try {
    const res = await http.post('/api/shipping/resolve')
    if (res.success) {
      ElMessage.success(`已刷新 ${res.data.resolved} 个订单的成品组合`)
      staleCount.value = 0
    } else {
      ElMessage.error(res.message)
    }
  } catch {
    ElMessage.error('刷新失败')
  } finally {
    resolving.value = false
  }
}

function typeLabel(type) {
  return TYPE_OPTIONS.find(o => o.value === type)?.label ?? type
}
function typeColor(type) {
  return TYPE_OPTIONS.find(o => o.value === type)?.color ?? '#8a7a6a'
}
</script>

<template>
  <div class="operator-config">

    <div class="config-header">
      <div class="header-left">
        <div class="config-title">操作人分类</div>
        <div class="config-sub">对发货清单「最近操作人」列的人员进行分类，用于过滤各模块的数据</div>
      </div>
      <div class="header-right">
        <!-- 刷新成品组合提示 -->
        <button
          v-if="staleCount > 0"
          class="btn-resolve"
          :disabled="resolving"
          @click="resolveStale"
        >
          {{ resolving ? '刷新中…' : `刷新成品组合 (${staleCount})` }}
        </button>
        <button class="btn-save" :disabled="saving" @click="saveClassify">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!loading && operators.length === 0" class="empty-state">
      <div class="empty-icon">📋</div>
      <div>暂无操作人数据，请先导入发货清单</div>
    </div>

    <!-- 加载 -->
    <div v-else-if="loading" class="loading-state">
      <div class="spinner"></div>
      <span>加载中…</span>
    </div>

    <!-- 操作人列表 -->
    <div v-else class="operator-list">
      <div
        v-for="item in operators"
        :key="item.operator"
        class="operator-row"
      >
        <div class="op-name">{{ item.operator }}</div>
        <div class="op-type-wrap">
          <button
            v-for="opt in TYPE_OPTIONS"
            :key="opt.value"
            class="type-btn"
            :class="{ active: item.type === opt.value }"
            :style="item.type === opt.value ? { background: opt.color, borderColor: opt.color, color: '#fff' } : {}"
            @click="item.type = opt.value"
          >{{ opt.label }}</button>
        </div>
      </div>
    </div>

  </div>
</template>

<style scoped>
.operator-config {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 680px;
}

.config-header {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
}
.config-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.config-sub   { font-size: 12px; color: var(--text-muted); }

.header-right { display: flex; gap: 8px; flex-shrink: 0; align-items: center; }

.btn-save, .btn-resolve {
  padding: 7px 16px;
  border-radius: 8px; border: none;
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.18s;
}
.btn-save {
  background: var(--accent); color: #fff;
}
.btn-save:hover:not(:disabled)    { background: var(--accent-hover); }
.btn-save:disabled, .btn-resolve:disabled { opacity: 0.45; cursor: not-allowed; }

.btn-resolve {
  background: rgba(208,90,60,0.1);
  border: 1px solid rgba(208,90,60,0.3);
  color: #d05a3c;
}
.btn-resolve:hover:not(:disabled) { background: rgba(208,90,60,0.18); }

/* 空状态 / 加载 */
.empty-state, .loading-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 10px; padding: 48px 0; color: var(--text-muted); font-size: 13px;
}
.empty-icon { font-size: 36px; }
.spinner {
  width: 24px; height: 24px;
  border: 2px solid var(--border); border-top-color: var(--accent);
  border-radius: 50%; animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* 操作人列表 */
.operator-list {
  display: flex; flex-direction: column; gap: 8px;
}
.operator-row {
  display: flex; align-items: center;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 16px;
  gap: 16px;
  transition: box-shadow 0.15s;
}
.operator-row:hover { box-shadow: 0 2px 8px var(--shadow); }

.op-name {
  flex: 1; font-size: 13px;
  color: var(--text-primary); font-weight: 500;
}

.op-type-wrap { display: flex; gap: 6px; flex-shrink: 0; }

.type-btn {
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
}
.type-btn:hover:not(.active) { border-color: var(--accent); color: var(--accent); }
</style>
