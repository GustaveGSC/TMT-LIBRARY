# 物料库模块（后端），交接 Codex

日期：2026-07-31
状态：待实现
前端：由 Claude 实现
方案背景：`2026-07-31-material-library-design.md`（先读它，本文档是可执行契约）

## 需求要点（用户原话摘录）

> 将原来产品库里的导入数据和编码规则迁移到物料库，并重新规划编码规则内容，
> 物料大类一共有以下几类：成品、产成品、半成品、原材料、无用物料
> …
> 之前是通过前缀来区分物料归属，实际上物料本身有分组编码这一项，但我又不放心
> 这个编码是否能够满足我要的分类
> …
> 使用新的表格，目前 bom 数据那边还只是一个半成品，我希望可以重新建一个新表按实际的
> 需求来，到合适的时候再把 bom 那边的数据结合起来

**大类归属是页面配置项，不是开发期常量。** 代码里不得硬编码分组→大类映射，
也不得按分组名关键词自动推导（用户已明确否决这两种做法）。

## 一、已核查的现状（只读查询所得，可直接采信）

| 事实 | 数据 |
|---|---|
| `import_product_raw` | 8,089 条，字段仅 `code`/`name`/`group_code`/`group_name`/`imported_at` |
| `group_code` 去重 | **67 个** |
| `erp_code_rules` | 63 条启用规则，`UNIQUE(prefix, type)` **已支持一个前缀配多个 type** |
| 现有规则覆盖率 | 未命中 **3,353 条（41%）**；material 3,026；semi 873；packaged 352；**finished+packaged 276**；finished 209 |
| `TYPE_SEMI` / `TYPE_MATERIAL` | **死代码**，全后端无任何消费方（grep 确认） |
| `cost_bom_node` | 130 条（material 109 / semi 16 / finished 5） |

### 1.1 `group_code` 单独不足以定大类（这是用户疑虑的答案）

67 个分组中 **9 个内部分类不一致**：

| 分组 | 条数 | 内部分布 |
|---|---|---|
| `1101` 成品_桌类 | 142 | 成品 126 / 成品+产成品 16 |
| `1108` 成品_成人桌 | 93 | 成品+产成品 50 / 未命中 36 / 成品 7 |
| `2001` 外贸成品_桌类 | 65 | 成品 50 / 成品+产成品 15 |
| `1104` 成品_附件类 | 124 | 未命中 111 / 产成品 13 |
| `1102` 成品_椅类 | 52 | 成品+产成品 51 / 未命中 1 |
| `3101` 贝视朗成品_灯类 | 31 | 成品+产成品 29 / 成品 1 / 产成品 1 |
| `14WD` 原材料_木器 | 596 | 原材料 595 / 未命中 1 |
| `14ME` 原材料_金属件 | 532 | 原材料 530 / 未命中 2 |
| `PCS`（脏数据） | 34 | 成品 23 / 未命中 9 / 产成品 2 |

区分靠比分组更细的前缀：`1101LA/LD/LH/LS` 是产成品而 `1101SG` 是成品；
`1108` 下挂了 10 条更细规则；`2001JL/LD/LH/LS/LU` 均为产成品。

**成品与产成品必须是多标签，不能做成单选 enum**——276 条兼具是真实业务情况
（用户说明：成品只含一个包装时技术人员省略了产成品层）。

## 二、建表

### 2.1 `erp_group_category` — 分组默认大类（新建）

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | Integer | PK | |
| `group_code` | String(64) | **NOT NULL, UNIQUE** | 对应 `import_product_raw.group_code` |
| `is_finished` | Boolean | NOT NULL default False | 成品 |
| `is_packaged` | Boolean | NOT NULL default False | 产成品 |
| `is_semi` | Boolean | NOT NULL default False | 半成品 |
| `is_material` | Boolean | NOT NULL default False | 原材料 |
| `is_useless` | Boolean | NOT NULL default False | 无用物料 |
| `remark` | String(255) | NULL | |
| `updated_by` | String(100) | NULL | |
| `created_at` / `updated_at` | DateTime | NOT NULL | |

