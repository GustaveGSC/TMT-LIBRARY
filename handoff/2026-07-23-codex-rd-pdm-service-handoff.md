# RD PDM 纯转换服务拆分交接

日期：2026-07-23

## 本批完成内容

按既定小批次，只将 PDM 的两组纯数据转换逻辑从 `backend/routes/rd/__init__.py` 移到：

- `backend/services/rd/pdm_to_bom.py`
  - `build_erp_data()`
  - `build_bom_data()`
  - ERP 物料列顺序常量与 BOM 列顺序常量

路由层继续负责且未移动：

- `POST /api/rd/pdm2bom/process` 的 multipart 上传、大小/类型校验、临时文件清理与 PDM 解析。
- `POST /api/rd/pdm2bom/export-erp`、`export-bom` 的请求校验、模板加载、工作簿写入和文件响应。
- 模板资源路径定位及 PDM 必填列定义。

原函数主体按既有循环、默认值和输出顺序搬移；路由只增加 service import，并把两处调用切换到新函数名。URL、方法、权限、请求/响应、文件内容规则和数据库均未变化，无需修改 `api.md` / `database.md`，无 Alembic migration。

## 提交

- `75de8fd refactor(rd): extract PDM transformation service`

分支：`codex/rd-pdm-service`

## 验证结果

- `python -m pytest backend/tests/test_rd_excel_logic.py backend/tests/test_rd_route_guards.py -q`：7 passed
- `python -m pytest backend/tests -q`：135 passed
- `python -m compileall -q backend`：通过
- `python -m alembic -c alembic.ini heads`：`20260721_04 (head)`
- `git diff --check`：通过

测试已改为直接从 `services.rd.pdm_to_bom` 导入构建函数，并断言旧路由模块不再残留 `_ptb_build_erp_data` / `_ptb_build_bom_data`。

## Claude 审查与部署提示

重点核对 service 中两函数与旧实现逐行语义一致，特别是：

- 工作中心/生产部门固定值与工单/请购类型缺列默认值的不同规则。
- BOM 遍历顺序、直接子级判定、无效数量回退为 1。

部署必须先上传新增的 `backend/services/rd/pdm_to_bom.py`，再上传修改后的 `backend/routes/rd/__init__.py`，最后 reload gunicorn。随后按既有纪律检查延迟日志、master PID、`/health`、`/ready`。如做业务验证，可使用现有小型 PDM 文件走 process → export，不涉及数据库写入。

这批有运行时代码变化，需要部署，但不涉及数据库迁移。

## 下一步建议

本批稳定上线后，再单独处理 ECR/ECN/BOM 的 `change_documents.py`。该部分体积显著更大，建议先只搬纯辅助函数、BOM 解析比对和工作簿生成/解析，HTTP 上传、临时文件、错误映射与 `Response` 继续留在路由层；不要与路由文件拆 Blueprint 同批进行。
