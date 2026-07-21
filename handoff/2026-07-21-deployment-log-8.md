# 部署记录 · 财务客户简称 + 外贸国家/品牌人工映射（后端）

日期：2026-07-21

## 背景

财务发货数据的"国家"/"品牌"目前来自产品标签，但内销产品走外贸订单时无法体现真实目的国/客户。真实信息只在财务原始数据"客户简称"列（未被读取存储）。第十轮交给 Codex 实施：`handoff/2026-07-21-codex-handoff-10.md` → `handoff/2026-07-21-codex-finance-customer-mapping.md`。

## 后端审查结论

`codex/backend-finance-customer-mapping`（`e8c9c04`）逐文件审查通过：

- **迁移 `20260721_02`**：升级前两道门禁（财务行 UPSERT 键非空、`(订单号,品号,交易日期)` 无重复组），任一不满足直接 `RuntimeError` 拒绝执行，不会自动删重。发现并修复了一个此前未知的问题：财务行 `line_no` 恒为 NULL，MySQL 唯一约束下多个 NULL 互不冲突，导致原有唯一键对财务行事实上从未生效——迁移把历史财务行规范为 `line_no='F:YYYYMMDD'`，新解析器同步生成同样的内部键，使数据库约束与业务判重键对齐。
- **UPSERT 改造**：`bulk_insert_shipping`/`bulk_insert_return` 由 `INSERT IGNORE` 改为 MySQL `ON DUPLICATE KEY UPDATE`，`customer_alias` 用 `COALESCE(新值, 旧值)` 保留策略（新文件有简称就覆盖，旧文件缺列不清空已有值）。核对 `import_finance` 调用点：`bulk_insert_*` 现在传入全量 `shipping_rows`/`return_rows`（不是之前的 `new_shipping`），命中已存在行才会真正走 UPDATE；`new_*`/`skipped_*` 仅用于统计 inserted/updated 计数，逻辑自洽。
- **解析器**："客户简称"列可选读取，未加入 `_REQUIRED_FINANCE_COL_NAMES`，缺列时字段为 None，不影响旧文件导入。
- **新表** `shipping_finance_customer_mapping`：`customer_alias` 唯一，`is_export/country/brand/note/updated_at`，字段与我原始交接文档一致。
- **新增 API**：`GET /api/shipping/finance-customer-aliases`（`shipping:view`，支持 keyword/分页，两表 UNION 后一次关联映射，无 N+1）、`POST /api/shipping/finance-customer-aliases/mapping`（`shipping:edit`）。
- **测试**：104 项全过（本地复跑确认），覆盖解析器可选列、真实 MySQL UPSERT SQL 形态、COALESCE 保留旧值、历史行进入 UPSERT 的端到端 mock、映射校验、API 权限矩阵（view 403 on POST / edit 200）、SQLite 独立迁移测试（含重复键场景下迁移正确拒绝）。

范围符合约定：本批不涉及 `shipping_order_finished` 聚合表或图表，映射结果暂不应用到分析层。

## 部署前独立核实（生产只读查询，未依赖迁移自身门禁）

```sql
SELECT COUNT(*) FROM shipping_record WHERE source='finance';          -- 364944
SELECT COUNT(*) FROM shipping_record WHERE source='finance'
  AND (ecommerce_order_no IS NULL OR product_code IS NULL OR shipped_date IS NULL); -- 0
-- 重复键分组计数                                                                    -- 0
```

两项风险计数均为 0，与 Codex 报告一致，迁移可安全执行。

## 全量备份

`ssh tmt` 上执行 `mysqldump --single-transaction --quick --routines --triggers`，输出：
`/root/backups/tmt_db_20260721_201532_pre_finance_customer_mapping.sql.gz`（31M，`gzip -t` 校验通过）。

## 部署步骤与结果

1. 确认无导入/resolve 任务在跑（`ps aux` 无相关进程）。
2. scp 同步 5 个变更文件到 `/opt/tmt-library/`，md5 逐一核对一致：
   `database/models/shipping/__init__.py`、`database/repository/shipping/__init__.py`、
   `routes/shipping/__init__.py`、`services/shipping/__init__.py`、
   `migrations/versions/20260721_02_add_finance_customer_mapping.py`
3. `python3.11 -m alembic -c alembic.ini upgrade head`（在 `/opt/tmt-library` 下执行，`alembic.ini` 在仓库根目录，非 `backend/` 下；服务器 `pip`/`python3` 默认 3.9 无 alembic，需用 `python3.11`，符合既有经验）。升级成功，无报错。
4. `alembic current` → `20260721_02 (head)`；`alembic check` → `No new upgrade operations detected.`
5. `systemctl reload gunicorn`；等待 8 秒后复查 `status`（Main PID 2081 未变，运行 17h+，新 worker 干净启动）+ `journalctl -u gunicorn -n 20`（无异常退出/崩溃记录）。
6. 验证：`/health` 200、`/ready` 200、`GET /api/shipping/finance-customer-aliases`（未登录）返回 401（符合权限预期，接口已挂载）。

## 影响说明

- 本批**只加字段/建表/规范内部 line_no**，未触碰历史 `customer_alias`（仍为 NULL，等用户重新导入财务数据才会补上）。
- 未修改任何现有查询行为，`shipping_order_finished`/图表/世界地图均未改动，线上功能应无感知变化。
- 前端尚未开发，两个新接口暂无 UI 入口。

## 后续（未完成）

- 前端"外贸客户匹配"配置页面（数据管理模块下）：列出去重客户简称（默认筛选含"外贸"），人工填国家/品牌/是否确认外贸/备注。
- 用户后续将 80MB 财务全量数据拆分为多个 <20MB 文件，在非高峰期分批重新导入，观察首批耗时与 `updated` 数量是否符合预期（约 36.5 万条历史行会被逐步补上 `customer_alias`）。
- 映射结果应用到 `shipping_order_finished`/图表分析：下一批，需等用户完成人工匹配、有实际数据后再具体设计消费逻辑。
