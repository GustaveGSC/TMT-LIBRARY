# 物料清单服务端排序与分列筛选完成，交接 Claude

日期：2026-08-03  
状态：代码完成、本地验证通过、**未部署**

## 实现

`GET /api/material/items` 新增：

- `code`：ERP 编码包含匹配
- `name`：ERP 名称包含匹配
- `short_name`：简称包含匹配（复用现有 LEFT JOIN）
- `sort_by=code|name|short_name|group_code`
- `sort_dir=asc|desc`，非法方向按 asc

保留 `keyword`，所有文本条件同时传入时为 AND。

排序字段使用后端白名单映射到 ORM 列，非法字段返回 400“排序字段无效”，没有动态 SQL
字段拼接。short_name 的 NULL 在升降序时均放最后。

## 两条分页路径

- 常见路径（未筛大类）：SQL `COUNT + LIMIT/OFFSET`，筛选和排序均在 SQL 完成；
  `product_material` 只对当页 code 做一次 IN 查询。
- 大类/未分类路径：先在 SQL 应用文本、状态、分组筛选，只取
  `code/group_code/name/short_name` 四个轻量列；Python 判定大类、排序和分页，随后回查当页完整行。

分组配置也加入模块级缓存，并在保存分组后主动失效；规则、停用关键词、分组配置缓存热态下，
常见列表路径保持业务查询为 COUNT、分页、当页人工属性三条。

## 验证

- 三个分列筛选可同时生效。
- 简称 ASC/DESC 均验证 NULL 在末尾。
- 大类筛选路径的简称排序结果一致。
- 非法 sort_by 通过真实 Cookie JWT 请求返回 400，不进入查询。
- 默认分页测试确认人工属性 IN 查询只收到当前页 code。
- 全量 pytest、compileall、diff check 均通过。

## 部署验收建议

1. 四个字段各验证 ASC/DESC，重点确认 MySQL collation 下中文名称顺序符合界面预期。
2. 验证简称为空的数千行始终排在非空简称之后。
3. 组合验证 `code + name + short_name + category + is_disabled` 的 AND 语义。
4. 开启 SQL 观测抽查普通路径查询数量和参数规模，确认没有恢复全表 ORM 加载。
5. 无数据库迁移，本批只需同步运行时代码并 reload。
