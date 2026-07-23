# 部署记录 · ECR/ECN/BOM 纯逻辑拆分（周期二 P3 分批拆分·第四组）

日期：2026-07-23

## 背景

在 Excel 逻辑行为护栏（`2026-07-23-codex-rd-excel-fixture-guards-handoff.md`）和上一批 PDM 拆分（`2026-07-23-deployment-log-18.md`）之后，Codex 拆分体积最大的一块：ECR/ECN 生成解析 + BOM 比对，23 个纯函数，RD 主路由从约1450行降到约350行。交接文档：`handoff/2026-07-23-codex-rd-change-documents-service-handoff.md`。

## 审查过程（含一轮返工）

**首次提交**（`94abac6`）审查时发现真实缺陷：新文件 `services/rd/change_documents.py` 在 `validate_bom()` 的异常分支里调用 `report_internal_error(...)`，但文件顶部只 import 了 openpyxl 相关内容，完全没有 `from error_handling import report_internal_error`。这会在 BOM 文件 `load_workbook` 失败时抛出未处理的 `NameError`，而不是原本设计的"记录内部错误 + 返回友好提示"。当时全量测试未捕获，是因为 `read_spreadsheet_upload` 的上传层校验已经在更早阶段拦截了畸形文件，这条异常分支在现有测试路径下走不到——但仍是一个真实的地雷：一旦出现"通过上传层校验但 openpyxl 打开仍失败"的文件（例如加密文件、上传层校验和 openpyxl 解析标准不完全一致的边缘情况），会直接 500 而不是预期的友好错误。已要求 Codex 修复后再合并，未合并这次提交。

**修复提交**（`656f952` + `a8f456a`）：
- 补上 `from error_handling import report_internal_error` 导入。
- 新增 `test_validate_bom_reports_open_failure`：直接 monkeypatch `report_internal_error` 并对不存在的文件调用 `validate_bom(role='before')`，断言返回 `'变更前文件无法读取（错误编号：fixed-error-id）'`，明确验证了失败分支不再抛 `NameError`。

## 最终审查结论

`codex/rd-change-documents-service`（`94abac6`+`656f952`+`ed43a11`+`a8f456a`）审查通过，`git merge --ff-only` 合入 master：

- 独立验证移动的正确性：把旧 `routes/rd/__init__.py` 中被删除的整段代码（1145行，样式常量到 `_parse_ecr_rows_xls` 结尾）与新 `services/rd/change_documents.py` 做归一化 diff（只把6个改名的入口函数 `_validate_bom`/`_compare_bom`/`_build_ecr_xlsx`/`_build_ecn_xlsx`/`_parse_ecr_rows_xlsx`/`_parse_ecr_rows_xls` 去掉下划线前缀后对比），结果**完全一致**（除了移走的注释分隔行和留在路由层的 `export_ecr` 路由函数本身），确认这是纯移动，无隐藏逻辑变化。
- `routes/rd/__init__.py` 里的调用点全部对应改成新函数名（`validate_bom`/`compare_bom_files`/`build_ecr_xlsx`/`build_ecn_xlsx`/`parse_ecr_rows_xls`/`parse_ecr_rows_xlsx`），multipart 上传、临时文件、错误映射、HTTP 响应封装原样保留在路由层。
- `test_rd_excel_logic.py`/`test_rd_upload_security.py` 同步更新为直接测试 service 层，并保留"旧函数确实从 `routes.rd` 移除"的负向断言。
- 本地复跑：`pytest` 136 passed（含 21 项定向测试），`compileall`/`git diff --check` 通过。

## 部署

按顺序（先上传 service，再上传路由，最后 reload）：

1. 确认服务器无导入/resolve 任务在跑。
2. scp 上传 `services/rd/change_documents.py`，md5 核对一致。
3. scp 上传 `routes/rd/__init__.py`，md5 核对一致。
4. `systemctl reload gunicorn`；8秒后复查：master pid 2151 未变，新 worker（8621）干净启动，无崩溃记录（日志中出现的 SAWarning 属于售后模块的既有查询警告，与本次改动无关）。
5. `/health`、`/ready` 均 200。
6. 实测 `ecr/export`、`ecr/parse-ecr`、`ecr/export-ecn`、`ecr/compare-bom` 四个端点（未登录）均返回 401 而非 500，证明 `services.rd.change_documents` 正确导入，路由调用链路无异常（包括本批修复的 `report_internal_error` 导入路径）。

## 影响说明

- 无接口契约变更、无数据库结构变更、无前端改动。
- ECR/ECN/BOM 纯逻辑现在位于 `services/rd/change_documents.py`；`routes/rd/__init__.py` 至此只剩路由/上传/响应封装，行数从约1450降到约350。

## 下一批

Codex 建议上线稳定后先观察，不立即继续拆 Blueprint（`routes/rd/cost.py` 902行、26个端点暂不处理）。
