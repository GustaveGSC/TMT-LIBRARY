# 交接说明 · Claude → Codex（第六轮，回到正常顺序：P1-4 上传限制）

日期：2026-07-20
P1-2（任务持久化+导入原子性）已部署验证，过程中出过一次约1分45秒的启动崩溃（`interrupt_running_tasks()` 漏了 `app_context()`），我已经热修复并记录在 [2026-07-20-incident-startup-crash.md](2026-07-20-incident-startup-crash.md)，Alembic 也已推进到 `20260720_02`。

另外记一笔跟这轮任务无关的事：生产 `ALLOW_REGISTER` 已被业务方手动改回 `true` 并要求保持开放，这是业务决策不是回归，详见 [2026-07-20-registration-reopened.md](2026-07-20-registration-reopened.md)，以后不要因为看到之前的安全报告就把它改回去。

---

## 本轮任务：P1-4 上传/导入全局大小限制

之前 P0/P1 报告里提到的范围（比之前只做的 og-image token 校验范围更大）：

- 产品封面 base64 上传（`upload_cover_image`）
- OSS 资料预签名上传（`presign_upload`）
- 发货/财务 Excel 导入（`_check_file`，现在直接 `file.read()` 不限制大小）
- ECR/ECN/PDM 文件
- BOM 成本文件

Flask 目前没有设置 `MAX_CONTENT_LENGTH`，全局没有请求体大小上限。

建议分层：

1. Flask 全局请求上限（`MAX_CONTENT_LENGTH`，具体数值你评估，参考 nginx 那边 `/api/version/upload` 是 500M、其余 `/api/` 是 20M 的现有约定）
2. 不同业务类型的独立上限（Excel 导入 vs 图片封面 vs BOM 文件，业务性质不同没必要一刀切）
3. 扩展名 + MIME + 真实文件头联合校验，而不是只信任客户端声明的扩展名/MIME（`upload_cover_image` 现在就是只信任客户端 MIME 子类型这个问题）
4. Excel 导入这类，行数/工作表数量/解压后大小也要有上限（zip bomb 类风险）

## 建议的验证范围

1. 实现方案
2. 补测试：超限文件应该被拒绝、正常大小文件不受影响、伪造扩展名/MIME 应该被真实文件头校验拦住
3. 照例 `python -m pytest` + `python -m compileall -q backend` + `git diff --check`
4. **这次部署前，麻烦重点自查一遍新增代码里所有直接写在 `create_app()` 顶层、脱离蓝图注册逻辑之外的调用，是不是都正确包了 `app.app_context()`**——上次那个漏了 context 包裹的 bug 我审查时也没看出来，双方都需要养成这个核对习惯，不能只靠事后补测试

## 协作方式不变

独立 worktree/分支，部署我这边执行，完成后照例写交接文档。

---

## 我这边（前端）欠的账，接下来处理

Codex 之前提过："SSE `onerror` 不应直接把任务判为失败；调用 `GET /api/shipping/import/status/<task_id>` 回查"——这个前端消费逻辑我还没改，会在处理完这条消息后单独处理，不需要 Codex 等我。
