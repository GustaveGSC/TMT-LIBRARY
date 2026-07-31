# 售后工具 · 工单录入（后端），交接 Codex

日期：2026-07-31
状态：待实现
前端：由 Claude 实现，本文档即双方契约
需求来源：用户口述 7 项，见下「需求原文」

## 需求原文

> 售后工具里，先加一个功能：工单录入。该功能具有以下内容：
> 1. 按照流水码生成售后订单号，规则为：当天日期加流水，比如 260731001，该流水号在多个用户共同使用
> 2. 选择售后产品，使用产品库里的产品，具体形式后续再确定
> 3. 选择售后产品的购买日期
> 4. 自动生成售后日期（当天的日期）
> 5. 选择售后原因（售后数据里的售后原因）
> 6. 输入备注
> 7. 选择售后发货物料，（物料库需要重新整理），需要可以输入数量

## 已与用户确认的三项前提

| 问题 | 用户结论 |
|---|---|
| 是否写入现有 `aftersale_case` / `aftersale_case_reason` | **不写入，独立建表**。理由：录入结果后续要导出到真正的 ERP 做发货处理，是业务单据，不是分析数据 |
| 一张单的结构 | **一个产品 + 一个原因 + 多个物料（每个物料带数量）** |
| 物料库来源 | **物料库整理作为独立任务先做完**，本期物料选择留占位 |

### 物料库现状（我已只读核查，供你设计时参考，本期不要实现）

- 现有 `aftersale_shipping_alias` 123 条是**人工口语简称**（「气弹簧」「电源」），
  与 `import_product_raw` 的 ERP 物料名精确重合仅 **1 条** → **不能**用作 ERP 导出的物料源。
- `import_product_raw` 里已有 ERP 售后专用分组 `group_code LIKE '99%'` 共 **599 条**
  （售后_椅类 404 / 售后_灯类 159 / 售后_其他 19 / 售后_桌类 9 / 售后_柜类 8），自带 ERP 编码。
- 原材料（`group_name LIKE '原材料%'` 或 `group_code='03'`）共 **4265 条**，名称未整理。
- 我已导出 `tmp/material-curation/售后发货物料_待整理.xlsx` 交用户筛选定稿。
- **本期物料明细表的外键先留空**，见下文 `material_*` 字段设计。

## 一、建表

两张新表，全部前缀 `aftersale_entry`，与现有售后分析表完全独立。

### `aftersale_entry` — 录入主表

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | Integer | PK, autoincrement | |
| `entry_no` | String(20) | **NOT NULL, UNIQUE** | 售后订单号，如 `260731001` |
| `model_id` | Integer | FK `product_model.id` ON DELETE SET NULL, NULL | 售后产品，取自产品库 |
| `purchase_date` | Date | NULL | 产品购买日期（人工选） |
| `aftersale_date` | Date | **NOT NULL** | 售后日期，服务端取当天，见 §3 |
| `reason_id` | Integer | FK `aftersale_reason.id` ON DELETE SET NULL, NULL | 具体原因 |
| `reason_category_id` | Integer | FK `aftersale_reason_category.id` ON DELETE SET NULL, NULL | 原因分类；`reason_id` 为空时用它 |
| `remark` | Text | NULL | 备注 |
| `status` | Enum | NOT NULL default `'submitted'` | `submitted` / `exported` / `void` |
| `exported_at` | DateTime | NULL | 导出 ERP 的时间，本期不写，先留列 |
| `created_by` | String(100) | NULL | 录入人 username |
| `created_at` | DateTime | NOT NULL default `now_cst` | |
| `updated_at` | DateTime | NOT NULL default/onupdate `now_cst` | |

索引：
```
UNIQUE ix_aftersale_entry_no        (entry_no)
       ix_aftersale_entry_date      (aftersale_date)
       ix_aftersale_entry_status    (status)
       ix_aftersale_entry_created_by(created_by)
```

