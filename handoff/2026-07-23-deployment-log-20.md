# 部署记录 · 售后语义匹配修复 + RD 成本库权限修复（全项目复查 P0/P1）

日期：2026-07-23

## 背景

`handoff/2026-07-23-codex-project-rescan.md` 全项目只读复查发现两个真实问题，`handoff/2026-07-23-codex-handoff-17.md` 批准立即修复：

1. **P0**：`match_shipping_alias()` 引用未定义的 `semantic` 变量，异常被 `except Exception: pass` 吞掉，导致语义匹配从未真正生效；无关键词命中时进一步在空列表上 `IndexError`，与生产日志已出现的报错吻合。
2. **P1**：`/api/rd/cost`（`cost_bp`）没有继承 `rd_bp` 的 `rd:view`/`rd:edit` Blueprint guard，任何登录账号理论上都能读取 RD 成本数据。

## 审查结论

`codex/aftersale-cost-auth-fixes`（`30f7b02`+`3f42557`+`cc1138e`）审查通过，`git merge --ff-only` 合入 master：

**售后修复**：
- `match_shipping_alias()` 新增 `semantic=True` 参数；`suggest_product()` 调用处透传 `semantic=semantic`（原来完全没传，是 bug 根因）。
- 语义评分分支的 `except Exception: pass` 改为 `report_internal_error('售后发货简称语义匹配失败')`，异常不再被静默吞掉。
- `best_kw_matched >= 2 or not sem_scores` 分支里新增 `if not top_candidates: return None, 0.0`，堵住空列表越界。
- 独立核实：第二处融合评分逻辑（`best_id`/`best_score` 初始化为 `None`/`-1.0` 的循环归约）本身不存在同类索引风险，不需要修改。
- 新增 `test_aftersale_shipping_alias.py` 4 个测试：无关键词无语义→`(None, 0.0)`、无关键词有语义命中→正确兜底、关键词并列→备注 tie-break 正确、语义模块异常→记录日志且安全返回 `(None, 0.0)`（直接断言 `report_internal_error` 被调用且 context 文本正确）。

**RD 成本库权限修复**：
- `cost_bp.before_request(make_blueprint_guard('rd:view', 'rd:edit'))`，与 `rd_bp` 现有写法完全一致。
- 保留原有 `@require_auth` 和 `_require_edit()`，未做去重简化（按我的要求：先保证行为正确，去重可后续单独评估）。
- 新增 `test_rd_cost_requires_domain_permissions`：无 `rd:view` 的账号访问 `/api/rd/cost/snapshots` 返回 403；仅 `rd:view` 可读但 `POST /preview` 返回 403（缺 `rd:edit`）；`rd:view`+`rd:edit` 可通过权限检查进入业务逻辑（返回 400"请上传 Excel 文件"，而非 403）。

本地复跑：`pytest` 141 passed，0 warning；`compileall`/`git diff --check` 通过。

## 部署前确认

RD 成本库权限收紧后，没有 `rd:view`/`rd:edit` 的账号会立即失去访问能力。已向用户确认：目前实际使用该功能的账号均已分配相应权限，可以直接部署。

## 部署

按售后优先、权限其次的顺序：

1. 确认服务器无导入/resolve 任务在跑。
2. scp 上传 `database/repository/aftersale/__init__.py`，md5 核对一致。
3. scp 上传 `routes/rd/cost.py`，md5 核对一致。
4. `systemctl reload gunicorn`；8秒后复查：master pid 2151 未变，新 worker（9444）干净启动，无崩溃记录。
5. `/health`、`/ready` 均 200。
6. 实测 `GET /api/rd/cost/snapshots`（未登录）返回 401（认证网关先拦截），非 500，证明新 guard 正确挂载。
7. 售后语义匹配修复涉及内部业务逻辑（`confirm_case`/`suggest_product` 调用链），无法通过简单探活验证，已由本地新增的 4 个针对性测试充分覆盖异常路径和正常路径，暂不在生产环境单独触发验证。

## 影响说明

- 接口契约变化：`/api/rd/cost` 下 26 个端点现在要求 `rd:view`（写操作额外要求 `rd:edit`），此前实际上任何登录账号均可访问。
- 售后自动匹配的语义评分分支从"实际上从未生效"恢复为按设计工作；如果之后发现推荐结果和之前（错误状态下）有差异，属于修复带来的预期行为变化，不是新故障。

## 下一批

按报告推荐顺序，其余 P1/P2/P3 项（客户映射新鲜度、单 worker CPU 风险、RD cost 分页、排序规则、登录页 resize 泄漏、测试覆盖补齐、Electron 死分支清理、大文件拆分、仓库卫生）暂不批量启动，等本批观察稳定后再定。
