# 物料库 · 售后物料组合（后端），交接 Codex

日期：2026-08-06
状态：待实现
前端：由 Claude 实现，本文档即双方契约

## 一、需求原文

> 在物料库里加一个「售后物料组合」页面，该页面用于管理物料的组合，
> 方便售后人员在选择售后件时进行快速选择。

即：把常一起寄出的几个物料预先打成一个有名字的包（如「领航员桌腿维修包」＝
桌腿 ×1 + 螺钉 ×4 + 垫片 ×2），售后人员选一次组合，等于选了若干物料。

## 二、已与用户确认

| 问题 | 结论 |
|---|---|
| 组合是否关联「适用产品/型号」 | **不需要**，只靠名称和分类查找 |

所以**不建任何与 `product_model` / `product_series` 的关联表**，结构保持最简。

## 三、建表

### `material_combo` — 组合主表

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | Integer | PK, autoincrement | |
| `name` | String(200) | **NOT NULL, UNIQUE** | 组合名称，如「领航员桌腿维修包」 |
| `category` | String(100) | NULL | 自由文本分类，用于界面分组与筛选 |
| `remark` | Text | NULL | |
| `is_disabled` | Boolean | NOT NULL default False | 停用（不进入后续选择候选） |
| `sort_order` | Integer | NOT NULL default 0 | 人工排序 |
| `created_by` | String(100) | NULL | |
| `created_at` / `updated_at` | DateTime | NOT NULL | |

索引：`UNIQUE(name)`、`ix_material_combo_disabled(is_disabled)`、`ix_material_combo_category(category)`

> `is_disabled` 这里是**普通两态布尔**，不要做成物料那样的三态。
> 物料的三态是因为要区分「跟随 ERP 默认」与「人工覆盖」；
> 组合完全是人工建的，没有 ERP 默认可跟随。

### `material_combo_item` — 组合明细

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | Integer | PK, autoincrement | |
| `combo_id` | Integer | FK `material_combo.id` **ON DELETE CASCADE**, NOT NULL | |
| `material_code` | String(255) | **NOT NULL** | ERP 物料编码 |
| `quantity` | Integer | NOT NULL default 1 | 建议数量，须 > 0 |
| `sort_order` | Integer | NOT NULL default 0 | 明细行顺序 |
| `created_at` | DateTime | NOT NULL | |

索引：`ix_material_combo_item_combo(combo_id)`、
`UNIQUE(combo_id, material_code)`（同一组合内同一物料不允许重复行）

关系：`MaterialCombo.items = relationship(..., cascade='all, delete-orphan', order_by=sort_order)`

### 🔴 排序规则必须显式声明

`material_combo_item.material_code` 要与 `import_product_raw.code` JOIN，
**必须显式声明 `utf8mb4_0900_ai_ci`**，否则会重现 revision `20260731_02` 修过的
「Illegal mix of collations」500。沿用既有写法：

```python
material_code = db.Column(
    db.String(255).with_variant(
        mysql.VARCHAR(255, collation='utf8mb4_0900_ai_ci'), 'mysql'),
    nullable=False,
)
```

⚠️ **这类缺陷只有对着真实 MySQL 才会暴露**（SQLite 没有排序规则概念，
测试会全绿）。请在迁移后自行用 MySQL 验证一次 JOIN。

### 关于 `material_code` 为什么不加外键

与 `aftersale_entry_material` 同样的理由：物料的权威表是 `import_product_raw`，
它会被**整表差异 UPSERT 重导**。给它加外键会让重导受约束牵制。
`material_code` 存值 + 查询时 JOIN 取名称即可。

但**要处理"引用了已不存在的物料"**：重导后某个编码可能消失（ERP 删了）。
详见 §4.2 的失效标记。

## 四、接口