### `aftersale_entry_material` — 物料明细

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | Integer | PK, autoincrement | |
| `entry_id` | Integer | FK `aftersale_entry.id` **ON DELETE CASCADE**, NOT NULL | |
| `material_code` | String(255) | NULL | ERP 物料编码。物料库定稿前**先存文本快照** |
| `material_name` | String(255) | NULL | ERP 物料名称快照 |
| `material_id` | Integer | NULL, **暂不加外键** | 物料库定稿后再补 FK，见下 |
| `quantity` | Integer | NOT NULL default 1 | 数量，须 > 0 |
| `sort_order` | Integer | NOT NULL default 0 | 明细行顺序 |
| `created_at` | DateTime | NOT NULL default `now_cst` | |

索引：`ix_aftersale_entry_material_entry (entry_id)`

> **`material_id` 为什么先不加外键**：物料库表还没定稿（用户在筛 Excel）。
> 现在加 FK 会指向一张不存在的表，之后改动要再迁移一次。
> 本期存 `material_code` + `material_name` 文本快照即可满足录入与导出；
> 物料库落地后再加一次迁移补 FK 并回填。
> **快照本身也有独立价值**：ERP 物料可能改名，单据应保留下单当时的名称。

关系：`AftersaleEntry.materials = relationship(..., cascade='all, delete-orphan', lazy='select')`

## 二、单号流水分配（本需求最容易出错的地方）

规则：`YYMMDD` + 3 位流水，当天从 `001` 起。示例 `260731001`。
**多个用户共用同一序列**，所以必须服务端原子分配，不能前端算、不能「查 max 再 +1」。

### 建议实现：序列表 + 单语句原子自增

```sql
CREATE TABLE aftersale_entry_seq (
  seq_date DATE     NOT NULL PRIMARY KEY,
  last_seq INT      NOT NULL DEFAULT 0
);
```

分配（一条 UPDATE 拿到新值，不需要显式事务或行锁等待）：

```sql
INSERT INTO aftersale_entry_seq (seq_date, last_seq) VALUES (:d, LAST_INSERT_ID(1))
  ON DUPLICATE KEY UPDATE last_seq = LAST_INSERT_ID(last_seq + 1);
SELECT LAST_INSERT_ID();
```

要点：
- `LAST_INSERT_ID(expr)` 是**会话级**的，并发安全，返回的就是本连接刚写入的值。
- 两条语句必须在**同一个连接**上执行。SQLAlchemy 里用同一个 `connection`，
  不要用 `db.session.execute` 两次而中间可能换连接。
- **不要**用 `SELECT MAX(entry_no)+1`：单 worker 也有多线程（导入任务用后台线程），
  且未来可能加 worker，MAX 方案必然产生重号。
- **分配时机 = 保存时**，不是打开表单时。前端打开表单不预占号，避免废单留空洞。
- 超过 999：不要报错阻塞业务。直接让流水位数自然增长（`1000` → `2607311000`）。
  已在此说明，若用户要求硬上限再改。

### 竞态兜底
`entry_no` 有 UNIQUE 约束。即使分配逻辑出意外，插入也会失败而不是产生重号。
捕获 `IntegrityError` 后**重试一次**（重新分配号），第二次仍失败则返回 `Result.fail`。

## 三、日期语义

- `aftersale_date` **由服务端取当天**（`now_cst().date()`），**不接受前端传入**。
  前端只做展示（灰显不可编辑）。理由：客户端时区/系统时间不可信，且这是单据日期。
- `purchase_date` 由前端传，可为空。
- **不要**在主表存「售后间隔天数」这类派生值。现有 `aftersale_case_reason.days_since_purchase`
  是导入场景的历史设计，这里不需要——需要时 `aftersale_date - purchase_date` 现算即可。

## 四、接口

