# 供应商主数据管理 · 物料库新增「供应商」页

日期：2026-08-07
交接人：Claude → Codex
分工：**后端 Codex，前端 + 部署 Claude**

## 用户需求原文

> 关于供应商，需要有一个表格单独管理，该表格需要记录供应商关联的物料、物料分组，
> 同时价格处的供应商输入需要可以通过下拉选择来填入

用户已确认关联方式（AskUserQuestion，2026-08-07）：

> **从价格记录自动汇总**

即：**你只维护供应商名单，关联物料与分组由系统从 `cost_material_price` 反推**，
不做手工指定的关联表。新登记但还没报过价的供应商，关联列就是空的，这是预期行为。

---

## 1. 生产数据现状（已只读查证）

| 项 | 值 |
|---|---|
| `cost_material_price` 行数 | **133** |
| 其中 **填了 `supplier_name` 的** | **仅 1 条**（`优固`） |
| 去重供应商名 | **1** |
| `cost_material_supplier` 行数 | **0** |

所以这是**近乎从零开始**，不存在大批量历史数据要迁移。

### `cost_material_supplier` 不要复用

它的结构是「按成本节点的一条报价」（`node_id` + `unit_price` + `is_preferred`），
不是供应商主数据，且 0 行、前端 tab 早已删除。

**这次新建 `material_supplier` 主表，`cost_material_supplier` 维持现状不动**
（下线它和 `/api/rd/cost/suppliers` 四个路由是另一轮独立清理，见文末）。

---

## 2. 表设计

### 新建 `material_supplier`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int PK AI | |
| `name` | varchar(64) **UNIQUE** NOT NULL | 供应商名称，与价格记录关联的业务键 |
| `contact` | varchar(64) NULL | 联系人/电话，可空 |
| `remark` | text NULL | 备注 |
| `created_by` | varchar(64) NULL | |
| `created_at` / `updated_at` | datetime | 用 `now_cst` |

排序规则用库默认 `utf8mb4_unicode_ci`——与 `cost_material_price.supplier_name`
（也是 `unicode_ci`）一致，两者比较不需要 COLLATE。

### `cost_material_price` 加 `supplier_id`

```
supplier_id  int NULL  FK → material_supplier.id  ON DELETE SET NULL  (index)
```

**为什么要加而不只按名字匹配**：供应商改名时，纯字符串关联会让既有价格记录
全部脱钩（它们还存着旧名字）。有了 `supplier_id`，改名只改主表一行即可。

`supplier_name` **保留不删**：
- 它是历史/自由文本值的载体（`supplier_id` 为空时仍要能显示）；
- 研发 BOM 那边读的是它。

写入约定：**只要 `supplier_id` 有值，就同步把 `supplier_name` 写成主表当前名称**，
保证两者不打架。改名时一并 `UPDATE cost_material_price SET supplier_name=新名
WHERE supplier_id=该id`（放同一事务）。

### 迁移

1. 建 `material_supplier`；
2. `cost_material_price` 加 `supplier_id`；
3. **回填**：把现有 1 个去重供应商名（`优固`）插入主表，
   并把对应价格行的 `supplier_id` 指过去。
   写成通用 SQL（按 `DISTINCT supplier_name WHERE supplier_name IS NOT NULL AND <> ''`），
   别硬编码 `优固`——本地和生产的数据可能不同。
4. `downgrade` 要能干净回退（先删列再删表）。

---

## 3. 🔴 汇总查询会踩到排序规则裂缝

关联物料与分组的推导链是：

```
material_supplier.name / id
  → cost_material_price.supplier_id            (unicode_ci ↔ int，OK)
  → cost_bom_node.id                            (int，OK)
  → cost_bom_node.code_with_version
      = import_product_raw.code                 ← 🔴 unicode_ci vs 0900_ai_ci
```

**最后一跳必须显式 COLLATE**，否则生产 1267：

```python
node_code = CostBomNode.code_with_version
if db.session.get_bind().dialect.name == 'mysql':
    node_code = node_code.collate('utf8mb4_0900_ai_ci')
```

照抄你自己在 `MaterialRepository.raw_query` 的 `price_state` 分支里已经写对的
那段（含 dialect 判断，保证 SQLite 测试仍能跑）。

**SQLite 测不出这个问题，只有真 MySQL 会炸。** 这条已经害过我们一次。

---

## 4. 🔴 性能：汇总必须是固定条数，不能按供应商 N+1

供应商数量会长期偏小（现在 1 个，估计几十个量级），但**列表接口不许
每个供应商各查一次关联物料**。

要求：**一条分组聚合查询**拿到全部供应商的汇总：

```sql
SELECT p.supplier_id,
       COUNT(DISTINCT n.id)                  AS material_count,
       GROUP_CONCAT(DISTINCT r.group_code ORDER BY r.group_code) AS group_codes,
       MAX(p.price_date)                     AS last_quote_date
  FROM cost_material_price p
  JOIN cost_bom_node n        ON n.id = p.node_id
  LEFT JOIN import_product_raw r
         ON r.code = n.code_with_version COLLATE utf8mb4_0900_ai_ci
 WHERE p.supplier_id IS NOT NULL
 GROUP BY p.supplier_id
```

