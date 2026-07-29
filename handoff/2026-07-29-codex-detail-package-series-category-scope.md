# 产品详情文件夹系列/品类适用范围：后端交接

分支：`codex/detail-package-series-category-scope`  
状态：已实现，未合并、未部署。

## 实现

- 新增迁移 `20260729_01`（基于 `20260728_03`）：
  - `product_detail_package_series`
  - `product_detail_package_category`
- `ProductDetailPackage` 新增 `series`、`categories` 关系，并在所有包响应中增加
  `series_ids`、`category_ids`。
- 新增两个写接口（均 `product:edit`）：
  - `PUT /api/product-detail-packages/:id/series`，`{series_ids:[int]}`
  - `PUT /api/product-detail-packages/:id/categories`，`{category_ids:[int]}`
- 读取匹配采用 **型号 OR 系列 OR 品类 OR 标签**。系列/品类关系在读取时按当前成品层级判断，未来新增型号/成品自动命中，不会固化成型号快照。
- 关联替换、请求参数校验、API/数据库契约均已补齐。

## 性能

包匹配仍为固定查询数量：单次取得当前成品的系列/品类范围，再 selectin 预加载所有包的四种范围关系；不随包数量增加 SQL 查询，未引入 N+1。

## 验证

- 新增测试覆盖：
  - 系列和品类范围均能匹配已有成品；
  - 后续新增到已选系列的型号仍命中系列包；
  - 后续新增到已选品类的另一系列型号仍命中品类包；
  - 包响应包含 `series_ids`/`category_ids`。
- `python -m pytest backend/tests -q`：通过。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。

## Claude 后续

1. 备份生产数据库，合并后执行 `alembic upgrade head`，确认 revision 为 `20260729_01`。
2. 以 editor 真实验证三个范围接口与产品详情匹配读取；viewer 写接口应为 403。
3. 前端在级联选择器启用 `checkStrictly: true`，按路径长度把品类/系列/型号分别提交到三个接口。
