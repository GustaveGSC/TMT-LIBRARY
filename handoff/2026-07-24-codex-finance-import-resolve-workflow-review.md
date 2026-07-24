# Codex 独立复核：财务导入、客户匹配与全局重算工作流

日期：2026-07-24  
性质：只读复核与方案设计，无运行时代码改动。

## 结论

Claude 报告的两个判断成立：

1. 客户映射的 `status/country/brand` 在图表请求中实时 JOIN；
2. 单纯修改已有客户映射后，不需要重新计算成品组合。

但报告遗漏了一条关键耦合，因此“完全不需要刷新全局数据”的结论不完整：

> 财务重导会 UPSERT 更新既有 `shipping_record.customer_alias`，但导入后的自动
> resolve 只处理尚无 `shipping_order_finished` 的新订单。既有订单派生表中的
> `customer_alias` 仍是旧值或空值，图表实时 JOIN 的又是派生表字段，因此只有
> `resolve-all` 后才能匹配到最新客户映射。

这能解释历史客户简称回填后，必须全量刷新的真实现象。

## 一、精确的数据链

### 新订单

```text
财务导入
→ 新增 shipping_record(customer_alias)
→ get_new_order_nos_by_source() 命中新订单
→ 自动 _resolve_orders()
→ shipping_order_finished.customer_alias 正确
→ 保存客户映射后图表实时 JOIN，立即生效
```

该路径不需要额外 `resolve-all`。

### 既有订单重导

```text
财务重导
→ ON DUPLICATE KEY UPDATE shipping_record.customer_alias
→ 既有行不会更新 batch_id
→ get_new_order_nos_by_source() 不包含这些订单
→ shipping_order_finished.customer_alias 没有同步
→ 客户映射 JOIN 仍使用旧/空 alias
→ resolve-all 后才恢复
```

`bulk_insert_shipping()` 的 UPSERT 确实更新 `customer_alias`，但
`get_new_order_nos_by_source()` 先按当前 `batch_id` 取订单，再排除已有派生结果；
因此它本质上不是“本批受影响订单”，只是“本批新增且未生成派生结果的订单”。

### 映射配置本身

`ShippingFinanceCustomerMapping` 保存后，图表按
`shipping_order_finished.customer_alias` 实时 JOIN 最新映射。只要派生表中的 alias
已经正确，修改四态、国家或品牌都立即生效，无需重算。

## 二、当前流程应如何调整

建议用户侧流程改为：

```text
导入财务数据
→ 系统自动增量更新本批受影响订单的派生结果
→ 维护“客户匹配”
→ 保存后立即生效
```

“刷新全局数据”不应继续作为日常必做步骤。建议：

- “外贸客户匹配”改名为“客户匹配”；
- 配置页提示“保存后立即生效，无需重建成品组合”；
- “刷新全局数据”改名为“重建全部成品组合”；
- 移到“数据健康/高级操作”，说明只在产品组合规则、通用件规则发生系统性变化，
  或修复历史派生数据时使用。

## 三、导入慢与失败的完整原因

### 1. 不必要的 UPSERT

服务层虽然计算了 `new_shipping/skipped_shipping`，实际却把完整的
`shipping_rows` 传给 `bulk_insert_shipping()`。因此历史文件重导时，完全未变化的
既有行也会执行 UPDATE，放大：

- 行锁和索引写入；
- redo/undo 与磁盘 I/O；
- 100 行 executemany 超过 30 秒 `read_timeout` 的概率；
- 后续“哪些订单真的变化”无法判断的问题。

生产超时发生在 UPSERT 阶段，不能简单归因于 resolve 期间连接空闲。

### 2. 成品组合算法

`_resolve_orders()` 对每个订单遍历全部约 404 个成品组合，复杂度接近
`O(订单数 × 成品数 × 组合物料数)`。25 万订单全量重算会产生上亿次 Python
字典访问和条件判断。

可以建立“物料编码 → 可能包含该物料的成品组合”倒排索引。每个订单先按实际拥有的
物料取候选集合，再按现有全局排序执行原贪心逻辑。只要最终候选仍保持现有
`sorted_finished` 顺序，精确码优先、等效码兜底和复杂组合优先的业务语义可以保持。
实施前必须用现有结果快照做逐订单等价对比，不能只比较总数。

