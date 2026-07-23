# RD ECR/ECN/BOM 纯逻辑服务拆分交接

日期：2026-07-23

## 本批完成内容

将 ECR、ECN 与 BOM 的纯文件逻辑从 `backend/routes/rd/__init__.py` 原样迁移到：

- `backend/services/rd/change_documents.py`

service 包含：

- BOM 必要列校验、解析、版本推算与差异比对。
- ECR 工作簿生成与 xlsx/xls 解析。
- ECN 工作簿生成。
- Excel 样式、合并单元格、列宽、勾选文本等内部辅助函数和常量。

六个供路由调用的 service 入口为：

- `validate_bom`
- `compare_bom`
- `build_ecr_xlsx`
- `build_ecn_xlsx`
- `parse_ecr_rows_xlsx`
- `parse_ecr_rows_xls`

路由层继续保留：multipart 上传、大小/类型校验、临时文件创建与清理、异常到 HTTP 响应的映射、文件名和 `Response`。原 `rd_bp`、URL、方法、权限及响应契约均未变化。PDM 路由也未移动。

`backend/routes/rd/__init__.py` 现在只剩 8 个顶层函数：4 个 ECR/ECN/BOM HTTP 端点、资源路径函数和 3 个 PDM HTTP 端点；notes/reminders 仍由已拆出的子模块挂载。

无需更新 `api.md` / `database.md`，无数据库迁移。

## 提交

- `94abac6 refactor(rd): extract change document service`

分支：`codex/rd-change-documents-service`

## 等价性核验

除现有 fixture 外，本地执行了一次未提交的 AST 对比脚本：

- 从 master 读取搬移前的 `routes/rd/__init__.py`。
- 对 service 中 23 个顶层纯函数逐一比较参数 AST 和完整函数体 AST。
- 仅允许上述 6 个入口名称去掉私有下划线。
- 结果：`23 extracted functions match master AST`。

该一次性脚本已删除，没有进入提交。

## 自动化验证

- Excel fixture + 上传安全 + 路由护栏：20 passed
- `python -m pytest backend/tests -q`：135 passed
- `python -m compileall -q backend`：通过
- `python -m alembic -c alembic.ini heads`：`20260721_04 (head)`
- `git diff --check`：通过

测试调整：

- Excel fixture 改为直接从 `services.rd.change_documents` 导入。
- 负向断言确认旧路由不再残留 BOM 比对、ECR/ECN 生成和 ECR 解析私有函数。
- 上传安全测试的 monkeypatch 目标切换到路由实际导入的 service 入口；仍验证 multipart 成功路径会清理全部 4 个临时文件。

## Claude 审查与部署提示

重点审查：

- service 不应 import Flask、request、Response、上传校验或 tempfile。
- logo 相对路径从 `services/rd/change_documents.py` 向上三级后仍指向项目根目录 `src/assets/logo-banner.png`，与原 routes 路径层级相同。
- 路由中的异常消息、文件名、响应 mimetype、Content-Disposition 及 finally 清理保持原样。

部署顺序必须为：

1. 先上传新增的 `backend/services/rd/change_documents.py`。
2. 再上传修改后的 `backend/routes/rd/__init__.py`。
3. reload gunicorn，并按既有纪律检查延迟日志、master PID、`/health`、`/ready`。
4. 建议用最小文件分别验证 ECR 导出、ECR 解析、ECN 导出、BOM 比对；PDM 三端点也做冒烟验证，确认同一 Blueprint 初始化正常。

这批有运行时代码变化，需要部署，但不涉及数据库迁移。

## 后续建议

至此 RD 主路由的大块纯逻辑已抽离。下一步不要立即继续结构移动，先观察部署稳定性；之后可只读复核当前约 350 行路由是否还值得按 `change.py` / `pdm_to_bom.py` 拆 Blueprint。若拆，必须先证明父 Blueprint guard 对子 Blueprint 的覆盖方式，或为子 Blueprint 显式设置相同 guard，不能仅依赖 URL 快照。
