# 售后工单列表：新增"只显示有媒体文件的订单"筛选（交接 Codex）

## 背景

用户要求在售后数据表格（`AftersaleTable.vue`）和图表页"查看数据"抽屉
（`AftersaleCasesDrawer.vue`）里都加一个"只显示有媒体文件的订单"勾选框。

前端已经把勾选框做好，并在两处都会把 `has_media: true` 作为查询参数传给
`GET /api/aftersale/cases`（通过 `AftersaleCasesTable.vue` 的 `buildParams()`，字段名
`has_media`）。**目前后端 `get_cases`/对应 repository 查询完全没有处理这个参数**，加了勾选框
也不会实际过滤，需要补上。

## 需要实现

- `GET /api/aftersale/cases` 支持可选查询参数 `has_media`（字符串 `'true'`/`'1'` 才生效，其余
  忽略，与其它布尔筛选参数的解析方式保持一致）。
- 为真时，只返回在 `aftersale_case_media` 表里存在对应 `order_no` 的工单，即：

  ```sql
  WHERE EXISTS (
    SELECT 1 FROM aftersale_case_media m
    WHERE m.order_no = aftersale_case.ecommerce_order_no
  )
  ```

  用 SQLAlchemy 写成 `.filter(AftersaleCase.ecommerce_order_no.in_(
  db.session.query(AftersaleCaseMedia.order_no).distinct()
  ))` 或等价的 `EXISTS` 子查询都可以，选性能更好的写法（`EXISTS` 通常优于 `IN` + 子查询在这种
  半连接场景下，两者请按实际 EXPLAIN 结果决定，不要凭感觉）。
- 分页 `total` 计数也要应用这个过滤条件（不能列表过滤了但分页总数没过滤，导致页数对不上）。

## 性能要求

- 这是列表页 Phase 1 主查询路径，`has_media=true` 时新增的这条过滤必须是**一次半连接/EXISTS
  判断**，不能变成先查全部 `aftersale_case_media` 的 `order_no` 集合再拉到 Python 层做
  `IN`（如果订单量大，这个集合可能很大，不适合整体拉到应用层）。
- 不加这个参数时（默认 `has_media` 不传或为 false）查询计划必须和现在完全一样，不能引入额外
  JOIN 或子查询开销——用条件式 `.filter()` 拼接，不要无条件加这段 EXISTS。

## 影响范围

- `AftersaleTable.vue`（售后数据 Tab 主表格）与 `AftersaleCasesDrawer.vue`（图表页"查看数据"
  抽屉，复用同一个 `AftersaleCasesTable.vue` 组件）都会传这个参数，只需要在
  `GET /api/aftersale/cases` 一处加上支持即可，前端两处都已经接好，不需要再改前端。
- `.claude/modules/api.md` 里 `GET /api/aftersale/cases` 那一行补充这个新参数的说明。

## 验证要求

- 真实 MySQL 下验证：`has_media=true` 时结果集只包含 `aftersale_case_media` 里存在记录的订单；
  `has_media` 不传时行为与现在完全一致（用 EXPLAIN 确认没有多余 JOIN/子查询开销）。
- 分页 `total` 与实际过滤后的行数一致。
