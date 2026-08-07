# 物料价格并入物料卡片 · 研发 BOM「物料查询」模块下线

日期：2026-08-07
交接人：Claude → Codex
分工：**后端 Codex，前端 + 部署 Claude**

## 用户需求原文

> 物料卡片还有一项内容：价格。该价格和研发部BOM处关联。需要把研发部BOM里的物料查询模块取消，
> 把这里的内容融入到物料卡片里。另外"物料清单"表格里需要加一列"价格"，
> 该列只有在"研发部"权限下才显示。

---

## 1. 生产数据现状（我已只读查证，勿凭猜测改）

| 项 | 值 |
|---|---|
| `cost_bom_node` 行数 | **130** |
| `cost_material_price` 行数 | **133**，覆盖 **127** 个节点 |
| `cost_material_supplier` 行数 | **0**（见 §6，是死表） |
| `import_product_raw` 行数 | **8,091** |

也就是说：**8,091 个物料里只有 130 个在成本体系里有身份**，价格覆盖 127 个。
绝大多数物料打开卡片时是"无价格记录"状态，这是常态不是异常。

### 🔴 JOIN 键已实测确定，不要用 `code`

| 候选键 | 匹配 |
|---|---|
| `cost_bom_node.code_with_version` ↔ `import_product_raw.code` | **130 / 130（100%）** |
| `cost_bom_node.code`（去版本） ↔ `import_product_raw.code` | 5 / 130 |

**必须用 `code_with_version`**。有价格的 127 个节点也是 127/127 全部匹配。

### 🔴 排序规则裂缝（老问题，这次又踩在正中间）

```
cost_bom_node          utf8mb4_unicode_ci
cost_material_price    utf8mb4_unicode_ci
product_material       utf8mb4_unicode_ci
import_product_raw     utf8mb4_0900_ai_ci   ← 不一样
```

任何 `cost_bom_node.code_with_version` 与 `import_product_raw.code` 的 JOIN
**必须显式 COLLATE**，否则生产直接 1267 错误：

```sql
ON n.code_with_version = r.code COLLATE utf8mb4_0900_ai_ci
```

ORM 侧同既有约定，用
`db.String(n).with_variant(mysql.VARCHAR(n, collation='utf8mb4_0900_ai_ci'), 'mysql')`。

**SQLite 没有排序规则概念，单元测试一定过，只有真 MySQL 会炸。**
这一条已经害过我们一次（物料库上线当天 500），别再来第二次。

---

## 2. 核心设计决定：价格源保持单一，node 惰性创建

用户说价格"**和研发部BOM处关联**"，即两边是同一份数据，不是两套。

因此**不新建价格表**。价格永远只存 `cost_material_price`，
`cost_bom_node` 作为"该物料在成本体系里的身份"按需创建：

```
卡片打开   → 按 code_with_version 找 node；找不到 → 价格区显示"暂无价格记录"，不建行
用户加价格 → 找不到 node 时**自动创建** cost_bom_node，再插 cost_material_price
```

自动创建时字段从物料库带过来：

| cost_bom_node 字段 | 取值 |
|---|---|
| `code_with_version` | 物料库 `code`（原样） |
| `code` | 去版本后的品号（复用既有 `_strip_version_py`，**不要另写一套**） |
| `name` / `spec` | 物料库 `name` / `spec` |
| `category` | 物料库 `group_name` |
| `node_type` | 由大类推断，见下 |

`node_type` 推断规则（物料库大类是**多标签**，按优先级取第一个命中）：

```
is_semi                → 'semi'
is_finished or is_packaged → 'finished'
其余（含未分类）        → 'material'
```

> 未分类物料占 41%，一律落 `'material'`。这是安全默认：`material` 是
> `cost_bom_node.node_type` 的 default，且成本树里叶子节点就是 material。

⚠️ `cost_bom_node.code` 有 **UNIQUE 约束**。去版本后可能与已有行撞
（例：物料库有 `14WD11001-A01` 和 `14WD11001-B01`，去版本都是 `14WD11001`）。
创建前必须先按 `code` 查，**撞了就复用那一行**，不要插入导致 1062。
这一点务必写测试覆盖。

---

## 3. 权限：`rd:view` / `rd:edit`，后端必须真拦

