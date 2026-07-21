# 部署记录 · 外贸客户人工映射应用到发货图表（第十一轮）

日期：2026-07-21

## 背景

第十轮（`customer_alias` 落库 + 人工映射配置页）已上线，用户导入3个月财务数据并人工标注了7条映射（4条确认外贸：香港/加拿大/德国/俄罗斯，3条确认非外贸）。这一轮把映射结果实际接入发货图表：`shipping_order_finished` 加 `customer_alias` 列，财务端内销/外贸判断和"地域"/"品牌"标签维度聚合改用人工映射，完全不再看产品标签；发货端（`source='shipping'`）内外销筛选器整体下线。

交接文档：`handoff/2026-07-21-codex-handoff-11.md`（我方需求）→ `handoff/2026-07-21-codex-finance-mapping-analytics.md`（Codex 实现说明）。

## 后端审查结论

`codex/backend-finance-mapping-analytics`（`2730283`）逐文件审查通过：

- **迁移 `20260721_03`**：纯加列 + 加索引（`customer_alias` + `(source, customer_alias)` 复合索引），无数据变更，幂等（先查 inspector 再决定是否执行），无风险。
- **`shipping_order_finished` 表与 `shipping_finance_customer_mapping` 表排序规则一致**（均为 `utf8mb4_unicode_ci`，生产库核实过），新增的 `customer_alias` JOIN 不会重蹈上一轮 `shipping_record`/`return_record` 排序规则冲突的覆辙。
- **`get_order_products`**：`customer_alias` 取订单内首个非空值，同订单多行简称不一致时不中断（有匹配测试覆盖）。
- **`get_chart_data` 核心改动**：财务端 `trade_type` 判断从 FTP 系列启发式切换为 `JOIN shipping_finance_customer_mapping`（INNER JOIN，未映射订单自然被排除）+ `is_export` 过滤；`地域`/`品牌` 标签维度识别分类名后改用 `mapping.country`/`mapping.brand` 聚合，且强制 `is_export=true` 且字段非空；`tag_filters` 契约不变（前端仍传标签 ID），后端内部转换成标签名再按映射文本过滤，未命中人工映射的产品标签路径完全保留给非财务/非地域品牌维度使用，两套逻辑不串。
- **`resolve_stale` 缺失的 `_invalidate_chart_options_cache()` 已补上**。
- **测试**：108 项全过（本地复跑确认），新增用例用真实 SQLite ORM 实例跑通了国家/品牌聚合、domestic/foreign/all 三态、tag_filters→人工映射转换、迁移列/索引校验，覆盖扎实。

## 部署前置检查

- 确认无导入/resolve 任务在跑（`shipping_task` 无 `status='running'` 记录）。
- 全量备份：`/root/backups/tmt_db_20260721_220844_pre_finance_mapping_analytics.sql.gz`（31M，`gzip -t` 校验通过）。
- 合并顺序：`master` 先 ff-only 合并 Codex 分支 `67df90a`，再合并 Claude 前端分支 `46965b7`（无冲突，各自改动文件不重叠）。合并后本地复跑 `pytest`（108 passed）+ `npm run build:web`（成功）。

## 部署步骤

1. scp 同步 5 个变更文件到 `/opt/tmt-library/`，md5 逐一核对一致：
   `database/models/shipping/__init__.py`、`database/repository/shipping/__init__.py`、
   `routes/shipping/__init__.py`、`services/shipping/__init__.py`、
   `migrations/versions/20260721_03_add_customer_alias_to_order_finished.py`
2. `python3.11 -m alembic -c alembic.ini upgrade head`（`/opt/tmt-library` 目录下执行）：`20260721_02 → 20260721_03` 成功。
3. `alembic current` → `20260721_03 (head)`；`alembic check` → `No new upgrade operations detected.`
4. `systemctl reload gunicorn`；8 秒后复查 `status`（Main PID 21789 未变）+ `journalctl`（无异常退出记录）。
5. tar+scp 部署完整 `dist-web/`，线上 `index-*.js` hash 与本地构建一致，`/health`/`/ready` 200。

