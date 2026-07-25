<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import { pollShippingTask } from '@/utils/shippingTaskPoll'
import { getConflictTaskId } from '@/utils/taskConflict'
import { usePermission } from '@/composables/usePermission'
import { useShippingTaskCancel } from '@/composables/useShippingTaskCancel'
import ShippingTaskCancelButton from '@/components/shipping/ShippingTaskCancelButton.vue'

// ── 权限 ──────────────────────────────────────────
const { canEditShipping } = usePermission()
const taskCancel = useShippingTaskCancel()
const currentTaskId = ref('')

// ── 重建全部成品组合 ──────────────────────────────
const resolving           = ref(false)
const showResolveConfirm  = ref(false)
const showResolveProgress = ref(false)
const resolveCurrentOrder = ref(0)
const resolveTotalOrders  = ref(0)
const resolvePrepareMsg   = ref('')
const resolvePrepareCount = ref(0)
const resolveSaving       = ref(false)
const resolveSaveCurrent  = ref(0)
const resolveSaveTotal    = ref(0)
const resolveCommitting   = ref(false)

let activePoller = null
onUnmounted(() => {
  activePoller?.stop()
})

function cancelResolve() {
  taskCancel.requestCancel(currentTaskId.value)
}

async function handleResolveAll() {
  if (resolving.value) return
  activePoller?.stop()
  activePoller = null
  taskCancel.reset()
  currentTaskId.value        = ''
  showResolveConfirm.value  = false
  resolving.value           = true
  resolveCurrentOrder.value = 0
  resolveTotalOrders.value  = 0
  resolvePrepareMsg.value   = '正在初始化…'
  resolveCommitting.value   = false
  showResolveProgress.value = true
  let wasCancelled = false
  try {
    const res = await http.post('/api/shipping/resolve-all')
    const conflictTaskId = getConflictTaskId(res)
    if (!res.success && !conflictTaskId) {
      showResolveProgress.value = false
      ElMessage.error(res.message || '启动失败')
      return
    }
    if (conflictTaskId) {
      ElMessage.warning(res.message || '已有发货数据任务在运行，正在接入该任务的进度')
      resolvePrepareMsg.value = '正在接入当前运行任务...'
    }
    const taskId = conflictTaskId || res.data.task_id
    currentTaskId.value = taskId

    await new Promise((resolve, reject) => {
      activePoller = pollShippingTask(taskId, {
        onEvent(data) {
          taskCancel.handlePollEvent(data)
          if (data.step === 'preparing') {
            resolvePrepareMsg.value   = data.message  ?? '正在准备数据…'
            resolveTotalOrders.value  = data.total    ?? 0
            resolvePrepareCount.value = data.current  ?? 0
          } else if (data.step === 'resolving') {
            resolvePrepareMsg.value   = ''
            resolveSaving.value       = false
            resolveCurrentOrder.value = data.current ?? 0
            resolveTotalOrders.value  = data.total   ?? 0
          } else if (data.step === 'saving') {
            resolveSaving.value      = true
            resolveSaveCurrent.value = data.current ?? 0
            resolveSaveTotal.value   = data.total   ?? 0
          } else if (data.step === 'committing') {
            resolveCommitting.value = true
          } else if (data.step === 'done') {
            activePoller?.stop()
            resolveCurrentOrder.value = data.data.resolved
            resolveTotalOrders.value  = data.data.resolved
            resolve()
          } else if (data.step === 'cancelled') {
            activePoller?.stop()
            wasCancelled = true
            resolve()
          } else if (data.step === 'error') {
            activePoller?.stop()
            ElMessage.error(data.message || '计算失败')
            reject()
          }
        },
      })
    })
    if (wasCancelled) {
      ElMessage.info('重算已取消，线上数据保持不变')
    } else {
      ElMessage.success(`刷新完成，共处理 ${resolveCurrentOrder.value.toLocaleString()} 条订单`)
    }
  } catch {
    // ElMessage 已在内部处理
  } finally {
    activePoller?.stop()
    activePoller = null
    taskCancel.reset()
    resolving.value           = false
    showResolveProgress.value = false
  }
}
</script>

