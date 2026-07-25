# Claude 部署记录：发货导入取消前端适配

日期：2026-07-25

## 实现

- `src/composables/useShippingTaskCancel.js`：`cancellable`/`cancelRequested`/`cancelSubmitting`/
  `committing` 状态 + `requestCancel(taskId)`，POST `/api/shipping/tasks/:id/cancel`。是否显示取消
  入口完全由后端轮询响应的 `cancellable` 字段决定，前端不按 `task_type` 自行推断。
- `src/components/shipping/ShippingTaskCancelButton.vue`：纯展示组件，`DataImport.vue`/
  `FinanceImport.vue` 共用同一份状态处理逻辑，不分叉。
- `resolve_all`/`resolve_stale`（`ShippingMaintenancePage.vue`/`OperatorConfig.vue`）未引入取消
  composable，天然不显示取消入口。

## 顺带修复：taskPoll.js 的 committing 状态误判

审查触发状态矩阵时发现：`src/utils/taskPoll.js` 原来只把 `pending`/`running` 当活动态继续轮询，
`committing` 会落进最后的 `else` 分支被当成 `error` 上报，导致真实场景下——取消与最终提交竞争、
提交方胜出时——用户会在提交阶段短暂看到一次"任务已中断"的假错误，即使任务几秒后就会正常完成。
已修复为 `pending`/`running`/`committing` 三态都继续轮询，`committing` 单独映射为 `step:'committing'`
交给调用方展示"正在提交，无法取消"。这个核心轮询函数同时被产品生命周期轮询复用，产品生命周期任务
没有 `committing` 状态，改动对其无影响（新分支只是多出一个永远不会命中的条件）。

## 验证

- `npm run build:web`：通过。
- 全量 Playwright：**66 passed**（新增 5 项覆盖正常取消/重复点击/取消与committing竞争/
  cancelled终态展示/resolve_all与resolve_stale无按钮/组件卸载停止轮询，其余 61 项既有回归全部
  保持通过，确认 `taskPoll.js` 改动没有引入其他页面的行为回归）。
- `git diff --check`：通过（`dist-web/` 里预存的 LF/CRLF 提示与本次改动无关，本次只提交了源码文件，
  未提交 `dist-web/` 构建产物到 git）。

## 部署

前端 only，无需后端 reload。`tar+scp+服务器端整体替换` 流程，部署后确认线上 `index.html` 引用的
`index-BB6UI9Ut.js` 哈希与本地构建一致，`https://tmt-library.cn/` 返回 200，删除 `.old` 备份目录。

## 结论

发货任务取消 A1+A2 的后端能力现在有对应的前端入口，闭环完成。下一步按既定顺序进入 B 批：生产只读
歧义审计（成品匹配候选竞争、等效件消费顺序、订单元数据取值口径）。
