# 交接说明 · Codex → Claude（财务人工映射进入图表统计）

日期：2026-07-21

## 完成内容

- 后端提交：`2730283 feat(shipping): apply finance customer mapping to analytics`
- 分支/worktree：`codex/backend-finance-mapping-analytics` / `E:/Project/tmt-library-codex`
- 新增 Alembic revision `20260721_03`：
  - `shipping_order_finished.customer_alias VARCHAR(255) NULL`
  - 复合索引 `ix_sof_source_customer_alias(source, customer_alias)`
- resolve 链路会把原始财务订单首个非空 `customer_alias` 写入每一条组合结果；同一订单多行简称不一致时保留首个非空值，不中断任务。
- 财务图表规则已经切换到人工映射：
  - `trade_type=foreign`：只包含命中 `is_export=true` 的简称。
  - `trade_type=domestic`：只包含命中 `is_export=false` 的简称。
  - 未映射简称不进入 domestic/foreign；`trade_type=all` 仍包含全部。
  - 财务端 `group_by=tag:<id>` 且分类名为“地域”或“品牌”时，分别按 mapping.country / mapping.brand 聚合；只统计 `is_export=true` 且维度值非空的数据。
  - 上述两个维度的 `tag_filters` 仍接收前端原有标签 ID，但后端只取标签显示名，再按人工映射筛选，不使用产品与标签的关联，保证地图主图和国家下钻口径一致。
  - 发货端保持原逻辑；前端固定传 `trade_type=all` 即可。
- `resolve_stale` 成功后补充清理 chart-options 缓存；`resolve-all` 原有清缓存逻辑已确认保留。
- 已同步 `.claude/modules/api.md`、`.claude/modules/database.md`。

## 自动化验证

- `python -m pytest backend/tests -q`：108 passed。
- `python -m compileall -q backend`：通过。
- `python -m alembic -c alembic.ini heads`：`20260721_03 (head)`。
- `git diff --check`：通过。
- 新用例覆盖：迁移列/索引、简称传递与落盘、财务内外销过滤、国家/品牌聚合、未映射在 all 中保留、地图下钻标签筛选转人工映射。
- 本地没有生产库结构，未执行生产 `alembic check` 和真实数量对账；这两项留作部署门禁。

## 建议合并与部署顺序

1. 合并 `2730283`，再合并 Claude 分支 `claude/frontend-hide-trade-type-shipping`；先跑一次合并后的后端测试和 web 构建。
2. 生产部署前确认没有发货/财务导入或 resolve 任务在运行，并按现有纪律备份数据库。
3. 服务器先执行 `alembic upgrade head`，确认 `alembic current` 为 `20260721_03`，再执行 `alembic check`；任何结构差异都先停下核验。
4. 部署后端并 `systemctl reload gunicorn`（禁止 restart / `--preload`），持续检查日志和 `/health`、`/ready` JSON。
5. 紧接着部署完整 `dist-web/`，避免前后端版本分离。
6. 从页面启动一次 `resolve-all`，等待持久化任务状态为 done；该步骤负责给历史 `shipping_order_finished` 补齐 customer_alias，迁移本身不回填业务数据。
7. resolve 完成后验证：
   - finance + all 的总量仍包含已映射和未映射数据；
   - foreign 只包含 4 条 `is_export=true` 映射；
   - domestic 只包含 3 条 `is_export=false` 映射；
   - 世界地图/国家排行只出现已确认外贸且 country 非空的香港、加拿大、德国、俄罗斯；
   - 按国家查看系列/品牌的下钻结果与该国家数量口径一致。

## 注意点

- 世界地图下钻仍依赖 chart-options 的“地域”标签列表能按名称找到对应标签 ID；现有旧地图机制通常已经具备这些国家标签。部署验证时请特别确认香港、加拿大、德国、俄罗斯都存在于该标签列表。若人工 mapping 填入一个从未建立过产品标签的新国家，主地图能显示，但当前前端下钻会跳过该国家，需要后续把筛选契约从标签 ID 扩展为映射文本（不影响本批主聚合）。
- 本批未部署、未 push，也未修改 `src/` 或 Electron。
