/**
 * 发货数据写类任务（导入/重算）共用同一把数据库级租约，同一时间只能有一个在跑。
 * 后端冲突时返回 409 + { success:false, message, data:{ task_id } }，task_id 指向
 * 当前持有租约、仍在跑的任务。
 *
 * http.js 已把 409 当作正常响应 resolve（不走 catch），所以调用方在 !res.success 分支
 * 判断是否带 task_id，带了就说明这不是"失败"而是"已有任务在跑"，应该接入现有的进度
 * 查看逻辑（SSE 或轮询），而不是只提示一句"任务冲突"就结束。
 */
export function getConflictTaskId(res) {
  if (res && res.success === false && res.data && res.data.task_id) {
    return res.data.task_id
  }
  return null
}
