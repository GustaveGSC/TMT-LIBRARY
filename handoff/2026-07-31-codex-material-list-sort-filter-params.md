# 物料清单需要服务端排序与分列筛选参数，交接 Codex

日期：2026-07-31
状态：**前端已实现并已按本契约发送参数，后端参数未实现前这些筛选/排序不生效**
前置：`2026-07-31-codex-material-library-backend.md`、`...-review-fixes.md`

## 背景

用户要求物料清单「使用表格的形式呈现（和产品库里的表格一样，需要有筛选和排序）」。

产品库表格的做法是**把全量数据加载到前端、在客户端做筛选排序分页**
（`ProductTable.vue` + `stores/product/finished.js`）。
物料清单**不能照搬**：`import_product_raw` 有 8,089 行，
而且 `/api/material/items` 已经是服务端分页——对当前 20~100 行做筛选排序毫无意义
（用户想找的那条大概率不在当页）。

所以物料清单的筛选与排序**必须走服务端参数**。这也符合 `CLAUDE.md` 的性能规范：
不要为了前端筛选把 8,089 行整体传到浏览器。

## 现状与缺口

`GET /api/material/items` 现有参数：`page` / `page_size` / `keyword` / `group_code` /
`category` / `unclassified` / `is_disabled`。

缺口：

| 前端已在发送 | 用途 | 现状 |
|---|---|---|
| `sort_by` | 排序字段 | ❌ 未实现 |
| `sort_dir` | `asc` / `desc` | ❌ 未实现 |
| `code` | 按 ERP 编码模糊筛选 | ❌ 未实现（现有 `keyword` 同时搜编码和名称，无法分列） |
| `name` | 按 ERP 名称模糊筛选 | ❌ 未实现 |
| `short_name` | 按简称模糊筛选 | ❌ 未实现 |

`group_code` / `category` / `unclassified` / `is_disabled` 前端已在用，**这四个已可用**。

## 需要实现

### 1. 分列文本筛选

新增三个可选参数，各自独立、可同时生效（AND 关系）：

| 参数 | 作用列 | 匹配方式 |
|---|---|---|
| `code` | `import_product_raw.code` | `LIKE '%值%'` |
| `name` | `import_product_raw.name` | `LIKE '%值%'` |
| `short_name` | `product_material.short_name` | `LIKE '%值%'`（走已有的 LEFT JOIN） |

- 三者都 `strip()`，空串视为未传；
- **保留现有 `keyword` 参数不动**（同时搜编码与名称），其他调用方可能在用；
  `keyword` 与 `code`/`name` 同时传时一并生效（AND），不要互相覆盖；
- `short_name` 筛选必须走已有的 `LEFT OUTER JOIN product_material`，
  **不要**为此再拉一遍全量 `product_material`。

⚠️ **`short_name` 筛选与「未填简称」的语义**：`product_material` 是按需创建的，
绝大多数物料没有对应行 → `short_name` 为 NULL。`LIKE` 对 NULL 不匹配，
所以筛 `short_name` 时这些行会被正确排除，符合预期。请确认实现后确实如此。

### 2. 排序

| 参数 | 取值 |
|---|---|
| `sort_by` | `code` / `name` / `short_name` / `group_code`（白名单，其他值一律 `Result.fail('排序字段无效')`） |
| `sort_dir` | `asc` / `desc`，默认 `asc`，非法值按 `asc` 处理 |

要点：
- **必须是白名单校验**，不能把参数直接拼进 `order_by`（SQL 注入面）；
- 默认排序保持现在的 `code ASC`，不传参数时行为不变；
- `short_name` 排序涉及 NULL：请统一让 **NULL 排在最后**（无论升降序），
  否则用户按简称排序时会先看到几千行空值。MySQL 里 `ORDER BY col IS NULL, col ASC/DESC` 即可；
- 排序要在 **SQL 层**完成，不要取出来在 Python 里排——那会退回全表加载。

### 3. 与「按大类筛选」路径的关系（重要）

`list_items` 现在有两条路径：

- **未按大类筛选**：走 SQL `LIMIT/OFFSET`，排序直接加进 SQL，**无额外成本**；
- **按大类筛选**（`category` 或 `unclassified`）：需要全量判定大类，
  目前是取 `code, group_code` 两列后在 Python 里过滤分页。
  这条路径上**排序也只能在 Python 侧做**（因为分页边界由大类过滤后的结果决定）。

请在这条路径上：
- 排序键从已取的两列能拿到的（`code` / `group_code`）直接在 Python 排；
- `name` / `short_name` 排序需要额外字段——**把它们一并加进 `with_entities`**
  （仍是轻量列，不要加载完整 ORM 对象），不要为排序退回 `query.all()`；
- 文本筛选（`code`/`name`/`short_name`）本来就能在 SQL 里做，
  应该在**进入大类判定之前**就过滤掉，这样需要判定的行数会大幅减少，是净收益。

## 前端已完成的部分（供你对照契约）

`src/components/material/MaterialItemsPanel.vue` 已改为 `el-table`：

- 列：**ERP 编码 / ERP 名称 / 简称 / 分组 / 大类 / 停用状态**；
- 表头形态与产品库一致：标签 + 排序按钮 + 筛选控件（文本框或下拉）；
- 文本筛选**带 350ms 防抖**（8,089 条，逐字符请求会打爆队列）；
  下拉筛选与排序是明确动作，立即请求；
- 分页 20/50/100 可切，默认 50；
- **点击 ERP 编码打开物料卡片**，卡片已从抽屉改为 `el-dialog`；
- 停用状态列展示 `is_disabled`（最终生效值），
  并在 `is_disabled_override` 非 null 时额外标一个「人工」小标签，
  用于区分「ERP 默认停用」与「人工强制停用/启用」；
- 左侧大类树已按用户要求**移除**，大类改为表格列 + 列筛选；
- 表格正文文字统一为 `#2c2420`（用户反馈原来的浅色看不清）。

## 验收方式

1. 三个文本筛选分别单独生效、且能与下拉筛选叠加（AND）；
2. 四个排序字段升降序都正确，`short_name` 排序时 NULL 恒在最后；
3. `sort_by` 传非白名单值返回明确错误，不产生 SQL 错误；
4. 核对 SQL 条数：未按大类筛选时应仍是「1 条 COUNT + 1 条分页查询 + 1 条 material IN」，
   **不因为新增筛选/排序而退回全表加载**；
5. 按大类筛选路径下，确认 `with_entities` 仍只取轻量列。
