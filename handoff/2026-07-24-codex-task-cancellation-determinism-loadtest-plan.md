# 发货任务取消、确定性解析与压测方案

日期：2026-07-24  
性质：只读审计与实施方案；尚未修改运行时代码

## 结论

这项工作不能作为一个大提交直接铺开。建议拆成四个有独立门禁的批次：

1. **A：持久化取消协议 + 导入任务全链路取消**
2. **B：解析确定性审计与稳定规则**
3. **C：重算任务可取消的 staging/cutover 模型**
4. **D：生产同规格压测与容量结论**

A/B 可以先做；C 必须经过磁盘、事务锁和切换耗时基准后才能上线；D 为前三批提供门禁数据，不以“本机跑得快”
代替生产同规格验证。

## 一、现状核查

### 1. 当前取消并不可靠

`backend/routes/shipping/__init__.py` 的 `_cancel_flags` 是进程内字典：

- reload 后消失；
- 未来增加 worker 后无法跨进程读取；
- 只在发货/财务导入的 `on_insert_progress()` 检查；
- Excel/CSV 解析、DB 快照比对、组合计算和保存阶段都没有检查；
- `resolve_all`、`resolve_stale` 完全不读取取消标志。

现有 `/api/shipping/import/cancel/<task_id>` 会接受任意 `pending/running` 的 shipping task。因此对
`resolve_all/resolve_stale` 调用时会返回“已发送中止信号”，但任务不会停止，这是一个真实契约错误。

### 2. 当前重算不能安全地“中途 rollback”

导入任务使用 `commit_chunks=False`，最后一次提交，取消时可完整 rollback。

全量/旧数据重算使用默认 `commit_chunks=True`：

- 先按500个订单分块删除旧派生行并提交；
- 再按200行分块插入新派生行并提交；
- 中途停止会留下已经删除、尚未重建或只重建部分的订单。

因此不能简单给 `_resolve_orders()` 加 `cancel_check` 后就开放重算取消，否则会把“无法取消”变成“可以破坏派生
数据的一键取消”。

### 3. 确定性风险不止一个排序键

已确认三处：

1. `finished_list` 查询无 `ORDER BY`，只按组件数倒序稳定排序；组件数相同的候选继承数据库偶然返回顺序。
2. `required_codes` 是 `frozenset`，消费多个要求组件时的遍历顺序受 Python hash seed 影响；当等效件集合重叠
   时可能影响后续候选。
3. `get_order_products()` 查询无 `ORDER BY`，订单的日期、操作人、渠道、地域等元数据取“第一行”；同一订单多行
   元数据不一致时结果取决于数据库返回顺序。客户简称也是“第一个非空值”。

现有“精确码优先、等效码按字典序”已经确定，不需要改变。

## 二、A批：持久化取消协议

### 数据库

给 `shipping_task` 增加：

- `cancel_requested_at DATETIME NULL`
- `cancel_requested_by INT NULL`（记录操作者；不加外键，避免账号清理影响任务历史）

不使用模块级 `_cancel_flags` 作为事实来源。后台线程通过独立短事务查询取消状态，不能复用导入业务 session，
否则 MySQL `REPEATABLE READ` 可能一直看不到请求。

### 统一接口

新增：

```text
POST /api/shipping/tasks/<task_id>/cancel
权限：shipping:edit
请求体：无
```

响应规则：

- 不存在：404；
- 已完成：400，“任务已经结束，无法取消”；
- 已进入不可取消提交阶段：409，“任务正在提交最终结果，已无法取消”；
- 第一次请求：200，“已发送取消请求”；
- 重复请求：200，同一文案，保持幂等。

旧 `/import/cancel/<task_id>` 保留一个发布周期，内部调用同一 service，不再操作内存字典。

### 状态机与竞态

状态扩展为：

```text
pending -> running -> committing -> done
                    \-> cancelled
                    \-> error/interrupted
```

- `cancel` 只在 `pending/running` 写入 `cancel_requested_at`。
- worker 在最终业务提交前，用条件更新将 `running -> committing`，条件必须包含
  `cancel_requested_at IS NULL`。
- 取消请求和 `committing` 转换谁先完成，谁获得决定权：
  - 取消先成功：worker rollback 并写 `cancelled`；
  - committing 先成功：取消接口返回409，任务完成提交。
