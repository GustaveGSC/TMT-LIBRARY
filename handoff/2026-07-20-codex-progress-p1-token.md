# Codex 后端进度 · P1-1 JWT 主动失效

日期：2026-07-20
分支：`codex/backend-p1-token`

## 方案

采用 `token_version`：

- `users` 新增 `token_version INT NOT NULL DEFAULT 0`。
- 注册用户 JWT 新增 `ver`。
- 每次鉴权只查询当前用户的 `is_active` 和 `token_version` 两列，不加载角色/权限关系。
- 账号不存在、被禁用或版本不一致时，沿用标准 HTTP 401。
- 游客请求读取当前 guest 角色权限，不继续信任 JWT 中可能过期的游客权限。

前端 `src/api/http.js` 无需修改，现有 401 清理登录态并跳转登录页的逻辑可以直接复用。

## 会使旧 Token 失效的操作

- 禁用或重新启用账号。
- 用户修改密码或管理员重置密码。
- 管理员通过用户更新接口修改密码/状态。
- 给用户分配或移除角色。
- 给角色分配权限、修改权限码或删除角色。
- 删除用户后，鉴权查询不到账号，也会返回 401。

## 数据库迁移

应用启动时添加 `users.token_version`；为避免 Gunicorn 多 worker reload 并发执行同一条 ALTER，迁移使用 MySQL advisory lock 串行化。该迁移失败会阻止新 worker 启动，不再静默忽略。

部署后，所有没有 `ver` 的旧注册用户和游客 Token 会失效，需要重新登录；交接已明确无需兼容旧 Token。

## 自动化测试

覆盖：

- 正常有效 Token 请求成功。
- 禁用账号后旧 Token 返回标准 401。
- 改密/token version 变化后旧 Token 返回标准 401。
- 删除账号后旧 Token 返回标准 401。
- 用户状态修改、密码修改确实请求递增 token version。
- 用户角色分配和移除都会递增 token version。
- 游客 Token 使用数据库中的当前 guest 权限。

验证命令：

```text
python -m pytest
python -m compileall -q backend
git diff --check
```

结果：`28 passed`；compileall 与 diff check 均通过。未连接生产数据库、未部署、未 push。

## 性能影响与 P1-5

每个需要鉴权的注册用户请求新增一条只查询 `users.is_active, users.token_version` 的主键查询。游客请求读取 guest 角色及权限。没有加入缓存，因为任务要求禁用/改密/撤权立即生效。

仓库代码默认仍是每 worker `POOL_SIZE=5, MAX_OVERFLOW=5`，文档声称 size=2；Claude 之前看到的未跟踪 `.env.web` 模板为 10/10，但该文件不在当前 worktree，Codex也没有读取生产服务器。本批部署前请 Claude 只读确认 systemd/Gunicorn 实际加载的 `.env` 中 `POOL_SIZE`、`MAX_OVERFLOW` 和 worker 数，再决定 P1-5 调整，避免仅改代码默认值却被生产环境变量覆盖。
