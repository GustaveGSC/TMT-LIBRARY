# 部署记录 · codex/backend-p0 合并 + 上线

日期：2026-07-20
执行人：Claude（按 AGENTS.md 部署权限统一由 Claude 执行）

## 操作记录

1. 核实 Codex 的 `codex/backend-p0` 分支：`python -m pytest` 本地复跑 19 passed，抽查了 `security_config.py`/`app.py`/`account/__init__.py`/`resource.py` 的实际 diff，逻辑正确，`/import/return` 及 `import_return()` 清理干净无残留引用
2. 只读核实服务器 `.env`：确认之前完全没有 `JWT_SECRET`/`SHARE_SECRET`/`APP_ENV`/`ALLOW_REGISTER`，等于生产环境此前一直在用代码里的默认密钥（验证了 P0-2/P0-3 报告属实）
3. 生成强随机 `JWT_SECRET`/`SHARE_SECRET`（在远程 shell 里用 `openssl rand -hex 32` 直接生成并追加进服务器 `.env`，未在本地/对话记录中出现明文），加上 `APP_ENV=production`、`ALLOW_REGISTER=false`
4. `git merge codex/backend-p0`（fast-forward，master 现在是 `2c65089`）
5. scp 部署 6 个改动文件到服务器（`app.py`、`security_config.py`、`routes/account/__init__.py`、`routes/product/resource.py`、`routes/shipping/__init__.py`、`services/shipping/__init__.py`），逐文件 md5sum 核对一致
6. `systemctl reload gunicorn`，`is-active` 确认存活，`/health` 200

## 部署后验证

| 检查项 | 结果 |
|---|---|
| `POST /api/shipping/import/return` | 404（已下线） |
| `GET /api/resources/1/og-image`（无 key） | 403（分享校验生效） |
| `POST /api/account/register` | 403（公开注册已关闭） |
| `GET /health` | 200 |
| `POST /api/account/login`（错误密码） | 400（正常业务响应，服务未崩溃） |

fail-fast 没有误伤：gunicorn reload 后服务正常存活，说明新写入的 `JWT_SECRET`/`SHARE_SECRET` 生效且不是默认值。

## 已知影响（预期内，非故障）

- **所有此前登录用户的 token 立即失效**，因为 `JWT_SECRET` 从默认值换成了新的强随机值，需要重新登录
- **已有的资料分享链接全部失效**，因为 `SHARE_SECRET` 同理更换，需要重新生成分享链接

## 未部署的部分

前端这批改动（HTTPS 客户端地址等，`ddfcbf9` 及之前）**还没有 rsync 到服务器**，也没有打桌面端安装包。当前服务器上跑的仍是旧版前端静态资源。下次前端一起有新改动时再统一部署，或者你要现在单独部署这批可以再说一声。

## 后续

Codex 下一批建议：账号禁用/改密/撤权后旧 token 失效机制，配套自动化测试（见 [2026-07-20-codex-progress.md](2026-07-20-codex-progress.md) 的"尚未处理"部分）。
