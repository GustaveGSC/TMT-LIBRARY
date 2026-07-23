# 部署记录 · 权限体系重做第一批（数据与兼容映射）

日期：2026-07-23

## 背景

延续权限体系重新设计（`handoff/2026-07-23-codex-permission-system-redesign-proposal.md` 定案、`handoff/2026-07-23-codex-handoff-21.md` 确认去掉版本发布范围），Codex 完成第一批：只新增权限数据和标准角色，不切换任何运行时鉴权逻辑。交接文档：`handoff/2026-07-23-codex-permission-redesign-phase1-handoff.md`（提交 `bdb0a65`，直接提交在 master）。

## 审查结论

审查通过：

- 新增 6 个权限码：`developer:analytics:view`、`account:users:view/edit`、`account:roles:view/edit`、`ops:login-config:edit`。确认**没有** `ops:release:edit`，符合上一轮确认去掉版本发布范围的要求。
- 新增 `developer`/`manager`/`ops` 三个标准角色，权限包精确绑定（developer→分析权限；manager→四个account权限；ops→登录页配置权限）。
- legacy `admin` 角色显式绑定数据库中**当前全部**权限（不只是新增的6个），为第二批移除代码级 admin 绕过做准备，行为上不会有任何变化。
- author 账号追加 `developer` 角色，**不撤销**任何既有角色（迁移只做加法）。
- admin 角色的用户和 author 的 `token_version` 递增一次——这是必要的 JWT 衔接：JWT payload 内嵌角色/权限，如果不失效旧 token，第二批切换后管理员可能带着迁移前的旧权限快照被意外锁出。
- 迁移全程幂等（`WHERE NOT EXISTS`模式），可重复执行不会重复插入。
- `test_alembic_baseline.py` 新增专项测试：精确断言三个标准角色的权限集合、admin拥有全部权限码、`ops:release:edit`确实不存在、author同时保留admin和拿到developer、普通账号（非admin非author）角色和token_version不受影响。
- 本地复跑：`pytest` 155 passed；`compileall` 通过；`alembic heads` 单头 `20260723_02`。

## 部署

按 Codex 给出的顺序：

1. **只读核对生产现状**（部署前）：
   ```
   admin  (id=1):  token_version=0, roles=admin
   author (id=12): token_version=0, roles=admin
   ```
   与迁移预期的起始状态一致（两者都只有 admin 角色）。
2. **全量备份数据库**：`mysqldump --single-transaction --quick --routines --triggers`，压缩至 `/opt/backups/tmt_db_pre_20260723_02_20260723_142417.sql.gz`（36.9MB，`gzip -t` 校验通过）。
3. 确认无导入/resolve 任务在跑。
4. 上传 `migrations/versions/20260723_02_prepare_permission_domains.py`、`scripts/seed_permissions.py`，md5 核对一致。
5. `alembic upgrade head`：`20260723_01 → 20260723_02` 执行成功。
6. **部署后核对**（对照 Codex 给的验证 SQL）：
   ```
   admin  (id=1):  token_version=1, roles=admin
   author (id=12): token_version=1, roles=admin,developer
   developer 角色权限: developer:analytics:view
   manager   角色权限: account:roles:edit, account:roles:view, account:users:edit, account:users:view
   ops       角色权限: ops:login-config:edit
   admin 角色权限数: 17（等于 permissions 表总数 17，即 admin 拥有当前全部权限）
   ops:release:edit 是否存在: 0（不存在）
   ```
   全部与预期精确匹配。
7. 本批无 Python 运行时代码变化，不需要为此单独 reload；`/health`、`/ready` 复查均 200（服务本身未受影响）。

## 影响说明

- 无接口契约变更（第二批才会切换运行时鉴权逻辑）、无前端改动。
- admin 和 author 账号的旧会话 Cookie 因 `token_version` 递增已失效，下次请求会收到 401，需要重新登录——这是预期行为，不是故障。其余普通业务账号完全不受影响。
- 目前权限表里的新角色/权限码尚未被任何运行时代码读取（第二批切换前，实际鉴权仍然是原来的 `admin` 角色代码绕过 + `username==='author'` 硬编码判断），本批纯粹是数据准备。

## 下一批

Codex 计划的第二批（后端鉴权切换）：
- 删除 `has_permission()` 的 admin 角色名绕过；
- account 蓝图从整体 admin 守卫改成 users/roles view/edit 权限矩阵；
- 用户分析端点切到 `developer:analytics:view`；
- 登录页配置写操作切到 `ops:login-config:edit`；
- `is_rd_admin()` 去掉 admin 角色绕过，只认 `rd:admin`；
- `version` 蓝图保持不动（已冻结功能）。

第二批完成后应与前端第三批（清理 `isAdmin`/`isAuthor`/`adminOnly`/`authorOnly`）连续部署，压缩界面权限显示和后端不一致的窗口期。
