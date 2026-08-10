# 清理 `cost_material_supplier` 死表与死路由

日期：2026-08-10
交接人：Claude → Codex
分工：**后端 Codex，部署 Claude**

供应商主数据（`material_supplier`）已上线并验收通过，旧的按节点报价机制彻底作废。

---

## 🔴 先更正我之前写错的一句

我在 `2026-08-07-codex-material-supplier.md` §8 里写过：

> - 路由 `GET /api/rd/cost/nodes`（「物料查询」tab 已下线）
>   ……以下已确认无前端调用方

**这句是错的。`/api/rd/cost/nodes` 仍在被调用，绝对不能删。**

我当时只核对了「物料查询」tab 不再调它，漏掉了**成本预估** tab
（`BomCost.vue`，都在 `subTab === 'estimate'` 里）：

| 位置 | 调用 | 用途 |
|---|---|---|
| `BomCost.vue:402` | `GET /api/rd/cost/nodes?q=…&node_type=finished` | 参考模式：搜快照里的成品 SKU |
| `BomCost.vue:459` | `GET /api/rd/cost/nodes?q=…` | 自由模式：搜物料 |
| `BomCost.vue:412` | `GET /api/rd/cost/nodes/<id>/usages` | 参考模式：取节点使用记录 |

**这三个都要保留。** 本次清理不碰 `/nodes` 家族的任何路由。

---

## 本次清理范围（已逐项核实）

### 1. 删表 `cost_material_supplier`

生产实测（2026-08-10 删表前）：

```
行数 = 0
指向它的外键 = 无
```

它自己有一个指向 `cost_bom_node` 的外键（`cost_material_supplier_ibfk_1`），
删表时会随表一起消失，不影响 `cost_bom_node`。

需要一个新迁移（`20260810_02`）：

- `upgrade`：`op.drop_table('cost_material_supplier')`
- `downgrade`：**必须能原样重建**（含 `node_id` 外键 `ON DELETE CASCADE`、
  `ix_cost_material_supplier_node_id` 索引），照抄生产现有 DDL：

