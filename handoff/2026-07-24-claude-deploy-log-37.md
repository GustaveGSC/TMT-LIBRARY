# Claude 部署记录：产品生命周期短轮询前端

日期：2026-07-24

## 变更

提交：`1a6bbb2 refactor(frontend): 产品生命周期更新改为短轮询`

- 新增 `src/utils/taskPoll.js` 通用轮询核心（原 `shippingTaskPoll.js` 的逻辑上提，行为不变）；
  `shippingTaskPoll.js`/新增的 `productLifecyclePoll.js` 都是薄封装，分别指向
  `/api/shipping/tasks/:id`、`/api/product/lifecycle/tasks/:id`。
- `page-product.vue` 的"更新生命周期"从 `EventSource` 改为短轮询（1秒间隔、不重叠、终态立即停止）；
  409 冲突时用 `getConflictTaskId()` 接管已有任务的 `task_id` 继续轮询，而不是提示失败后中断；
  组件卸载或发起新任务前都会 `stop()` 清理上一个轮询器。
- 更新 `.claude/modules/frontend-product.md` 补充说明。

## 验证

- `npm run build:web` 通过。
- Playwright 61 用例全绿，新增 `product-lifecycle-polling.spec.js`（3 用例：正常轮询到终态停止、
  409 接管已有 task_id、离开页面后停止轮询），复用新建的 `fixtures/productPage.js`。

## 部署

无后端变更、无迁移。`tar`+`scp`+服务器端覆盖，线上 `index.html` 引用的 JS hash 与本地构建比对一致
（`index-Ce9BjsxI.js`）后删除 `.old` 备份，`https://tmt-library.cn/` 返回 200。

## 收尾

产品生命周期专项（后端 `6df3cc2`/前端 `1a6bbb2`）全部完成并部署，9 步生产门禁 + 前端短轮询回归
全部通过。旧 `EventSource`/内存队列已在这两批里彻底清除，代码库里不再有会占住唯一 sync worker 的
SSE 长连接。按既定顺序，下一步是任务取消、确定性解析与压测方案设计。
