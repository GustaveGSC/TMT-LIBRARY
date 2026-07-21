# Codex → Claude Code：财务客户简称与人工映射后端交接

日期：2026-07-21
分支：`codex/backend-finance-customer-mapping`

## 完成内容

- `shipping_record`、`return_record` 增加可空 `customer_alias VARCHAR(255)` 及索引。
- 财务 CSV/XLSX 解析可选读取“客户简称”；未提供该列的旧文件仍可正常导入。
- 发货与销退批量写入从 `INSERT IGNORE` 改为 MySQL `ON DUPLICATE KEY UPDATE`。
- 重导时已存在的财务行不再在 service 层被过滤掉，而是全部进入 UPSERT：
  - 返回结果区分 `inserted` / `updated`、`inserted_returns` / `updated_returns`。
  - 新文件有非空简称时覆盖历史简称；旧文件缺少简称时用 COALESCE 保留数据库已有值。
  - 同时允许数量、品名、规格、区域等受控字段随财务更正更新；不改历史 batch_id。
- 新建 `shipping_finance_customer_mapping`：客户简称唯一，保存 `is_export/country/brand/note/updated_at`，当前不参与聚合或图表。
- 新增两个接口：
  - `GET /api/shipping/finance-customer-aliases?keyword=&page=1&per_page=100`（shipping:view）
  - `POST /api/shipping/finance-customer-aliases/mapping`（shipping:edit）
- 列表查询在两张原始表分别按索引聚合，UNION 后一次关联 mapping；分页请求固定两条 SQL（count + data），无 N+1。
- 已更新 `api.md` / `database.md`，字段和响应契约可直接供前端页面实现。

## 必要的唯一键修正

旧财务发货行 `line_no=NULL`，MySQL 唯一键允许多个 NULL，单纯改成 ON DUPLICATE 仍无法触发更新。迁移 `20260721_02` 因此把历史财务行规范为 `line_no='F:YYYYMMDD'`，新解析器生成同样的内部键，使数据库唯一约束与业务判重键 `(订单号, 品号, 交易日期)` 对齐。

迁移在任何 DDL 前执行两道门禁：

- 财务发货 UPSERT 键不得有 NULL。
- `(ecommerce_order_no, product_code, shipped_date)` 不得存在重复组。

任一门禁失败都会拒绝升级，不会自动删除或合并生产数据。

## 自动化验证

- `python -m pytest backend/tests -q`：通过（104 tests）。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。
- 独立 SQLite 迁移测试验证字段、映射表、内部键规范；重复历史键会中止迁移。
- 测试覆盖可选列解析、真实 MySQL UPSERT SQL、缺简称不覆盖旧值、历史行进入 UPSERT、映射校验、API 权限/分页契约。

## 部署前门禁（必须执行）

本批会更新约 36.5 万条财务行的内部 line_no，并改变后续大批量导入写入语义。部署前必须：

1. 确认没有导入/resolve 任务运行。
2. 对生产数据库做全量备份并核对备份文件非空。
3. 只读执行并记录：

```sql
SELECT COUNT(*) FROM shipping_record WHERE source='finance';
SELECT COUNT(*) FROM shipping_record
WHERE source='finance'
  AND (ecommerce_order_no IS NULL OR product_code IS NULL OR shipped_date IS NULL);
SELECT COUNT(*) FROM (
  SELECT ecommerce_order_no, product_code, shipped_date
  FROM shipping_record WHERE source='finance'
  GROUP BY ecommerce_order_no, product_code, shipped_date
  HAVING COUNT(*) > 1
) duplicate_finance_keys;
```

后两项必须为 0。若不是 0，停止部署并把样本交回 Codex分析，禁止直接删重。

## 部署顺序

1. 同步本批文件，暂不 reload。
2. 在维护窗口执行 `python -m alembic -c alembic.ini upgrade head`；该过程会更新财务行并创建索引，可能持有表锁，需耐心等待，禁止中断。
3. 确认 `alembic current` 为 `20260721_02 (head)`，执行 `alembic check`。
4. reload gunicorn，并按既定纪律延迟复查 status/journal、`/health`、`/ready`。
5. 验证两个新 API 后再交给前端开发/部署。
6. 不要在部署脚本里自动重导历史财务文件；由用户备份确认后在非高峰期按 <20MB 分批手动导入，并观察首批耗时、任务状态及 updated 数量。

本批未部署、未 push，未修改前端，也未把映射应用到 `shipping_order_finished` 或图表。
