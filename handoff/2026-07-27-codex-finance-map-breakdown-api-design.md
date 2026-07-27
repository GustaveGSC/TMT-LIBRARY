# 财务世界地图批量 tooltip 接口设计（第 2 批，未实现）

## 依据与目标

第 0 批生产采样证明：财务地图主图与单国家 tooltip SQL 均为毫秒级，问题是现有前端为每个国家发一条 HTTP 请求。第 2 批只解决这个固定往返/单 worker 排队成本：一次请求、一次聚合、返回全部国家的细分结果；不为本已很快的 SQL 新增索引。

首批**明确限定财务端**（`source=finance`）的世界地图。发货端基于产品标签的地图可另立一批处理，避免把两套“国家”语义和多对多标签 fan-out 混进同一个高风险接口。

## 建议接口契约

```text
POST /api/shipping/map-breakdown
权限：shipping:view（保持 chart-data 的查询权限）
```

请求体：

```json
{
  "source": "finance",
  "country_category_id": 3,
  "countries": ["加拿大", "德国"],
  "breakdown_group_by": "series",
  "date_start": "2026-01-01",
  "date_end": "2026-07-27",
  "category_ids": [], "series_ids": [], "model_ids": [],
  "channel_names": [], "channel_codes": [],
  "provinces": [], "cities": [], "districts": [],
  "tag_filters": []
}
```

- `source` 必须为 `finance`；其他值返回 400。
- `country_category_id` 必须是名称为“地域”的启用发货维度分类；否则 400。
- `countries`：1–100 个非空字符串、去重后处理；仅允许主地图当前有数的国家传入。
- `breakdown_group_by`：`series` 或 `tag:<id>`；后者必须是名称为“品牌”的启用发货维度分类。首批不开放任意分组维度，防止接口变成第二个通用 chart-data。
- 保留现有筛选字段语义；`trade_type` 不接收，因为世界地图本身固定为人工映射的 `status=export`。

成功响应：

```json
{
  "success": true,
  "message": "",
  "data": {
    "items": [
      {
        "country": "加拿大",
        "label": "S001",
        "name": "系列名称",
        "quantity": 12,
        "return_quantity": 1,
        "actual_quantity": 11
      }
    ]
  }
}
```

`items` 是扁平结果，后端按 `country, actual_quantity DESC` 排序；前端按 country regroup 成当前 `tooltipBreakdown[country]` 的展示结构。返回三种指标，指标切换不应重新请求。

## 后端实现边界

- 仅一条聚合 SQL：`GROUP BY mapping.country, breakdown label[, name]`；不得按国家循环调用 `get_chart_data()`。
- 使用现有 `ix_sof_source_customer_alias` 和人工 mapping JOIN；第 0 批已证明该路径 3–9ms，无需为本接口新增索引。
- 复用并逐项对齐现有财务 `chart-data` 的日期、产品层级、渠道、行政区、禁用成品前缀筛选，以及 `status=export/country 非空` 口径。
- 品牌模式按人工 mapping 的 `brand` 字段分组，不依赖产品标签库中是否存在该品牌；与当前 tooltip 的逐国请求保持一致。
- 不返回 summary，避免无用的第二次扫描。
- 观测沿用第 0 批开关，新增 event `map_breakdown`，记录 country_count、breakdown_group_by、item_count、duration_ms，不记录国家文本。

## 等价性与联调门禁

1. 后端 fixture：至少两个国家、多个系列/品牌、未审核/内销映射、空品牌、日期/渠道筛选，断言批量结果按 country regroup 后逐项等于旧 `chart-data` 的逐国结果。
2. 权限：真实 Cookie JWT 的 viewer 200、无 shipping:view 403；非法 source/分类/国家数 400。
3. 查询数：监听 SQL，接口请求仅允许固定的元数据查询 + **一条**主聚合，严禁随 country 数增加。
4. 前端联调：同一真实筛选下，对旧逐国结果与新批量结果做一次临时逐项对照；确认后删除旧 `Promise.all(countries.map(...))` 路径。
5. 生产：重复第 0 批的 8 国家样本，验证 chart-data tooltip 请求从 8 降为 1，且主图与 `/health` 无回归。

## 需 Claude 确认的前端影响

前端只需替换 `fetchTooltipBreakdown()` 的请求和本地 regroup，不改变 tooltip HTML、详情面板、指标选择或地图交互。请确认是否接受“首批仅财务端；发货端继续旧路径”的明确范围；若接受，Codex 可按以上契约开始后端实现。