统一前缀 `/api/aftersale/entries`，权限码沿用 **`aftersale:view` / `aftersale:edit`**
（不要新造权限码，用户没提出独立授权需求；如后续要独立授权再加）。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/aftersale/entries` | `aftersale:view` | 分页列表，支持 `date_start`/`date_end`/`keyword`/`status`/`created_by`/`page`/`page_size` |
| GET | `/api/aftersale/entries/<id>` | `aftersale:view` | 单条详情，含 materials |
| POST | `/api/aftersale/entries` | `aftersale:edit` | 新建，服务端分配 `entry_no` 与 `aftersale_date` |
| PUT | `/api/aftersale/entries/<id>` | `aftersale:edit` | 修改；`entry_no` 与 `aftersale_date` **不可改** |
| DELETE | `/api/aftersale/entries/<id>` | `aftersale:edit` | 删除（明细 CASCADE） |
| GET | `/api/aftersale/entries/next-no` | `aftersale:view` | **仅预览**下一个号，不占号，见下 |

### POST 请求体

```json
{
  "model_id": 123,
  "purchase_date": "2025-06-01",
  "reason_id": 45,
  "reason_category_id": 7,
  "remark": "客户反馈桌腿晃动",
  "materials": [
    { "material_code": "9902BR001-A01", "material_name": "售后_椅类_博睿_靠背蓝色", "quantity": 2 },
    { "material_code": "9901QM001-A01", "material_name": "启明星气弹簧组件（售后用）", "quantity": 1 }
  ]
}
```

校验：
- `materials` 可为空数组（允许先建单后补物料），但每一项 `quantity` 必须是 **正整数**，
  非正整数直接 `Result.fail('数量必须为正整数')`，不要静默改成 1。
- `model_id` / `reason_id` / `reason_category_id` 传了就必须存在，否则 fail。
- `reason_id` 与 `reason_category_id` 同时为空是允许的（草稿式录入），
  但如果 `reason_id` 非空，服务端应用它的 `category_id` 覆盖 `reason_category_id`，保证两者一致。
- `remark` 长度不限（Text），但要 `strip()`；空串存 NULL。

### 响应

`to_dict()` 至少包含：`id, entry_no, aftersale_date, purchase_date, remark, status, created_by, created_at`，
产品侧 `model_id, model_code, model_name, series_name, product_category_name`，
原因侧 `reason_id, reason_name, reason_category_id, reason_category`，
以及 `materials: [{id, material_code, material_name, quantity, sort_order}]`。

字段命名请与 `AftersaleCaseReason.to_dict()` 保持一致（`model_code` / `reason_name` /
`reason_category` 等），前端已有的展示组件可以直接复用。

### `next-no` 的语义务必写清

这个接口**只预览、不占号**，用于表单上灰显「本单号将是 260731003」。
返回 `{ "preview_no": "260731003", "is_preview": true }`。
实际号在 POST 时才分配，**可能与预览不同**（别人先提交了）。
前端我会在提交成功后用响应里的真实 `entry_no` 覆盖显示。
如果你认为这个预览接口价值不大、容易让人误解，可以不实现，告诉我即可，我在前端改为
提交后才显示单号。

## 五、性能与既有约定

- 列表接口必须 `joinedload` 产品与原因关联，**不要 lazy load**：
  `AftersaleEntry → ProductModel → ProductSeries → ProductCategory` 与 `AftersaleReason → category`
  都是 lazy 关系，逐行访问会 N+1。参考 `CLAUDE.md` 性能规范。
- `materials` 用 `selectinload`（一条 IN 查询）而不是 `joinedload`（会放大主表行数）。
- 单页默认 20 条，`page_size` 上限 100。
- **`make_blueprint_guard` 的 `view_post_paths` 白名单**：本模块 POST 都是写操作，
  **不要**加白名单。（这条是提醒你别顺手加——见 memory 里那条踩过的坑。）
- 服务器单 worker + 连接池 5+5，本模块查询量小，但列表接口别在循环里查关联。

## 六、迁移

一个 alembic revision，建三张表（`aftersale_entry`、`aftersale_entry_material`、
`aftersale_entry_seq`），无数据回填。
`downgrade()` 要能干净删掉三张表（注意先删有 FK 的子表）。

部署由我负责：备份 → `alembic upgrade head` → 校验 → `systemctl reload gunicorn` → 功能验证。

## 七、本期不做

- 物料库表本身（用户在筛 Excel，定稿后单独一轮）
- 导出到 ERP 的实现（`status='exported'` / `exported_at` 只是先把列留出来）
- 与 `aftersale_case` 的任何关联或数据合并（用户明确要求独立）

## 八、我的验收方式

1. 核对迁移前后表结构与本文档一致，`alembic current` 正确；
2. **并发压测单号分配**：多线程并发 POST，断言拿到的 `entry_no` 无重复、无跳号；
3. 真实 HTTP 跑完 CRUD，确认 `quantity` 非法值被拒、`entry_no`/`aftersale_date` 改不动；
4. 列表接口看查询条数（确认无 N+1）与响应时间；
5. 清理测试数据。