## resolve-all 数据回填

迁移本身不回填历史数据（`customer_alias` 只对新 resolve 的订单生效），按交接文档要求执行一次全量 `resolve-all` 补齐历史结果。

- **执行方式**：直接在服务器上以独立 Python 脚本调用 `shipping_service.resolve_all()`，不经过 gunicorn worker/HTTP 请求——目的是避免触发当天早些时候刚处理过的"单 worker CPU 密集任务撞 gunicorn watchdog 超时被 SIGKILL"问题（`handoff/2026-07-21-claude-hotfix-finance-collation.md` 记录的那次事故）。脚本内直接 `app.app_context()` 调用，独立进程，不占用/阻塞 gunicorn 主服务。
- **规模**：133,701 个发货端订单 + 115,898 个财务端订单，共 249,599 个订单。
- **耗时**：819.1 秒（约13.7分钟）。期间监控了内存（一度降到约120MB可用，但很快回升到689MB，未触发OOM，进程本身RSS峰值约638MB后回落）。
- **首次尝试因脚本笔误失败**（`_invalidate_chart_options_cache` 误从 `services.shipping` 导入，实际在 `database.repository.shipping`），在真正调用 `resolve_all()` 之前就因 `ImportError` 退出，未触碰任何数据，随后修正重试成功。
- **结果**：`{'resolved': 249599}`，随后 `db.session.commit()` + 手动调用 `_invalidate_chart_options_cache()`。

## 部署后生产验证（直接调用 repository 函数核对，未经前端）

```
shipping_order_finished: source=shipping 358,460 行, source=finance 330,681 行
finance 中 customer_alias 非空: 18,114 行

地域维度 trade_type=all:     德国301 / 加拿大98 / 香港22 / 俄罗斯3（仅4个确认外贸国家）
地域维度 trade_type=foreign: 与 all 完全一致
地域维度 trade_type=domestic: 空（符合预期——非外贸订单没有国家）

channel 维度 actual_quantity 总量：
  all=161,855（含未映射订单）
  foreign=424（仅4条确认外贸映射）
  domestic=27（仅3条确认非外贸映射中有实际发货的2条）
```

三个 trade_type 桶互不重叠、未映射订单只出现在 `all` 里、国家维度只展示确认外贸且填了国家的数据——与交接文档验证清单和用户确认的业务规则完全一致。

## 已知限制（沿用 Codex 交接文档里的提示，未处理，不阻塞本次上线）

- 世界地图下钻仍依赖 chart-options 的"地域"标签列表按名称找 tag_id；已核实香港/加拿大/德国/俄罗斯当前都存在对应产品标签，下钻可用。如果用户后续标注了一个从未建立过产品标签的新国家，主图能显示但下钻会跳过该国家，需要后续把筛选契约从标签 ID 扩展为映射文本，这次不影响。

## 影响说明

- 财务端图表：国家/品牌维度、内外销筛选立即生效，前端无需改动（响应契约复用现有"地域"/"品牌"标签维度机制）。
- 发货端图表：内外销筛选器已隐藏，固定按 `all` 请求，行为不变（发货端本来就没有可靠的内外销判断依据）。
- 未涉及生产数据的破坏性变更，全程有备份兜底。

## 后续

- 用户继续分批导入剩余 22 个批次财务数据，每导入完一批财务数据需要重新 resolve（可以用 `resolve_stale`，因为 stale 标记机制应该会在新数据写入时自动标记相关订单，不需要每次都全量 resolve-all；具体待用户下次操作时观察验证）。
- 继续在配置页面人工标注更多外贸客户简称，标注后同样需要 resolve 才能反映到图表（新映射不会自动触发 stale 标记，因为 `shipping_finance_customer_mapping` 表变化不会让 `shipping_order_finished.is_stale` 置位——这一点如果影响用户体验，可能需要在保存映射后提示用户去刷新，值得后续跟 Codex/用户确认）。
