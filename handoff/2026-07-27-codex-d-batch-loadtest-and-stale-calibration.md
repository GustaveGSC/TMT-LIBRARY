# D 批：同规格压测方案与 resolve_stale 上限校准

日期：2026-07-27

性质：只读方案与生产只读核验。**未改运行时代码、未触发任务、未在生产执行写压测。**

## 一、结论

1. 建议先建设独立、同规格的压测实例，再决定是否进行任何写入压力测试；不以生产数据库承载压测。
2. `resolve_all` 已有可信生产基线：250,565 个订单对、691,990 行输出，完整重建 386.9 秒；全量组件守恒
   校验 0 不一致。它是 D 批的“真实上限参考”，不是替代压测环境的理由。
3. **`MAX_STALE_RESOLVE_ORDERS` 维持 10,000，不上调、不改成动态值。** 生产没有历史 stale 样本，且代码
   中没有将 `is_stale` 置为 `True` 的生产路径；目前无法用真实历史分布校准该值。
4. 更基础的问题是 stale 生命周期未闭环：当前 `resolve_stale` 有消费端和 UI，但没有生产端标记订单过期。
   需要先单独确认哪些规则变更应标记哪些订单 stale，随后才能用克隆环境建立真实样本并校准上限。

## 二、生产只读核验

### 1. 历史样本不存在

以已有数据库账号执行纯 `SELECT` / `SHOW INDEX`，没有调用 `create_app()`，没有创建临时表或写入数据：

- 当前 `shipping_order_finished.is_stale=1`：0 行、0 个 `(order_no, source)`；
- `shipping_task(task_type='resolve_stale')`：0 条历史任务；
- 源码全局检索：`is_stale=True` 没有生产写入点；导入、staging 与 full generation 写入都明确写入
  `False`。

所以“历史上一次规则变更产生多少 stale 订单”目前无从统计，不能编造分布或据此调高 10,000。

### 2. subset cutover 查询路径

对实际实现同形的 `DELETE ... WHERE EXISTS (shipping_resolve_target)` 执行 `EXPLAIN FORMAT=JSON`。MySQL 的计划是：

```text
shipping_resolve_target(task_id 主键前缀) → shipping_order_finished(ix_sof_order_no)
```

- target 以 `task_id` 的主键前缀查找；
- live 表按 `ix_sof_order_no` 逐订单定位，`source` 为附加过滤；
- 优化器当前估算每个 target 对检查约 5 行；
- 这与之前无 WHERE 的全表 DELETE 完全不同，不会因为语句形态本身重演那次 30 秒 read timeout。

但 live 表没有 `(source, ecommerce_order_no)` 复合索引。因此 10,000 个 target 对在当前估算下仍可能检查约
50,000 行，而且实际锁等待、目标订单行数与 staging 写入量尚未测量。它不足以支持提高上限。

## 三、压测环境方案

### 推荐：隔离的生产同规格副本

建立仅限运维访问的独立实例，目标配置与生产一致或更弱，避免在更强机器上得出虚假结论：

| 项目 | 要求 |
|---|---|
| 计算 | 2 vCPU、约 1.7 GB RAM、同类磁盘规格 |
| Web | Gunicorn `-w 1`、默认 sync worker；禁止 `--preload` |
| 数据库 | MySQL 版本与生产一致；buffer pool 128 MB；连接池 5+5 |
| 应用 | 同一 commit、同一迁移版本、同 nginx/gunicorn timeout 配置 |
| 压测驱动 | 独立于被测实例运行，不能与被测 worker 争抢 2 个 CPU |

数据使用生产快照的受控脱敏副本：订单号、客户简称、操作人、地址等敏感文本可稳定哈希/替换；`product_code`、
成品—组件关系、等效件关系、来源、日期分布、每订单行数和数量必须保留，才能保持解析候选与数据库索引分布。
快照不得暴露到公网，不复用生产 OSS 凭据，也不得回连生产数据库。

如果暂时无法建设同规格副本，D 批停在方案阶段；不以本机、共享开发库或生产写压测替代。

## 四、场景矩阵

所有写入场景只在隔离实例运行；每个场景先跑 1 次预热，再至少跑 3 次，报告中位数与最慢一次。

| 域 | 场景 | 规模/变量 | 必须验证 |
|---|---|---|---|
| 财务导入 | 新数据、完全重复、10% 变化重导 | 1k / 10k / 50k / 100k 行 | 写入正确性、增量 resolve、耗时分段 |
| 发货导入 | 正常导入与最大允许文件边界 | 1k / 10k / 50k / 100k 行 | 解析、UPSERT、组合与内存 |
| 取消 | parsing / comparing / inserting / resolving / committing | 每种至少一档 10k+ | 终态、租约、正式表 checksum |
| 并发 | 两客户端同时启动写任务 | 导入×导入、导入×resolve | 恰一方持租约，另一方 409 + task_id |
| stale 重算 | 1k / 5k / 10k `(order_no,source)` 对 | 两来源比例接近生产 | staging、cutover、取消与读延迟 |
| 全量重算 | shipping、finance、合并全量 | 1k / 10k / 100k / 全量 | generation 构建、rename、组件守恒 |
| 确定性 | 相同输入重复三次及三个 hash seed | 全量至少一次 | 按业务主键排序后的结果 hash 一致 |