<template>
  <div class="shipping-maintenance-page">
    <div class="config-header">
      <div class="config-title">重建全部成品组合</div>
      <div class="config-sub">
        重新计算全部历史订单的成品组合。日常导入和修改客户匹配都不需要用到这个操作——只有在
        产品组合规则、通用件等效规则发生系统性变化，或者重新导入历史财务数据补全了客户简称
        （既有订单的派生数据不会自动同步）之后，才需要在这里手动重建一次。数据量大时耗时较长，
        请在业务低峰期操作。
      </div>
    </div>
    <button
      v-if="canEditShipping"
      class="btn-resolve"
      :class="{ resolving }"
      :disabled="resolving"
      @click="showResolveConfirm = true"
    >
      <svg class="resolve-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
      </svg>
      <span>重建全部成品组合</span>
    </button>

    <!-- ── 重建全部成品组合确认弹窗 ─────────────────── -->
    <el-dialog
      v-model="showResolveConfirm"
      title="重建全部成品组合（高级）"
      width="440px"
      :close-on-click-modal="false"
    >
      <div class="confirm-body">
        将重新计算全部历史订单的成品组合（含发货数量、销退数量、实际数量），数据量较大时可能耗时较长
        （数万到数十万订单级别可能需要数分钟），确认继续？
      </div>
      <template #footer>
        <el-button @click="showResolveConfirm = false">取消</el-button>
        <el-button type="primary" @click="handleResolveAll">确认重建</el-button>
      </template>
    </el-dialog>

    <!-- ── 重建进度弹窗 ──────────────────────────── -->
    <el-dialog
      v-model="showResolveProgress"
      title="重建全部成品组合（高级）"
      width="420px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="false"
    >
      <div class="progress-body">
        <template v-if="resolveCommitting">
          <div class="progress-label">
            <span>正在提交最终结果，此阶段已无法取消…</span>
          </div>
          <el-progress :percentage="100" :stroke-width="10" :color="'#c4883a'" status="" />
        </template>
        <template v-else-if="resolvePrepareMsg">
          <div class="progress-label">
            <span class="progress-prepare-msg">{{ resolvePrepareMsg }}</span>
            <span class="progress-count">
              {{ resolvePrepareCount.toLocaleString() }}
              <span class="progress-sep">/</span>
              {{ resolveTotalOrders > 0 ? resolveTotalOrders.toLocaleString() : '…' }}
            </span>
          </div>
          <el-progress
            :percentage="resolveTotalOrders > 0 ? Math.min(Math.round(resolvePrepareCount / resolveTotalOrders * 100), 99) : 0"
            :stroke-width="10"
            :color="'#c4883a'"
            status=""
          />
        </template>
        <template v-else-if="!resolveSaving">
          <div class="progress-label">
            <span>当前处理订单</span>
            <span class="progress-count">
              {{ resolveCurrentOrder.toLocaleString() }}
              <span class="progress-sep">/</span>
              {{ resolveTotalOrders > 0 ? resolveTotalOrders.toLocaleString() : '…' }}
            </span>
          </div>
          <el-progress
            :percentage="resolveTotalOrders > 0 ? Math.min(Math.round(resolveCurrentOrder / resolveTotalOrders * 100), 99) : 0"
            :stroke-width="10"
            :color="'#c4883a'"
            status=""
          />
        </template>
        <template v-else>
          <div class="progress-label">
            <span>正在写入数据库</span>
            <span class="progress-count">
              {{ resolveSaveCurrent.toLocaleString() }}
              <span class="progress-sep">/</span>
              {{ resolveSaveTotal > 0 ? resolveSaveTotal.toLocaleString() : '…' }}
            </span>
          </div>
          <el-progress
            :percentage="resolveSaveTotal > 0 ? Math.min(Math.round(resolveSaveCurrent / resolveSaveTotal * 100), 100) : 0"
            :stroke-width="10"
            :color="'#c4883a'"
            status=""
          />
        </template>
        <div class="progress-hint">请勿关闭窗口，计算完成后将自动关闭</div>
        <ShippingTaskCancelButton
          class="progress-cancel-btn"
          :cancellable="taskCancel.cancellable.value"
          :cancel-requested="taskCancel.cancelRequested.value"
          :cancel-submitting="taskCancel.cancelSubmitting.value"
          :committing="taskCancel.committing.value"
          @cancel="cancelResolve"
        />
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.shipping-maintenance-page {
  width: 100%; height: 100%;
  overflow-y: auto;
  padding: 24px;
  box-sizing: border-box;
  display: flex; flex-direction: column; gap: 18px;
  max-width: 640px;
}

.config-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.config-sub   { font-size: 12px; color: var(--text-muted); line-height: 1.7; }

.btn-resolve {
  display: flex; align-items: center; gap: 6px;
  align-self: flex-start;
  padding: 9px 20px;
  border: 1px solid var(--border); border-radius: 8px;
  background: transparent; color: var(--text-muted);
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.18s; white-space: nowrap;
}
.btn-resolve:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.btn-resolve:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-resolve.resolving { border-color: rgba(196,136,58,0.4); color: var(--accent); }
.resolve-icon { width: 15px; height: 15px; flex-shrink: 0; }

.confirm-body { font-size: 13px; color: var(--text-primary); line-height: 1.7; }

.progress-body { display: flex; flex-direction: column; gap: 10px; }
.progress-label { display: flex; justify-content: space-between; align-items: baseline; font-size: 13px; color: var(--text-primary); }
.progress-prepare-msg { color: var(--text-muted); }
.progress-count { font-variant-numeric: tabular-nums; color: var(--text-muted); font-size: 12px; }
.progress-sep { margin: 0 3px; }
.progress-hint { font-size: 12px; color: var(--text-muted); text-align: center; }
.progress-cancel-btn { align-self: center; margin-top: 4px; }
</style>
