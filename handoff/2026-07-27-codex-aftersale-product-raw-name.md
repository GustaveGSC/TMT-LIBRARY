# 售后展开行物料名称改用 ERP 产品导入名称

## 已完成

- `_get_order_products()` 和 `_get_batch_order_products()` 均改为优先使用 `import_product_raw.name`。
- 关联键为 `shipping_record.product_code = import_product_raw.code`；若产品库导入表找不到该编码或名称为空，保持原 `shipping_record.product_name` 兜底。
- 未修改售后自动匹配、简称匹配或其他业务输入路径；本批只影响展开行返回的 `products[].name` 展示值。

## 性能

- 订单物料仍先以一条 `shipping_record` GROUP BY 查询聚合。
- 对本批去重后的编码仅执行一条 `import_product_raw ... IN (...)` 映射查询，再在 Python 合并。
- 不会按订单或物料逐行查询，不引入 N+1。

## 验证

- 新测试覆盖：导入产品名称优先、缺失时回退原始发货名称、`shipping_record` 与 `import_product_raw` 各只查询一次。
- `pytest backend/tests -q`：通过（含 2 个既有 skip）。
- `python -m compileall -q backend`、`git diff --check`：通过。

## 部署验证

- 无迁移。上传 `backend/database/repository/aftersale/__init__.py` 后 reload。
- 用一个已知 `shipping_record.product_code` 存在于 `import_product_raw` 的售后订单验证展开行显示 ERP 全名；再用一个缺失映射的历史编码验证仍显示原始名称。
