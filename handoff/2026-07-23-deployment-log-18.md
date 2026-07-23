# 部署记录 · PDM 纯转换逻辑拆分（周期二 P3 分批拆分·第三组）

日期：2026-07-23

## 背景

在 `2026-07-23-codex-rd-excel-fixture-guards-handoff.md` 建立的 Excel 逻辑行为护栏保护下，Codex 开始拆分 PDM/ECR/ECN/BOM 四块纯逻辑中体积最小的一块：PDM→ERP/BOM 转换。交接文档：`handoff/2026-07-23-codex-rd-pdm-service-handoff.md`。

## 审查结论

`codex/rd-pdm-service`（`75de8fd` + `880c4c3`）审查通过，`git merge --ff-only` 合入 master：

- `build_erp_data()`/`build_bom_data()`（原 `_ptb_build_erp_data`/`_ptb_build_bom_data`）及列映射常量 `MATERIAL_COLUMNS`/`BOM_COLUMNS`（原 `_PTB_COLUMNS_TO_MATERIAL`/`_PTB_COLUMNS_TO_BOM`）移到新文件 `services/rd/pdm_to_bom.py`，逐行核对函数体（循环结构、默认值分支、`dict_bom` 聚合顺序）与原代码完全一致，只改了函数名/常量名，无逻辑变化。
- 上传校验（`read_spreadsheet_upload`）、临时文件处理、模板加载、HTTP 响应封装全部保留在 `routes/rd/__init__.py`，只是调用处从本地函数改成 `from services.rd.pdm_to_bom import build_bom_data, build_erp_data`。
- `test_rd_excel_logic.py` 同步更新为直接测试 service 层函数，并新增负向断言 `assert not hasattr(rd_routes, '_ptb_build_erp_data')` / `_ptb_build_bom_data`，确认旧函数确实从路由模块移除，不是"新增了 service 但路由里还留着旧实现"这种表面拆分。
- 本地复跑：`pytest` 135 passed，`compileall`/`git diff --check` 通过。

## 部署

按顺序（先上传 service，再上传路由，最后 reload）：

1. 确认服务器无导入/resolve 任务在跑。
2. scp 上传 `services/rd/pdm_to_bom.py`，md5 核对一致。
3. scp 上传 `routes/rd/__init__.py`，md5 核对一致。
4. `systemctl reload gunicorn`；8秒后复查：master pid 2151 未变，新 worker（7626）干净启动，无崩溃记录。
5. `/health`、`/ready` 均 200。
6. 实测 `pdm2bom/process`、`pdm2bom/export-erp`、`pdm2bom/export-bom` 三个端点（未登录）均返回 401 而非 500，证明 `services.rd.pdm_to_bom` 被正确导入，路由层调用链路无异常。

## 影响说明

- 无接口契约变更、无数据库结构变更、无前端改动。
- PDM 转换纯逻辑现在位于 `services/rd/pdm_to_bom.py`，与路由的上传/模板/响应逻辑分离。

## 下一批

Codex 建议稳定后再单独处理体积更大的 ECR/ECN/BOM 纯逻辑拆分（`_compare_bom`、`_build_ecr_xlsx`/`_parse_ecr_rows_xlsx`、`_build_ecn_xlsx` 等），已有 `test_rd_excel_logic.py` 里对应的行为护栏兜底。
