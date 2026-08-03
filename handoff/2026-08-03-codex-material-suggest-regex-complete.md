# 物料筛选候选与正则模式完成，交接 Claude

日期：2026-08-03  
状态：代码完成、本地验证通过、**未部署**

## 新增候选接口

`GET /api/material/suggest?field=code|name|short_name&q=<文本>&limit=20`

- field 严格白名单；非法返回 400“字段无效”。
- q strip 后为空直接返回 `[]`，不访问数据库。
- limit 默认 20、范围 1–50；非法整数返回 400。
- 每次只执行一条 `SELECT DISTINCT ... LIKE ... ORDER BY ... LIMIT`：
  - code/name 只查 `import_product_raw`，不 JOIN。
  - short_name 只查 `product_material`。
- NULL/空串不进入候选。

## 正则筛选

`GET /api/material/items` 新增 `match_mode=like|regex`：

- 默认/不传仍为原 LIKE 包含匹配。
- regex 只影响 `code/name/short_name`，旧 keyword 仍为 LIKE。
- SQL 使用 ORM 列 `.op('REGEXP')`，排序字段仍是既有白名单，不拼 SQL 字符串。
- 第一层用 Python `re.compile` 拦截常见非法表达式。
- 第二层捕获 MySQL 1139、3690–3699 ICU 正则错误，rollback session 后返回
  400“正则表达式无效”；其他数据库错误继续交全局异常处理，不伪装成用户输入错误。
- 非法 match_mode 返回 400“匹配模式无效”。

## 验证

- 候选 DISTINCT、limit 和单 SQL 断言通过。
- q 为空不查库；非法 field 返回 400。
- `^(14ME|14WD)` 正确命中两组。
- regex 与旧 keyword 叠加为 AND，且 keyword 仍使用 LIKE。
- `[` 在进入数据库前返回 400，不产生 500。
- 全量 pytest、compileall、diff check 通过。

## 生产验收建议

1. 用 `^14ME` 对照 `code LIKE '14ME%'` 的数量。
2. 验证 `14ME|14WD`、简称候选为空、候选 limit。
3. 用 Python 可通过但 MySQL ICU 不接受的表达式验证第二层错误转换。
4. 观测 suggest 每次恰好一条 SQL；确认 code/name 候选无 JOIN。
5. 本批无迁移，只需同步运行时代码并 reload。
