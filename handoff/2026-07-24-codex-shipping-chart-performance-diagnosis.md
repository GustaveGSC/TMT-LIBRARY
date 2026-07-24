# 发货图表缓慢：Codex 独立诊断与优化顺序

日期：2026-07-24  
性质：只读诊断，无运行时代码变更、无需部署

## 1. 结论

Claude 提供的生产慢查询证据可信，但“发货图表慢”实际由三层问题叠加：

1. **售后图表跨域扫描发货聚合表**：`_get_shipping_agg()` 没有 `source`、操作人过滤和索引
   hint，单条查询在生产反复耗时 7–10 秒。
2. **一次售后图表请求可能重复执行该慢查询**：默认原因/原因分类维度下，发货总量分母和整体参考线
   分母在默认条件下是同一条查询，却执行两次；单次请求可能因此仅分母就占用约 14–20 秒。
3. **发货看板自身也有固定额外成本**：分类树是 N+1，且随日期变化重复请求；`chart-data` 的分组和
   summary 对同一套过滤执行两遍。

服务器小内存和单 worker 会放大上述问题，但当前首先应修复确定的 SQL 和重复执行，不能先靠扩容或
调 buffer pool 掩盖查询缺陷。

## 2. 请求链路

### 发货看板自身

首次打开：

```text
GET /api/shipping/chart-options
GET /api/category/tree
POST /api/shipping/chart-data
```

其中：

- `chart-options` 有 5 分钟缓存，但冷缓存仍会访问发货聚合表和产品维度；
- `category/tree` 当前是 1 次分类查询 + 每个分类 1 次系列查询 + 每个系列 1 次型号查询；
- `chart-data` 对 grouped rows 和 summary 分别执行一次完整过滤/JOIN。

### 售后看板跨域读取

售后图表计算“售后件数 / 同期净发货量”时调用：

```text
AftersaleRepository.get_chart_data()
  ├─ 售后工单聚合
  ├─ _get_shipping_agg(...)          # 每项/每组的发货分母
  └─ _get_shipping_agg(total_only)   # overall reference
```

它访问的仍是 `shipping_order_finished`。在单 worker 下，售后请求运行期间发货看板请求也会排队，因此
用户感受到的是“发货图表偶发非常慢”，即使慢 SQL 的调用入口来自售后模块。

## 3. 已确认的 SQL 问题

### 3.1 缺少 source 过滤不是单纯性能问题

当前 `_get_shipping_agg()`：

- 同时统计 `source='shipping'` 和 `source='finance'`；
- 没有排除 `type='aftersale'` 的操作人；
- 售后前端没有 source 选择器。

从现有数据流判断，售后分母应采用发货端口径：

- 售后待处理工单来自 `shipping_record.operator` 命中售后操作人分类的记录；
- 财务导入明确跳过 `部门名称='售后组'`；
- 财务导入生成的记录没有与售后队列对应的操作人语义；
- 发货看板 `source='shipping'` 本身会排除售后操作人。

因此当前分母将两个来源相加，并把售后操作人的发货行纳入分母，与售后工单分子的来源不对称。
除非业务明确决定使用财务口径，否则应统一为：

```python
sof.source == 'shipping'
AND (sof.operator IS NULL OR sof.operator NOT IN (aftersale operators))
```

这也是本报告的推荐业务结论。

同类问题还存在于产品详情售后月度数据 `get_series_monthly_by_model_id()`：它排除了售后操作人，但没有
过滤 `source`，会把财务和发货来源相加。应与 `_get_shipping_agg()` 同批统一口径。

### 3.2 缺少索引 hint

`_get_shipping_agg()` 全部路径都没有 `with_hint()`。按项目现有索引纪律：

- 有日期范围：`USE INDEX (ix_sof_source_date)`；
- 无日期、按产品范围：`USE INDEX (ix_sof_source_finished_code)`。

增加 hint 的前提是同时增加 `source='shipping'`；否则 `source_*` 复合索引无法正确发挥作用。

对于跨越两年半、覆盖绝大多数 shipping 行的范围，强制索引仍可能读取大量表页，不能期望从
7–10 秒直接变成几十毫秒。部署前应对修复后的 SQL 做 `EXPLAIN ANALYZE`，记录：

- access type；
- chosen index；
- rows examined；
- actual time；
- 临时表/filesort。

### 3.3 同一个慢分母会执行两遍

`get_chart_data()` 在 `group_by in ('reason', 'reason_category')` 时先执行：

```python
total_shipped = _get_shipping_agg(..., total_only=True)
```

随后又为整体参考线执行：

```python
overall_ship = _get_shipping_agg(..., total_only=True)
```

默认 `exclude_no_sales_series=False` 时，两次参数和口径等价。生产日志中的一条 7–10 秒扫描可能在一次
页面请求内出现两遍。

建议：

- 默认模式直接复用 `total_shipped`；
- `exclude_no_sales_series=True` 时若口径确实不同，再单独查询；
- product/channel/province 维度可从 grouped shipping aggregate 同时得到总量，避免再做一次全表扫描；
- 增加 SQL 计数测试，确保默认原因维度只查询一次发货分母。

## 4. 发货看板自身的问题

### 4.1 分类树确有 N+1，但不能直接套 selectinload

`ProductCategory.series` 和 `ProductSeries.models` 都是 `lazy='dynamic'`。`to_dict(with_children=True)`
会对每个父对象单独执行 `.order_by()` 查询，形成 N+1。

