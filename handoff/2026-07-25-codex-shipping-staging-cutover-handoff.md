# C 批：发货派生数据 staging/cutover 交接

日期：2026-07-25  
分支：`codex/shipping-determinism-audit`  
状态：后端实现和本地验证完成；**未部署，禁止跳过 staging 门禁直接上线**

## 1. 完成内容

### 数据结构

新增 Alembic revision `20260725_01`：

- `shipping_resolve_target`：按 `task_id + source + ecommerce_order_no` 保存本次重算的精确范围。
- `shipping_order_finished_staging`：保存任务隔离的完整派生结果，业务列与
  `shipping_order_finished` 对齐。

两表刻意不建外键，避免大批量 cutover/清理引入级联锁。索引只保留可覆盖实际查询的复合
主键/复合索引，没有再建以 `task_id` 开头的重复单列索引。

### 重算流程

`resolve_all` 和 `resolve_stale` 都改为：

1. 固化本次目标订单范围；
2. 一次加载确定性解析所需的产品组合/通用件上下文；
3. 按 source 和订单分块计算，仅提交到 task 私有 staging；
4. 校验目标数量，并确认 staging 没有越界订单；
5. 最终取消检查后执行 `running → committing` CAS；
6. 用一个数据库事务替换正式结果；
7. **在同一事务内**把 `shipping_task` 写成 `done`、释放租约。

全量重算会先把 shipping 和 finance 两个 source 都准备完整，再统一 cutover；不会出现一半
新口径、一半旧口径。旧数据重算只替换 target 表列出的 `(source, order_no)`。

### 取消、reload 与清理

- `resolve_all` / `resolve_stale` 已加入后端可取消类型。
- staging 阶段取消或失败只清理私有代，正式结果不变。
- CAS 后不再允许取消。
- 正式表切换与任务 `done` 原子提交，关闭“数据已切换但 reload 恢复把任务标成 interrupted”
  的窗口。
- 终态超过一小时的遗留 staging，会在下一次重算开始时延迟清理；一小时延迟用于避免 graceful
  reload 时新 worker 与仍在退场的旧 worker 发生误删竞争。

## 2. 接口契约

URL 和启动响应不变：

- `POST /api/shipping/resolve-all`
- `POST /api/shipping/resolve`
- `GET /api/shipping/tasks/:task_id`
- `POST /api/shipping/tasks/:task_id/cancel`

变化：

- 两类 resolve task 的轮询结果现在可返回 `cancellable=true`。
- 取消成功后终态为 `cancelled`，文案为“重算已取消，线上数据保持不变”。
- 成功 result：

```json
{
  "resolved": 123,
  "staged_rows": 456,
  "deleted_rows": 450,
  "inserted_rows": 456,
  "cleanup_pending": false
}
```

`api.md` / `database.md` 已同步。

## 3. 自动化验证

- 后端全量：235 项测试通过。
- 新增真实 SQLite 事务测试：
  - 取消清理不改变正式代；
  - subset cutover 只替换目标订单；
  - staging INSERT 故障时 DELETE 一并回滚；
  - task 状态不再是 committing 时拒绝 cutover，正式代回滚；
  - cutover 与 task done/租约释放同时成功；
  - 一小时延迟清理只删除过期终态 task 的 staging；
  - 取消赢得 CAS 时绝不调用 cutover。
- `python -m compileall -q backend` 通过。
- `git diff --check` 通过。
- `alembic heads`：`20260725_01 (head)`，单头。

## 4. Claude 前端协作项

后端契约已经稳定，可以开始：

1. `ShippingMaintenancePage.vue` 的全量重建进度弹窗接入现有
   `useShippingTaskCancel` / `ShippingTaskCancelButton`，完全以轮询响应的 `cancellable`、
   `cancel_requested`、`committing` 为准。
2. `OperatorConfig.vue` 的旧数据重算同样接入取消状态。
3. cancelled 不按普通 error 展示；明确提示线上数据未改变。
4. 补 Playwright：取消请求、requested 状态、committing 竞争、cancelled 终态、组件卸载停止轮询。

前端仍不要单独部署，应和本批后端在 staging/cutover 门禁通过后一起发布。

## 5. 上线前强制 staging 门禁

本地 SQLite 只能证明事务语义，不能替代生产同版本 MySQL 的容量/锁时长验证。部署方需在生产
快照或同规格 staging 上完成并记录：

1. 先做数据库全量备份。
2. migration upgrade 后执行 `alembic current/check`，确认单头且无额外差异。
3. 记录正式表行数/数据大小/索引大小，以及 staging 完整代的行数和磁盘增量。
4. 在 staging 跑一次完整 `resolve_all`，新旧确定性结果做全量等价性/预期差异核对。
5. 测量：
   - staging 总构建耗时；
   - 最终 DELETE + INSERT SELECT cutover 事务耗时；
   - cutover 期间 `/health`、`/ready` 和普通读请求延迟；
   - MySQL 锁等待、临时空间、磁盘剩余量。
6. 在 staging 分别验证：
   - 构建中取消：正式表 checksum/行数完全不变；
   - cutover INSERT 人为失败：DELETE 回滚，正式表不变；
   - CAS 后模拟 reload：任务和正式代不能出现矛盾状态。
7. 只有磁盘有足够余量、cutover 锁时长可接受、结果门禁通过，才能安排生产低峰窗口。

如果 staging 证明全表 DELETE + INSERT SELECT 的锁时长不可接受，不得退回旧的分块覆盖方案；
应继续设计表代际/rename 型 cutover 后再上线。

## 6. 部署顺序

本批暂不授权部署。门禁通过后的建议顺序：

1. 生产全量备份；
2. 上传新增模型/迁移/仓储/service/route（尚不 reload）；
3. `alembic upgrade head`；
4. 核对新表结构和索引；
5. reload；
6. 严格检查一段时间内 gunicorn 日志、master PID、`/health`、`/ready`；
7. 部署已适配取消按钮的完整 `dist-web`；
8. 先做小范围 `resolve_stale` 端到端验证，再开放全量重建。

