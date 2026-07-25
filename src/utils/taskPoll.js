import http from '@/api/http'

/**
 * 通用后台任务短轮询核心，供各域（shipping/product...）的持久化任务 GET 端点复用。
 *
 * 约定：目标端点返回持久化任务的通用结构 `{status, progress, result, message}`，
 * `progress` 形状和旧 SSE 事件一致（含 `step` 字段），本函数原样透传给 onEvent，
 * 调用方原有的 handleEvent()/handleData() switch 逻辑不用改。
 *
 * 保证：
 * - 不重叠请求：上一次 GET 完成（含返回后的处理）才安排下一次；
 * - 终态（done/cancelled/error/interrupted）立即停止，不再安排下一轮；
 * - 单次网络异常视为暂时性，继续下一轮（401 由 http.js 全局拦截器统一处理登录跳转）；
 * - 调用方必须在组件卸载/任务对话框关闭/被新任务替代时调用返回的 stop()。
 */
export function pollTask(taskStatusUrl, { onEvent, interval = 1000 } = {}) {
  let stopped = false
  let timer = null

  function scheduleNext() {
    if (stopped) return
    timer = setTimeout(tick, interval)
  }

  async function tick() {
    if (stopped) return
    try {
      const res = await http.get(taskStatusUrl)
      if (stopped) return
      if (!res.success) {
        // 任务不存在等业务失败：视为终态错误，不再继续轮询
        onEvent({ step: 'error', message: res.message || '任务查询失败' })
        return
      }
      const task = res.data
      const { status } = task
      if (status === 'pending' || status === 'running' || status === 'committing') {
        // committing：正在做最终业务提交，仍是活动态，必须继续轮询，不能落进下面的终态/错误分支
        onEvent({
          ...task.progress,
          cancellable: task.cancellable,
          cancelRequested: task.cancel_requested,
          // step 必须最后赋值：committing 是任务状态本身推导出的，不能被 progress.step 覆盖
          step: status === 'committing' ? 'committing' : (task.progress?.step ?? status),
        })
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
