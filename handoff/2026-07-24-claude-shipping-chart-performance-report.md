# 发货数据图表加载缓慢 · 诊断报告

日期：2026-07-24
性质：只读诊断（代码走查 + 生产环境慢查询日志/资源实测），无代码变更。请Codex审核后再决定修复方案和实施顺序。

## 结论先行

用户反馈的"发货图表加载非常慢"，诊断后确认至少有**一个已经在生产环境反复发生的具体慢查询**（非推测），加上**服务器内存/单worker架构层面的放大效应**。优先级从高到低：

1. **`_get_shipping_agg`（售后模块，非发货模块自己的代码）查询 `shipping_order_finished` 完全没有 `source` 过滤、没有 `USE INDEX` hint** —— 生产慢查询日志实测 7-10 秒，最近一次发生在昨天（2026-07-23）。
2. **生产 MySQL InnoDB buffer pool 只有 128MB，但 `shipping_order_finished`+`shipping_record` 两张表数据+索引合计超过750MB** —— 结构性内存不足，任何查询都可能因为缓存未命中而走磁盘IO。
3. **单Gunicorn worker导致所有请求（含慢查询、CPU密集的Excel导入解析）完全串行**，第1、2点的慢查询会直接拖慢同时段所有用户的所有请求，包括发货图表本身的请求——这能解释"非常慢"这种偶发、量级远超"索引没命中几百毫秒"的体感。
4. **`/api/category/tree` 存在经典N+1查询**，且被发货看板每次改日期筛选都无谓重新请求一遍（内容与日期无关）。

## 一、生产环境实测数据（本次直接查库/查日志获得，非推测）

### 数据规模

```
shipping_order_finished：660,720 行，data 120.1MB + index 168.5MB（索引比数据本身还大，9个索引）
shipping_record：739,032 行，data 265.8MB + index 198.9MB
return_record：18,451 行，data 4.5MB + index 7.7MB
```

### 服务器资源

```
总内存 1.6GB，已用 835MB，可用 839MB，swap已用 290MB（有实际换出，不是理论风险）
innodb_buffer_pool_size = 128MB
```

`shipping_order_finished` 一张表的 data+index 就有 288.6MB，`shipping_record` 是 464.7MB，两张表合计 753MB+，**InnoDB buffer pool（128MB）连一张表的索引都放不下**，意味着大量查询即使命中了正确的索引，也需要频繁从磁盘读取索引/数据页，而不是内存命中。

### 慢查询日志实锤：`_get_shipping_agg` 无索引hint、无source过滤

`backend/database/repository/aftersale/__init__.py:2418-2430`（`_get_shipping_agg`，用于售后仪表盘"销售占比"的分母计算）：

```python
q = db.session.query(
    label_expr.label('label'),
    func.sum(sof.actual_quantity).label('qty'),
).filter(sof.finished_code.isnot(None))   # ← 没有 sof.source == ... 过滤

if need_product_join:
    q = (q
         .join(ProductFinished, sof.finished_code == ProductFinished.code)
         .join(ProductModel, ProductFinished.model_id == ProductModel.id)
         .join(ProductSeries, ProductModel.series_id == ProductSeries.id)
         .join(ProductCategory, ProductSeries.category_id == ProductCategory.id))
```

整个函数（2370-2454行左右）**全程没有一处 `with_hint`/`USE INDEX`**，也没有过滤 `source`。对照发货模块自己的 `_apply_filters`（`backend/database/repository/shipping/__init__.py:1017-1131`）——那边对同一张表的查询是有完整hint覆盖的（已核实无遗漏），**这个漏洞出在售后模块里复制的另一套对 `shipping_order_finished` 的查询逻辑，两边没有共用同一个查询构建函数**。

生产慢查询日志实测（最近一次）：

```
Time: 2026-07-23T01:44:09
Query_time: 7.494392  Rows_examined: 1,729,183
SELECT coalesce(product_category.name, '未知') AS label, sum(shipping_order_finished.actual_quantity) AS qty 
FROM shipping_order_finished 
INNER JOIN product_finished ON shipping_order_finished.finished_code = product_finished.code 
INNER JOIN product_model ON product_finished.model_id = product_model.id 
INNER JOIN product_series ON product_model.series_id = product_series.id 
INNER JOIN product_category ON product_series.category_id = product_category.id 
WHERE shipping_order_finished.finished_code IS NOT NULL 
  AND shipping_order_finished.shipped_date >= '2024-01-01' AND shipping_order_finished.shipped_date <= '2026-07-23' 
GROUP BY coalesce(product_category.name, '未知');
```

这个模式在慢查询日志里反复出现（4月到7月都有记录，最慢一次10.2秒/扫69万行，多次3-5秒/扫百万级行），**不是偶发一次，是每次触发都慢**。

