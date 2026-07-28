# 产品详情包后端：生产验证通过并已上线

日期：2026-07-28

## 结论

Codex 的独立"产品详情包"后端实现（799fbed）代码审查通过：新表设计干净（不复用
`product_resource`）、匹配算法正确复用了 `product_resource` 既有的 `_matches_tag_condition`
（不是重新发明）、`confirm_media` 对 `storage_key` 前缀+禁止子路径的越权校验到位、删除时序
（DB 先提交、OSS 后清理、失败留痕）符合既定模式。本地测试全绿，已合并部署，真实 HTTP+OSS
验证全部通过。

## 部署

- 无活跃 `shipping_task`；`mysqldump` 备份（`tmt_db_20260728_backup_pre_detail_packages.sql.gz`，
  已核对 "Dump completed" 结尾）。
- 上传 7 个文件（新模型/repository/routes/service + migration + `migrations/env.py` + `app.py`
  蓝图注册），MD5 全部核对一致。
- `alembic upgrade head`（`20260728_01 -> 20260728_02`），`alembic current` 确认到 head，
  `SHOW TABLES LIKE 'product_detail_package%'` 核实 5 张新表全部存在。
- `systemctl reload gunicorn`，master PID 未变，无崩溃重启，`/health`/`/ready` 正常。

## 真实 HTTP/OSS 验证（测试数据，完成后已清理干净）

| 验证项 | 结果 |
|---|---|
| viewer 读 GET 列表 | 200 |
| viewer 写 POST 建包 | 403 |
| 建包 → 设型号范围（真实成品 `1101TS15-A` 的 model_id） | 200 |
| presign → 真实 OSS PUT → confirm 一张图片 | 全部 200 |
| `GET /finished/1101TS15-A`（按型号匹配） | 200，匹配到测试包，媒体数=1 |
| 列表页 `media_count`/`cover_thumbnail` 批量聚合 | 200，数值正确 |
| 删除媒体 | 200，OSS 对象访问确认 404（真实删除） |
| 删除包（级联） | 200，DB 行确认消失 |
| 标签范围匹配（`tag_condition: {op:OR, items:[{tag_id}]}`，真实带标签成品 `1101DL01-A`） | 200，匹配成功 |

型号匹配和标签匹配两条路径都验证通过，删除时序（DB 先提交、OSS 真实清理）符合设计要求。

## 已知的性能权衡（非缺陷，供后续关注）

`matching_finished_packages` 目前是"查全部包 + Python 精确匹配"（常数条查询，不是 N+1），
但没有像 `product_resource` 那样先用 SQL 候选过滤缩小范围。当前包数量小，可接受；如果未来
包数量增长到影响性能，需要补一版 SQL 层候选过滤再交给 Python 精确求值 `tag_condition`。

## 当前状态

后端全部接口已上线可用。前端（独立包管理页 + 产品详情页匹配展示区块）由 Claude 接下来实现。
