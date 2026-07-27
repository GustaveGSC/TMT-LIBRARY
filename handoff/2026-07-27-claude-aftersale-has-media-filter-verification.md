# 售后 has_media 筛选：生产验证通过并已上线

日期：2026-07-27

## 结论

Codex 的 `has_media` 筛选实现（93d4a6c）审查通过，本地测试全绿，无迁移，同步三个文件后
`reload`，真实 HTTP + EXPLAIN 验证全部符合预期。数据 Tab 和图表页"查看数据"抽屉里此前已经
接好的"只显示有媒体文件的订单"勾选框现在真正生效。

## 验证结果（真实生产数据，只读）

| 验证项 | 结果 |
|---|---|
| `has_media=true` | `total=1`，返回订单 `260630100`（生产真实已导入媒体的订单） |
| 不传 `has_media` | `total=2638`，正常返回混合结果（含无媒体历史工单） |
| `has_media=true` 时 EXPLAIN | `aftersale_case_media` 走 `index`（LooseScan，命中
  `ix_aftersale_case_media_order_no`），`aftersale_case` 侧 `eq_ref` 命中
  `ecommerce_order_no` 索引——相关 EXISTS 半连接按预期编译执行 |
| 不传 `has_media` 时 SQL | 确认不包含 `aftersale_case_media` 表，零额外查询开销 |

## 当前状态

售后图片/视频导入功能相关的两个独立后端待办中，`has_media` 筛选已完成闭环。仍剩一项："物料
名称缺规格"（`handoff/2026-07-27-claude-aftersale-product-name-spec-request.md`），等 Codex
处理。
