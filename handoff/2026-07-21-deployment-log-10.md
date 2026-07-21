# 部署记录 · 客户简称映射改四态，修正内外销判断错误（第十二轮）

日期：2026-07-21

## 背景

第十一轮上线后，用户实测发现"内销"筛选只有27条，排查发现是我在 `handoff/2026-07-21-codex-handoff-11.md` 里业务规则（第一节）和技术指令（第四节）自相矛盾：规则里说"确认不是外贸"应该"既不算内销也不算外贸"，但技术指令却把这类记录直接定义成了"内销"。Codex 按技术指令正确实现，问题出在我这份交接文档本身，不是实现问题。

跟用户重新确认后，实际需求比之前设想的更明确：`is_export` 布尔字段不够用，需要四态：
- `pending`（未审核，默认）
- `export`（外贸客户）
- `domestic`（内销客户）
- `non_sales`（非销售客户——已审核，但既不算外贸也不算内销的终态，如赠品样品，不会被"仅看未审核"反复提醒）

交接文档：`handoff/2026-07-21-codex-handoff-12.md` → `handoff/2026-07-21-codex-customer-status-handoff.md`。

## 后端审查结论

`codex/backend-customer-status`（`530b4e5`）逐文件审查通过：

- **迁移 `20260721_04`**：`shipping_finance_customer_mapping` 加 `status VARCHAR(20) NOT NULL DEFAULT 'pending'`，一次性 `UPDATE ... SET status = CASE WHEN is_export THEN 'export' ELSE 'non_sales' END` 转换存量数据后删除 `is_export` 列。幂等、`downgrade()` 对称处理，表只有个位数记录，无性能顾虑。
- **`get_chart_data` 内外销判断修正**：`trade_type='foreign'` 只匹配 `status='export'`，`trade_type='domestic'` 只匹配 `status='domestic'`（这是这次修正的核心——上一轮错误地把 `is_export=false` 当作 domestic）；`pending`/`non_sales`/未映射三类均不进入 domestic/foreign 子集，只在 `all` 里出现。
- **国家/品牌聚合**：只统计 `status='export'` 且字段非空的记录，和上一轮一致，未变。
- **`GET /api/shipping/finance-customer-aliases` 新增 `status` 查询参数**：`status=pending` 同时包含"从未创建映射记录"和"显式 pending"两种情况（用 `mapping.id IS NULL OR status='pending'`），方便前端"仅看未审核"一次查询搞定，不用二次过滤；非法值返回 400。
- **`POST .../mapping` 请求体从 `is_export` 布尔值改成 `status` 四选一**，服务层校验非法值抛 `ValueError` → 400；这是破坏性接口改动，旧版前端请求会因为拿不到合法 `status` 直接 400。
- **测试**：110 项全过（本地复跑确认）。新增测试覆盖存量数据迁移（4条→export、3条→non_sales，精确验证）、四态图表隔离（pending/non_sales/未映射同时验证都只在 all 里、export/domestic 分别隔离）、非法 status 值校验、GET pending 查询契约。

## 部署前置检查

- `shipping_task` 无 `running` 记录。
- 全量备份：`/root/backups/tmt_db_20260721_225944_pre_customer_status.sql.gz`，`gzip -t` 校验通过。
- 迁移前核对存量数据：`is_export=true` 4条、`is_export=false` 3条，与 Codex 交接文档预期一致。
- 合并：`master` ff-only 合并 `76816e0`。本地复跑 `pytest`（110 passed）+ `npm run build:web`（成功）。

## 前端改动（我方）

`FinanceCustomerMapping.vue` 重写：
- 默认关键字从 `外贸` 改成空（四态上线后所有简称都需要审核，不再只关注含"外贸"字样的）
- "确认外贸"勾选框换成四态 `el-select`（未审核/外贸客户/内销客户/非销售客户）
- "仅看未匹配"改成"仅看未审核"，直接请求后端 `status=pending`，不再前端二次过滤
- 草稿字段 `is_export` → `status`，保存请求体同步改
- 行状态徽章按四态分别着色（pending 橙/export 绿/domestic 蓝/non_sales 灰褐）
- 同步更新 `.claude/modules/frontend-data-mgmt.md`

## 部署步骤

1. scp 同步 5 个后端变更文件，md5 核对一致。
2. `python3.11 -m alembic -c alembic.ini upgrade head`：`20260721_03 → 20260721_04` 成功。
3. `alembic current` → `20260721_04 (head)`；`alembic check` → 无差异。
4. 迁移后核对：`status` 分组统计 `export=4, non_sales=3`，无 NULL、无遗留 `domestic`/`pending`，与预期完全一致。
5. `systemctl reload gunicorn`；8秒后复查无异常。
6. **立即**部署完整 `dist-web/`（压缩破坏性接口不兼容窗口），线上 JS hash 校验一致，`/health`/`/ready` 200。

## 部署后生产验证（直接调用 repository 函数核对）

```
channel 维度 actual_quantity 总量：
  all=161,855（不变，仍含未映射/pending/non_sales）
  foreign=424（不变，4条 export 映射未受影响）
  domestic=0（修正后的正确结果——当前没有任何一条 status=domestic 的映射，之前显示的27是上一轮的错误实现）

地域维度 trade_type=foreign：德国301 / 加拿大98 / 香港22 / 俄罗斯3（不变）

GET status=pending：total=161（168个去重简称中，7条已处理，161条待审核，数字吻合）
```

`domestic` 归零是本次修复的直接验证，符合 Codex 交接文档"当前没有 domestic 映射，上线后内销结果为空是预期行为"的说明。

## 影响说明

- 这是一次破坏性接口改动，前后端同批上线，未观察到不兼容窗口内的报错（reload 后立即接着部署前端，间隔仅数十秒）。
- 历史保存的3条"确认不是外贸"映射自动迁移为 `non_sales`，不需要用户重新处理。
- 用户接下来会开始逐条审核 161 条待处理简称，把非外贸相关的客户标记为 `domestic` 或 `non_sales`。

## 后续

- 目前"内销"图表仍会是空的，直到用户标注出第一条 `domestic` 状态的映射。
- 之前记录过的已知问题仍待跟进：保存新映射不会自动触发 `is_stale`，用户改完映射后仍需手动点"刷新全局数据"（或等下次导入数据）才会反映到图表。
