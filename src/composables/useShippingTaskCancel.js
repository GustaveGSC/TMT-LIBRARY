import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

/**
 * 发货导入任务（import_shipping/import_finance）取消按钮的共享状态与动作。
 * DataImport.vue 和 FinanceImport.vue 共用同一份逻辑，避免状态处理分叉。
 *
 * resolve_all/resolve_stale 等不可取消任务不使用本 composable——是否显示取消入口
 * 完全由后端轮询响应里的 `cancellable` 字段决定，前端不自行按 task_type 推断。
 */
export function useShippingTaskCancel() {
  const cancellable      = ref(false)  // 当前任务是否处于"可以发起取消"的状态
  const cancelRequested  = ref(false)  // 取消请求已被后端持久化接受
  const cancelSubmitting = ref(false)  // 取消 POST 请求进行中，防止重复点击
  const committing        = ref(false) // 任务已进入不可取消的最终提交阶段

  function reset() {
    cancellable.value = false
    cancelRequested.value = false
    cancelSubmitting.value = false
    committing.value = false
  }

  /** 在轮询 onEvent 里对每个事件调用一次，同步取消相关状态 */
  function handlePollEvent(data) {
    if (typeof data.cancellable === 'boolean') cancellable.value = data.cancellable
    if (data.cancelRequested) cancelRequested.value = true
    committing.value = data.step === 'committing'
  }

  async function requestCancel(taskId) {
    if (!taskId || cancelSubmitting.value || cancelRequested.value) return
    cancelSubmitting.value = true
    try {
      const res = await http.post(`/api/shipping/tasks/${taskId}/cancel`)
      if (res.success) {
        // 200 覆盖首次和重复请求两种情况，均代表取消请求已被持久化接受
        cancelRequested.value = true
      } else if (res.data?.status === 'committing') {
        // 取消与最终提交的 CAS 竞态里提交一方胜出：不能展示"取消成功"
        committing.value = true
        ElMessage.warning(res.message || '任务正在提交最终结果，已无法取消')
      } else {
        ElMessage.warning(res.message || '取消失败')
      }
    } catch {
      ElMessage.error('取消请求失败，请重试')
    } finally {
      cancelSubmitting.value = false
    }
  }

  return {
    cancellable,
    cancelRequested,
    cancelSubmitting,
    committing,
    reset,
    handlePollEvent,
    requestCancel,
  }
}
