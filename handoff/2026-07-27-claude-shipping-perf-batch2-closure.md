# 发货看板性能第 2 批：财务世界地图批量接口已上线

日期：2026-07-27

## 结论

Codex 的批量地图细分接口（20e4e13，`POST /api/shipping/map-breakdown`，仅财务端）已通过审查、
本地测试、前端联调、生产等价性验证和 8 国样本门禁，前后端均已部署上线。

## 后端

审查 `backend/database/repository/shipping/__init__.py` 新增的 `get_finance_map_breakdown()`：
严格校验 `source=finance`、`country_category_id` 必须是启用的"地域"分类、`countries` 1–100 个、
`breakdown_group_by` 限定 `series` 或启用的"品牌"标签维度；一条 `GROUP BY country, label` 聚合，
复用现有 `ix_sof_source_customer_alias`/`ix_sof_source_date` 索引 hint，未新增索引或迁移。
路由已正确加入 `_VIEW_POST` 白名单（吸取了 d926dc3 那次"POST 默认按编辑权限拦截"的教训）。

本地 `pytest backend/tests -q` 全绿（含新增两项：品牌/系列模式的三国 fixture 等价性断言、SQL
监听断言两国不增加主聚合查询次数）、`compileall` 通过，合并部署（三个文件 MD5 核对、
`systemctl reload`，master PID 未变，`/health`/`/ready` 正常）。

## 前端

`fetchTooltipBreakdown()`（`src/views/shippingViews/ShippingDashboard.vue`）财务端改调新批量接口，
一次拿全部国家细分数据；发货端产品标签多对多语义与财务人工映射不同，按设计保留原逐国请求路径。

顺带解决了 Codex 设计文档里提到的"指标切换/纯地图重绘不应重新请求"：把 `tooltipBreakdown` 从
`ref` 改成基于原始三指标数据（`quantity`/`return_quantity`/`actual_quantity`）的 `computed`，
用筛选条件+国家集合+tooltip模式的指纹判断是否需要重新拉取——之前 `renderChart()` 每次都会在地图
分支无条件调用 `fetchTooltipBreakdown()`，现在切换显示指标只是本地重算，不再触发任何网络请求
（财务端和发货端都受益）。

本地 `npm run build:web` 编译通过，无 TS/编译错误。

## 生产验证（真实 HTTP，只读）

1. **等价性对照**：8 国样本（捷克/德国/台湾/蒙古/香港/白俄罗斯/印度尼西亚/加拿大），分别在
   `series` 和"品牌"两种细分模式下，对旧逐国 `chart-data` 结果 regroup 后与新批量
   `map-breakdown` 结果逐项比对（label、quantity、return_quantity、actual_quantity），**两种
   模式全部 8 国完全一致**，无遗漏无多余。
2. **8 国样本门禁（请求数）**：旧路径 8 次独立请求耗时 118.9ms；新路径 1 次请求耗时 20.2ms。
   请求数从 8 降为 1，达成第 0 批报告里定的验收目标。
3. **错误路径**：`source=shipping` 请求批量接口正确返回 400 及说明文字，不会误处理成财务端逻辑。
4. **部署过程**：无残留活跃 `shipping_task`；后端三文件 MD5 核对、reload 无 worker 重启循环；
   前端 `dist-web` 整体覆盖部署，`index.html` 引用的 `index-Zp1NvxLG.js` 与本地构建 hash 一致，
   验证线上可正常拉取 200 后删除 `.old` 备份目录。

## 当前状态

- 财务端世界地图"按系列/品牌"tooltip 已切换为批量接口，生产验证通过。
- 发货端世界地图 tooltip 保持原逐国请求路径（按设计范围保留，未来若需要可参照本批模式单独立项）。
- 指标切换（发货量/销退量/净发货）在两端都不再触发任何 tooltip 相关网络请求。
- 第 1 批（前端防抖/options 缓存/GeoJSON 预热）、第 3 批（chart-options 覆盖索引，需用默认日期
  范围重新评估选择性）均未开始，按原计划视优先级择机推进，不阻塞当前收口。