```sql
CREATE TABLE `cost_material_supplier` (
  `id` int NOT NULL AUTO_INCREMENT,
  `node_id` int NOT NULL,
  `supplier_name` varchar(64) NOT NULL,
  `unit_price` decimal(12,4) NOT NULL,
  `price_date` date DEFAULT NULL,
  `is_preferred` tinyint(1) NOT NULL,
  `notes` text,
  `created_by` varchar(64) DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_cost_material_supplier_node_id` (`node_id`),
  CONSTRAINT `cost_material_supplier_ibfk_1` FOREIGN KEY (`node_id`)
    REFERENCES `cost_bom_node` (`id`) ON DELETE CASCADE
) COLLATE=utf8mb4_unicode_ci
```

⚠️ `downgrade` 只恢复结构，**不可能恢复数据**——这里可以接受，因为表是 0 行。
请在迁移的 docstring 里写明这一点。

⚠️ 迁移里请**先判断表是否存在**再 drop（`sa.inspect(...).get_table_names()`），
和你 `20260810_01` 里的写法一致，免得在没建过这张表的环境上炸。

### 2. 删 4 个死路由（`backend/routes/rd/cost.py`）

源码里已确认**零调用方**（`grep -rn "cost/suppliers" src/` 无命中）：

| 路径 | 函数 |
|---|---|
| `GET /api/rd/cost/suppliers` | `list_suppliers` |
| `POST /api/rd/cost/suppliers` | `add_supplier` |
| `DELETE /api/rd/cost/suppliers/<id>` | `delete_supplier` |
| `PATCH /api/rd/cost/suppliers/<id>` | `update_supplier` |

> 说明：`out/renderer/` 里有历史命中，那是**旧的 Electron 构建产物**，
> 不是源码；桌面端已于 2026-07-21 停止支持，不作为保留依据。

### 3. 删模型与其关联

- `backend/database/models/rd/cost.py`：删 `class CostMaterialSupplier`
- 同文件 `CostBomNode.suppliers` 的 `db.relationship('CostMaterialSupplier', …)`
- `CostBomNode.to_dict()` 的 `include_suppliers` 分支与形参

🔴 **连带点**：`routes/rd/cost.py:get_node` 目前是
`node.to_dict(include_suppliers=True)`。删掉形参后这里会 **TypeError**，
必须一起改成 `node.to_dict()`。

`GET /nodes/<id>` 本身源码里已无调用方，但它属于 `/nodes` 家族、成本快照
将来可能用到，**保留路由**，只去掉 `include_suppliers`。

### 4. 同步这些引用点

| 文件 | 处理 |
|---|---|
| `backend/scripts/create_cost_tables.py` | 去掉 import 与建表列表里的 `CostMaterialSupplier.__table__` |
| `backend/tests/test_material_prices.py` | fixture 里建表清单去掉它 |
| `backend/tests/test_rd_route_guards.py` | 路由清单去掉 4 条 suppliers（**保留 nodes 各条**） |
| `.claude/modules/database.md` / `api.md` | 同步删除对应条目 |

---

## 验收要求

1. `alembic upgrade head` 后 `cost_material_supplier` 不存在，
   且 `cost_bom_node` / `cost_material_price` 结构与数据不变；
2. `alembic downgrade -1` 能重建该表（结构与上面 DDL 一致），再 `upgrade` 又能删掉；
3. 4 个 suppliers 路由返回 404（不再注册）；
4. **`/api/rd/cost/nodes`、`/nodes/<id>`、`/nodes/<id>/usages` 全部仍然可用**——
   这是本次最重要的回归项，因为成本预估依赖它们；
5. `get_node` 不再报 TypeError；
6. 全量测试通过（提醒：跑测试请带 `--basetemp`，否则本机会有大量假 error）；
7. Alembic 保持单头。

第 2、4 项请写测试。第 4 项尤其重要 —— 我上一轮正是在这里判断错了。

---

## 部署注意（我这边）

- 有迁移且是 **DROP TABLE**，部署前照例整库备份 + 校验 `Dump completed`；
- 删表前我会再查一次行数，**只要不是 0 就中止**，不会凭这份文档的旧数据下手。

---

# ✅ 验收与部署记录（2026-08-11，`4b6da8a`）

已部署。含迁移 `20260810_02`（**DROP TABLE**），Alembic 单头。

## 部署过程

| 步骤 | 结果 |
|---|---|
| **删表前复查行数** | **0**（不是 0 就会中止；没凭交接文档的旧数据下手）✅ |
| 备份 | 545M，`Dump completed on 2026-08-11 6:35:05` ✅ |
| 上传 | 4 个文件，MD5 逐一比对一致 ✅ |
| 迁移 | `20260810_01 → 20260810_02 (head)` ✅ |
| reload | master **2198 全程未变** ✅ |
| 健康检查 | `/health` `/ready` 200 ✅ |

## 验收

| 验收项 | 结果 |
|---|---|
| 表已删除 | `information_schema` 中 `cost_material_supplier` 计数 **0** ✅ |
| 邻表未受影响 | `cost_bom_node` **130** / `cost_material_price` **133** / `material_supplier` **1**，全部不变 ✅ |
| 旧路由 | `/api/rd/cost/suppliers` → **404**（已不注册）✅ |
| **活路由仍在** | `/nodes`、`/nodes/1`、`/nodes/1/usages`、`/snapshots` 全部 **401**（需鉴权，说明路由存在且不是 500）✅ |
| **成本预估真实路径** | 自由模式 `q=14` → total **108**、本页 20 条中 **17 条带价**、查询 **3 条**；参考模式 `node_type=finished` → total **5**（1101LH04-A 等）✅ |
| `get_node` 无 TypeError | `success=True`，响应**不再含 `suppliers` 键** ✅ |
| 价格口径一致 | `/nodes` 与物料库 `latest_for_materials` 对 20 个码**逐一一致，0 个偏差** ✅ |

测试：`312 tests / 310 passed / 2 skipped / 0 errors / 0 failures`（带 `--basetemp`）。

## 关于 Codex 多做的那处改动 —— 是对的，而且因果链值得记

Codex 顺手把 `search_nodes` 的最新价查询从裸 SQL 改成了 SQLAlchemy `in_()`：

```python
# 旧
sql_text("... WHERE node_id IN :ids ...")，{'ids': tuple(node_ids)}
# 新
CostMaterialPrice.node_id.in_(node_ids)
```

我没要求这个改动，但它**修掉了一个潜伏缺陷**：`text()` 里的 `:ids` 传 tuple
并不会真正展开成 `IN (...)`，需要 `bindparam(expanding=True)`；它此前能工作
纯粹是因为 **PyMySQL 恰好把 tuple 渲染成 `(1,2,3)`**。换驱动或换库就会坏。

因果链：**我在交接里把「必须写测试证明 `/nodes` 仍可用」列为最重要的验收项，
那个测试跑在 SQLite 上，于是立刻暴露了这处不可移植的写法。** 如果我当时只写
「保留 /nodes 别删」而没要求写测试，这个缺陷会继续潜伏。

排序键（`node_id, price_date DESC, created_at DESC`）与改动前完全一致，无行为变化；
生产实测价格与物料库口径 20/20 一致，印证了这一点。

## 至此物料库这条线全部收口

物料库五个 tab：物料清单（含价格列）/ 售后物料组合 / 供应商 / 编码规则 / 导入数据。
研发 BOM 只剩 成本快照 / 成本预估，物料详情统一走物料卡片。

遗留（优先级最低，已不可达）：`_strip_version` 把 `-S1`/`-C1` 变体码当版本号，
受影响的 55 个物料全在已标为「无用物料」的金蝶组，而无用物料不可加价格，
风险不可达。若将来重新启用金蝶两组需重新评估。