### 3. 单 sync worker + SSE

任务在线程中运行，但进度接口是长时间 SSE。生产只有一个 sync worker，SSE 请求会长期
占住该 worker；其他 HTTP 请求无法由同一个 worker 接收。CPU 密集线程还会进一步争用
GIL 和 CPU。

因此“系统卡住”至少包含两层：

- SSE 长连接占用唯一请求 worker；
- 后台匹配线程持续占用 CPU。

仅优化算法不能彻底解决可用性。短期应让长任务前端使用持久化状态短轮询，或让 SSE
快速断开后回查；中期再评估独立任务进程。不能在 1.675GB 主机上未经容量验证直接增加
多个 Gunicorn worker。

## 四、推荐实施顺序

### 第 A 批：低风险流程纠正

1. 保存客户映射后立即失效 chart-options 缓存；
2. 前端改名“客户匹配”，增加“保存后立即生效”提示；
3. 将“刷新全局数据”改为“重建全部成品组合（高级）”并移出日常流程；
4. 补测试证明单纯修改映射不调用 resolve，下一次 chart-data 使用新映射。

### 第 B 批：导入增量正确性

1. 在写入前批量读取既有行必要字段，区分：
   - 新增行；
   - 实际发生变化的行；
   - 完全相同的行；
2. 只 UPSERT 新增/变化行；
3. 收集受影响订单：
   - 物料编码、数量、销退变化 → 增量 `_resolve_orders()`；
   - 只有客户简称/地区等元数据变化 → 可直接安全同步派生表元数据，或统一增量 resolve；
4. 新增、变化的销退记录也必须把对应既有订单加入受影响集合；
5. 自动完成本批增量派生更新，用户不再手工全量重算。

第一版可统一增量 resolve 所有“实际变化订单”，优先保证正确性；后续再把纯元数据变化优化为
直接 UPDATE。

### 第 C 批：匹配算法候选剪枝

1. 建立物料到成品组合的倒排索引；
2. 保持原 `sorted_finished` 相对顺序和 `_avail/_consume` 实现；
3. 用真实脱敏样本比较优化前后每个订单的：
   - finished_code；
   - quantity/return_quantity/actual_quantity；
   - 未匹配剩余物料；
4. 结果逐项一致后才替换；
5. 记录 1千/1万/全量订单耗时与峰值 RSS。

### 第 D 批：长任务传输与执行模型

短期把导入/全量重算进度改为 1–2 秒短轮询持久化任务状态，避免 SSE 独占唯一 sync
worker。中期若任务量继续增长，再评估独立 task worker；不要用增加 Gunicorn worker
代替任务队列。

## 五、事务策略

不建议直接把当前整单事务改成“每 100 行 commit”：

- 会产生用户无法判断的部分导入；
- raw 表与派生表可能处于不同版本；
- 失败后重试和取消语义更复杂。

优先通过“跳过未变化行 + 只增量重算受影响订单”缩短事务。若仍超过可靠时限，再设计：

- staging 表；
- 批次状态；
- 最终一次原子切换/合并；
- 可恢复的派生阶段。

在没有 staging/批次可见性机制前，不应牺牲现有整单回滚保证。

## 六、需要补的测试

- 重导只补 `customer_alias` 的既有订单，派生表 alias 自动更新；
- 既有发货数量变化，派生数量自动重算；
- 新增或修改销退，`return_quantity/actual_quantity` 自动重算；
- 完全相同文件重导不执行事实表 UPDATE、不触发 resolve；
- 修改映射状态/国家/品牌后不调用 resolve，chart-data 立即变化；
- 候选剪枝前后逐订单结果完全一致；
- 长任务轮询期间普通 `/health` 和业务请求仍可响应。

## 七、对原诊断四个问题的答复

1. **存在遗漏耦合**：既有订单 UPSERT 后派生 alias 不同步。
2. **算法值得单独优化**：但先修增量正确性和不必要 UPSERT，再做严格等价的候选剪枝。
3. **不能直接拆分提交**：超时更可能由无差别 UPSERT、锁等待和 I/O 放大；保留整单原子性，
   先减少写入和重算范围。
4. **缓存失效可直接修**：属于低风险第 A 批。