为什么用 5 个布尔列而不是一张多对多关联表：大类是**固定的 5 个**、不会增删，
布尔列查询和配置都最直接，也避免为 67×5 的小数据引入关联表和额外 JOIN。
若你认为 `Enum` 数组或 JSON 更好，可以提出，但**不要用单个 enum 列**。

**不要预置任何种子数据。** 表建好后全部为空 = 全部「未分类」，由用户在页面上配。

### 2.2 `product_material` — 物料主数据（新建）

用户明确要求**新建表**，不复用 `cost_bom_node`。

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | Integer | PK | |
| `code` | String(255) | **NOT NULL, UNIQUE** | ERP 编码，与 `import_product_raw.code` 同值 |
| `short_name` | String(255) | NULL | **简称**，人工维护，录入/挑选时显示 |
| `category` | String(100) | NULL | 人工维护的物料分类（自由文本，非大类） |
| `spec` | String(512) | NULL | 规格，见 §4.2 |
| `cover_image` | String(500) | NULL | 图片 OSS URL |
| `cover_image_original` | String(500) | NULL | 原始高清图 |
| `img_updated_at` | Integer | NULL | 缓存破坏用时间戳 |
| `remark` | Text | NULL | |
| `is_disabled` | Boolean | NOT NULL default False | 停用（不进后续选择候选） |
| `created_at` / `updated_at` | DateTime | NOT NULL | |

索引：`UNIQUE(code)`、`ix_product_material_disabled(is_disabled)`

要点：
- **不要把 `name` / `group_code` / `group_name` 复制进这张表**。它们是 ERP 权威数据，
  归 `import_product_raw` 所有，重新导入时会更新；复制会产生两份真相。
  查询时按 `code` 关联取用即可。
- 这张表只存**人工附加的属性**。8,089 条物料里绝大多数不需要人工维护，
  所以**按需创建行**（用户第一次给某物料填简称/传图才 INSERT），不要预先灌 8,089 条空行。
- 图片字段参考 `ProductFinished.cover_image` 的既有 OSS 实现，不要另造一套。

### 2.3 `erp_code_rules` — 保持不动

结构不改、数据不动、**接口路径也不要改**（原因见 §3.1）。
现有 63 条规则原样保留，它们已把 `1101LA` 是产成品这类区分编码在内，不需要重录。

## 三、大类判定服务

```
判定(code) -> set[大类]:
    1. 前缀例外：erp_code_rules 中所有 prefix 能 startswith 匹配 code 且未禁用的，
       取其 type 集合。命中则**直接返回**（可多标签）。
    2. 分组默认：按 code 所属的 group_code 查 erp_group_category，
       返回其勾选的大类集合。
    3. 都没有 → 返回空集，前端呈现为「未分类」。
```

注意：`erp_code_rules.type` 现有取值只有 finished/packaged/semi/material，
**没有 useless**。需要给 `VALID_TYPES` 增加 `TYPE_USELESS = 'useless'`，
这样前缀例外也能把某些编码标成无用物料。`TYPE_LABELS` 同步加「无用物料」。

顺带说明：`TYPE_SEMI` / `TYPE_MATERIAL` 目前是死代码，本模块就是它们的第一个消费方。

### 3.1 性能：不要在保存配置时全量重算

要判定的是 8,089 条。规则总量很小（63 条前缀 + 67 条分组 ≈ 130 条），
所以**在查询时实时判定**，把规则集缓存到模块级内存（参考
`get_chart_options` 的缓存做法，并在规则增删改后主动失效）。

**禁止**：
- 在保存规则/分组配置的请求里同步重算并回写 8,089 条（单 worker 会被长时间占满）；
- 在列表接口里对每条物料单独查规则（N+1）。规则集必须一次性加载后在内存里匹配。

