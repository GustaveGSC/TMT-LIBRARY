import { pollTask } from '@/utils/taskPoll'

/**
 * 产品生命周期更新任务短轮询，轮询 `GET /api/product/lifecycle/tasks/<task_id>`。
 * 见 handoff/2026-07-24-claude-product-lifecycle-task-handoff.md。核心轮询逻辑见 taskPoll.js。
 */
export function pollProductLifecycleTask(taskId, options) {
  return pollTask(`/api/product/lifecycle/tasks/${taskId}`, options)
}
