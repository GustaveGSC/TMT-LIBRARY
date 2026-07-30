# 发货物料简称列表需要返回使用次数（use_count），交接 Codex

日期：2026-07-30
状态：待实现（前端已就绪，加上字段即自动生效）

## 背景

用户要求「工单处理 → 设置 → 售后原因库 / 发货物料简称」两个列表**按数量降序排序**，
并各加一个刷新按钮。

- **售后原因库**：`AftersaleReason` 已有 `use_count` 字段，前端排序已完成上线。
- **发货物料简称**：`AftersaleShippingAlias` **没有使用次数字段**，
  `to_dict()` 只返回 `{id, name, keywords, sort_order}`。

用户已确认「数量」指**被引用次数**（不是关键词数量）。

实测这个口径很有价值（只读查询）：

```
气弹簧          563 次
电源            138 次
桌面（产成品）     84 次
桌垫             75 次
桌腿（产成品）     62 次
```

123 个简称里只有 1 个从未被引用过，分布差异极大，排序后常用简称能直接浮到顶部。

## 需要实现

`GET /api/aftersale/shipping-aliases` 返回的每个简称增加 `use_count` 字段
= `aftersale_case_reason` 中引用该简称的行数。

```sql
SELECT sa.id, COUNT(cr.id) AS use_count
FROM aftersale_shipping_alias sa
LEFT JOIN aftersale_case_reason cr ON cr.shipping_alias_id = sa.id
GROUP BY sa.id
```

### 契约要点

- **一条聚合查询搞定，不要在循环里逐个 count**（123 个简称会变成 123 条查询）。
  建议先一次 `GROUP BY` 拿到 `{alias_id: count}` 字典，再拼进列表结果。
- 从未被引用的简称 `use_count` 返回 `0`，不要返回 `null`（前端按数值排序）。
- `AftersaleReason.use_count` 是表上的实际列（写入时维护）；简称这个是**实时聚合算出来的**，
  不需要加表字段、不需要迁移。除非你评估后认为该表也应该加持久化列——但那需要回填 +
  在确认/修改工单时维护，改动面大得多，本需求用聚合就够。
- 其他返回字段与顺序保持不变，避免影响既有调用方
  （该接口还被 `AftersaleProcess.vue` 的简称下拉、`AftersaleCasesTable.vue` 的行内编辑用到）。
- 该接口在只读白名单外但是 GET，权限不变（`aftersale:view`）。

## 前端已就绪，无需你改

`AftersaleReasonLib.vue` 已改好并上线：

- 两个列表都按 `use_count` 降序排序（次数相同按名称升序，保证顺序稳定）
- **`use_count` 缺失时按 0 处理**，所以现在不会报错，只是简称退化为按名称排序；
  你加上字段后排序自动生效，前端不用再动
- 简称列表项在 `use_count > 0` 时会显示「已用 N 次」（与原因库一致）
- 两个 tab 各加了刷新按钮（复用现成的 `loadAll()`，带 loading 旋转态）

## 验收

加上字段后我会：
1. 真实 HTTP 核对 `use_count` 与直接 SQL 聚合的结果一致；
2. 确认接口查询数量没有变成 N+1（看响应时间 + 必要时 EXPLAIN）；
3. 浏览器确认简称列表按次数降序、且「已用 N 次」显示正确。
