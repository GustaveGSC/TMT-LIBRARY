# 发货看板性能诊断与优化方案（只读）

## 范围

分析 `ShippingDashboard.vue`、`/api/shipping/chart-options`、`/api/shipping/chart-data` 的：首次进入、日期/维度切换、财务端世界地图额外 tooltip 内容三条链路。本文不包含代码或部署变更。

## 已确认的根因

### P0：世界地图额外 tooltip 是 N 次完整聚合请求

`fetchTooltipBreakdown()` 会取 `lastMapItems` 中每个有数据国家，并以 `Promise.all` 对每个国家调用一次 `POST /api/shipping/chart-data`。系列/品牌模式下，国家数为 N，就有 N 条完整的图表聚合请求；每条都重新执行筛选、财务客户映射 JOIN、分组，品牌标签场景还会执行额外汇总。

浏览器“并发”不会提高本服务器的吞吐：Gunicorn 是单 sync worker，数据库连接池也有限，这些请求会在服务端排队。因此国家越多，tooltip 内容越晚完整出现，也会拖慢同一时段的其他请求。`renderChart()` 在任何地图重渲后都会触发该流程；数据指标切换虽然只是前端字段切换，也可能造成重复拉取。

这不是推测，代码路径直接可见。现有单个国家请求失败会静默吞掉，也缺少对 N、总时长和失败数的观测。

### P1：首次进入与日期切换存在重复的宽查询

- 首次进入按 `loadOptions()` → `loadChartData()` 串行执行。`chart-options` 在缓存冷启动时需要渠道 distinct、省市区 distinct、活跃产品 JOIN distinct、日期边界等多类查询；随后再执行主图聚合。
- 日期范围 `watch` 每次变化立即调用 `loadOptions()`，没有防抖/请求取消。用户连续调整日期时会产生过期 options 请求；主图仍由“查询”动作加载，两个请求在单 worker 上会相互排队。
- 后端 options 虽有 5 分钟内存缓存，但缓存 key 含完整日期范围；不同日期组合全部冷缓存。频道/省市区 distinct 结果需要读取多个字段，现有 `(source, shipped_date)` 索引不是覆盖索引。

### P2：世界地图首次切换还有独立的前端资源成本

`world.json` 约 1.01 MB，首次进入世界地图时还会同时读取 `china-map.json`（约 0.58 MB）、合并 GeoJSON feature 并注册地图。后续已注册地图会复用，因此这是“首次切换”成本，不是每次 tooltip 的根因。

### 可单独消除的一次主图扫描

财务端“地域/品牌”人工映射维度是一对一的 customer_alias mapping；按地域/品牌分组时不会发生产品标签多对多 fan-out。现有 `get_chart_data()` 将这类映射维度和普通 tag 一样额外执行一次 summary 聚合查询。可在测试证明“分组完整覆盖过滤集”后复用 grouped rows 汇总，省去一次主表扫描。普通产品标签维度仍不能这样改。

## 建议实施顺序

### 第 0 批：先量化，不改口径

1. 在前端对 options、主图、tooltip breakdown 分别记录 Performance API 时长、请求参数 hash、国家数和是否命中缓存；只记录性能元数据，不记录业务明细。
2. 后端为 chart-data/options 记录耗时、`source/group_by/trade_type`、响应 item 数，并通过慢查询日志保留 SQL。
3. 用生产实际三类 payload 执行 `EXPLAIN ANALYZE`：默认首次图、财务地域世界地图、tooltip 系列/品牌。先确认 rows examined、索引、JOIN 顺序，再决定是否增加索引。

### 第 1 批：低风险前端去重与资源复用

1. 日期 options 加 250–400ms 防抖、参数去重、最新请求序号保护；过期响应不得覆盖新状态。
2. 在浏览器端按 `(source,date_start,date_end)` 缓存 options；导入/重算成功时显式失效。保留后端 5 分钟缓存作为第二层。
3. 对世界地图 GeoJSON 用 idle/preload 预热（用户选择“地域”分析维度时），不阻塞主图。
4. tooltip breakdown 做 key 化缓存；key 包含 source、筛选、地域维度、tooltip 模式。切换显示指标时复用同一份 quantity/return/actual 原始结果，前端再取对应字段；地图平移、面板开关、纯 ECharts 重绘绝不重新请求。

### 第 2 批：把 N 请求收敛为一个批量接口（最高收益）

新增一个后端批量 breakdown 接口，接收主图相同筛选、地域维度及 `breakdown_group_by=series|tag:<brand_id>`，一次 SQL 按：

`country, breakdown label[, name]`

分组并返回所有国家的三种指标。前端按 country regroup 后直接填 tooltip/详情面板。财务端地域/品牌必须继续使用人工 mapping 文本语义；发货端继续使用标签 id 语义。不能在后端循环逐国家查询，也不能只用“限制 Promise 并发”代替批量查询。

接口应有单独的 API 契约、真实 Cookie 权限测试、请求数断言，以及 10/30/实际国家数下的等价性测试。原来的逐国请求可在联调期保留为受 feature flag 控制的回退路径，确认结果一致后删除。

### 第 3 批：按 EXPLAIN 决定数据库优化

- 若 options 的 distinct 查询存在大量回表，评估两条专用覆盖索引：
  `(source, shipped_date, channel_name, channel_code, channel_org_name)` 与
  `(source, shipped_date, province, city, district)`。
- 索引会扩大写入成本和磁盘占用；`shipping_order_finished` 的 live/next 代际表必须同步迁移，不能先加后补。
- 若主图是 mapping 查询慢，先评估 `(source, customer_alias)` 现有索引与日期范围组合的真实选择性；不得盲目新增多个宽索引。
- 优先消除财务 mapping 地图的冗余 summary 扫描；不改变普通 tag 多对多的既有统计口径。

## 不建议的做法

- 不做“所有 chart-data 结果无限缓存”：筛选组合基数高，单 worker 内存紧张，且导入/重算后失效边界复杂。
- 不只降低 Promise 并发：可减轻瞬时压力，却仍是 N 次全量聚合，用户总等待不会根治。
- 不先加索引再测：现有表接近 70 万解析行，宽索引和代际表会带来显著 DDL/磁盘成本。

## 预期验收

- 非默认世界地图 tooltip 请求数：从“有数据国家数 N”降为 **1**。
- 指标切换/地图重绘：breakdown 请求数为 **0**（命中前端缓存）。
- 连续日期调整：只提交最终稳定参数的 options 请求；旧响应不覆盖新选项。
- 首次世界地图的 GeoJSON 加载与数据库 tooltip 耗时分别可观测，不再混为“地图慢”。