- 接口收到取消请求时不能立刻释放租约；只有 worker 真正进入终态才释放，避免第二个写任务与仍在退出的线程并发。

### 导入任务检查点

给解析器和 `_resolve_orders()` 显式传 `cancel_check`，至少在以下位置检查：

- 读取文件前后；
- CSV/XLSX 每500行；
- 文件内合并后；
- DB 快照查询每个 key chunk 前后；
- 每个 bulk insert chunk 前后；
- 每个发货/销退加载 chunk；
- 销退匹配和订单组合循环每100个订单；
- 删除旧派生行之前；
- 每个保存 chunk 前后；
- 最终 `committing` 状态转换前。

`openpyxl.load_workbook()` 本身无法安全抢占；该调用期间取消只能等待函数返回。前端文案必须是“正在取消”，不能承诺
“立即停止”。

### A批范围限制

A批只对 `import_shipping/import_finance` 宣布完整可取消。`resolve_all/resolve_stale` 在C批前必须明确返回
“该任务暂不支持取消”，不能继续假成功。

## 三、B批：确定性解析

### 先做生产只读统计

在决定 tie-break 前统计：

1. 组件数量相同且可能竞争同一订单物料的成品候选数量；
2. 等效件集合重叠并可能因要求组件消费顺序改变结果的组合；
3. 同一 `(order_no, source)` 下 shipped_date/operator/channel/province/city/customer_alias 存在多个非空值的订单数；
4. 分别用不同 `PYTHONHASHSEED`、候选顺序和元数据行顺序跑真实订单，统计结果差异。

### 建议稳定规则

若生产对比确认业务可接受：

- 成品候选：组件数降序 → `finished_code` 升序；
- 成品要求组件：排序后的 tuple，禁止运行时遍历 set/frozenset；
- 等效件消费：保持现有“精确码优先 → 其他等效码字典序”；
- 订单物料数量：只做交换律求和，不依赖行顺序；
- 订单元数据不能继续取偶然第一行。先根据统计确定规则：
  - 若真实数据全部一致：显式 `ORDER BY record.id` 固化现状，并加一致性监测；
  - 若存在冲突：由业务确认“最早记录、最新记录或非空优先”的口径后再实施，不能由开发者猜测。

### B批门禁

- 同一数据用至少3个不同 `PYTHONHASHSEED` 重复运行，输出 hash 必须一致；
- 对生产真实 shipping/finance 订单全量比较新旧结果；
- 非歧义订单必须 0 不一致；
- 歧义订单单独列清单，只有明确接受新 tie-break 后才能部署；
- 新增合成测试覆盖“同组件数竞争、重叠等效件、输入行乱序、候选乱序”。

## 四、C批：重算任务的安全取消

### 不采用的方案

- 不把全量重算强行改成一个持续数分钟的大事务；
- 不允许“处理过的订单是新规则、未处理的是旧规则”作为取消终态；
- 不在删除旧结果后靠 best-effort 恢复；
- 不用内存保存全部新结果作为唯一副本。

### 推荐 staging + 原子 cutover

新增轻量 staging 表，字段为：

- `task_id`
- 与 `shipping_order_finished` 写入所需的业务字段
- 仅保留 staging 写入/清理必要索引，不复制全部图表查询索引

流程：

1. 持有现有 `shipping_data_mutation` 租约，阻止导入和其他重算改变输入。
2. 分块读取、计算并提交到 staging；这段可以随时取消。
3. 取消时删除该 task_id 的 staging 行，正式派生表完全不变。
4. 全部计算完成后竞争 `running -> committing`。
5. 成功进入 committing 后，用一个短事务：
   - 删除目标 source/order 范围的旧行；
   - `INSERT ... SELECT` 从 staging 写入正式表；
   - commit。
6. 提交后清理 staging，任务 done；清理失败可由 TTL 作业补偿，不影响正式结果。

全量重算应先把 shipping/finance 两个来源都准备到 staging，再统一 cutover，避免一个来源新规则、另一个来源旧规则。

### C批必须先测

