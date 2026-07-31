# 物料库后端部署记录 + 一处需 Codex 收口的排序规则漂移

日期：2026-07-31
部署人：Claude
后端提交：`b0ea8f4` → 返工 `08db6e1`
状态：**已部署并通过生产功能验收；排序规则漂移已于同日由 `8c0474b` / revision `20260731_02` 收口。**

---

## 一、必须由 Codex 收口的问题：新表与 `import_product_raw` 排序规则不一致

### 现象

部署后首次生产功能验证，`GET /api/material/items` **直接 500**：

```
(1267, "Illegal mix of collations (utf8mb4_unicode_ci,IMPLICIT) and
        (utf8mb4_0900_ai_ci,IMPLICIT) for operation '='")
SQL: ... FROM import_product_raw
     LEFT OUTER JOIN product_material ON product_material.code = import_product_raw.code
```

### 根因

不是 Codex 写错了，是**库里本来就存在历史排序规则裂缝**：

| 表 | 排序规则 |
|---|---|
| `tmt_db`（库默认） | `utf8mb4_unicode_ci` |
| **`import_product_raw`** | **`utf8mb4_0900_ai_ci`** |
| `product_finished` / `product_model` | `utf8mb4_0900_ai_ci` |
| `aftersale_case` | `utf8mb4_unicode_ci` |
| 迁移新建的三张表 | `utf8mb4_unicode_ci`（跟随库默认，本身没错） |

新表跟随库默认是合理的，但 `list_items` 的 `LEFT JOIN product_material ON code = code`
跨过了这条裂缝，MySQL 拒绝比较。

**为什么本地测试没发现**：测试跑在 SQLite 上，SQLite 没有排序规则概念，
这类缺陷**只有对着真实 MySQL 才会暴露**。这也是生产功能验收不能省的原因。

### 我做的临时处置（生产已生效，但属于 schema 漂移）

两张新表当时都是空表（已先 `SELECT COUNT(*)` 断言为 0），我把 **JOIN 键**对齐到
`import_product_raw` 的排序规则，以解除生产 500：

```sql
ALTER TABLE product_material   MODIFY code       VARCHAR(255)
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL;
ALTER TABLE erp_group_category MODIFY group_code  VARCHAR(64)
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL;
```

（`erp_group_category.group_code` 目前只在 Python 侧做字典匹配、没有 SQL JOIN，
是**预防性**对齐——将来一旦有人给它加 JOIN 就会踩同样的坑。
`material_disable_keyword.keyword` 只作为 Python 字面量参与 `LIKE`，未改。）

### ✅ 已收口（2026-07-31，Codex 提交 `8c0474b`）

新增 revision **`20260731_02`**，保留已 stamp 的 `20260731_01` 不变，
模型层用 `String(n).with_variant(mysql.VARCHAR(n, collation=...), 'mysql')` 声明，
SQLite 不受影响、测试仍可跑，并补了 DDL 编译断言测试。
**未改动 `import_product_raw`**，符合要求。

部署选择：**实跑 `upgrade` 而非 `stamp`**。
迁移内容与我手工那两条 ALTER 完全等价，所以在生产上是幂等空操作；
实跑能顺带验证迁移本身可用，而 `stamp` 只记版本不执行、验证不到。
结果：`20260731_01` → **`20260731_02 (head)`**，排序规则核对一致，
master PID 2091 未变，功能复验数字（8,089 / 3,026 / 3,353 / 43）与修复前完全一致，
确认无副作用。**schema 漂移已消除，全新环境 upgrade 后即为正确状态。**

以下为当时提给 Codex 的要求，留档：

### 需要 Codex 做的

**这两条 ALTER 现在只存在于生产库，不在任何迁移里** ——
全新环境（本地、测试、将来重建生产）执行 `alembic upgrade head` 得到的仍是
`utf8mb4_unicode_ci`，一跑就 500。必须回写：

1. 在**模型层**显式声明 JOIN 键的排序规则，让 ORM 与迁移自动带上，例如
   `db.Column(db.String(255).with_variant(mysql.VARCHAR(255, collation='utf8mb4_0900_ai_ci'), 'mysql'), ...)`
   （具体写法你定，要求是 MySQL 下生成带 COLLATE 的 DDL，SQLite 下不受影响、测试仍可跑）；
2. 追加一个新的 revision 做这两条 `ALTER`（**不要改已应用的 `20260731_01`**，
   生产已经 stamp 到它了）；该 revision 在生产上执行等价于空操作，正是我们要的效果；
3. `downgrade()` 里不必回退排序规则（表会被整张删掉）。

**请勿**改 `import_product_raw` 的排序规则去迁就新表：它有 8,089 行、
被产品库/发货/售后多处引用，改它的风险远大于改两张空表。

### 建议顺带考虑（非本次必须）

