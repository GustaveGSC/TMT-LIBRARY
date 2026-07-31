# 物料库后端 b0ea8f4 · 审查结论与待修项

日期：2026-07-31
审查人：Claude
结论：**暂不部署**。P0 会让 ERP 导入 100% 失败。
基线：`2026-07-31-codex-material-library-backend.md`（原契约）

---

## P0 · 表头别名对不上真实导出，导入必然失败

用户提供了真实导入文件（`C:\Users\gusta\Desktop\123.xlsx`，8,086 行，单 sheet）。
实测表头 13 列：

| 索引 | 表头 | 对应字段 |
|---|---|---|
| 0 | 品号 | code |
| 1 | 品名 | name |
| 2 | 规格 | spec |
| 3 | 品号描述 | — |
| 4 | 归类品 | — |
| 5 | 计量体系 | — |
| 6 | **单位名称** | —（值为 `PCS`，见 §附录） |
| 7 | **品号群组** | **group_code** |
| 8 | **群组名称** | **group_name** |
| 9 | 批号管理 | — |
| 10 | 序列号管理 | — |
| 11 | 图号 | — |
| 12 | **状态** | —（值为 `生效` / `失效`，见 P3） |

对照 `routes/product/import_raw.py` 的 `_HEADER_ALIASES`：

| 字段 | 真实表头 | 现有别名 | 结果 |
|---|---|---|---|
| code | 品号 | 品号 / 物料编码 / 编码 | ✅ 命中 |
| name | 品名 | 品名 / 物料名称 / 名称 | ✅ 命中 |
| spec | 规格 | 规格 / 规格型号 | ✅ 命中 |
| group_code | **品号群组** | 分组编码 / 物料分组编码 / 分组代码 | ❌ **未命中** |
| group_name | **群组名称** | 分组名称 / 物料分组名称 | ❌ **未命中** |

`group_code` / `group_name` 都在 `_REQUIRED_HEADERS` 里 → `_header_map()` 抛
`UploadValidationError('Excel 缺少必需表头：分组编码、分组名称')` → **任何导入都会被拒绝**。

原来的固定列索引 `group_code=7 / group_name=8` 对这个布局**是正确的**，
所以这属于"修完 bug 反而把能用的功能弄坏了"。

### 需要的改动

给两个字段补上真实别名（放在**首位**，作为优先匹配项）：

```python
'group_code': ('品号群组', '分组编码', '物料分组编码', '分组代码'),
'group_name': ('群组名称', '分组名称', '物料分组名称'),
```

---

## P1 · 别名匹配顺序不确定（`set` 无序）

```python
_HEADER_ALIASES = { 'code': {'品号', '物料编码', '编码'}, ... }   # ← set
for alias in aliases:
    if alias in normalized:
        result[field] = normalized[alias]
        break
```

`set` 的迭代顺序不保证。若某份导出同时含「物料名称」和「名称」两列，
命中哪一列**每次运行可能不同**，属于随机行为。

**改为有序的 `tuple`**，按优先级从高到低排列（真实表头放第一个）。

---

## P1 · 列表接口每次请求全表加载，违反契约的性能红线

`services/product/material.py::list_items`：

```python
raw_rows = query.all()                     # 无筛选时 = 8,089 条完整 ORM 对象
classified = [(raw, self._categories(...)) for raw in raw_rows]
materials = MaterialRepository.materials_for_codes([raw.code for raw, _ in classified])
                                           # IN 子句塞入 8,089 个参数
total = len(classified)
selected = classified[(page - 1) * page_size:page * page_size]   # 只留 20 条
```

没有 N+1 是对的，但换成了"每翻一页都全表加载 + 一条 8,000 参数的 IN 查询"，
在单 worker / 1.7GB 内存的机器上是实打实的浪费。原契约 §5.3 的要求是
「`product_material` 用一次 `IN` 批量取，不要逐行查」，本意是**按当页的 code 批量取**。

### 需要的改动

- **未按大类筛选时**（`category` 与 `unclassified` 均为空，这是最常见路径）：
  用 SQL `LIMIT/OFFSET` 分页，`total` 用 `COUNT(*)`，只对当页 20 行做大类判定；
- **按大类筛选时**：确实需要全量判定，但只取判定必需的两列
  （`with_entities(ImportProductRaw.code, ImportProductRaw.group_code)`），
  不要加载完整 ORM 对象；拿到当页 code 后再查完整行；