- staging 全量数据的磁盘增量；
- staging 写入速度和临时空间峰值；
- 最终 delete + insert-select 的锁等待与事务耗时；
- cutover 期间图表读取的 p95/max 延迟；
- 中途取消后正式表 checksum 完全不变；
- cutover 前取消、cutover 竞争取消、cutover 后取消三种竞态。

若 staging 磁盘或最终事务不可接受，停止C批并重新评估 generation 列方案；不能退回不一致的分块覆盖。

## 五、D批：压测设计

### 环境

- 与生产相同：2核、约1.7GB RAM、单 sync worker、QueuePool 5+5；
- 优先使用生产脱敏快照或同等数据量副本；
- 禁止直接在生产库执行写压测；
- 生产只允许最终门禁的只读查询和可 rollback 小样本。

### 场景矩阵

导入：

- 1千、1万、5万、10万行；
- 全新、完全重复、10%变化的财务重导；
- parsing/inserting/resolving/committing 各阶段取消；
- 两个客户端并发启动，验证一个成功、一个409接管。

重算：

- 1千、1万、10万、全量订单；
- shipping、finance、两来源合计；
- staging 25%/75%时取消；
- cutover 边界取消；
- reload 后任务 interrupted、租约释放、staging 可清理。

确定性：

- 同一数据至少3种 hash seed、3次重复；
- 候选顺序、订单行顺序随机打乱；
- 输出按业务主键排序后计算 checksum。

### 采集指标

- 总耗时、各阶段耗时、rows/s；
- `/health`、`/ready` 并发探测 p50/p95/max；
- gunicorn heartbeat/worker 重启；
- Python RSS峰值、系统 available、swap in/out；
- CPU利用率与load；
- MySQL连接峰值、锁等待、事务时长、临时表/磁盘增量；
- 取消请求到 worker 终态的延迟；
- 409数量、任务失败/中断数量；
- 取消前后正式业务表 checksum。

### 初始验收线

- 业务数据：取消导入后 checksum 与开始前一致；重算 staging 取消后正式表一致；
- 确定性：重复运行输出 hash 100%一致；
- 并发：数据库租约竞争测试100%只有一个持有者；
- 可用性：后台任务期间 `/health` p95 < 1秒、max < 2秒，无 worker timeout/restart；
- 资源：无持续 swap-in/out、无 OOM、连接数不超过既定池上限；
- 取消响应：可检查循环阶段5秒内进入 cancelled；不可抢占的文件打开阶段单独记录实际最大延迟；
- cutover：实测锁等待和读请求延迟需单独经用户接受，不能只用平均值掩盖最大停顿。

验收线可在首轮基准后收紧，但不能为了让测试变绿而放宽数据一致性、worker重启或OOM三条硬门禁。

## 六、自动化测试要求

后端至少新增：

- 数据库持久化取消、幂等取消、reload恢复；
- cancel 与 committing CAS 竞态；
- 导入在 parsing/inserting/resolving 三阶段取消均 rollback；
- 不支持取消的任务明确拒绝；
- 取消过程中租约不释放；
- staging 取消不修改正式表；
- staging cutover 原子性；
- 多 hash seed/乱序输入结果一致；
- 旧接口兼容转发；
- 权限测试：`shipping:view` 不能取消，`shipping:edit` 可以。

前端由 Claude 在A/C契约稳定后处理：

- 按 `cancellable`/任务类型显示取消按钮；
- 取消后显示“正在取消”，继续轮询到真正终态；
- 409接管的任务也遵循后端返回的可取消状态；
- 卸载时只停止轮询，不自动发送取消；
- Playwright 覆盖重复点击、终态、不可取消提交阶段和接管任务。

## 七、建议实施顺序

1. Codex A1：迁移 + repository CAS +统一取消接口；
2. Codex A2：导入解析/写入/增量 resolve 检查点和原子回滚测试；
3. Claude：导入取消前端适配；
4. Codex B：生产只读歧义审计，先提交报告，再实施稳定排序；
5. Codex/Claude 联合完成B批全量等价门禁；
6. Codex C：staging 原型与基准，门禁通过后才形成正式迁移；
7. Claude：重算取消前端适配；
8. D批完整压测，形成容量结论后再进入后续缓存/结构拆分。

A批不能顺带实现C批；B批不能在生产歧义统计前直接选择 tie-break。这两个边界用于控制这项工作的回归面。
