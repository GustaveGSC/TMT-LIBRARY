# 交接说明 · Claude → Codex（第二十轮，权限体系补充：开发者/运维权限码）

日期：2026-07-23

用户要求重新梳理权限体系，明确"开发者/管理者/运维/各功能模块"四类。已和用户对齐两个关键决策：

1. **admin 角色继续保留"绝对绕过一切权限检查"的现状**（`has_permission()` 里 `if 'admin' in roles: return True` 不变）。admin 天然拥有全部权限，包括本次新增的权限码。
2. **author 账号继续保留硬编码特殊账号身份**（不改成数据库角色），但把现在散落在前后端 7+ 处的 `username === 'author'` 判断，收敛为"author 对特定权限码有硬编码豁免"，为将来真要引入协作者留出扩展空间。

## 现状调研已确认的具体问题（我独立审计过，不是猜测）

- `backend/routes/account/__init__.py` 里 login-logs / login-stats 接口注释写"author 专用"，但实际鉴权只走蓝图级 `_require_account_auth`（校验 `'admin' in roles`），**admin 角色的账号目前也能访问**，和注释意图不一致。这次顺手用权限码方式统一解决，不需要单独再开一批修。
- `PUT /api/config/login-mottos`（登录页轮播语句配置）目前是 `'admin' not in roles and username != 'author'` 才拒绝，即 admin 或 author 才能改，其余账号无论如何都不行，没有走权限码体系，无法单独分配给"运维"这类新角色。

## 需要新增的权限码

| 权限码 | 用途 | 归属模块 |
|---|---|---|
| `analytics:view` | 查看用户行为分析（登录日志、DAU统计） | 开发者 |
| `ops:edit` | 运维配置（当前范围：登录页轮播语句管理；未来可扩展到版本发布等） | 运维 |

请在权限 seed（`backend/database/models/account/` 相关或权限表初始数据）里补上这两条，`description` 建议：
- `analytics:view` → "查看登录日志与用户行为统计"
- `ops:edit` → "运维配置管理（登录页文案等）"

不需要新建"开发者""运维"这两个数据库角色本身——按现有角色管理界面的设计，用户可以自行在管理界面建角色、绑定这些新权限码，不需要预置。

## `has_permission()` 需要新增的硬编码规则

在 `backend/auth.py` 的 `has_permission(user, perm)` 里，`admin` 短路判断之后，新增：

```python
if user.get('username') == 'author' and perm in ('analytics:view', 'ops:edit'):
    return True
```

这样 author 账号对这两个权限码天然通过，其他账号需要显式绑定角色权限才能通过，逻辑和 `admin` 短路并列但范围更窄（只覆盖这两个特定权限码，不是全权）。

## 需要改用权限码校验的现有端点

1. **login-logs / login-stats（或类似的用户分析接口）**：把现在"蓝图级 `_require_account_auth` 里校验 `admin` 角色"这种方式，改成对这几个具体路由用 `has_permission(user, 'analytics:view')` 校验（admin 会自动通过，因为 admin 全权短路；author 会通过新加的硬编码规则；两者结果和现状完全一致，只是实现方式统一了）。
2. **`PUT /api/config/login-mottos`**：把现在的 `'admin' not in roles and username != 'author'` 判断，改成 `not has_permission(user, 'ops:edit')` 判断。admin/author 行为不变（分别走短路和硬编码豁免），但现在理论上可以给新角色单独分配 `ops:edit` 而不需要给他们 admin。

## 不需要改动的部分

- 账号本身的保护逻辑（`admin`/`author` 不可删除/禁用）——这是账号保护机制，和这次的权限码扩展无关，不用动。
- `page-users.vue` 里非 author 登录时隐藏 author 记录——这是前端展示逻辑，我这边处理（如果需要）。
- 四个业务模块（product/shipping/aftersale/rd）现有权限码不动。
- account 蓝图（用户/角色/权限管理本身）继续保持"只认 admin 角色"，不引入新权限码——这是本来就该由 admin 独占的核心管理功能，用户已确认这次不做进一步细分。

## 测试要求

- 新增权限码的 seed/migration 测试。
- `has_permission()` 的 author 硬编码豁免测试（覆盖：author 对 `analytics:view`/`ops:edit` 通过；author 对其他未列出的权限码不通过，防止硬编码规则范围意外扩大；admin 对新权限码依然通过）。
- login-logs 类接口和 login-mottos 接口改用权限码后的真实 Cookie 权限测试：普通账号无权限码时 403、绑定了对应权限码的普通账号可以通过、admin/author 行为与改动前一致。

## 提交方式

照例本地 `pytest`+`compileall`+`git diff --check`，写交接文档。这批涉及权限表数据变更（新增权限码），如果通过 migration 实现，按之前的部署纪律（备份数据库 + alembic upgrade + reload）来。

我这边前端会做：`usePermission.js` 暴露 `can('analytics:view')`/`can('ops:edit')`，首页"开发者工具"入口和设置抽屉"登录页文案管理"入口的显隐从 `isAuthor` 判断改用对应权限码判断。等你这批权限码上线后我再部署前端，顺序上后端先行。
