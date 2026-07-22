# 部署记录 · RD 遗留路径读取协议移除（周期二 P3 第十六轮）

日期：2026-07-22

## 背景

`handoff/2026-07-22-codex-handoff-16.md` 批准跳过排期，立即执行审计报告里的"第0批：安全门禁"：`parse-ecr`/`compare-bom`/`pdm2bom/process` 三个端点此前接受 JSON 里的 `ecr_path`/`bom_before_path`/`bom_after_path`/`file_path` 字段并直接检查/读取服务端任意文件系统路径，是已停用 Electron 桌面端协议留下的安全债。交接文档：`handoff/2026-07-22-codex-rd-upload-security.md`。

## 审查结论

`codex/rd-upload-only`（`f94ffc9` + `69722a5`）审查通过，`git merge --ff-only` 合入 master：

- 三个端点的 `content_type` 分支判断全部移除，只保留原来 multipart 分支的逻辑（`request.files.get(...)` + `read_spreadsheet_upload` 校验 + 临时文件），非 multipart 请求不再有任何特殊处理路径。
- 新增 `backend/tests/test_rd_upload_security.py`：
  - 核心断言 `test_legacy_server_path_payloads_are_rejected`：对 `os.path.exists`/`os.path.isfile` 打 monkeypatch 让其抛异常，证明发送旧 JSON 路径字段时代码**根本不会走到路径检查这一步**，直接 400，而不是"检查了但拒绝"——这是最强的回归保护，不是黑盒测试。
  - 另有缺文件 400、非法文件内容 400、超限 413、成功路径下临时文件清理（4 个临时文件全部 `os.unlink`）等测试，覆盖全面。
- `.claude/modules/api.md` 同步更新了这三个接口的说明（不再提"桌面端传路径"）。
- 本地复跑：`pytest` 128 passed，`python -m compileall backend` 通过，`git diff --check` 通过。

## 部署

只涉及 `backend/routes/rd/__init__.py` 一个运行时文件，无数据库变更：

1. 确认服务器无导入/resolve 任务在跑。
2. scp 上传 `backend/routes/rd/__init__.py`，md5 核对一致（`4f8628454f9a388f77aba18a0fd5edbc`）。
3. `systemctl reload gunicorn`；8秒后复查：master pid 2258 未变，新 worker（14789）干净启动，`journalctl` 无崩溃记录。
4. `/health`、`/ready` 均 200。
5. 生产环境实测：向 `POST /api/rd/ecr/parse-ecr` 发送旧协议 JSON payload（`{"ecr_path":"/etc/passwd"}`），返回 401（未登录先被认证拦截，符合预期，未触发 500，证明部署无异常）。协议层面的拒绝行为已由本地测试的 `os.path.exists`/`isfile` 不被调用这一断言充分验证，不需要在生产环境用真实账号重复验证。

## 影响说明

- 接口契约变化：`parse-ecr`/`compare-bom`/`pdm2bom/process` 不再接受 `ecr_path`/`bom_before_path`/`bom_after_path`/`file_path` JSON 字段，只接受 multipart 上传。
- 前端 `EcrForm.vue`/`EcnForm.vue`/`PdmToBomForm.vue` 里发送这些字段的代码全部包在 `window.electronAPI` 判断内，Electron 已停用，实际不会被触发，未做改动。
- `frontend-rdtools.md` 里"发送本地文件路径"的陈旧描述待我下一步更新。

## 下一批

回到审计报告排的"第1批：建立行为护栏"（URL map 快照测试覆盖全部 17 个主 RD + 26 个 cost 路由/方法；`_compare_bom`/ECR/ECN 往返/`_ptb_build_erp_data`/`_ptb_build_bom_data` 的 fixture 测试；notes/reminders 真实权限/归属测试），是否现在做还是先歇一版待定。