价格是成本数据，敏感度高于物料基础信息。

| 操作 | 权限码 |
|---|---|
| 看价格（列 + 卡片价格区） | `rd:view` |
| 增删价格、改供应商 | `rd:edit` |

### 🔴 不能只靠前端隐藏

物料库接口挂在 `product_bp`（`product:view`/`product:edit`）。
一个只有 `product:view` 的用户直接 curl `/api/material/items` **必须拿不到价格字段**。

要求：

1. `GET /api/material/items`：仅当请求者有 `rd:view` 时，每行才带
   `latest_price` / `latest_price_source`；无权限时**字段整体不出现**（不是给 null）。
2. `GET /api/material/items/<code>`：同上，另外带 `has_cost_node`（布尔）
   让前端知道该不该显示"添加价格"按钮。
3. 价格的增删改接口独立于物料接口，**自己校验 `rd:edit`**，
   不要依赖调用方已通过 `product:edit`。

`make_blueprint_guard` 是蓝图级的，做不到字段级——需要在 service/route 里
显式判断当前用户权限。参考项目里既有的权限读取方式（`g` 上的用户信息）。

### ⚠️ `view_post_paths` 白名单
若价格查询做成 POST（不建议），记得加白名单，否则 view 权限用户 403。
建议全部用 GET 避免这个坑。

---

## 4. 接口清单

### 4.1 改造既有

**`GET /api/material/items`** — 列表加价格（仅 `rd:view`）

新增可选参数：
- `sort_by=price`（配合既有 `sort_order`）
- `price_state=has|none`（筛"有价格 / 无价格"）

🔴 **性能硬要求**：价格必须是**一条**批量查询，不能每行一查。
照抄 `routes/rd/cost.py:search_nodes` 里已有的写法——
先取本页 20 个 code，一条 SQL 拿最新价：

```sql
SELECT n.code_with_version, p.unit_price, p.source
  FROM cost_bom_node n
  JOIN cost_material_price p ON p.node_id = n.id
 WHERE n.code_with_version COLLATE utf8mb4_0900_ai_ci IN :codes
   AND p.unit_price IS NOT NULL
 ORDER BY n.code_with_version, p.price_date DESC, p.created_at DESC
```

Python 端取每个 code 的第一条即最新。**本次改造后单页查询数不得增加超过 1 条。**

> ⚠️ `sort_by=price` 会破坏这个模型——按价格排序无法只查本页。
> 若实现困难，**允许先不做价格排序**，明确告诉我，我前端就不放排序按钮。
> 不要为了排序把它改成全表 JOIN 后内存分页（8,091 行 × 每次筛选，服务器扛不住）。

**`GET /api/material/items/<code>`** — 详情加 `has_cost_node`、`cost_node_id`、
`latest_price`（均仅 `rd:view`）。

