# 部署记录 · 取消 guest 角色与游客登录体系

日期：2026-07-23

## 背景

延续账号安全加固批次里"注册后角色语义"待决策的问题（`handoff/2026-07-23-deployment-log-21.md`），Codex 没有走我建议的"注册自动给 guest"方案，而是选择了另一条更彻底的路：直接取消 guest 角色和游客登录整个体系，从根本上消除 `api.md` 文档与实现之间的契约冲突。交接文档：`handoff/2026-07-23-codex-remove-guest-role-handoff.md`（提交 `4bad6f5`，直接提交在 master）。

## 审查结论

审查通过：

- `GET /api/account/guest` 端点及对应 `guest_login()` service 方法整体删除。
- `auth.py` 的 `verify_token()` 移除了对 `id=None, username='guest'` 的特殊信任分支（原逻辑会为这类 token 动态从数据库读取 guest 角色权限并放行），改为直接 `return None`，旧游客 Cookie 请求会走正常的 401 流程。
- `_CSRF_EXEMPT_ENDPOINTS`、`_ACCOUNT_PUBLIC` 两处豁免清单同步移除 `account.guest_login`。
- 新增 Alembic `20260723_01`：按 `user_roles` → `role_permissions` → `roles` 顺序删除 guest 角色及其关联（外键安全顺序），有完整的表/角色存在性判断（幂等，避免在表不存在的边缘环境报错）；downgrade 用 `INSERT ... WHERE NOT EXISTS` 保证可重复执行。
- 删除只负责创建 guest 角色的 `backend/scripts/seed_roles.py`（已确认不再被其他模块引用）。
- `test_token_revocation.py` 把原来的"guest token 权限动态生效"测试改写为 `test_legacy_guest_token_is_rejected`（断言遗留 guest token 返回401）；`test_alembic_baseline.py` 新增迁移专项测试，直接验证 guest 角色和两张关联表记录被精确删除、admin 角色不受影响。
- 本地复跑：`pytest` 154 passed；`compileall` 通过；`alembic heads` 单头 `20260723_01`。

## 前端清理（我完成）

- `UserSettingsDrawer.vue`：移除 `isGuest` computed（原判断依据是 `username === '游客'`，实际上和旧 `guest_login` 返回的 `username: 'guest'` 就对不上，是个本来就有问题的死判断）及"游客不显示改密"的模板分支，改密区块现在对所有用户可见。
- `page-permissions.vue`：`BUILTIN_ROLES` 从 `['admin', 'guest']` 改为 `['admin']`。
- `page-index.vue`：无本地用户信息时的兜底显示文案从"游客"改为"用户"（这只是一个防御性缺省值，正常流程不会触发）。
- `page-login-logs.vue` 的历史 `identity_type === 'guest'` 展示按 Codex 建议保留不动——这是纯展示历史日志数据的分支，数据库里的旧游客登录记录不会被删除，需要继续正确显示。
- 全局搜索确认前端没有残留对 `/api/account/guest` 的调用。
- 构建通过，无编译错误。

## 部署

这批涉及数据库结构和数据变更，按交接给出的顺序执行：

1. **全量备份数据库**：服务器上执行 `mysqldump --single-transaction --quick --routines --triggers`，压缩后存至 `/opt/backups/tmt_db_pre_20260723_01_20260723_132451.sql.gz`（38.6MB，`gzip -t` 校验通过）。过程中发现服务器 `.env` 文件是 CRLF 换行，直接 `source .env` 会因为 `$'\r'` 报错导致变量为空、mysqldump 连接失败产生一个空文件——已定位并改用 `tr -d '\r'` 逐行解析变量后重新执行，确认备份文件完整。
2. 确认无导入/resolve 任务在跑。
3. 上传迁移文件 `migrations/versions/20260723_01_remove_guest_role.py`、`auth.py`、`routes/account/__init__.py`、`services/account/__init__.py`、`database/models/account/__init__.py`，md5 逐一核对一致。
4. 删除服务器上的 `backend/scripts/seed_roles.py`。
5. `alembic upgrade head`：`20260721_04 → 20260723_01` 执行成功；查询 `roles` 表确认 guest 角色（原 id 未记录具体值）已消失，`admin` 及其余 8 个业务角色均完整保留。
6. `systemctl reload gunicorn`；8秒后复查：master pid 2151 未变，新 worker（12961）干净启动，无崩溃记录。
7. `/health`、`/ready` 均 200；`GET /api/account/guest` 返回 404（端点已移除，非 500）；`POST /api/account/login` 空 body 仍正常返回 400（登录主流程未受影响）。
8. 前端构建部署：`dist-web/index.html` 的 JS hash 与生产比对一致，部署完成后删除 `.old` 备份目录。

未在生产环境用伪造的旧 guest token 重复验证 401 行为——这是纯代码逻辑变化（移除一个 if 分支的特殊信任判断），已由本地 `test_legacy_guest_token_is_rejected` 直接对 `verify_token()` 做了精确验证，不需要在生产环境用无法安全获取签名密钥的方式重复测试。

## 影响说明

- **破坏性变更**：`GET /api/account/guest` 接口彻底移除，任何仍持有旧游客 Cookie 的客户端会话会变成 401（预期行为，游客登录本身已下线）。
- 数据库层面：`roles`/`user_roles`/`role_permissions` 三表中 guest 相关记录被物理删除；`user_login_log` 中历史游客登录记录（`username='guest'`）保留不动，仅用于审计追溯。
- 前端：改密码功能现在对所有登录用户可见（原来的"游客不可改密"分支是死代码，从未被触发过，因为并没有真正区分出游客身份的正确判断逻辑）。
- 现在"自助注册用户默认无角色/无业务权限，只能用通用工具"是唯一路径，不再有 guest 这条平行分支，`api.md` 与实现完全对齐。

## 未处理项

无——本批是登录/注册模块这一轮优化里最后一个待决策项的落地，前后端均已同步。后续如果要继续下一个模块的优化，可以另起话题。
