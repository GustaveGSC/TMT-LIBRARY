import http from '@/api/http'

/**
 * SSE 连接异常断开（比如后端 reload 导致内存队列丢失）时的兜底：
 * 改查持久化的任务状态接口，而不是直接判定任务失败。
 * pending/running 说明任务其实还在后台跑，短暂延迟后重新订阅 SSE；
 * 否则把数据库里的终态转成和 SSE 消息一致的事件格式，交给调用方原有的 onEvent 处理。
 */
export async function recoverShippingTaskAfterSseError(taskId, { onEvent, retry }) {
  try {
    const res = await http.get(`/api/shipping/import/status/${taskId}`)
    const task = res.success ? res.data : null

    if (!task) {
      onEvent({ step: 'error', message: 'SSE 连接中断，请重试' })
      return
    }
    if (task.status === 'pending' || task.status === 'running') {
      setTimeout(retry, 1500)
      return
    }
    if (task.status === 'done') {
      onEvent({ step: 'done', data: task.result })
    } else if (task.status === 'cancelled') {
      onEvent({ step: 'cancelled', message: task.message })
    } else {
      // error / interrupted（进程重启导致任务被标记中断）
      onEvent({ step: 'error', message: task.message || '任务已中断（服务重载或异常退出），请重新上传' })
    }
  } catch {
    onEvent({ step: 'error', message: 'SSE 连接中断，请重试' })
  }
}