全量重算的正确性不再比较“原始组件数量 = 成品件数”。应逐订单校验：

```text
Σ 原始组件 quantity
  = Σ(非空 finished_code quantity × 该成品组件数)
  + Σ(finished_code=NULL 的 quantity)
```

对于存在销退的订单，销退匹配结果另按同一组件规则核验；不能以图表聚合总和代替逐订单校验。

## 五、采集方法与指标

### 业务正确性（硬门禁）

- 导入取消前后：`shipping_record`、`return_record`、`shipping_order_finished` 的范围 checksum 不变；
- stale 取消：正式表范围 checksum 不变，task 私有 staging/target 最终清空；
- full resolve：两来源订单覆盖完整、逐订单组件守恒 100%、三轮结果 hash 一致；
- 并发：每次仅一个 `shipping_mutation` 租约持有者；
- 任务：无假 done/假 cancelled，409 返回正在运行任务的 task_id。

### 可用性与资源

- `/health`、`/ready` 每秒探测一次；图表读请求以固定认证会话每 2 秒探测一次；
- 每 5 秒采集 worker PID/RSS、系统 available memory、`vmstat` swap-in/out、CPU/load；
- 每 5 秒采集 MySQL 连接数、锁等待、长事务、临时表与磁盘占用；
- 记录任务各阶段耗时、rows/s、取消请求到终态延迟、cutover 前后查询延迟；
- 监控连接必须 `autocommit=True`；整个门禁脚本只初始化一次应用，不能在任务运行中再次 `create_app()`。

## 六、验收阈值

以已验证生产全量基线（386.9 秒、691,990 行、health p95 <200 ms、chart-data p95 <2.5 s）为参照。

| 指标 | 通过 | 需人工复核 | 失败（硬门禁除外均可先停止调查） |
|---|---:|---:|---:|
| 正确性 / 确定性 | 0 不一致 | 不适用 | 任意不一致 |
| worker / OOM | 0 restart、0 OOM | 不适用 | 任意 restart/OOM |
| swap | 无持续 swap-in/out | 单个短暂采样，需解释 | 连续 30 秒以上换页 |
| health / ready | 0 失败；p95 ≤250 ms；max ≤3 s | p95 250–500 ms | 任意失败、p95 >500 ms 或 max >5 s |
| chart-data | 0 失败；p95 ≤3 s；max ≤5 s | p95 3–5 s | 任意失败、p95 >5 s 或 max >10 s |
| 全量耗时 | ≤480 s（生产基线 +25%） | 480–600 s | >600 s |
| 取消 | 可检查阶段 ≤5 s 进入 cancelled | 5–15 s，需分析阶段 | >15 s 或正式数据不一致 |
| stale cutover | 单事务 ≤10 s，锁等待 ≤2 s | 10–20 s 或 2–5 s | >20 s、>5 s 或读请求失败 |

这些阈值不允许用平均值掩盖峰值，也不允许为“让测试通过”而放宽数据一致性、OOM、worker 重启三条硬门禁。

## 七、resolve_stale 上限建议与前置决策

### 当前建议

保持 `MAX_STALE_RESOLVE_ORDERS=10000`。这是保守熔断，不是已验证容量；既不应提高，也没有证据支持降低。

动态上限暂不建议实现：缺少真实样本时，基于订单数或预计行数的公式只会制造看似精确的未经验证规则。

### 必须先完成的两项工作

1. **产品/后端语义设计**：定义哪些变化会使哪些订单 stale。例如成品—组件关系、等效件关系、仓库排除规则
   的变更是否应标记全部历史订单，还是只能要求运行 resolve_all。当前代码没有任何标记路径，`resolve_stale`
   实际上不会产生工作量。
2. **隔离实例实测**：用接近生产来源比例与订单行数分布的 1k、5k、10k stale 对运行完整 staging/cutover。
   同时记录实际 target 对数、live 删除行数、staging 行数、执行计划和锁等待。

若 10k 达标且计划稳定，才评估以下单独变更：

- 在 live 表增加 `(source, ecommerce_order_no)` 复合索引，以消除当前按订单号取行后再过滤 source 的额外扫描；
- 复测 10k 后，再按 20k、50k 分级推进；每一级独立门禁，不跳级；
- 只有各级通过后，才调整配置上限；动态公式仍需至少多轮真实基准支撑。

## 八、下一步

本文件不授权部署、建实例、克隆生产库、执行写压测、修改 stale 标记语义或调整环境变量。

请 Claude/用户复核后先确定：是否建设隔离同规格压测实例，以及 stale 的业务生产者应该采用“按影响范围标记”还是
“规则变更一律走 resolve_all”。确定后才能进入 D 批实施。
