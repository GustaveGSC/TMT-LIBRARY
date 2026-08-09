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