前缀匹配请**按前缀长度降序**排列后匹配，与 `backend/routes/rd/cost.py:330` 的既有做法一致
（那里已经是 `ORDER BY LENGTH(prefix) DESC`）。

## 四、两个已定位的既有缺陷（本轮一并修）

### 4.1 导入解析列错位（用户提到的「导入的时候错位了」——已查清根因）

`backend/routes/product/import_raw.py` 用**硬编码列索引**解析 Excel：

```python
_COL_CODE = 0; _COL_NAME = 1; _COL_SPEC = 2; _COL_GROUP_CODE = 7; _COL_GROUP_NAME = 8
```

且**不校验表头**。证据链：
- 生产库 34 条 `group_code='PCS'` 的行，**全部来自单一批次 `2026-07-23 10:55:22`**
  （该批次共导入 34 行，全部错位）；
- 这些行 `group_code='PCS'`（PCS 是**单位**，pieces），`group_name='1509'`（才是真正的分组编码）；
- 即该次 Excel 的列相对标准布局**整体偏移一列**。
- 用户已核对源 Excel 内容是正确的 → 问题在解析端。

**修法**：读表头行，**按表头名称映射列**，而不是固定索引；
必需列缺失时**明确报错中止导入**，不要静默继续产出脏数据。
表头名称请从生产实际的 ERP 导出文件确认（我可以协助取样）。

同时需要**清理已产生的 34 条脏数据**——但这是数据修正，
请在迁移里单独写清楚做了什么，或提供一个一次性脚本放 `backend/scripts/`，
由我执行并核对。**不要在 `upgrade()` 里悄悄改业务数据。**

### 4.2 `spec` 被拼进了 `name`

`services/product/import_raw.py` 的 `_clean_name(name, spec)` 把规格**拼接到名称末尾**：

```python
return f"{cleaned} {spec}" if spec else cleaned
```

这是物料名称极长的原因之一（如
`原材料_金属件_铁件_桌腿钢架 TS14120H __M101（哑光白）_A01`）。

**处理方式**：给 `import_product_raw` 增加独立的 `spec` 列并单独存一份。

⚠️ **但不要改 `name` 的现有组成**。`name` 的当前形态是承重的：
售后语义匹配、物料简称关键词匹配等多处逻辑都建立在它之上，
改变名称组成会静默影响这些匹配结果。所以是**新增 spec 列**，
`name` 保持原样。`product_material.spec`（§2.2）可从这里取默认值。

## 五、接口

### 5.1 编码规则相关（迁移 = 只搬前端界面，接口路径不动）

`/api/erp-code-rules/` **保持现有路径与行为**。原因：
- `backend/routes/rd/cost.py:333` 直接读 `erp_code_rules` 做最长前缀匹配取 description，
  BOM 成本功能依赖它；
- `src/stores/product/finished.js:205` 与 `src/views/productViews/ProductRules.vue` 在调用。

改路径会波及 BOM 成本逻辑且没有任何收益。**迁移由我在前端完成**：
把 `ProductRules.vue` 的界面搬到物料库模块下，接口调用不变。
你只需要给 `type` 增加 `useless` 取值（§3）。

### 5.2 分组默认大类配置（新增）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/material/group-categories` | `product:view` | 返回**全部 67 个分组**：`group_code`、`group_name`（可能一码多名，见 §6）、`material_count`、已配大类、`override_count`（该分组内被前缀例外覆盖的条数） |
| PUT | `/api/material/group-categories/<group_code>` | `product:edit` | 保存该分组的大类勾选 |

`GET` 必须**一次聚合出 material_count 与 override_count**，不要每个分组查一次
（67 次查询）。

### 5.3 物料列表与详情（新增）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/material/items` | `product:view` | 分页；筛选 `category`(大类)/`group_code`/`keyword`(编码或名称模糊)/`is_disabled`/`unclassified`；返回 ERP 字段 + 大类标签 + `product_material` 的人工字段 |
| GET | `/api/material/items/<code>` | `product:view` | 单条详情（物料卡片用） |
| PUT | `/api/material/items/<code>` | `product:edit` | 保存简称/分类/规格/备注/停用；**行不存在时按需创建**（§2.2） |
| POST | `/api/material/items/<code>/image` | `product:edit` | 上传图片，复用产品库既有 OSS 实现 |

