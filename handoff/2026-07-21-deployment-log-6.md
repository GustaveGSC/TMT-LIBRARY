# 部署记录 · P1异常泄露/readiness检查/SQL拼接隐患 + product:delete后端清理

日期：2026-07-21
分支：`codex/backend-p1-error-readiness-sql`（`b95c7d9`），fast-forward 合并，73 passed。

## 审查结论

- **异常响应收紧**：新增 `backend/error_handling.py`，`report_internal_error`/`internal_error_response`/`internal_error_result`/`internal_task_error` 四个变体覆盖了项目里几种不同的错误返回写法（直接 Response、Result 转 response、Result 对象、后台任务消息字符串）。服务端用 `current_app.logger.exception()` 记录完整 traceback，客户端只收到"XX失败（错误编号：xxxxxx）"，不再泄露原始异常文本。改动面覆盖了 product/resource、rd、rd/cost、shipping、version、aftersale 等多处路由。
- **`/ready` readiness 检查**：`_check_database_readiness` 执行 `SELECT 1` 探测真实数据库连接，和原有的 `/health`（纯进程存活）分开，503 表示未就绪。
- **SQL 拼接修复**：`aftersale/__init__.py` 的 `q_distinct` 改成接收 ORM 列对象（`AftersaleCase.channel_name` 等），彻底不再有字符串拼接进 SQL 的路径，不是简单加白名单校验，是从根上换了实现方式。
- **`20260721_01` 迁移**：删除 `product:delete` 权限种子数据，迁移里做了幂等处理（表不存在/权限不存在都直接跳过）和正确的删除顺序（先删 `role_permissions` 关联再删 `permissions` 行，避免外键报错），downgrade 也写了。

## 部署过程

1. 迁移涉及权限表数据变更，先做了一次全量 mysqldump 备份（`/opt/backups/tmt_db_pre_20260721_01_*.sql`）
2. 部署 15 个文件（`app.py`、`error_handling.py` 新文件、迁移文件、以及所有替换了异常处理写法的路由/服务文件），md5 全部核对一致
3. `alembic upgrade head`：`20260720_02 -> 20260721_01`，`alembic current` 确认到 head
4. `systemctl reload gunicorn`，等待几秒后复查 `status`/`journalctl`，确认无崩溃
5. 验证 `/health`、`/ready`、登录接口

## 意外发现并顺手修复：nginx 从未代理 `/health`/`/ready`

验证 `/ready` 时发现返回的是前端 SPA 的 `index.html`（HTTP 200，但内容是网页不是 JSON）。排查发现 `/etc/nginx/conf.d/tmt-library.conf` 里 `location /` 是 `try_files $uri /index.html`（SPA 兜底），而 `/health`/`/ready` 从来没有单独的 `location` 块代理到后端——**`/health` 端点从部署以来可能就一直没有真正生效过**，之前的验证只看了 HTTP 状态码（都是 200），没看响应内容，所以一直没发现。

已在 nginx 配置里补上：
```nginx
location /health {
    proxy_pass http://127.0.0.1:8765;
    proxy_set_header Host $host;
}
location /ready {
    proxy_pass http://127.0.0.1:8765;
    proxy_set_header Host $host;
}
```
改之前备份了原配置文件（`tmt-library.conf.bak.*`），`nginx -t` 语法检查通过后 `systemctl reload nginx`（不是 restart）。验证：直连 `127.0.0.1:8765` 后端本身一直是对的，问题完全在 nginx 转发层。现在 `/health`、`/ready` 都能拿到正确的 JSON，首页正常。

## 部署后验证

| 检查项 | 结果 |
|---|---|
| `/health`（经 nginx） | `{"status":"ok"}` |
| `/ready`（经 nginx） | `{"status":"ready"}` |
| 登录接口（错误密码） | 400，正常响应 |
| gunicorn reload | 无崩溃，日志干净 |
| 首页 | 200，正常加载 |

## 教训

以后验证健康检查类端点，不能只看 HTTP 状态码，要看**响应内容**——SPA 的 `try_files` 兜底会让几乎任何路径都返回 200，状态码本身不能证明请求真的到了后端。
