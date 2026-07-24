import http from '@/api/http'

/**
 * 发货后台任务（导入/重算）统一短轮询。
 *
 * 后端不再为新任务创建 SSE 内存队列，进度和终态只写持久化 `shipping_task` 表
 * （见 handoff/2026-07-24-claude-handoff-33.md）。这里统一每 1 秒轮询
 * `GET /api/shipping/tasks/<task_id>`，把 `status`/`progress`/`result` 翻译成
 * 和旧 SSE 事件一致的 `{ step, ... }` 形状，交给调用方原有的 onEvent 处理函数，
 * 这样各调用点原有的 handleEvent()/handleData() switch 逻辑不用改。
 *
 * 保证：
 * - 不重叠请求：上一次 GET 完成（含返回后的处理）才安排下一次；
 * - 终态（done/cancelled/error/interrupted）立即停止，不再安排下一轮；
 * - 单次网络异常视为暂时性，继续下一轮（401 由 http.js 全局拦截器统一处理登录跳转）；
 * - 调用方必须在组件卸载/任务对话框关闭/被新任务替代时调用返回的 stop()。
 */
export function pollShippingTask(taskId, { onEvent, interval = 1000 } = {}) {
  let stopped = false
  let timer = null

  function scheduleNext() {
    if (stopped) return
    timer = setTimeout(tick, interval)
  }

  async function tick() {
    if (stopped) return
    try {
      const res = await http.get(`/api/shipping/tasks/${taskId}`)
      if (stopped) return
      if (!res.success) {
        // 任务不存在等业务失败：视为终态错误，不再继续轮询
        onEvent({ step: 'error', message: res.message || '任务查询失败' })
        return
      }
      const task = res.data
      const { status } = task
      if (status === 'pending' || status === 'running') {
        onEvent({ step: task.progress?.step ?? status, ...task.progress })
        scheduleNext()
      } else if (status === 'done') {
        onEvent({ step: 'done', data: task.result })
      } else if (status === 'cancelled') {
        onEvent({ step: 'cancelled', message: task.message })
      } else {
        // error / interrupted（进程重启导致任务被标记中断）
        onEvent({ step: 'error', message: task.message || '任务已中断（服务重载或异常退出），请重试' })
      }
    } catch {
      // 单次网络异常，暂时性，继续下一轮
      scheduleNext()
    }
  }

  tick()

  return {
    stop() {
      stopped = true
      if (timer) clearTimeout(timer)
    },
  }
}
