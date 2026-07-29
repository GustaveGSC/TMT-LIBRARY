# 产品详情文件夹适用范围增加"适用系列/适用品类"，交接 Codex

状态：待实现

## 背景

产品详情文件夹（`ProductDetailPackage`）目前的适用范围只支持两种匹配方式：型号
（`package_model` 关联表，精确到具体型号）和标签（`package_tag` + `tag_condition`）。
用户希望再增加"适用系列"、"适用品类"两个粒度，语义和型号一致——文件夹关联某个系列/品类后，
该系列/品类下（含未来新增）的所有产品都会在详情页展示这个文件夹的内容，不是一次性展开成
当前型号列表的快照。

前端这边我已经把 `ProductDetailPackages.vue` 的型号级联选择器从"误用了裸 `multiple` 属性
导致实际是单选模式"的 bug 修复了（Element Plus 的 `el-cascader` 多选必须通过
`:props="{ multiple: true }"` 配置，不是组件上的裸 `multiple` 属性——之前那样写等于没生效，
`@change` 拿到的其实是单个路径数组，`paths.map(p => p[p.length-1])` 对着数字取 `.length`
全部变成 `undefined`，这就是"选择适用型号会报错 model_ids 必须为正整数数组"的根因）。这个
bug 修复不依赖这次的系列/品类需求，已经单独部署。

## 需要实现

### 1. 数据库：新增两张关联表，镜像现有 `package_model` 的写法

```python
package_series = db.Table(
    'product_detail_package_series',
    db.Column('package_id', db.Integer, db.ForeignKey('product_detail_package.id', ondelete='CASCADE'), primary_key=True),
    db.Column('series_id', db.Integer, db.ForeignKey('product_series.id', ondelete='CASCADE'), primary_key=True),
)

package_category = db.Table(
    'product_detail_package_category',
    db.Column('package_id', db.Integer, db.ForeignKey('product_detail_package.id', ondelete='CASCADE'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('product_category.id', ondelete='CASCADE'), primary_key=True),
)
```

`ProductDetailPackage` 增加对应 `db.relationship`（`series`/`categories`，`lazy='selectin'`，
和现有 `models` 写法一致），`to_dict()` 增加 `series_ids`/`category_ids`（同 `model_ids`
写法）。新增迁移文件（`down_revision` 接当前 head）。

### 2. Repository：`DetailPackageRepository` 增加 `set_series`/`set_categories`

完全镜像现有 `set_models`（`backend/database/repository/product/detail_package.py:65-72`）：
先删后插，`db.session.commit()`。

### 3. `matching_finished_packages` 匹配逻辑扩展

当前（`backend/database/repository/product/detail_package.py:87-107`）只判断
`model_match`（型号精确匹配）和 `tag_match`。需要增加：

```python
series_match = bool(finished.model and finished.model.series_id and
                     finished.model.series_id in {s.id for s in package.series})
category_match = bool(finished.model and finished.model.series and finished.model.series.category_id and
                       finished.model.series.category_id in {c.id for c in package.categories})
if model_match or series_match or category_match or tag_match:
    matched.append(package)
```

注意 `finished.model`/`finished.model.series` 这两跳关系访问如果是 `lazy=True`（默认）会在
循环里对每个 package 触发额外查询——但这两跳是访问 `finished`（外层已经查过的单个对象）的关系，
不是循环里的每个 package，只会触发最多 2 次额外查询（一次拿 model，一次拿 series），不是
N+1（package 数量无关）。如果想更省，可以在函数开头 `finished = ProductFinished.query.options(
joinedload(ProductFinished.model).joinedload(ProductModel.series)).filter_by(code=code).first()`
预加载，但不是必须。

### 4. 路由：`backend/routes/product/detail_package.py` 增加

```python
@detail_package_bp.put('/<int:package_id>/series')
def set_series(package_id):
    return detail_package_service.set_series(package_id, (request.get_json() or {}).get('series_ids', [])).to_response()

@detail_package_bp.put('/<int:package_id>/categories')
def set_categories(package_id):
    return detail_package_service.set_categories(package_id, (request.get_json() or {}).get('category_ids', [])).to_response()
```

### 5. Service：`DetailPackageService` 增加 `set_series`/`set_categories`

镜像现有 `set_models`（校验 `series_ids`/`category_ids` 是正整数数组，查不到 package 返回
`Result.fail`，成功后返回更新后的 `package.to_dict()`）。

## 契约要点

- 三个维度（型号/系列/品类）之间是 **OR** 语义：产品只要命中型号、系列、品类、标签任意一个
  条件就算匹配（和现在型号 vs 标签的 OR 关系一致，不需要额外设计"且/或"开关）。
- 系列/品类范围下未来新增的型号/子系列会自动纳入匹配（不是快照展开成型号 id 列表），这是
  它和"直接多选很多个型号"的本质区别，也是用户要这个功能的原因。
- 不需要处理"型号已经被某个系列覆盖，还要不要在 model_ids 里去重"这种优化——三个维度各自独立
  存储和判断，允许语义上有重叠（同一产品可能同时命中型号条件和系列条件），不影响最终结果
  （最终只看"是否匹配"，不是"匹配了几次"）。

## 不需要的改动

- 不需要改标签相关逻辑（`set_tags`/`tag_condition`）。
- 不需要改前端——级联选择器和保存调用的接线我来做（`el-cascader` 现在已经是
  `:props="{ multiple: true }"` 的正确多选模式，下一步是加 `checkStrictly: true` 让系列/
  品类节点本身也能被勾选，而不必强制下钻到型号叶子节点，再按路径长度分流调用
  `/models`、`/series`、`/categories` 三个接口）。

## 验证要求

- 单测：文件夹关联某系列后，该系列下已有型号的产品命中；后续给该系列新增一个型号（新建
  `ProductModel`）后，新型号对应的产品也命中（验证"不是快照"）。品类同理。
- `matching_finished_packages` 现有测试（型号/标签匹配）确认无回归。
- `to_dict()` 返回的 `series_ids`/`category_ids` 字段格式和排序方式与现有 `model_ids`
  一致。

## Claude 后续动作

收到实现后我会 review、部署（含迁移，走标准备份→上传→`alembic upgrade head`→`alembic
current`→reload 流程），然后做前端接线：级联选择器加 `checkStrictly: true`，按选中路径
深度（品类1级/系列2级/型号3级）分流调用三个保存接口，并做真实浏览器验证。
