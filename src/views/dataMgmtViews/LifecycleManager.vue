<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

// ── 响应式状态 ────────────────────────────────────
const running = ref(false)
const current = ref(0)
const total   = ref(0)

// ── 计算属性 ──────────────────────────────────────
const progress = computed(() =>
  total.value > 0 ? Math.round((current.value / total.value) * 100) : 0
)

// ── 方法 ──────────────────────────────────────────
async function handleUpdate() {
  if (running.value) return
  running.value = true
  current.value = 0
  total.value   = 0

  try {
    // 启动后台任务
    const res = await http.post('/api/product/lifecycle/update')
    if (!res.success) {
      ElMessage.error(res.message || '启动失败')
      return
    }
    const taskId = res.data.task_id

    // 订阅 SSE 进度流
    await new Promise((resolve, reject) => {
      const es = new EventSource(
        `http://127.0.0.1:8765/api/product/lifecycle/progress/${taskId}`
      )
      es.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.step === 'processing') {
          // 更新进度条
          current.value = data.current
          total.value   = data.total
        } else if (data.step === 'done') {
          es.close()
          const d = data.data
          ElMessage.success(
            `生命周期更新完成，共更新 ${d.updated} 条记录（${d.total_models} 个型号）`
          )
          resolve()
        } else if (data.step === 'error') {
          es.close()
          ElMessage.error(data.message || '更新失败')
          reject(new Error(data.message))
        }
      }
      es.onerror = () => {
        es.close()
        ElMessage.error('连接中断，请重试')
        reject(new Error('SSE 连接中断'))
      }
    })
  } catch {
    // ElMessage 已在内部处理
  } finally {
    running.value = false
  }
}
</script>

<template>
  <div class="lifecycle-manager">
    <div class="lc-card">
      <div class="lc-header">
        <div class="lc-title">生命周期管理</div>
        <div class="lc-sub">
          批量根据每个型号的发货数据推算上市日期和退市日期，仅更新状态为「已录入」的成品。
          处理规则：无数据时定为 2020-01 上市 / 2023-12 退市；近 2 个月内有数据则清空退市日期。
        </div>
      </div>

      <div class="lc-body">
        <!-- 触发按钮 -->
        <button
          class="btn-update"
          :class="{ running }"
          :disabled="running"
          title="根据发货数据批量更新成品上市/退市日期"
          @click="handleUpdate"
        >
          <span v-if="!running">更新生命周期</span>
          <span v-else>更新中…</span>
        </button>

        <!-- 进度区（运行时显示） -->
        <div v-if="running" class="progress-wrap">
          <el-progress
            :percentage="progress"
            :stroke-width="8"
            :color="'#c4883a'"
            style="flex: 1"
          />
          <span class="progress-text">{{ current }} / {{ total }} 个型号</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lifecycle-manager {
  max-width: 560px;
}

.lc-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 28px 32px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.lc-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.lc-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.lc-sub {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.7;
}

.lc-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.btn-update {
  align-self: flex-start;
  padding: 8px 22px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.18s, opacity 0.18s;
}

.btn-update:hover:not(:disabled) {
  background: #b8782e;
}

.btn-update:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.progress-wrap {
  display: flex;
  align-items: center;
  gap: 14px;
}

.progress-text {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}
</style>