统一前缀 `/api/material/combos`，权限沿用 **`product:view` / `product:edit`**。
不要新造权限码。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/material/combos` | view | 列表，支持 `keyword`（名称模糊）/`category`/`is_disabled`；**含明细** |
| GET | `/api/material/combos/<id>` | view | 单条详情，含明细 |
| POST | `/api/material/combos` | edit | 新建 |
| PUT | `/api/material/combos/<id>` | edit | 修改（**明细整体替换**，见下） |
| DELETE | `/api/material/combos/<id>` | edit | 删除（明细 CASCADE） |
| GET | `/api/material/combos/categories` | view | 已用过的分类去重列表，供下拉候选 |

### 4.1 请求与响应

POST / PUT 请求体：

```json
{
  "name": "领航员桌腿维修包",
  "category": "桌腿",
  "remark": "常见桌腿晃动整套更换",
  "is_disabled": false,
  "sort_order": 0,
  "items": [
    { "material_code": "14ME01001-A01", "quantity": 1 },
    { "material_code": "14ST01010-A01", "quantity": 4 }
  ]
}
```

- **`items` 整体替换**（先删后插），不做逐行 diff —— 明细行少、整体替换最不容易出错；
- `name` 必填、`strip()` 后不能为空、重名返回 `Result.fail('组合名称已存在')`
  （靠 UNIQUE 兜底并捕获 `IntegrityError`，不要只靠先查后插——那有竞态）；
- `quantity` 必须是**正整数**，非法值直接 fail，**不要静默改成 1**；
- `items` 允许为空数组（先建壳后补明细）；
- 同一 `material_code` 在 `items` 里重复出现 → fail，提示具体重复的编码。

响应里每条明细除 `material_code` / `quantity` 外，**还要带上物料的展示信息**：

```json
{
  "material_code": "14ME01001-A01",
  "quantity": 1,
  "material_name": "原材料_金属件_铁件_桌腿钢架 TS14120H __M101（哑光白）_A01",
  "short_name": "桌腿钢架",
  "group_name": "原材料_金属件",
  "is_missing": false
}
```

- `material_name` / `group_name` 取自 `import_product_raw`；
- `short_name` 取自 `product_material`（人工维护的简称，可能为 NULL）；
- 这三个字段**一次 JOIN 拿到**，不要逐条查。

### 4.2 `is_missing`：引用了已不存在的物料

重导后某个 `material_code` 可能在 `import_product_raw` 里查不到。
此时该明细行 `is_missing: true`，`material_name` 为 `null`。

**不要因此报错、也不要自动删除该行** —— 静默删掉用户配置的组合是危险的。
让前端把这一行标红提示，由人工决定。

### 4.3 性能

- 列表接口**必须一次性把所有明细连带物料信息取回**：
  先查符合条件的 combo，再用一次 `IN` 拿全部明细，再用一次 `IN`
  JOIN `import_product_raw` + `LEFT JOIN product_material` 拿展示字段。
  **三条查询固定**，不随组合数量增长。
- **禁止**在循环里查明细或物料（N+1）。组合数量不大，但明细×物料的乘积会放大。
- 组合总量预计几十到几百条，不需要分页；但请在返回里带 `total`，
  将来要分页时前端不用改结构。
- POST 都是写操作，**不要**加进 `make_blueprint_guard` 的 `view_post_paths` 白名单。

## 五、明确不做

- **不支持组合嵌套**（组合里包含组合）。会引入环检测与展开深度问题，
  而售后备件场景用不到。若明细里出现的编码恰好是另一个组合的名字，也不做特殊处理。
- **不与 `aftersale_shipping_alias` 打通**。那 123 条是给自动匹配文本用的
  口语简称词典（「气弹簧」「电源」），与 ERP 名精确重合仅 1 条，两者语义不同。
- **不做「组合展开成 ERP 行」的接口**。将来售后工单录入选了组合后，
  由前端把明细展开成若干物料行提交 —— ERP 不认识我们的组合概念，
  最终导出必须是逐个物料编码。这一步等工单录入恢复时再做。

## 六、迁移

一个 alembic revision，建两张表，无数据回填、无种子数据。
`downgrade()` 先删子表 `material_combo_item` 再删 `material_combo`。

部署由我负责：备份 → `alembic upgrade head` → 校验 → `systemctl reload gunicorn`
→ master PID 与日志核对 → `/health` `/ready` → 真实 HTTP 功能验证。

## 七、我的验收方式

1. 迁移前后表结构核对，`alembic current` 正确；
2. **MySQL 上实测 JOIN**（排序规则声明是否生效），不只跑 SQLite 测试；
3. CRUD 全流程：重名被拒、`quantity` 非法值被拒、`items` 内重复编码被拒；
4. 明细整体替换语义正确（改完不残留旧行）；
5. 删除组合后明细被 CASCADE 清掉，不留孤儿；
6. `is_missing`：手工造一条引用不存在编码的明细，确认返回 `true` 且不报错、不自动删除；
7. 列表接口 SQL 条数固定为 3 条，不随组合数增长；
8. 清理测试数据。

## 八、前端我会做的（供对照）

物料库新增第三个 tab「售后物料组合」：

- 左侧组合列表（按分类分组、可搜索、显示明细条数），右侧选中组合的明细编辑；
- 明细行：物料选择器（复用 `/api/material/items` 的搜索，**默认限定原材料大类**）
  + 数量输入 + 拖拽排序 + 删除；
- 顶部「新建组合」，名称/分类/备注/停用 就地编辑；
- 与分组默认大类那边一致的「有未保存改动」提示条 + 保存/放弃。

⚠️ 一个现状要提醒：**大类配置目前一条都没配**（`erp_group_category` 为 0 行），
所以 8,091 条物料里 3,354 条是「未分类」。如果明细的物料选择器默认只显示原材料，
那些未分类的物料会选不到。我会在选择器里默认放开全部大类、
并把大类做成可选筛选，等你把分组大类配起来之后再考虑收紧默认值。

---

# ✅ 验收与部署记录（2026-08-07，`6e4ae93` / revision `20260807_01`）

## 关键项：排序规则这次没再踩坑

```
material_combo_item.material_code → utf8mb4_0900_ai_ci   ✅
material_combo.name/category/remark/created_by → utf8mb4_unicode_ci（库默认，正确）
```

只有参与 JOIN 的 `material_code` 对齐到 `import_product_raw`，其余跟随库默认——
正是契约要求的做法。同一个坑（revision `20260731_02` 修过的 collation 500）第二次没有重现。

## 七项功能验收（生产真实数据）

| 验收项 | 结果 |
|---|---|
| 新建含真实物料 + 不存在物料 | ✅ JOIN 取到 `原材料_金属件_铁件_桌腿钢架 TS14120H…` |
| **`is_missing`** | ✅ `NOT-EXIST-XYZ` → `is_missing: true`、`material_name` 空，**不报错、不自动删除** |
| 重名 | ✅ 「组合名称已存在」 |
| 数量为 0 | ✅ 「物料「14ME01001-A01」的数量必须是正整数」 |
| items 内重复编码 | ✅ 「物料编码「14ME01001-A01」重复」 |
| 明细整体替换 | ✅ 替换后只剩 1 条，无旧行残留 |
| **列表 SQL 条数** | ✅ **固定 3 条**，与契约一致 |
| CASCADE 删除 | ✅ 明细 1 → 0，无孤儿 |

测试数据已全部清理，`material_combo` 剩余 0 条。

## 部署过程

| 步骤 | 结果 |
|---|---|
| 数据库备份 | `backups/tmt_db_before_combo_20260807_144150.sql`，547M，`Dump completed` 已核对 |
| 上传 | 6 个文件（tar 打包），MD5 逐一比对一致 |
| Alembic | `20260731_02` → **`20260807_01 (head)`** |
| reload | master PID **2106 未变**（优雅替换）；日志干净 |
| 健康检查 | `/health` `/ready` 均 200；`/api/material/combos` 401（鉴权正常） |
| 测试 | 256 passed + 44 errors（本机 `tmp_path` 权限），`256+44=300` 与 Codex 报告一致 |

## 前端现状

`b05e0cb` 已上线，「售后物料组合」tab 现在**功能完整可用**。

物料选择器仍**未限定大类**——`erp_group_category` 目前 0 行，
8,091 条里 3,354 条「未分类」，限定后会大量选不到。界面上有提示。
等分组默认大类配起来后可以收紧默认值。