### 4.2 新增（都按 material code 定位，前端不接触 node_id）

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/material/items/<code>/prices` | 价格记录列表（含 `order_no`，同原 `/nodes/<id>/prices`） | `rd:view` |
| POST | `/api/material/items/<code>/prices` | 添加价格；node 不存在时按 §2 自动创建 | `rd:edit` |
| PATCH | `/api/material/prices/<price_id>` | 改 `supplier_name` | `rd:edit` |
| DELETE | `/api/material/prices/<price_id>` | 删除价格记录 | `rd:edit` |
| GET | `/api/material/items/<code>/usages` | 使用记录（同原 `/nodes/<id>/usages`） | `rd:view` |

> 用 material `code` 而不是 `node_id` 做入口，是因为 8,091 个物料里
> 大部分没有 node，前端拿不到 node_id。**内部再翻译成 node_id。**

`source` 语义沿用现有 enum：`bom_import` / `manual` / `bom_calc`。
卡片手动添加一律 `manual`。

### 4.3 下线

`GET /api/rd/cost/nodes`（列表查询）在前端「物料查询」tab 移除后无调用方。
**但请先保留接口**（`/nodes/<id>`、`/nodes/<id>/prices`、`/usages` 等仍被
成本快照/BOM 树用到，不要一起删）。等我确认线上无调用再单独清理。

---

## 5. 需要你确认的一处语义冲突

`cost_bom_node.notes` 和 `product_material.remark` 是**两个不同的备注**：

- `product_material.remark` — 物料卡片的备注，用户在物料库里填的
- `cost_bom_node.notes` — 成本节点备注，原抽屉「基本信息」里可编辑

我的处理：**卡片的「备注」仍只绑 `product_material.remark`**，
`cost_bom_node.notes` 在价格区单独作为「成本备注」展示编辑，
这样两份数据都不丢也不会互相覆盖。

同理 `is_purchased_semi`（外购半成品，仅 semi 有意义）也放在价格区，
不混进卡片基础属性。

如果你认为该合并成一个，先说，别直接改。

---

## 6. 顺带清理：`cost_material_supplier` 是死表

- 表里 **0 行**
- `BomCost.vue` 的抽屉模板里「供应商」tab **已经不存在了**，
  但 `saveSupplier` / `deleteSupplier` / `togglePreferred` / `supplierFormVisible`
  这些函数和 ref 还在（我这次会一并删掉前端死代码）
- 供应商实际存在 `cost_material_price.supplier_name`

后端 `/api/rd/cost/suppliers` 那几个路由（`list_suppliers`/`add_supplier`/
`delete_supplier`/`update_supplier`）在前端死代码删除后就没有调用方了。
**这次先不动**，我部署后确认线上无调用，再单独一轮下线表和路由。
列在这里免得以后忘。

---

## 7. 验收要求（我会在真 MySQL 上跑）

1. **COLLATE**：列表、详情、价格、使用记录四条路径在生产 MySQL 全部无 1267；
2. **JOIN 正确性**：130 个有 node 的物料，价格与原 `/api/rd/cost/nodes` 逐条一致；
3. **惰性创建**：给一个原本无 node 的物料加价格 → 新建 node，字段与物料库一致，
   `node_type` 符合 §2 规则；
4. **UNIQUE 撞码**：构造去版本后同码的两个物料（如 `-A01`/`-B01`），
   分别加价格 → **复用同一 node，不报 1062**；
5. **权限真拦**：只有 `product:view` 的用户 curl 列表和详情
   → 响应里**没有** `latest_price` 字段；调价格增删接口 → 403；
6. **查询数**：列表接口改造前后单页查询数之差 ≤ 1；
7. 回归：BOM 成本快照、BOM 树、成本预估三处价格显示不变。

第 4、5 项请务必写单元测试——第 4 项是 MySQL 独有约束（SQLite 也有 UNIQUE，
这条测试有效），第 5 项是安全边界。第 1 项测试测不到，只能靠我部署时验证。

---

## 8. 我这边同时做的前端

1. `BomCost.vue`：删除「物料查询」tab（`subTab === 'nodes'` 整块）、
   节点详情抽屉、相关 state 与方法，以及 §6 的供应商死代码；
   `subTab` 只剩 `snapshots` / `estimate`。
2. `MaterialCard.vue`：新增「价格」区（价格记录表 + 手动添加 + 使用记录 +
   成本备注），仅 `canViewRd` 显示，编辑操作仅 `canEditRd`。
3. `MaterialItemsPanel.vue`：加「价格」列，仅 `canViewRd` 显示。

我会等你后端提交后再联调部署。前端我可以先按上述契约写好。

---

# ✅ 验收与部署记录（2026-08-07，`0d66115`）

后端已部署。无迁移，Alembic 仍 `20260807_01`。

## 七项验收结果

| 验收项 | 结果 |
|---|---|
| ① COLLATE（真 MySQL） | `price_state=has/none` 双向无 1267；**has 127 + none 7964 = 8091 = 总数**，无遗漏无重叠 ✅ |
| ② 与原研发接口价格一致 | 原接口有价 127 条，物料库口径 **127/127 完全一致**，0 条不一致 ✅ |
| ③ 惰性创建 | 新建 node 的 `code`/`code_with_version`/`name`/`category` 与物料库一致；未分类物料 `categories=[]` → `node_type=material`，符合规则 ✅ |
| ④ UNIQUE 撞码复用 | `01.01.AD16002-S1` / `-S2` 分别加价 → **同 base 只有 1 个 node**，无 1062 ✅ |
| ⑤ 权限真拦 | `include_cost=False` 时 `latest_price`/`latest_price_source`/`has_cost_node`/`cost_node_id`/`cost_notes` **五个字段全部不存在**（不是 null）✅ |
| ⑥ 查询增量 | 3 条 → 4 条，**增量恰好 1** ✅ |
| ⑦ 回归 | 快照 2 / SKU 5 / BOM 行 213 不变；`/health` `/ready` 200 ✅ |

测试：本机 `306 tests, failures=0, errors=44`（全是本机 `WinError 5` 的 tmp 目录问题），
`260 + 44 = 304`，与 Codex 报告一致。

部署：6 个文件 MD5 **逐一比对全部一致**；reload 后 master PID **2106 未变**，无崩溃循环。

## 实现质量评价

两处做得比我要求的更好：

1. **绕开了 COLLATE 风险而非只是加 COLLATE**：价格查询用 Python 列表传 code 走
   `IN (:params)`，比较用列自身排序规则，根本不产生跨表 JOIN。唯一真正跨表的
   `price_state` EXISTS 子查询才加了显式 `.collate()`，并用 dialect 判断保护 SQLite。
2. `_strip_version` 复用 `services.rd.cost_import` 的既有实现，没另写一套。

---

## 🟡 遗留问题：`_strip_version` 把变体码误当版本号（建议修，Codex 接）

### 现象

`_strip_version` 的正则是 `-[A-Z]\d+$`（一个或多个数字），
它在吃掉真版本 `-A01`/`-B02` 的同时，也吃掉了**变体码**：

```
01.01.AD16002-S1   梦境(2018款)-书架(4-3)
01.01.AD16002-S2   梦境(2018款)-书架(4-4)     ← 不同零件
01.01.AD16002-M-C1 梦境(2018款)-桌面(4-1)-红
01.01.AD16002-M-C3 梦境(2018款)-桌面(4-1)-蓝  ← 不同颜色
```

由于 `cost_bom_node.code` 是 UNIQUE，这些物料会被迫共用同一个成本节点，
**因而共用同一份价格**。我在验收 ④ 里实测到了：给 `-S1` 加价 12.3456 后，
`-S2` 的 `latest_price` 也变成 12.3456。

### 影响面（已量化）

| 分类 | 组数 | 物料数 | 共用价格是否正确 |
|---|---|---|---|
| 后缀两位数字（`-A01`/`-A02`/`-B01`，**真版本**） | 561 | **1,366** | ✅ **正确**——同一零件不同图纸版本，价格本就该一样 |
| 后缀一位数字（`-S1`/`-C1`/`-C3`，**变体**） | 27 | **55** | ❌ 不同零件/颜色，价格串了 |

**线上当前实际错误数 = 0**：58 例走 base 回退的物料全部是
`1301050-A02 → 节点 1301050-A01` 这种同零件不同版本，属于设计意图内的正确行为。
`01.01.*` 那批一个节点都还没有，且卡片前端尚未上线，无人能触发。
所以这是**前瞻性风险，不是现网故障**。

### 建议修法：把正则收紧为两位数字

```python
return re.sub(r'-[A-Z]\d{2}$', '', code.strip())
```

**我已实测这个收紧对研发 BOM 零影响**：现有 130 个节点里有 125 个
`code ≠ code_with_version`，收紧后归约结果发生变化的是 **0 个**。
也就是说所有既有节点用的都是两位数版本号，收紧不会让 BOM 导入找不到任何现有节点。

⚠️ 但 `_strip_version` 被 `cost_import.py` 用在约 15 处（节点识别、父子关联、
外购半成品判断等），是研发 BOM 的**节点身份规则**。虽然实测零影响，
仍请你自己复核一遍这 15 处，并补一条测试固定「`-S1` 不再被当版本」这个行为。

### 我没有擅自改的理由

`_strip_version` 属于研发 BOM 域，改它等于改成本体系的节点标识规则。
即使实测零回归，这也不该由部署方顺手改。且是否把 `-S1`/`-C1` 视为
"不同物料"本质上是业务语义问题，需用户确认（我已同步给用户）。

---

## 待确认后再做的收尾

1. `cost_material_supplier` 死表 + `/api/rd/cost/suppliers` 四个路由下线
   （待我删掉前端死代码、确认线上无调用后单独一轮）；
2. `GET /api/rd/cost/nodes` 在「物料查询」tab 下线后无调用方，同上。
