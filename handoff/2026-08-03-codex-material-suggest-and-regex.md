# 物料清单：筛选候选面板 + 正则筛选，交接 Codex

日期：2026-08-03
状态：**前端已实现并已按本契约发送参数/调用接口，后端未实现前这两项不生效**
前置：`2026-08-03-codex-material-list-sort-filter-complete.md`（服务端排序与分列筛选已上线）

## 用户需求原文

> 3、筛选需要出现候选面板，需要可以正则筛选

## 为什么这两项必须在服务端做

物料 8,089 条、接口是服务端分页。

- **候选面板**：候选值不能从当页 50 行推导——用户想选的值大概率不在当页。
  必须服务端对全表做 DISTINCT。
- **正则筛选**：同理，只能由 MySQL 的 `REGEXP` 在全表上执行。

（这与产品库不同：`ProductTable.vue` 的候选值来自 store 里已全量加载的 523 条成品，
可以在客户端算。物料量级是它的 15 倍，走不了同一条路。）

---

## 一、新增候选值接口

```
GET /api/material/suggest?field=<code|name|short_name>&q=<关键词>&limit=20
→ Result.ok(data=["值1", "值2", ...])
```

| 参数 | 说明 |
|---|---|
| `field` | **白名单**：`code` / `name` / `short_name`。其他值返回 `Result.fail('字段无效')` |
| `q` | 关键词，`strip()` 后为空则返回空数组（不要返回全表） |
| `limit` | 默认 20，**上限 50** |

实现要点：

- `SELECT DISTINCT <col> ... WHERE <col> LIKE '%q%' AND <col> IS NOT NULL AND <col> <> '' ORDER BY <col> LIMIT n`；
- `code` / `name` 取自 `import_product_raw`，`short_name` 取自 `product_material`；
- `short_name` 目前库里全为 NULL，返回空数组是正确行为，不要报错；
- 权限 `product:view`；
- **必须只有一条 SQL**。这个接口会被输入框防抖触发（前端已做 350ms 防抖），
  但仍属高频，务必保证单查询 + `LIMIT`。
- `name` 列没有索引，`LIKE '%q%'` 是全表扫描。8,089 行规模可接受，
  但**不要**在这个接口里再做 JOIN 或大类判定——它只需要一列的去重值。

## 二、正则筛选

新增参数 `match_mode`，作用于**现有的 `code` / `name` / `short_name` 三个文本筛选**：

| 取值 | 行为 |
|---|---|
| `like`（默认，不传时） | 保持现状 `LIKE '%值%'`，**行为不得改变** |
| `regex` | 改用 MySQL `REGEXP` |

实现要点：

- SQLAlchemy 写法：`column.op('REGEXP')(value)`；
- **非法正则必须优雅失败**：MySQL 会抛 error 1139 / 3692 之类，
  请捕获并返回 `Result.fail('正则表达式无效')`，**不要让它变成 500**。
  建议在 Python 侧先用 `re.compile(value)` 预校验，能拦掉大部分语法错误、
  且不消耗数据库；但 MySQL 与 Python 的正则方言不完全相同，
  所以**数据库那层的异常捕获也要保留**，两层都要有。
- `match_mode` 只影响这三个文本筛选。`group_code` / `category` /
  `unclassified` / `is_disabled` 是精确匹配，与它无关。
- `keyword`（旧的编码+名称联合搜索）**不受 `match_mode` 影响**，保持 `LIKE`，
  避免影响其他调用方。
- 性能：`REGEXP` 用不上索引，必然全表扫描。8,089 行没问题，
  但这也意味着**不要**在正则模式下再放宽 `page_size` 上限。

### 一个需要你判断的取舍

`REGEXP` 在 MySQL 8 里是 ICU 实现，支持的语法与 Python `re` 有差异
（例如 `\d` 在 ICU 里可用，但 `(?i)` 内联标志的行为不同）。
如果你认为「Python 预校验 + 数据库异常捕获」两层仍会漏掉某些让用户困惑的情况，
可以在错误消息里带上数据库返回的原始原因，方便定位。具体措辞你定。

## 三、前端已完成的部分（对照契约）

`src/components/common/DataTable.vue`（共享组件，向后兼容）：

- 列配置新增 `filterSuggest: true` → 该文本筛选列显示候选面板；
- 新增 `suggestProvider` prop：`(prop, keyword) => Promise<string[]>`，
  候选数据源由调用方注入，组件只负责 UI；
- 候选面板 350ms 防抖、失焦延迟 160ms 隐藏（否则 blur 先于点击触发会点不中）；
- 候选面板会被表头单元格的 `overflow:hidden` 裁掉，所以只在
  `.app-data-table--suggest`（即确实启用了候选的表格）上放开 overflow，
  **不影响产品库产成品清单那张表**。

`src/components/material/MaterialItemsPanel.vue`：

- `code` / `name` / `short_name` 三列启用候选面板，调用 `/api/material/suggest`；
- 底栏新增两个开关：
  - **不显示停用状态数据**（默认勾选）→ 发 `is_disabled=0`；
    ⚠️ 与「停用状态」列筛选的关系：**列筛选显式选了值就以列筛选为准**
    （便于专门查看停用项），列筛选为空时才套用这个开关。
  - **正则筛选** → 发 `match_mode=regex`；
- ERP 编码列改为黑色粗体、无下划线（按用户要求）。

## 四、验收方式

1. `/api/material/suggest` 三个字段各自返回去重候选、受 `limit` 限制、
   `q` 为空返回空数组、非法 `field` 返回明确错误；
2. 核对该接口 SQL 条数为 1；
3. `match_mode=regex` 下：`^14ME` 之类锚定正则命中数与 `LIKE '14ME%'` 一致；
   `14ME|14WD` 这类或分支能正确命中两组；
4. **非法正则（如 `[` 或 `(`）返回明确错误而不是 500**；
5. 不传 `match_mode` 时结果与现在完全一致（回归）；
6. 正则模式与 `group_code` / 大类 / 停用筛选叠加时行为正确。
