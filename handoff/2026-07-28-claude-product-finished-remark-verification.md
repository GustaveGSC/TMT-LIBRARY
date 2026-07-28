# 成品备注字段：后端通过生产验证并已上线

日期：2026-07-28

## 结论

Codex 的实现（d1d86fb）审查通过，改动精准匹配需求（模型+列表查询+保存白名单三处），无冗余。
本地测试全绿。备份+迁移+部署+真实 HTTP 验证全部通过。

## 部署

- 无活跃 `shipping_task`；`mysqldump` 备份（`tmt_db_20260728_backup_pre_finished_remark.sql.gz`，
  已核对 "Dump completed" 结尾）。
- `alembic upgrade head`（`20260727_02 -> 20260728_01`），`alembic current` 确认到 head，
  `SHOW COLUMNS FROM product_finished LIKE 'remark'` 核实 `TEXT NULL`。
- `systemctl reload gunicorn`，master PID 未变，无崩溃重启，`/health` 正常。

## 真实 HTTP 验证（用生产真实成品编码，完成后已清空）

| 验证项 | 结果 |
|---|---|
| 列表 `GET /api/product/finished` 现有项 | `remark: null`（未设置时） |
| `POST /api/product/finished` 保存 `remark` | 200，响应含新值 |
| 再次 `GET` 列表读回 | 与保存值一致 |
| `POST` 传 `remark: null` 清空 | 200，读回 `None`，验证清空可用 |

## 当前状态

后端字段已可用，前端展示/编辑 UI 由 Claude 接下来实现，放置在 `FinishedExpandRow.vue` 标签行
和折叠区（资料/参数/数据）之间。