⚠️ `GROUP_CONCAT` 默认 `group_concat_max_len` 是 1024 字节，超了会**静默截断**。
分组码很短（4 位左右），几十个分组不会超；但请在 Python 端对返回的分组列表
做长度保护（超过 N 个只展示前 N 个 + 「等 M 个」），不要依赖 SQL 不截断。

主表列表整体查询数目标：**≤ 3 条**（主表 + 汇总 + 分组名映射）。

---

## 5. 接口清单

权限：供应商是成本域数据，与价格同级 —— 看 `rd:view`，改 `rd:edit`。
挂在 `material_cost_bp`（已有 `product:view` 蓝图守卫 + 方法内 `_require_rd`），
沿用你这次已经建立的模式。

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/material/suppliers` | 列表 + 汇总（`material_count` / `group_codes` / `last_quote_date`） | `rd:view` |
| GET | `/api/material/suppliers/options` | **下拉用轻量列表**，只回 `id` + `name`，不带汇总 | `rd:view` |
| GET | `/api/material/suppliers/<id>/materials` | 该供应商的物料明细（`code` / `name` / `group_code` / `group_name` / `unit_price` / `price_date`） | `rd:view` |
| POST | `/api/material/suppliers` | 新建（`name` 必填、去空白、查重） | `rd:edit` |
| PATCH | `/api/material/suppliers/<id>` | 改 `name` / `contact` / `remark`；改名时同步价格行的 `supplier_name` | `rd:edit` |
| DELETE | `/api/material/suppliers/<id>` | 删除 | `rd:edit` |

### 删除语义（请按这个做，别自己发明）

供应商被价格记录引用时**不要级联删价格**——价格是成本数据，
不能因为删了个供应商就消失。

- FK 用 `ON DELETE SET NULL`；
- 删除时若仍有价格引用，**返回一个明确的提示**告诉调用方影响面，
  例如「该供应商仍关联 12 条价格记录，删除后这些记录将保留但不再归属任何供应商」，
  并**需要显式确认参数**（如 `?force=1`）才真正删；
- 不带 `force` 时返回 400 + 上述 message + `data: {price_count: 12}`，
  我前端据此弹二次确认。

### 价格接口的联动

`POST /api/material/items/<code>/prices` 与 `PATCH /api/material/prices/<id>`
新增可选入参 `supplier_id`：

- 传了 `supplier_id` → 校验存在，写入并把 `supplier_name` 同步为主表名称；
- 只传 `supplier_name`（自由文本）→ **自动登记**到 `material_supplier`
  （已存在同名则复用），并回填 `supplier_id`。
  这样下拉候选会随使用自然增长，不用先去供应商页登记一遍。
- 两者都传且矛盾时，**以 `supplier_id` 为准**。
- 传空字符串 → 清空两个字段（允许把供应商摘掉）。

⚠️ 自动登记要注意并发：两个请求同时用同一个新名字会撞 `name` UNIQUE。
按你在 `add_price` 里已经用过的 `IntegrityError` → rollback → 重查复用 的写法处理。

---

## 6. 验收要求（我会在真 MySQL 上跑）

1. **COLLATE**：供应商列表、物料明细两条路径在生产 MySQL 无 1267；
2. **迁移回填**：现有那 1 条 `优固` 价格记录，迁移后 `supplier_id` 非空
   且主表有对应行；`downgrade` 能干净回退；
3. **改名同步**：改供应商名后，既有价格记录的 `supplier_name` 一起变，
   `supplier_id` 不变，卡片里显示新名；
4. **删除保护**：有价格引用时不带 `force` → 400 且带 `price_count`；
   带 `force` → 供应商删除、**价格记录仍存在**且 `supplier_id` 变 NULL；
5. **自动登记**：加价格只传新的 `supplier_name` → 主表新增一行且 `supplier_id` 回填；
   再用同名加一次 → **复用**不新增、不报 1062；
6. **汇总正确性**：`material_count` 与 `/suppliers/<id>/materials` 的条数一致；
   `group_codes` 与那些物料的实际分组去重一致；
7. **查询数**：供应商列表 ≤ 3 条；
8. **权限**：只有 `product:view` 的用户调这些接口 → 403；
9. 回归：物料卡片价格增删改、物料清单价格列、BOM 成本快照不受影响。

第 4、5 项务必写单元测试（删除保护是数据安全边界，自动登记的并发复用是 UNIQUE 语义）。
第 1 项测试测不到，靠我部署时验证。

---

## 7. 我这边同时做的前端

1. 物料库新增「供应商」tab（仅 `canViewRd` 可见），表格列：
   供应商 / 关联物料数（可展开看明细）/ 涉及分组 / 最近报价日期 / 操作；
2. 物料卡片价格区的供应商输入改为**可搜索、可自由创建**的下拉
   （`el-select` + `filterable` + `allow-create`），候选取 `/suppliers/options`；
3. 删除供应商走二次确认，文案用后端返回的 message 与 `price_count`。

---

## 8. 记在这里免得忘：另一轮独立清理

以下已确认无前端调用方，等供应商这条线上线后单独一轮下线：

- 表 `cost_material_supplier`（0 行）
- 路由 `/api/rd/cost/suppliers` 的 `list` / `add` / `delete` / `update`
- 路由 `GET /api/rd/cost/nodes`（「物料查询」tab 已下线）
