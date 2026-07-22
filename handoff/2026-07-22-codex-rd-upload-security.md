# 交接说明 · Codex → Claude（RD 第0批：关闭服务端路径读取）

日期：2026-07-22

## 完成内容

- 提交：`f94ffc9 fix(rd): remove server path upload protocol`
- 分支/worktree：`codex/rd-upload-only` / `E:/Project/tmt-library/.worktrees/codex-rd-upload-only`
- 以下三个端点已删除 JSON 路径分支，只接受 `multipart/form-data`：
  - `POST /api/rd/ecr/parse-ecr`：字段 `ecr_file`
  - `POST /api/rd/ecr/compare-bom`：字段 `bom_before`、`bom_after`
  - `POST /api/rd/pdm2bom/process`：字段 `pdm_file`
- `ecr_path`、`bom_before_path`、`bom_after_path`、`file_path` 不再被读取、检查或传给 Excel 解析器；非 multipart 请求因缺上传文件返回 400。
- 三条 multipart 路径继续经过 `read_spreadsheet_upload` 的扩展名、MIME、文件头、大小和 zip bomb 校验。
- 临时文件行为保持不变并由 finally 清理。
- `.claude/modules/api.md` 新增三个接口的上传契约及旧协议下线说明。

## 自动化测试

新增 `backend/tests/test_rd_upload_security.py`，13 个用例覆盖：

- 四个旧路径字段分别发送时返回 400。
- 旧协议测试将 `os.path.exists/isfile` 替换为调用即失败，证明服务端没有检查客户端路径。
- 三个端点缺文件返回 400。
- 三个端点伪造 Excel 内容返回 400。
- 三个端点上传超限错误映射为 413。
- 三个 multipart 成功路径均返回 200，并验证创建的 4 个临时文件全部删除。

全量验证：

- `python -m pytest backend/tests -q`：128 passed。
- `python -m compileall -q backend`：通过。
- `python -m alembic -c alembic.ini heads`：`20260721_04 (head)`。
- `git diff --check`：通过。
- 运行时代码全仓搜索确认不再含四个旧请求字段。

## 部署

- 无数据库迁移、无前端改动或构建要求。
- 上传 `backend/routes/rd/__init__.py` 后执行 `systemctl reload gunicorn`。
- 延迟复查 status/journal，并验证 `/health`、`/ready`。
- 用 Web 端分别实测 ECR 解析、BOM 比对、PDM 处理至少各一次；确认 multipart 正常。
- 可用已认证 rd:edit 会话发送旧 JSON 请求做负向验证，预期 400 且消息要求上传文件。

## 影响说明

- 当前 Web 调用不变。
- 已停用 Electron 的路径型请求将收到 400，这是批准的安全性破坏性变更。
- 不涉及 notes/reminders 拆分；下一批回到审计计划的“建立行为护栏”。

本批未部署、未 push，未修改 `src/` 或 Electron。
