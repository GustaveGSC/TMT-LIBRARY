# 财务世界地图批量 tooltip 接口：后端实现交接

## 已完成

- 新增 `POST /api/shipping/map-breakdown`，权限为 `shipping:view`。
- 接口严格限定 `source=finance`：国家来自客户人工映射的 `country`，仅统计 `status=export` 的映射；不改变发货端基于产品标签多对多关系的既有逐国路径。
- 一次 grouped 查询返回最多 100 个国家的系列或品牌细分。返回 `quantity`、`return_quantity`、`actual_quantity` 三种指标，前端切换指标不需要再次请求。
- 保持现有财务 `chart-data` 的日期、产品层级、渠道、地区、标签筛选和禁用成品前缀过滤语义；品牌按人工映射文本分组，不要求产品标签库中存在同名标签。
- 批量查询使用既有 `shipping_order_finished` 复合索引 hint；没有新增索引或数据库迁移。
- 已更新 `.claude/modules/api.md`，接口参数、响应与错误边界已落盘。

## 验证结果

- `pytest backend/tests -q`：通过（含 2 个既有 skip）。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。
- 新增 fixture 同时验证两个国家的品牌模式与系列模式，未映射、内销、非销售、未审核数据不会混入结果。
- SQL 监听断言：两个国家的品牌批量查询只执行一条访问 `shipping_order_finished` 的主聚合 SQL，不随国家数量增加。
- 真实 Cookie JWT 权限测试：无 `shipping:view` 为 403，持有 `shipping:view` 的 viewer 为 200。

## Claude 联调与部署门禁

1. 前端仅在财务世界地图把原逐国 `chart-data` 请求替换为一次 `map-breakdown` 请求，并按 `country` regroup；发货端保持原实现。
2. 用相同筛选条件临时逐项对照旧逐国结果和新接口结果，再删除旧的 `Promise.all(countries.map(...))` 路径。
3. 生产采用第 0 批相同的 8 国样本，确认 tooltip 相关请求数从 8 降到 1，并核验主图数值、tooltip 三项指标和 `/health` 均正常。
4. 本批没有部署；请按后端常规顺序同步 repository、service、route 后 reload，并观察日志确认无 worker 重启循环。

## 发现与处理

实现初版的 POST 路由未加入 Blueprint 的只读 POST 白名单，真实权限测试立即暴露 viewer 得到 403；已修为 `/chart-data` 与 `/map-breakdown` 均按 `shipping:view` 放行。该问题已有回归测试，避免依赖默认 POST=编辑权限的隐式行为。