- `materials_for_codes` **只传当页的 code**，不要传全量；
- `is_disabled` 筛选建议走 `LEFT JOIN product_material` 交给数据库，
  避免为了过滤停用状态而把全量 material 行拉进内存。

---

## P2 · 2 条编码含 `/`，detail / 保存 / 图片三个接口对它们 404

生产库实测：

```
01.99.CD01001/CD02001-（3-2）-C1
01.99.CD01001/CD02001-（3-2）-C3
```

Flask 默认的 `<code>` 字符串转换器**不匹配斜杠**，这两条物料无法打开卡片、无法保存、无法传图。
另有 12 条编码含空格（如 `210 436 00 31 66`）——空格前端已用 `encodeURIComponent` 处理，没问题；
斜杠不行（`%2F` 在多数 WSGI/nginx 组合下会被提前解码）。

同时 `code` 被直接拼进 OSS key：

```python
rel_path = f'materials/{code}.{ext}'
```

含斜杠的编码会凭空多出一级目录。

### 需要的改动

路由用 `<path:code>`，或把 code 挪到查询参数；**并且**对 OSS key 做字符净化
（斜杠、空格等替换为安全字符，或改用编码的哈希做文件名）。
注意 `<path:code>` 与 `/items/<code>/image` 组合时的匹配行为要实测确认。

---

## P3 · 建议（非缺陷，需用户决定）：`is_disabled` 可以从 ERP 取，不必纯人工

真实导出里有两个现成的停用信号，目前都没有导入：

| 信号 | 数量 |
|---|---|
| `状态` = `失效` | **265** |
| `品名` 含「（已停用）」 | **2,858** |

而 `product_material.is_disabled` 现在是**纯人工维护**。8,086 条物料靠手工标停用不现实。
建议把 `状态` 一并导入 `import_product_raw`（新增一列），
让物料库的"停用"默认取 ERP 状态、人工只做例外覆盖——与大类判定同样的思路。

这属于范围扩展，**请等用户确认后再做**，不要自行实现。

---

## 已核对通过（无需改动）

- 迁移 `20260731_01`：建两表 + 加 `spec` 列 + 索引；`downgrade()` 先子表后父表，可干净回退；
  **没有在迁移里改业务数据**，符合契约；
- 差异 UPSERT **只增改不删**，库里有而导出里没有的行原样保留，不会丢数据；
  靠 `group_code` 变化命中更新来纠正 PCS，设计正确；
- **`name` 组成未被改动**，`_clean_name` 原样保留 → 售后语义匹配等下游逻辑不受影响（这是最关键的一条）；
- 大类判定语义正确：前缀命中即返回、不再看分组默认；多标签用 `set` 聚合，成品+产成品能并存；
  规则缓存为类级、增删改后失效；
- 图片接口 OSS 拼接**正确**（`OSS_BASE_URL` 已含 `/tmt-library`，key 另加前缀、URL 不加），
  与 `routes/product/finished.py:217-224` 既有写法一致——此处历史上踩过坑，这次没踩；
- 返回字段与前端已实现的契约一致（`data.items` / `data.total` / `categories` / `category_labels`）；
  图片接口 `{data_url, orig_data_url}` 前端可直接接上传按钮；
- 蓝图已注册（`app.py:102, 135`）；`tests/test_material_library.py` 5 项全过；
- 全量 pytest：**231 passed, 2 skipped, 38 errors**。38 个 error 全部是本机
  pytest 临时目录 `PermissionError: [WinError 5]`（凡用 `tmp_path` 的测试都中招），非代码问题。

## 一个应当知晓的一次性代价

差异比较字段含 `spec`，而库里 `spec` 全为 NULL、导出里 62%（5,026 行）有值，
所以**修好后的首次重导会更新约 8,000 行**。这是 spec 回填的预期成本，一次性，
但导入耗时会明显长于以往，注意别撞 gunicorn 的看门狗超时（当前 `--timeout 1800`）。

## 附录 · PCS 脏数据成因已精确定位

真实布局：`单位名称`(6) → `品号群组`(7) → `群组名称`(8)。
坏批次（`2026-07-23 10:55:22`，34 行）的文件**比这个布局少一列**，
于是固定索引 7 读到了 `单位名称` = `PCS`、索引 8 读到了 `品号群组` = `1509`，
与库里脏数据完全吻合。

旁证：真实导出的 `品号群组` 去重为 **66** 个，而生产库 `group_code` 去重为 **67** 个，
多出来的正是 `PCS`。按表头映射修好后重导，`PCS` 这个伪分组会自然消失。