`product_finished` / `product_model` 也是 `0900_ai_ci`，而 `aftersale_case` 是 `unicode_ci`。
库里这条裂缝是历史遗留，将来任何新增的跨表 JOIN 都可能踩到。
建议在 `.claude/modules/database.md` 里记一条：
**新建表若要与 `import_product_raw` / `product_finished` / `product_model` JOIN，
JOIN 键必须显式声明 `utf8mb4_0900_ai_ci`。**

---

## 二、部署过程记录（已完成）

| 步骤 | 结果 |
|---|---|
| 数据库备份 | `backups/tmt_db_before_material_20260731_162730.sql`，532M，`Dump completed` 已核对 |
| 后端文件上传 | 13 个文件（tar 打包，避免多文件 scp 互相覆盖） |
| MD5 校验 | 5 个关键文件本地与服务器逐一比对一致 |
| Alembic | `20260729_01` → **`20260731_01 (head)`** |
| 表结构核对 | 三张新表就位；`product_material.is_disabled` 为 `tinyint(1) NULL`（三态）；`import_product_raw` 新增 `spec`/`raw_name`/`status` |
| 预置数据 | `material_disable_keyword` 两条：`停用`、`作废`（均启用）；`erp_group_category` 与 `product_material` **为空**，未预置任何业务判断 ✓ |
| 服务重载 | `systemctl reload`，master PID **2091 未变**（优雅替换非冷启动）；8 秒后二次复查仍 active |
| 日志 | SIGHUP → 新 worker 13777 启动 → 旧 worker 2113 退出，无崩溃、无重启循环 |
| 健康检查 | `/health` `/ready` 均 200 |
| 路由可达 | 四个新接口未带 token 返回 401（非 404/500） |

## 三、生产功能验收结果（排序规则修复后）

在生产 app context 中直接调服务层（路由是薄封装），并与我此前对真实导出文件的
独立统计交叉验证：

| 检查项 | 实测 | 交叉验证 |
|---|---|---|
| 列表总数 | 8,089 | = 库中实际行数 |
| `category=material` | 3,026 | = 我独立按规则统计的 3,026 ✓ |
| `unclassified` | 3,353 | = 我独立统计的「未命中任何规则」3,353 ✓ |
| 分组数 | 67（含 PCS 34 条） | 重导前 PCS 仍在，符合预期 |
| 被前缀例外覆盖 | 4,736 | = 58% 命中率，与规则覆盖统计一致 |
| 仅停用 / `disable-preview.keyword_hit` | 43 | = `name LIKE '%停用%'` 42 + 「作废」1 ✓ |
| `status_inactive` | 0 | 正确：重导前 `status` 全为 NULL |
| 含斜杠编码详情 | 成功 | `01.99.CD01001/CD02001-（3-2）-C1` 可访问 |
| 关键词搜索「气弹簧」 | 52 | — |

P0 表头修复用**用户提供的真实导出文件**（`123.xlsx`，8,086 行）实跑解析器验证：
`group_code` 无空值、`status` 读出 生效 7,821 / 失效 265（与我独立统计完全一致）、
**`group_code` 去重 66 且 PCS 归零**。

含斜杠编码的三条路由（detail / PUT / image）在 `<path:code>` 下均正确解析，
`/image` 子路径未被贪婪匹配吞掉（已用 `test_request_context` 实测）。

## 四、尚未生效、需要一次重导才能启用的功能

`import_product_raw.raw_name` 与 `status` 对既有 8,089 行**都是 NULL**，
所以下列能力目前处于「已上线但近乎空转」状态：

- **按 ERP 状态判定停用**：`status_inactive` 现在是 0，重导后会变成约 265；
- **按名称关键词判定停用**：现在只有 43 条（靠 `coalesce(raw_name, name)` 回退到已被
  `_clean_name` 清洗过的 `name`），重导后会跳到约 2,900 条（并集 36.1%）。

`coalesce` 回退设计是对的——不会报错，只是命中少。**要真正启用需要用户重新导入一次 ERP 数据**。
重导同时会：修正 34 条 PCS 脏数据（伪分组 `PCS` 消失，分组数 67 → 66）、
回填 `spec`（约 5,026 行有值）、回填 `raw_name` 与 `status`。

⚠️ **重导会更新约 8,000 行**（差异比较含 `spec`/`raw_name`/`status`，而库里这三列全为 NULL），
耗时会明显长于以往。gunicorn 当前 `--timeout 1800`，按经验应该够，但导入时留意别撞看门狗。

## 五、我这边待做的前端

- 「停用规则」子 tab：关键词 CRUD + 命中条数实时预览（接 `/api/material/disable-preview`）
- 物料卡片的图片上传按钮（接 `{data_url, orig_data_url}`）
- 三态停用的 UI 表达：区分「默认停用」与「人工停用/人工启用」
  （接口已返回 `is_disabled` 最终值与 `is_disabled_override` 人工值）
- 「显示已停用」开关提到更显眼位置——默认停用比例将达 36.1%
- 导入数据界面从产品库搬迁（含表头校验失败的错误提示）
