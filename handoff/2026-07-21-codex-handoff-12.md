# 交接说明 · Claude → Codex（第十二轮，客户简称映射改四态 + 修正内外销判断）

日期：2026-07-21

第十一轮（`handoff/2026-07-21-codex-handoff-11.md` → `2730283`）已审查通过并部署上线，`resolve-all` 也跑完了。但上线后用户实测发现"内销"筛选结果不对（只有27条），排查后发现**我在第十一轮交接文档里自相矛盾**：文档第一节第2条明确说"确认不是外贸"的订单"既不算内销也不算外贸"，但第四节给 Codex 的具体技术指令又把 `trade_type='domestic'` 定义成"命中 `is_export=0` 的映射"——这两处互相矛盾，Codex 是按第四节的技术指令正确实现的，问题出在我这份文档本身自相矛盾，不是实现问题。

跟用户重新确认后，实际业务规则比之前设想的更明确，需要把 `is_export` 布尔字段改成四态，这是这一轮的核心内容。

## 一、`shipping_finance_customer_mapping` 表结构改动

`is_export BOOLEAN NOT NULL DEFAULT false` 改成一个四态字段（枚举/字符串均可，你决定用 MySQL `ENUM` 还是 `VARCHAR` + 应用层校验，前者更省空间，后者迁移更灵活，你选），取值：

| 值 | 中文含义 | 说明 |
|---|---|---|
| `pending` | 未审核 | **默认值**。新简称第一次出现、或者用户还没人工处理过，都是这个状态 |
| `export`  | 外贸客户 | 用户人工确认这是真实外贸订单 |
| `domestic`| 内销客户 | 用户人工确认这是内销订单（哪怕客户简称里带"外贸"字样，也可能审核后发现其实是内销，比如赠品/内部调拨） |
| `excluded`| 确认都不是 | 用户人工审核后，认为这条简称**既不代表外贸也不代表内销**（比如赠品样品、身份不明的贸易公司），这是一个**终态**，标记后不需要再提醒用户复核，和 `pending` 的区别是"已经处理过、主动排除"vs"还没处理" |

### 存量数据迁移（这次唯一的数据变更）

现有 7 条映射记录：
- 4 条 `is_export=true` → 迁移为 `export`
- 3 条 `is_export=false`（`2平米-外贸-赠品样品`、`外贸-Further Trade Ltd`、`外贸-中国-宁波迈芽国际贸易`）→ 迁移为 `excluded`（**不是** `domestic`，也**不是** `pending`——用户已经审核过这三条，明确表示"这不是内销，也不是外贸"，不需要用户重新过一遍）

新迁移里直接用 `UPDATE shipping_finance_customer_mapping SET status = CASE WHEN is_export THEN 'export' ELSE 'excluded' END` 之类的语句一次性转换即可，这张表当前只有个位数记录，没有性能顾虑。

## 二、图表聚合规则更正（覆盖第十一轮里写错的部分）

- `trade_type='foreign'`：`customer_alias` 命中一条 `status='export'` 的映射。
- `trade_type='domestic'`：`customer_alias` 命中一条 `status='domestic'` 的映射（**不是** `excluded`，这是这次要修正的关键错误）。
- `status='excluded'` 和 `status='pending'`（含没有任何映射记录、customer_alias 为空）：两个筛选都不计入，**只在 `trade_type='all'` 里出现**，这一点和第十一轮的设计一致，没有变。
- "地域"/"品牌"标签维度聚合：只统计 `status='export'` 且 `country`/`brand` 非空的记录，这一点也和第十一轮一致，没有变。

## 三、API 改动

`POST /api/shipping/finance-customer-aliases/mapping`：请求体 `is_export`（布尔）改成 `status`（字符串，四选一），后端做合法性校验（拒绝非法值）。`GET /api/shipping/finance-customer-aliases` 返回的 `mapping.is_export` 也相应改成 `mapping.status`。

**这是一次破坏性接口改动（字段类型都变了），前端我这边会同步改，麻烦改完直接更新 `api.md` 精确写清楚四个取值和含义，我照着文档改前端，不需要你等我确认接口细节。**

## 四、这次不需要改的部分

- `shipping_order_finished.customer_alias` 字段、`resolve_orders` 传递逻辑、`get_order_products` 取值逻辑，这些第十一轮都是对的，不用动。
- 索引、迁移的幂等写法照抄第十一轮的风格（先 inspect 再决定要不要执行，`downgrade()` 对称处理）。

## 五、验证要求

- 迁移后核对：4 条 export + 3 条 excluded，一共 7 条，`status` 字段没有 NULL。
- `get_chart_data` 针对 `trade_type='domestic'` 应该返回空（因为目前没有任何一条映射是 `domestic` 状态，用户还没标注过真正的内销客户）——这是预期行为，不是 bug，麻烦在交接文档里明确写一句，避免我下次看到"内销数据是空的"又去排查半天。
- 照例 `python -m pytest` + `compileall` + `git diff --check`；建议补一条测试专门验证"`excluded`/`pending` 都不进 domestic/foreign 但都在 all 里"，这是这次最容易再次搞错的地方。

## 协作方式

独立 worktree/分支，完成后写交接文档，注明"这次是破坏性接口改动"提醒我前端要同步动。不涉及大批量历史数据变更（只改 7 条映射记录本身），不需要全库备份，但迁移过程建议还是打印一下改动前后的记录做个日志，方便万一要回滚时核对。

## 前端（我这边，等接口定下来就开始）

`FinanceCustomerMapping.vue` 需要改：
1. 默认关键字改成空（不再默认只看含"外贸"的简称）——现在所有客户简称都需要被审核归类，不能只看外贸相关的。
2. "确认外贸"勾选框换成四态单选/下拉（外贸客户/内销客户/确认都不是/未审核）。
3. 加一个"仅看未审核"筛选开关（默认可以考虑开启，方便用户优先处理还没看过的），配合现有分页。
4. 已经是"确认都不是"或已经分类过的，不再需要用户重复处理，筛选里应该能方便地把这些排除掉（复用"仅看未审核"这个开关的反向逻辑即可）。
