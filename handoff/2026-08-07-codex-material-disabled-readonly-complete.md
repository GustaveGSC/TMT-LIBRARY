# 物料停用状态只读化后端收口完成

日期：2026-08-07  
对象：Claude Code

## 完成内容

- `MaterialService.save_item()` 的可写白名单移除 `is_disabled`；旧调用方或恶意请求携带该字段时会被忽略。
- `MaterialRepository.effective_disabled_expression()` 移除 `product_material.is_disabled` 人工覆盖分支。
- 物料响应移除 `is_disabled_override`，`is_disabled` 始终由以下实时规则计算：
  - ERP `status == '失效'`；或
  - `coalesce(raw_name, name)` 命中启用的 `material_disable_keyword`。
- `product_material.is_disabled` 数据库列保留，不新增迁移；当前运行时代码不再读写该列。
- `list_items?is_disabled=0|1` 保留，供停用状态列的主动筛选使用。
- 停用关键词管理与 `/api/material/disable-preview` 保持不变。

## 组合接口衔接

新版前端组合明细读取 `item.is_disabled` 展示只读角标，因此补充组合明细响应字段：

- 组合的第三条物料展示查询通过相关 `EXISTS` 同时计算停用状态；
- 直接读取 ERP 状态和启用关键词，不依赖人工覆盖；
- 不增加查询次数，列表仍固定三条 SELECT；
- ERP 编码缺失时返回 `is_missing:true, is_disabled:false`。

## 文档与测试

- 更新 `.claude/modules/api.md`：移除三态写入契约，补充组合明细只读状态。
- 更新 `.claude/modules/database.md`：明确 `product_material.is_disabled` 是保留死列。
- 回归测试覆盖：
  - 请求体传 `is_disabled:false` 后数据库列仍为 NULL；
  - 响应不再出现 `is_disabled_override`；
  - 关键词命中的物料继续返回 `is_disabled:true`；
  - 组合明细返回同口径的 `is_disabled:true`；
  - 固定三查询门禁继续通过。

验证结果：

- `pytest -q tests/test_material_library.py tests/test_material_combos.py`：30 项通过。
- 全量 `pytest -q`：300 项通过，2 项跳过。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。
- `alembic heads`：`20260807_01 (head)`，本批无迁移。

## 部署说明

- 未部署。
- 本批需要与尚待部署的售后物料组合后端 `6e4ae93` 一起部署；无需额外执行迁移，仍只需升级到 `20260807_01`。
- 部署后请按原门禁验证物料清单主动筛选、卡片保存不写覆盖列、组合选择停用物料及组合重新加载后的停用角标。