Claude 建议的 `selectinload(ProductCategory.series).selectinload(ProductSeries.models)` 不能直接用于
dynamic relationship；dynamic 关系不支持常规集合 eager population。

安全方案二选一：

1. 保持模型关系不变，仓储分别批量查询 categories/series/models，按外键在 Python 组树；
2. 评估所有调用方后，把关系从 dynamic 改为可 eager-load 的 `selectin`，同时替换现有
   `self.series.order_by(...)` 调用。

建议采用方案 1，改动面更小，并补“固定 3 条 SQL”测试。

### 4.2 分类树被日期 watcher 重复加载

`ShippingDashboard.loadOptions()` 把：

- 日期相关的 `/api/shipping/chart-options`
- 日期无关的 `/api/category/tree`

绑在同一个 Promise.all 中。日期变化、来源变化和初始化都可能重复拉分类树；初始化从本地偏好恢复
日期时，还可能触发 watcher 与显式 `loadOptions()` 重叠。

建议 Claude 拆成：

- `loadCategoryTreeOnce()`：共享 Promise + 产品分类变更后失效；
- `loadChartOptions()`：随 source/date 变化；
- 初始化时抑制 watch，完成恢复后只发一次 options 请求。

### 4.3 grouped 和 summary 重复过滤/JOIN

发货 `get_chart_data()` 当前执行两条 SQL：

- grouped aggregation；
- summary aggregation。

普通互斥维度（日期、产品、渠道、省市区）可用窗口聚合或从 grouped rows 求和，减少一次扫描。
标签多对多维度可能存在重复计数语义，不能直接统一套用应用层求和；应先为各 group_by 建口径测试，
再逐维度优化。

该项是 P2，不应阻塞前两项修复。

## 5. 服务器资源判断

生产数据表和索引总量远大于 128MB buffer pool，说明缓存命中率可能不足；但“swap 已占用 290MB”
本身不能证明当前持续发生换页。Linux 可能长期保留历史换出页。

调整 MySQL 前还需要采集：

- `vmstat 1` 的 `si/so`；
- 磁盘 await/util；
- `Innodb_buffer_pool_reads` 与 `Innodb_buffer_pool_read_requests`；
- `Innodb_buffer_pool_pages_free/dirty`；
- mysqld RSS 与系统 available memory；
- gunicorn 实际 worker class、threads 和进程 RSS。

在 1.675GB 主机上直接把 buffer pool 提到 512MB 有 OOM 风险。建议顺序：

1. 修 SQL、去重复查询；
2. 观察一周慢日志和 buffer pool miss；
3. 若仍受 IO 限制，从 128MB 小步提高到 256MB，并设置回滚门槛；
4. 若业务量继续增长，升级内存比继续堆复合索引更可靠。

### 单 worker 的精确说明

需要核实 systemd 中是否真的为默认 sync worker、是否设置 `--threads`。仅知道 `-w 1` 不能推出完全
没有请求并发：

- sync 单 worker：一个慢 SQL 会阻塞全部 HTTP；SSE 长连接也会占用 worker；
- gthread/async：仍会争用连接、CPU和内存，但不会严格串行。

项目文档写的是单 sync worker，因此当前应按最坏情况处理；部署验证时必须记录实际命令行和
worker class，避免基于过期文档做容量结论。

## 6. 不建议立即做的事

- 不要先抽一个“发货/售后通用万能查询构建器”。两个模块的过滤口径不同，过早共用容易再次引入口径
  错误。先抽小的明确 helper：source/operator 基础条件和 index hint 选择。
- 不要用 `time.sleep(0)` 代替 SQL 和任务并发治理。
- 不要直接增加新索引。现有 `shipping_order_finished` 已有 9 个索引、索引体积超过数据体积；先用
  `EXPLAIN ANALYZE` 证明缺口。
- 不要仅靠 5 分钟结果缓存掩盖慢查询；缓存失效目前仍不完整。

## 7. 推荐实施顺序

### 性能第 1 批：售后发货分母正确性与慢查询

Codex：

1. `_get_shipping_agg()` 固定 `source='shipping'`；
2. 排除售后操作人；
3. 根据日期/产品条件选择现有 hint；
4. 默认原因维度复用分母，禁止重复扫描；
5. `get_series_monthly_by_model_id()` 同步 source 口径和 hint；
6. 补 SQL 编译断言、查询次数和统计口径测试。

该批是后端正确性+性能修复，应独立提交，不与 XSS、任务租约混合。

### 性能第 2 批：分类树固定查询数

Codex 用三次批量查询组树并补查询数量测试；Claude 随后拆前端请求和共享 Promise。

### 性能第 3 批：发货 chart-data 双查询

按 group_by 分批合并 grouped/summary，先覆盖普通单值维度，再单独处理标签多对多。

### 性能第 4 批：容量调整

由 Claude 只读采集生产指标，Codex评估参数；实际配置修改仍由 Claude 部署并准备回滚。

## 8. 与当前已授权批次的关系

分享页 XSS、仓库越权和任务租约仍然有效，但本次性能修复涉及售后仓储，应单独提交。建议顺序：

1. 分享页 XSS；
2. 仓库越权（极小修复）；
3. 售后发货分母慢查询；
4. 任务租约（涉及迁移和并发协议）；
5. 分类树；
6. 其余性能优化。

本报告没有修改上述功能代码。

