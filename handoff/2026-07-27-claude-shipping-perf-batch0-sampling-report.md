# 发货看板性能第 0 批：生产真实采样与 EXPLAIN ANALYZE 结果

日期：2026-07-27

## 部署与采样过程

1. 审查 656069a（结构化耗时日志，opt-in，不改 SQL/响应/权限），本地 compile+全量 pytest 通过，
   合并部署。
2. **部署时发现并修复了观测功能本身的一个 bug**：`current_app.logger.info()` 在 Flask 默认配置下
   实际有效日志级别是 `WARNING`（未显式 `logging.basicConfig`），`SHIPPING_CHART_PERF_LOG=true`
   打开后日志**完全不会输出**到 journalctl。已提交一行修复（813409e）：开关生效时把 logger 提升到
   `INFO`。这不是这次诊断本身的结论，是采样过程中顺带发现的观测功能自身缺陷，已修复并部署。
3. `.env` 临时加 `SHIPPING_CHART_PERF_LOG=true`，reload 生效后对三类场景各真实调用 3 轮
   （脚本模拟真实前端请求 body，非直接查库），从 journalctl 提取全部 `shipping_chart_perf` 行。
4. 用 `before_cursor_execute` 事件捕获三类场景对应的真实 SELECT 语句+参数，在只读事务
   （`SET SESSION TRANSACTION READ ONLY`）里对每类的代表性 SQL 执行 `EXPLAIN ANALYZE`。
5. 采样结束后：`.env` 移除该开关、reload 恢复默认（无 INFO 日志噪音），清理服务器上的临时脚本。

## 结果

### 端点耗时（`shipping_chart_perf` 日志，本次生产真实采样）

| 场景 | 首次(冷) | 后续(热，命中5分钟内存缓存或索引命中) |
|---|---|---|
| chart-options（shipping源，无日期范围命中默认缓存key） | 2170.1ms | 0.0ms（第2、3次完全命中内存缓存） |
| chart-data 默认按日期（shipping源） | 1280.1ms | 552.0ms / 547.4ms |
| chart-data 财务地域世界地图（group_by=tag:3） | 35.9ms | 14.1ms / 14.0ms |
| chart-data tooltip系列细分（单国家，group_by=series） | 7.0–24.8ms（24次调用） | 稳定在7–9ms |

### EXPLAIN ANALYZE（真实生产数据，只读事务）

**1. chart-options 冷路径（非默认日期范围，绕开内存缓存）**：
`shipping_order_finished` **全表扫描**（`Table scan on shipping_order_finished`，
`actual rows=691990`），随后走 `product_finished`/`product_model`/`product_series`/
`product_category` 逐行 nested loop 关联去重活跃产品 id。**实测 803ms**，与日志层观测的
2170ms（含其余 distinct 查询、连接建立、序列化）方向一致。**这是三类查询里唯一存在真实全表扫描
的一条，确认 Codex 判断的 P1 是真实存在的、优先级应该在 P0 之后处理。**

**2. 财务地域世界地图主图（group_by=tag:3）**：走
`ix_sof_source_customer_alias(source, customer_alias)` 索引查找，`shipping_finance_customer_mapping`
只需扫 349 行，实测 **8.56ms**，不是瓶颈。

**3. tooltip 系列细分（单国家）**：同样命中 `ix_sof_source_customer_alias`，实测 **2.94ms**（不含
product_finished/model/series 逐行 join 開销，41 行也很快）。

## 重要修正：N 次 tooltip 请求的瓶颈不在单条查询成本

Codex 的 P0 判断方向是对的（N 次请求确实存在、确实会在单 worker 上排队），但**根因层面需要
修正一点**：单条 tooltip 查询本身很快（生产真实数据 7–25ms），不是"每条查询都很慢，N 条自然更
慢"。24 次真实调用（8 国 × 3 轮）总耗时都在 130–145ms 量级，均摊到每次约 5–18ms。

真正的成本来源是：**N 次独立 HTTP 请求本身的固定开销**（Flask 路由分发、鉴权中间件、JSON 序列化、
以及最关键的——**单 sync worker 期间任何一次请求都会阻塞同一进程处理其他并发用户的请求**）。也
就是说，即使把每条 tooltip SQL 优化到 0ms，只要还是 N 次独立 HTTP 往返，单 worker 排队问题依然
存在；反过来，哪怕不做批量合并，只优化 SQL 也解决不了根本问题。**这进一步支持第 2 批"收敛为一个
批量接口"的方案**——收益不是来自"让单条查询更快"，而是来自"把 N 次 HTTP 往返变成 1 次"，这与
Codex 原方案的建议一致，但请求 Codex 在设计批量接口时不要把优化重点放在 SQL 层面（SQL 已经够快），
重点应放在**用一条 SQL 一次性按 `country, breakdown_label` 分组**从而消除 N 次网络/进程调度开销。

## 对第 3 批的建议调整

- **chart-options 覆盖索引**：确认有必要，`(source, shipped_date, finished_code)` 相关的过滤在
  全表扫描后靠 `finished_code IS NOT NULL` + `NOT LIKE '110412%'` + 日期范围过滤，命中率低
  （19479 预估行里实际 0 行匹配这个特定冷日期范围，但仍需扫全表 691990 行）。建议 Codex 按原方案
  评估 `(source, shipped_date)` 或进一步窄化的索引，但要看默认日期范围（用户最常用的近期范围）下
  的真实选择性，不要只看这个特意选的冷范围。
- **财务地域/tooltip 索引**：`ix_sof_source_customer_alias` 已经工作得很好（8ms/3ms 级别），
  **不需要为这两类查询新增索引**，第 3 批可以跳过这部分。
- **财务地图冗余 summary 扫描**：本次未单独验证这一项（不在三类代表 payload 内），维持 Codex 原
  方案，留给后续批次验证。

## 结论：是否放行进入第 2 批设计

**放行**。四项放行标准（端点分位数、tooltip 请求数、三条代表 SQL 的 EXPLAIN ANALYZE、采样窗口
样本数）均已满足；采样窗口 2026-07-27 11:35 前后约1分钟，样本数：options 3次、默认主图3次、
财务地图3次、tooltip 24次（8国×3轮）。

请 Codex 基于上述"批量接口收益来自减少 HTTP 往返次数、而非单条 SQL 优化"的修正结论设计第 2 批
批量地图细分接口。
