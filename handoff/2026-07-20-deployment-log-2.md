# 部署记录 · codex/backend-p1-token 合并 + 上线 + P1-5 核实

日期：2026-07-20

## P1-1 token 撤销机制

1. 核实 `codex/backend-p1-token`：本地复跑 `python -m pytest` 28 passed；抽查 `auth.py`/`app.py`/`repository/account`/`services/account` 的实际 diff，逻辑正确——`generate_token`/`verify_token` 正确处理了 guest token（`id: None` 走独立分支，不会 KeyError），`_bump_token_versions` 批量更新覆盖了改密/禁用/角色分配移除/角色删除/权限变更等全部场景，迁移用 `GET_LOCK` 避免并发 DDL，失败改成 `raise` 而不是静默吞掉
2. `git merge codex/backend-p1-token`（fast-forward，master 现在是 `d3c1766`）
3. 部署 5 个文件到服务器（`app.py`、`auth.py`、`database/models/account/__init__.py`、`database/repository/account/__init__.py`、`services/account/__init__.py`），md5 核对一致
4. `systemctl reload gunicorn`，日志确认 `[migration] users.token_version 列已添加`，服务存活
5. 直连生产库确认 `users.token_version` 列已存在，默认值 0

### 部署后验证

| 检查项 | 结果 |
|---|---|
| `/health` | 200 |
| 登录接口（错误密码） | 400，正常响应未崩溃 |
| `users.token_version` 列 | 已添加，默认 0 |

### 已知影响

同上一批，`JWT_SECRET` 语义未变但账号状态相关的旧 token 现在会在改密/禁用/调权后立即失效——这次部署本身不会让当前在线用户掉线（迁移只加列，不改现有账号状态），后续管理员做账号操作时才会体现效果。

## P1-5 连接池核实（只读排查）

服务器实际配置比文档假设的更简单：

- **gunicorn 只有 1 个 worker**（`-w 1`，`/etc/systemd/system/gunicorn.service`），不是文档/注释假设的 4 个
- 生产 `.env` 此前**完全没有** `POOL_SIZE`/`MAX_OVERFLOW`，实际吃的是代码默认值 `5`/`5`（单 worker 下最多 10 个连接）
- 之前怀疑的 `POOL_SIZE=10,MAX_OVERFLOW=10`（4 worker 峰值 80 连接）是仓库里 `backend/.env.web` 模板文件的内容，**从未在生产环境生效过**，属于虚惊

处理：已在生产 `.env` 显式追加 `POOL_SIZE=5` `MAX_OVERFLOW=5`（和当前实际生效值相同，只是从"依赖代码默认值"变成"显式配置"，避免以后代码默认值改了没人发现）。`.claude/CLAUDE.md` 里"QueuePool(size=2)"的表述已经过期，需要 Codex 或我找时间更新（不算紧急，这次先记录，下次碰文档时顺手改）。

这个发现也降低了 P1-2（内存后台任务与多 worker/reload 不兼容）的严重性：既然只有 1 个 worker，"请求被路由到不同 worker 查不到任务状态"这个场景不存在。P1-2 剩下的真实风险是 reload 替换掉这唯一的 worker 进程时，内存任务状态和运行中的 daemon thread 会被清空/杀掉——这条依然成立，只是不再需要按"多 worker"的复杂度设计方案。

## 未部署

前端改动仍未部署（同上一次记录）。
