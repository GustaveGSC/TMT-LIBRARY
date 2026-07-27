# 发货看板性能第 0 批：后端观测交接

## 改动范围

仅修改 `backend/routes/shipping/__init__.py`，不改 SQL、缓存、响应 JSON 或权限。

新增环境开关 `SHIPPING_CHART_PERF_LOG=true`。开启时，以下端点会写结构化 INFO 日志：

- `GET /api/shipping/chart-options`
- `POST /api/shipping/chart-data`

日志前缀固定为 `shipping_chart_perf`，字段包括：event、duration_ms、source、group_by、是否有日期范围、筛选数量、tag filter 数及 item_count。**不记录**国家/省份/产品/客户名称、订单号或用户身份；只记录数量，避免性能采样扩大数据暴露面。

错误路径同样记录 `*_error` 事件及耗时。

## 本地验证

- `pytest backend/tests -q`：通过（两项已有的 MySQL integration 测试按未配置环境预期跳过）。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。
- 新增路由测试验证：开启开关后日志有请求 shape 与 item_count，且筛选原始值不会写入日志。

## Claude 部署与采样步骤

1. 先按通常后端流程部署本提交；在生产 `.env` 临时加入 `SHIPPING_CHART_PERF_LOG=true`，reload 后观察日志无异常。
2. 采样期间只执行正常 UI 操作，每类至少 3 次：
   - 默认首次进入；
   - 财务端地域世界地图主图；
   - 世界地图切到“按系列”或“按品牌”的 tooltip 内容。
3. 从 `journalctl -u gunicorn` 提取 `shipping_chart_perf` 行，按 event/group_by/source 汇总 p50/p95、总数、连续 burst；重点验证 tooltip 是否出现“相同筛选、不同单国家 tag filter”的 N 条 `data` 记录。
4. 在采样窗口临时将 MySQL slow log 阈值调低（由运维按现有安全流程操作），从慢日志选出三类真实 SQL。对每条在**隔离/只读会话**执行 `EXPLAIN ANALYZE`，记录 actual rows、loops、耗时、使用索引和临时表/filesort：
   - chart-options 渠道/省市区 distinct；
   - 财务地域主图；
   - tooltip 系列或品牌细分。
5. 采样结束立即删除该环境开关或设为 false 并 reload，避免永久 INFO 日志噪音。

## 第 0 批的放行标准

报告必须同时包含：端点时延分位数、每次世界 tooltip 的 chart-data 请求数、三条代表 SQL 的 EXPLAIN ANALYZE、慢日志时间窗口与样本数。缺任何一项，不进入批量 tooltip 接口设计。

## 未做事项

- 未修改前端 Performance API 埋点，属 `src/` 所有权，由 Claude 单独提交。
- 未新增索引、缓存、批量接口或 SQL hint；这些均等待采样结论。
