# resolve_stale 按影响范围标记：产品决策已确认，批准实施

日期：2026-07-27

## 审查结论

只读设计方案审查无异议。抽查验证了三个真实写入口都存在且与描述一致：
`POST/DELETE /api/product/finished/<id>/packaged/<id>`、
`POST/DELETE /api/shipping/equivalents[/<id>]`、`POST /api/shipping/warehouses/filter`。
"安全超集"标记思路、销退记录回查正向 source、规则保存与 stale 标记同事务、与 `shipping_mutation`
共享短时 lease 避免竞态，这几个关键设计点认同，不需要调整。

## 用户产品决策

1. **超过 `MAX_STALE_RESOLVE_ORDERS` 上限时：允许保存规则并挂起 stale，不阻止保存。**
   UI 必须明确提示"超过增量安全上限，需走全量重建或等待上限经门禁调整"，不能悄悄只重算部分——
   与设计方案第五节的建议一致，按此实施。
2. **影响范围接近全量时：UI 直接引导用户走 `resolve_all`。**
   避免长期积压大量 stale 订单增加数据不一致窗口。
3. **成品—组件关系、等效件接口暂不迁移至 product 域。**
   保持现状（URL 仍在 shipping 域下），不阻塞本批 stale 标记功能实施；域迁移留给后续结构整理批次，
   迁移前需保留兼容层，到时候再单独排期。

## 现在可以开始实施

按设计方案第七节的验收测试要求逐类覆盖（正向命中/销退命中/无命中、shipping+finance 双来源、已
匹配/未匹配/竞争成品订单、重复保存不扩大 scope、与运行中 resolve 的 409/租约隔离、标记后
`resolve_stale` 能完整恢复、超上限时规则保存一致但任务明确拒绝、viewer 无法变更规则）。

实施前记得先在生产做只读 `EXPLAIN`（方案第六节），缺索引就单独出一个 Alembic 迁移，不要让配置
保存退化成大表扫描。

`(source, ecommerce_order_no)` 复合索引和 `MAX_STALE_RESOLVE_ORDERS` 上限调整仍不在本批授权范围
内——这批做完、有了真实的 stale 标记规模数据之后，再回头评估要不要动。
