# 交接说明 · Claude → Codex（第十轮，财务端客户简称 + 外贸国家/品牌人工匹配）

日期：2026-07-21
新需求，业务背景：外贸发货数据目前的"国家"/"品牌"来自**产品标签**（挂在成品编码上），但实际存在"内销产品走外贸订单"的情况——真实的目的国家/客户信息只存在于财务原始数据的"客户简称"列里（例如"外贸-印尼-PT URBAN RITEL"：外贸标记+国家+客户公司名），这一列目前完全没有被读取/存储。产品标签是**产品级**属性，天然没法表达"这一单发去哪个国家、卖给谁"这种**订单级**信息，这是结构性问题，不是数据录入疏漏。

用户已确认的决策：
1. 客户简称 → 国家/品牌的匹配**完全人工**，不做自动解析（列出去重后的客户简称，人工逐条填国家和品牌）
2. 重新导入历史数据时用 **UPSERT**（按现有唯一键更新），不做全清空重导
3. 80MB 的全量财务文件用户会自己拆分成多个 <20MB 的文件分批导入，不改上传大小限制

---

## 一、Schema 改动

`shipping_record` 和 `return_record` 都要加 `customer_alias`（客户简称，`VARCHAR`，可空）字段：

- 建议长度参考现有 `channel_org_name` 之类的字段（`String(255)` 应该够）
- 需要一条 Alembic migration（当前 head 是 `20260721_01`，这次新建一个）
- 现有 25 个历史批次的记录这一列会是 NULL，等用户重新导入后才会补上

## 二、解析代码改动

`backend/services/shipping/__init__.py`：

- `_extract_finance_row(row, col_map)` 新增读取"客户简称"列，加进返回的 dict
- **不要**加进 `_REQUIRED_FINANCE_COL_NAMES`（保持可选，兼容以后可能缺这一列的文件，缺失时该字段就是 None，不影响其余解析）
- `bulk_insert_shipping`/`bulk_insert_return` 的 `_make_param` 加上 `customer_alias` 字段

## 三、导入行为改成真正的 UPSERT（这是这次最关键的改动）

现状：`bulk_insert_shipping`/`bulk_insert_return` 都是 `INSERT IGNORE`（MySQL 语义：命中唯一键冲突就静默跳过，**不会更新任何字段**）。这意味着如果只是简单重新导入，已存在的历史记录（按 `(订单号, 行号, 品号, 类型, 来源)` / `(订单号, 品号, 交易日期)` 判重）会被直接跳过，`customer_alias` 永远补不进去——这次重新导入的整个目的就落空了。

需要改成 `INSERT ... ON DUPLICATE KEY UPDATE`，至少更新 `customer_alias`（如果你认为顺手把其它可能被后续更正过的字段也一起 UPDATE 更稳妥，比如 `channel_name`/`product_name`，可以你来判断，但至少 `customer_alias` 必须覆盖）。

**性能提醒**：这批数据量不小（`shipping_record` 里 finance 来源的记录约 36.5 万条），`ON DUPLICATE KEY UPDATE` 本质还是走索引命中，按现有 100 条一批（`CHUNK = 100`）分块提交应该问题不大，但建议实际测一下这次全量重导的耗时，评估要不要在导入进度提示里加个预估时间，或者建议用户挑非高峰期操作（虽然是 Web 端触发的后台任务，不会阻塞用户操作，但会占用数据库连接和 CPU 一段时间）。

## 四、新增：外贸客户简称人工匹配配置

### 数据结构

新建一张表（比如 `shipping_finance_customer_mapping`）：

| 字段 | 说明 |
|---|---|
| `id` | 主键 |
| `customer_alias` | 客户简称原文，唯一 |
| `is_export` | 是否确认为真实外贸订单（人工判断，因为不是所有含"外贸"字样的简称都一定是，也可能有不含"外贸"字样但其实是的——这个人工判断标准交给用户在页面里自己拿捏） |
| `country` | 人工填写的国家（文本，不强制关联到"地域"标签表，因为客户简称里写的国家和产品标签体系可能不是同一套命名，人工判断） |
| `brand` | 人工填写的品牌（同上，文本） |
| `note` | 备注（可选，让用户能记录"为什么这么判断"这类信息） |
| `updated_at` | 更新时间 |

### API

- `GET /api/shipping/finance-customer-aliases`：返回 `shipping_record`/`return_record` 里 `customer_alias` 非空的**去重列表**，带上出现次数（方便用户判断优先处理哪些），以及是否已有匹配记录（关联 `shipping_finance_customer_mapping`）。支持一个"只看含'外贸'关键字"的过滤参数（前端会做一个默认开启的筛选，但后端返回全量去重列表，筛选逻辑前端做也行，看你觉得哪边方便——如果去重列表数据量大，建议后端支持关键字过滤参数，避免前端拿到全量再筛）
- `POST /api/shipping/finance-customer-aliases/mapping`：新增/更新一条映射（`customer_alias` + `is_export` + `country` + `brand` + `note`）
- 权限：复用 `shipping:edit`（列表用 `shipping:view`）

## 五、这次先不做的部分（下一批再说）

**把匹配结果应用到 `shipping_order_finished`（发货聚合表）和图表分析** 这次先不做——需要等用户真正跑过一轮人工匹配、有了实际数据之后，再具体讨论 `resolve_orders` 怎么消费这份映射（比如优先级：客户简称映射 > 产品标签，没匹配到时怎么兜底），以及世界地图/图表要不要跟着改。这次范围只到"能把客户简称存下来 + 能人工维护映射表"为止，应用层的改动是下一批。

## 验证范围

- 迁移在测试库跑一遍，确认字段类型/长度没问题
- 补测试覆盖：解析器正确读到客户简称列、UPSERT 场景下重复导入会更新而不是跳过 customer_alias、映射表的增删改查
- 照例 `python -m pytest` + `python -m compileall -q backend` + `git diff --check`

## 协作方式

独立 worktree/分支，完成后照例写交接文档。**这次涉及大批量真实生产数据的 UPSERT 操作，部署前务必先做一次全量数据库备份**，并且建议先在只读方式核实一遍受影响行数的预估（比如先 `SELECT COUNT(*)` 评估这次 UPSERT 大概会碰多少行），确认没问题再让用户开始重新导入。

## 前端（我这边，等后端 API 就绪后开始）

新增一个"外贸客户匹配"配置页面（大概率放在数据管理模块下，具体位置等后端接口定下来后我再定），列出去重后的客户简称（默认筛选含"外贸"的），每行可以填国家/品牌/是否确认外贸/备注，保存调用后端接口。
