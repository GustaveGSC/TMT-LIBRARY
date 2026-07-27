# 确认工单表格物料名称：ERP 覆盖修复

## 根因与修复

前一版只覆盖待处理队列的实时 `shipping_record` 聚合。用户实际使用的「数据」Tab 与图表抽屉均调用 `GET /api/aftersale/cases`，该接口返回 `aftersale_case.products` 的历史 JSON 快照，因此未被覆盖。

本次在 `AftersaleService.get_cases()` 的响应组装阶段：

1. 将当前分页全部工单转换为响应 dict；
2. 收集所有 `products[].code`；
3. 用一次 `import_product_raw.code IN (...)` 查 ERP 名称；
4. 仅覆盖返回 payload 的 `products[].name`，查不到保留快照原名。

不会修改/回填历史 JSON 快照，也不会影响待处理队列或自动匹配逻辑。

## 性能与验证

- 当前页无物料编码时不查询 `import_product_raw`；有编码时固定增加一次批量 IN 查询，不随订单数或物料数增长。
- 新测试覆盖确认工单：ERP 全名覆盖、缺失映射回退、`import_product_raw` 查询数为 1。
- `pytest backend/tests -q`：通过（含 2 个既有 skip）。
- `python -m compileall -q backend`、`git diff --check`：通过。

## 部署验证（必须）

- 无迁移。上传 repository、service、测试/文档按需后 reload。
- 真实 HTTP 验证：`GET /api/aftersale/cases?search=20260127006` 中 `1208YJZM01-A` 的 `products[].name` 应为 `import_product_raw.name` 的 ERP 全名。
- 正常不带 search 查询一页确认工单，核对多订单页面名称均正确，并观察日志无异常。
- 图表页「查看数据」抽屉复用同一接口，应一并验证。