列表接口默认每页 20，`page_size` 上限 100。
`product_material` 用一次 `IN` 批量取（`selectinload` 或先取 code 列表再一次查），
**不要逐行查**。

### 5.4 权限

全部沿用 `product:view` / `product:edit`（主页入口也是按 `product:view` 显示的）。
**不要新造权限码**——用户没提出独立授权需求。
POST 都是写操作，**不要**加进 `make_blueprint_guard` 的 `view_post_paths` 白名单。

## 六、数据质量问题的处理口径（用户已答复）

| 问题 | 用户答复 | 落到实现 |
|---|---|---|
| `13100`（半成品_椅灯类 83 条）会被前缀 `1310` 命中 | 「实际上是 1310 0001 这样的」——即分组 `1310` + 四位流水，`group_code` 存成 `13100` 是切分位置错了 | 这属于 §4.1 同源的解析问题。**先不要自行改数据**，判定逻辑照常按 `group_code` 走；等 §4.1 按表头名映射修好、重新导入后自然纠正。若重新导入后仍是 `13100`，再报给我 |
| `group_code='PCS'` 34 条 | 「导入的时候错位了，但我去查了导入的 excel 文件是对上的」 | 根因已查清，见 §4.1 |
| `1107`/`1108` 一码多名 | 「这个不用纠结，最终由我来确定」 | **不要做任何自动合并或去重**。`GET group-categories` 里把多个名称用「 / 」并列展示即可，配置仍以 `group_code` 为唯一键 |

## 七、本期不做（用户明确表示「先不考虑，后续再做决定」）

- 物料卡片上除图片/简称/分类/规格/备注之外还要放什么
- 「无用物料」是否在页面默认隐藏
- `cost_bom_node` / `cost_material_price` / `cost_material_supplier` 的合并与迁移
  → **本期完全不动**，研发工具的 BOM 成本功能照常运行
- 价格 / 供应商的维护入口搬迁 → 随 BOM 合并阶段一起做
- 售后工单录入（已暂停，见 `2026-07-31-codex-aftersale-entry-backend.md`，该文档暂不生效）

## 八、迁移

一个 alembic revision：
- 新建 `erp_group_category`、`product_material`
- `import_product_raw` 增加 `spec` 列（nullable，不回填——回填需要重新导入）
- `erp_code_rules` 的 `type` 增加 `useless` 取值 → **已确认无需 DDL 变更**：
  该列在生产库是 `varchar(20)`（不是 DB Enum），模型里也是 `db.String(20)`，
  只改 `VALID_TYPES` / `TYPE_LABELS` 常量即可

`downgrade()` 要能干净回退。**不要在迁移里改业务数据**（脏数据清理走脚本，见 §4.1）。

部署由我负责：备份 → `alembic upgrade head` → 校验 → `systemctl reload gunicorn`
→ 确认 master PID 未变、无崩溃 → `/health` `/ready` → 功能验证。

## 九、我的验收方式

1. 迁移前后表结构与本文档核对，`alembic current` 正确；
2. **大类判定正确性**：抽查 §1.1 那 9 个内部不一致的分组，确认前缀例外优先于分组默认、
   且成品+产成品能同时返回；确认未配置的分组返回「未分类」而不是报错；
3. **查询数量**：列表接口与 `group-categories` 接口分别核对 SQL 条数，确认无 N+1、
   无 67 次循环查询；保存配置的请求不触发全量重算；
4. **导入解析修复**：用列布局正确与偏移一列的两份样例 Excel 各跑一次，
   确认前者正常、后者**明确报错而不是静默写入脏数据**；
5. 34 条 PCS 脏数据清理脚本单独执行并核对前后条数；
6. 清理测试数据。
