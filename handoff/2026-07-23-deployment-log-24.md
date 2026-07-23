# 部署记录 · 权限体系重做第二批（后端切换）+ 第三批（前端切换）连续部署

日期：2026-07-23

## 背景

延续权限体系重做（第一批数据准备已部署，见 `deployment-log-23.md`），Codex 完成第二批后端鉴权切换，我完成第三批前端同步。按 Codex 建议连续部署，压缩权限显示不一致的窗口期。交接文档：`handoff/2026-07-23-codex-permission-redesign-phase2-handoff.md`（后端提交 `b263138`）。

## 审查结论：后端第二批

审查通过：

- `has_permission()` 删除 `admin` 角色名短路；`is_rd_admin()` 改为直接调用 `has_permission(user, 'rd:admin')`，不再有角色名绕过。
- `account` 蓝图从"整体 admin 守卫"改成端点权限矩阵（`_ACCOUNT_ENDPOINT_PERMISSIONS` 字典），逐一核对蓝图内全部路由（login/register/logout 公开，change_password 本人+`account:users:edit`，其余 18 个端点全部有对应权限码映射），确认没有端点遗漏导致意外放行或意外拒绝。
- `PUT /api/config/login-mottos` 改用 `has_permission(user, 'ops:login-config:edit')`。
- `backend/routes/product/resource.py` 资料类型管理移除了多余的 `_require_admin()` 二次校验——这个检查本来就是冗余的，蓝图级 `make_blueprint_guard('product:view', 'product:edit', ...)` 已经在守护，之前是"产品编辑者因为第二层 admin 检查被误拒绝"的真实 bug，这次顺带修掉。
- `version` 蓝图确认未动，仍是唯一保留角色名鉴权的冻结功能。
- 新增 `test_explicit_permission_authorization.py`：精确验证 admin 角色名无权限码时被拒绝、author 用户名无 developer 权限时被拒绝、账号端点矩阵逐条 exact-match、资料类型管理改用 product:edit 而非 admin 角色。
- 本地复跑：`pytest` 165 passed；`compileall` 通过；`git diff --check` 除文档里的 markdown 软换行尾随空格外无问题。

## 审查结论：前端第三批（我完成）

- `usePermission.js`：`can()` 删除 `isAdmin` 全局放行，新增 `canViewAnalytics`/`canViewUsers`/`canEditUsers`/`canViewRoles`/`canEditRoles`/`canEditOpsLoginConfig` 计算属性；`isAdmin` 保留但仅用于纯展示（"管理员"标签）和冻结的 version-release 入口。
- `routers/index.js`：删除 `authorOnly`；`/admin/users`→`account:users:view`、`/admin/permissions`→`account:roles:view`、`/admin/login-logs`→`developer:analytics:view`；`adminOnly` 只保留给 `/admin/version-release`（冻结）；路由守卫的权限检查删除 `isAdmin` 短路，纯按 `perms.includes(required)` 判断。
- `UserSettingsDrawer.vue`：管理员/开发者/运维三组入口分别按 `canViewUsers`/`canViewRoles`/`canViewAnalytics`/`canEditOpsLoginConfig` 独立显隐；版本发布入口保留 `isAdmin` 判断（对应后端仍未改动的冻结逻辑）。
- `page-index.vue`：清理了两处死代码——`isAuthor`/`isAdmin` 变量声明后实际未在模板任何位置使用（"开发者工具"入口早已迁移到 `UserSettingsDrawer.vue`，这两个变量是遗留）。
- `ProductResources.vue`："管理类型"按钮从 `isAdmin` 改为 `canEditProduct`，与后端 `product:edit` 对齐。
- **主动发现并修复的衔接问题**：`page-permissions.vue`/`page-users.vue` 的路由访问权限从 `adminOnly` 放宽为 `account:roles:view`/`account:users:view`（只读权限）后，页面本身原来没有区分"查看"和"编辑"两种权限——只有 `account:*:view` 权限的用户进入页面后仍会看到"新增/编辑/删除/绑定权限"等操作按钮，点击后会被后端 403 拒绝，是个真实的 UX 缺口。已补上 `canEditRoles`/`canEditUsers` 门禁到对应的新增/编辑/删除/绑定权限按钮上，这不在 Codex 交接文档列出的清单里，是我在实现过程中发现并顺手修的。

本地 `npm run build:web` 构建通过，无编译错误。

## 部署

按 Codex 建议的连续部署顺序：

1. 确认服务器无导入/resolve 任务在跑。
2. 上传后端 4 个文件（`auth.py`、`routes/account/__init__.py`、`routes/config/__init__.py`、`routes/product/resource.py`），md5 逐一核对一致。
3. `systemctl reload gunicorn`；8秒后复查：master pid 2151 未变，新 worker（14708）干净启动，无崩溃记录。
4. `/health`、`/ready` 均 200；探活关键端点均无 500：`GET /api/account/users`（未登录）401、`GET /api/account/login-logs`（未登录）401、`PUT /api/config/login-mottos`（未登录）401、`GET /api/config/login-mottos`（公开）200、`POST /api/resources/types`（未登录）401。
5. 立即上传完整 `dist-web/`：`index.html` 的 JS hash 与生产比对一致，部署完成后删除 `.old` 备份目录。

## 未完成的验证：需要人工确认

Codex 建议的部署后验收步骤里，"用当前 admin/author 实测用户列表、权限页 API、登录分析 API、登录文案保存"和"用 developer/manager/ops 权限账号分别验收页面入口和 API"这两步需要真实账号登录，我这边不持有 admin/author 的登录密码，无法代为验证。**需要你登录后实测**：

- admin 账号：重新登录（上一批迁移已使旧会话失效）后，确认用户管理/权限管理页面能正常打开和操作（因为迁移已经给 admin 显式绑定了全部17个权限码）。
- author 账号：重新登录后，确认"用户分析"入口可见且能看到登录日志/DAU数据；如果 author 同时还保留 admin 角色（迁移未撤销），管理员相关入口也应该继续可见。
- 如果方便的话，用 `page-permissions.vue` 给某个测试账号分配 `developer`/`manager`/`ops` 三个新角色中的一个，验证对应入口按预期显隐、越权操作按预期被拒绝（403），验证完可以删除测试角色分配。

## 影响说明

- **破坏性变更**：任何账号如果此前是靠 `admin` 角色名或 `username==='author'` 隐性获得功能权限（而没有被第一批迁移显式赋权），现在会失去对应功能入口/接口访问权。第一批迁移已经处理了 admin（显式绑定全部权限）和 author（追加 developer 角色，保留原有 admin），理论上不会有人意外掉权，但仍需人工登录确认。
- 资料类型管理（`/api/resources/types`）现在任何有 `product:edit` 权限的账号都可以操作，不再需要 admin 角色——这是范围放宽（面向所有产品编辑者），不是收紧。
- `version` 蓝图（Electron 安装包分发，已冻结）继续用 admin 角色名鉴权，是这次重做里唯一保留的角色名鉴权入口，将来清理 Electron 死代码时再一并处理。

## 下一步

Codex 交接的第四批"生产权限审计"（列出生产所有用户→角色→权限的最终展开结果，重点确认没有意外撤权/扩权，用测试账号验收后删除）待人工验证完成后再排期。