**需要向Codex确认的业务问题**：这个查询完全没有 `source` 过滤，意味着同时统计了 `source='shipping'` 和 `source='finance'` 两个数据源的发货量作为售后"销售占比"分母——这是否是有意为之（两个来源的量本来就该合并统计），还是遗漏了过滤条件？之前会话确认过的业务口径"分母=净发货量(actual_quantity)"没有明确说是否要分source，需要Codex确认这是不是连带的正确性问题，不只是性能问题。

### 单worker放大效应（已有文档记录，本次用生产数据佐证）

`.claude/claude.md` 已记录生产是 `-w 1` 单sync worker。这意味着：上面那条7-10秒的慢查询执行期间，**这台服务器上所有其他HTTP请求（包括发货图表本身的请求）都在排队等待**，不存在真正并发处理。如果用户打开发货图表的同时，售后仪表盘的这条慢查询恰好在跑（或者恰好有人在导入Excel，CPU密集解析同样占用这唯一的worker），发货图表的请求会被迫等待，表现为"非常慢"——且是间歇性的，取决于当时服务器在处理什么。

## 二、代码结构性问题（Explore agent只读审查，已交叉验证）

### `/api/category/tree` 存在N+1查询，且被无谓重复请求

- `backend/database/repository/product/category.py:11-13`：`CategoryRepository.get_all_tree()` 只是 `ProductCategory.query.order_by(...).all()`，没有 `joinedload`/`selectinload`。
- `backend/database/models/product/category.py:24,56`：`to_dict(with_children=True)` 对每个 category 触发一次 `self.series` 惰性查询，每个 series 又触发一次 `self.models` 惰性查询——标准N+1，1次分类查询+N次系列查询+M次型号查询。
- `ShippingDashboard.vue:2761`：`watch(() => filters.value.dateRange, () => loadOptions(), {deep:true})`，`loadOptions()`内部会重新请求 `/api/category/tree`（`:1591`），但分类树内容和日期筛选完全无关，每次用户改日期都会触发一次完整的N+1查询链。

在单worker场景下，这条N+1（可能几十次SQL往返）会完整占用worker的处理时间，直接拖慢它前面排队的所有请求。

### `get_chart_data` 的 `grouped_q` 与 `summary_q` 重复执行同一套过滤/JOIN逻辑两遍

`backend/database/repository/shipping/__init__.py:1210-1234`：分组明细和汇总统计是两条独立SQL，各自走一遍完整的 `_apply_filters`（含最多4-5表JOIN）。有优化空间（合并成一次查询+`WITH ROLLUP`，或应用层从明细汇总），但相对第一部分的慢查询bug，这个是叠加因素，不是主因。

### 已排除的怀疑方向（确认无问题，不用再查）

- 发货模块自己的 `get_chart_data`/`get_chart_options`/`_apply_filters` 对 `shipping_order_finished` 的索引hint覆盖**无遗漏**，所有实际会被触发的查询路径都有对应hint且hint名字与真实索引一致。
- `get_cross_filter_options`（CLAUDE.md提到"6条JOIN查询"那个）**属于售后模块，不属于发货模块**，与"发货图表慢"无关，之前的怀疑方向搞错了归属，可以从排查清单里划掉。
- `ShippingDashboard.vue` 的 `onMounted` 里 `loadOptions()`→`loadChartData()` 串行**是功能性必需**（默认`groupBy='product'`依赖`categoryTree`/`activeProductIds`推导层级），不是可以无脑改并行的bug。
- ECharts渲染本身：图表实例有复用保护（`if (chartInst) return`），未发现"每次重建实例"反模式。

## 三、建议的修复方向（供Codex评估具体实施方式，不是最终方案）

1. **P0**：`_get_shipping_agg` 补 `USE INDEX` hint（参照发货模块 `_apply_filters` 的hint选择逻辑），并确认`source`过滤是否应该补上（需先确认业务口径）。这是目前唯一有生产日志实锤、且直接影响"图表慢"体感的一条。
2. **P1**：`/api/category/tree` 消除N+1（`selectinload(ProductCategory.series).selectinload(ProductSeries.models)`），前端把这个请求从"随日期筛选联动"改成"只在挂载时拉一次/做模块级缓存"。
3. **P2**：`grouped_q`/`summary_q` 合并优化，减少重复JOIN开销。
4. **架构层面（不在这批解决，但建议记录）**：InnoDB buffer pool 128MB相对于当前数据量已经偏小，且服务器已经在用swap，这是超出"改几个查询"范畴的容量规划问题，建议单独评估是否需要调整MySQL配置或升级服务器规格，不应该用"改代码"的方式掩盖"资源不够"的事实。

## 四、给Codex的具体问题

1. `_get_shipping_agg` 不过滤`source`是否是业务本意？如果是bug需要一并修正统计口径。
2. 发货模块和售后模块各自维护了一套几乎相同的"按product/category/series/model分组统计`shipping_order_finished`"查询逻辑（`_apply_filters` vs `_get_shipping_agg`），是否值得抽成共享的查询构建函数，避免这次的hint遗漏以后在其他调用点重演？
3. InnoDB buffer pool调整是否在你的职责范围内评估（涉及生产MySQL配置，不是纯代码修改）。
