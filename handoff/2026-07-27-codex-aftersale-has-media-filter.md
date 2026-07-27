# 售后工单「仅显示有媒体」后端筛选交接

## 已完成

- `GET /api/aftersale/cases` 新增可选 `has_media` 参数；仅字符串 `true` 或 `1` 生效，其余值等同未传。
- 生效时在主查询追加相关 `EXISTS` 半连接：`aftersale_case_media.order_no = aftersale_case.ecommerce_order_no`。
- 同一个 `q` 同时用于 `count()` 与分页结果，因此 total 与实际结果保持一致。
- 未传/false 时不构造 EXISTS 子查询，原查询计划和额外查询数不变。
- 已更新 `.claude/modules/api.md`。

## 验证

- 新增测试：有媒体和无媒体工单混合时，仅返回有媒体订单、total=1；未传筛选时两条均返回、total=2。
- `pytest backend/tests -q`：通过（含 2 个既有 skip）。
- `python -m compileall -q backend` 与 `git diff --check`：通过。

## 部署验收

- 无迁移。同步 aftersale route/service/repository 后 reload。
- 真实 MySQL 用 `has_media=true` 检查列表和 total；无参数再查一次，确认包含无媒体历史工单。
- 用 `EXPLAIN` 确认生效路径为相关 EXISTS 并命中 `ix_aftersale_case_media_order_no`；无参数 SQL 不应含媒体表子查询。
- 前端两个既有勾选入口已传参数，部署后无需前端变更即可生效。
