# 交接说明 · Claude → Codex（第二十轮，权限体系补充：开发者/运维权限码）

日期：2026-07-23

用户要求重新梳理权限体系，明确"开发者/管理者/运维/各功能模块"四类。已和用户对齐两个关键决策：

1. **admin 角色继续保留"绝对绕过一切权限检查"的现状**（`has_permission()` 里 `if 'admin' in roles: return True` 不变）。admin 天然拥有全部权限，包括本次新增的权限码。
2. **author 账号继续保留硬编码特殊账号身份**（不改成数据库角色），但把现在散落在前后端 7+ 处的 `username === 'author'` 判断，收敛为"author 对特定权限码有硬编码豁免"，为将来真要引入协作者留出扩展空间。

这条先只给方案，不预先分工谁改哪部分，你看完整体设计后评估怎么实施、需要动哪些文件、要不要拆批次，回个方案或者直接动手都可以。

## 现状调研已确认的具体问题（我独立审计过，不是猜测）

- `backend/routes/account/__init__.py` 里 login-logs / login-stats 接口注释写"author 专用"，但实际鉴权只走蓝图级 `_require_account_auth`（校验 `'admin' in roles`），**admin 角色的账号目前也能访问**，和注释意图不一致。
- `PUT /api/config/login-mottos`（登录页轮播语句配置）目前是 `'admin' not in roles and username != 'author'` 才拒绝，即 admin 或 author 才能改，其余账号无论如何都不行，没有走权限码体系，无法单独分配给"运维"这类新角色。
- 前端 `src/composables/usePermission.js`、`src/views/indexViews/page-index.vue`（首页"开发者工具"入口）、`src/components/user/UserSettingsDrawer.vue`（设置抽屉里"登录页文案管理"入口）目前都是靠 `isAuthor`（即 `username === 'author'`）控制显隐，和后端这次要收敛的判断是同一件事的前后端两侧。

## 设计：新增两个权限码

| 权限码 | 用途 | 归属模块 |
|---|---|---|
| `analytics:view` | 查看用户行为分析（登录日志、DAU统计） | 开发者 |
| `ops:edit` | 运维配置（当前范围：登录页轮播语句管理；未来可扩展到版本发布等） | 运维 |

不需要新建"开发者""运维"这两个数据库角色本身——按现有角色管理界面的设计，以后要引入协作者时可以自行建角色、绑定这些权限码，这次不用预置。

`has_permission()` 里 `admin` 短路判断之后建议新增：

```python
if user.get('username') == 'author' and perm in ('analytics:view', 'ops:edit'):
    return True
```

author 对这两个权限码天然通过，其他账号需要显式绑定角色权限才能通过。

**需要改用权限码校验的现有端点**：
1. login-logs / login-stats（或类似的用户分析接口）：改用 `has_permission(user, 'analytics:view')`。
2. `PUT /api/config/login-mottos`：改用 `has_permission(user, 'ops:edit')`。

两处改动后，admin/author 的实际行为都和现状完全一致，只是实现方式统一到权限码体系，同时为将来的角色扩展留出空间。

**不需要动的部分**：账号保护逻辑（admin/author 不可删除禁用）、四个业务模块现有权限码、account 蓝图（用户/角色/权限管理本身继续只认 admin 角色，这次不做进一步细分）。

## 测试要求

- 新增权限码的 seed/migration 测试。
- `has_permission()` 的 author 硬编码豁免测试（覆盖：author 对 `analytics:view`/`ops:edit` 通过；author 对其他未列出的权限码不通过，防止硬编码规则范围意外扩大；admin 对新权限码依然通过）。
- login-logs 类接口和 login-mottos 接口改用权限码后的真实 Cookie 权限测试：普通账号无权限码时拒绝、绑定了对应权限码的普通账号可以通过、admin/author 行为与改动前一致。

## 提交方式

照例本地 `pytest`+`compileall`+`git diff --check`，写交接文档。这批涉及权限表数据变更（新增权限码），如果通过 migration 实现，按之前的部署纪律（备份数据库 + alembic upgrade + reload）来。前端联动的部分（`isAuthor` 判断改用权限码）等你确认整体方案/后端落地后再定谁来做、怎么排期。
