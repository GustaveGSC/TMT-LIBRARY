import { pollTask } from '@/utils/taskPoll'

/**
 * 发货后台任务（导入/重算）短轮询，轮询 `GET /api/shipping/tasks/<task_id>`。
 * 见 handoff/2026-07-24-claude-handoff-33.md。核心轮询逻辑见 taskPoll.js。
 */
export function pollShippingTask(taskId, options) {
  return pollTask(`/api/shipping/tasks/${taskId}`, options)
}
