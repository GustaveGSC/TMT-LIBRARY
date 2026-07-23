# 部署记录 · admin 角色越权分配漏洞修复（含两处相邻绕过）

日期：2026-07-23

## 背景

用户提出"admin 是内置角色，是不是不应该可以分配给别的用户"，我独立核实后确认这是本次权限重做引入的真实权限提升漏洞（`handoff/2026-07-23-codex-handoff-22.md`）：`account:users:edit` 权限被拆分给 `manager` 角色后，manager 可以直接调用角色分配接口把自己或任何人提升为 `admin`。已部署前端纵深防御（隐藏 UI 选项，`53d8cfd`），本次是后端真正的安全边界。交接文档：`handoff/2026-07-23-codex-admin-role-escalation-fix.md`（提交 `0aa78fa`，直接提交在 master）。

## 审查结论

审查通过，且 Codex 在排查同一权限面时，主动发现并修复了两处我没有要求但同样严重的相邻绕过：

**1. 原始漏洞修复**：`assign_role`/`remove_role`/`delete_role` 在 `AccountService` 层新增守卫——分配/撤销 `admin` 角色要求操作者自己已持有 `admin` 角色，无 operator 上下文时默认拒绝（防止其他 service 调用路径绕过），内置 `admin` 角色本体任何人都不可删除。错误响应带稳定的 `error_code`（`admin_role_requires_admin`），路由层 `_guarded_mutation_response` 据此把这类失败映射成 403（其余业务失败仍是标准 400）。

**2.（主动发现）`PUT /api/account/users/:id` mass assignment**：原来的 `update_user()` 把请求体原样透传给仓储，仓储对任何 `hasattr(User, key)` 的字段都会赋值。这意味着一个只有 `account:users:edit` 的 manager，可以绕开专门的角色/状态/密码接口，直接一次 PUT 请求提交 `{"roles": [], "token_version": 999, "is_active": false}` 之类的字段，直接清空别人的 admin 角色、伪造 token_version 或篡改内部鉴权字段——这条路径完全不受"分配 admin 需要 admin"这条新守卫的保护，因为它压根不经过 `assign_role`。修复为白名单：这个通用更新接口现在只接受 `display_name` 一个字段，其余字段（含 `roles`/`password`/`is_active`/`username`/`token_version`）一律拒绝，密码/状态/角色必须走各自的专用端点。前端 `page-users.vue` 的编辑表单本来就只发 `display_name`（用户名编辑框在编辑模式下本就是禁用状态），所以这个收紧对现有前端零影响，纯粹是堵一个后端 API 层的口子。

**3.（主动发现）受保护账号密码重置接管**：`reset_password()` 原本任何有 `account:users:edit` 的账号都能重置任意用户密码，包括 admin/author。这意味着 manager 可以直接重置 admin 的密码，用新密码登录接管超级管理员账号——这是比直接分配 admin 角色更隐蔽的一条提权路径（分配角色至少在角色关联表里留痕，重置密码后攻击者可以直接以 admin 身份登录，行为上和"是 admin"没有区别）。修复为：admin/author 这两个受保护账号的密码重置，额外要求操作者自己已持有 admin 角色，非 admin 返回 403（`error_code=protected_account_requires_admin`）；普通账号不受影响，manager 仍可正常重置。

## 测试覆盖

新增/修改的测试精确到位：manager 分配/撤销 admin → 403 且断言仓储层的 `assign_role`/`remove_role` 函数从未被调用（不是"业务上被拒绝"而是"根本没走到数据变更那一步"）；manager 分配 developer 等普通角色 → 200 正常生效；service 层无 operator 上下文时变更 admin 角色 → 拒绝；删除内置 admin 角色 → 403；PUT 用户信息带 `roles`/`token_version`/`is_active`/`password` → 400 且仓储 `update` 从未被调用；manager 重置 admin 密码 → 403；admin 重置 author 密码 → 200 正常生效。本地复跑：`pytest` 175 passed；`compileall` 通过。

## 部署

本批无数据库变更，不需要 Alembic：

1. 确认服务器无导入/resolve 任务在跑。
2. 上传 `services/account/__init__.py`、`routes/account/__init__.py`，md5 核对一致。
3. `systemctl reload gunicorn`；8秒后复查：master pid 2151 未变，新 worker（15824）干净启动，无崩溃记录。
4. `/health`、`/ready` 均 200；探活三个关键端点（未登录）均 401（认证网关先拦截），非 500：`POST /api/account/users/:id/roles/:id`、`PUT /api/account/users/:id`（带 `roles:[]`）、`POST /api/account/users/:id/reset-password`。
5. 403 守卫本身的行为（manager 被拒绝、admin 正常通过）是纯逻辑判断，已由本地测试精确覆盖（断言到"仓储层函数从未被调用"这个粒度），不需要在生产环境用真实 manager 账号重复验证——目前生产也还没有账号被分配 manager 角色，没有真实账号可用于此项验证。

## 影响说明

- **接口契约变化**：`PUT /api/account/users/:id` 从"任意 hasattr 字段"收紧为"仅 `display_name`"，是破坏性收紧，但前端从未依赖被收紧的部分，无需同步修改。
- manager 角色现在是名副其实的"能管用户但不能自我提权/接管超管账号"，符合最小权限原则，这也是这次三处修复共同要达成的目标。
- admin/author 密码重置权限收窄为仅 admin 自己可操作，manager 如果需要重置自己账号密码本来就走"本人改密"通道，不受影响。

## 后续

用户提出的原始问题（admin 是否应该可被分配）到这里算是完整闭环：前端隐藏入口（`53d8cfd`）+ 后端强制校验（`0aa78fa`）+ 两处相邻漏洞一并堵上。权限体系重做的第四批"生产权限审计"（列出生产所有用户→角色→权限最终展开结果）可以在这之后排期。
