# 交接说明 · Claude → Codex（第二十二轮，修复 admin 角色可被越权分配的漏洞）

日期：2026-07-23

用户提出一个问题："admin 是内置角色，是不是不应该可以分配给别的用户"，我核实后确认这是一个真实的权限提升漏洞，由本次权限重做引入，需要立即修复。

## 问题

`backend/routes/account/__init__.py`：

```python
@account_bp.post("/users/<int:user_id>/roles/<int:role_id>")
def assign_role(user_id, role_id):
    return account_service.assign_role(user_id, role_id).to_response()
```

`assign_role`/`remove_role` 两个端点在权限矩阵里只要求 `account:users:edit`（见 `_ACCOUNT_ENDPOINT_PERMISSIONS`），对 `role_id` 具体是哪个角色**没有任何限制**。`page-users.vue` 的"分配角色"弹窗把 `GET /api/account/roles` 返回的全部角色（含 `admin`）平铺成 checkbox，同样没有过滤。

## 为什么这是本次重做才出现的新风险

第二批之前，account 蓝图整体只认 `admin` 角色（`_require_account_auth` 校验 `'admin' in roles'`），能进到这个功能的人本来就已经是 admin 了，谁分配给谁都不构成提权。

第二批把 `account:users:edit` 拆成独立权限码，就是为了让 `manager` 角色（不需要是 admin）也能管理用户——这正是这次重做的设计目标。但代价是：任何拿到 `manager` 角色（只有 `account:users:*` 四个权限码，没有 `admin`）的账号，现在可以打开这个弹窗，勾选 `admin`，把自己或任何人提升为拥有全部17个权限的超级管理员。这是一条完整的权限提升路径，且不需要任何额外条件。

目前生产环境还没有人被分配 `manager` 角色（只有 admin/author 持有 admin+developer），所以还没被实际利用，但这个漏洞会在第一次真正开始用 `manager` 角色时变成活跃风险——而这正是本次重做的核心使用场景，不能不修就上线用。

## 建议修复

分配/撤销 `admin` 角色本身，需要额外要求操作者自己已经持有 `admin` 角色——不能授予自己都没有的权限。具体：

在 `assign_role`/`remove_role`（或它们背后的 `account_service.assign_role`/`remove_role`）里，如果目标 `role_id` 对应的角色 `name == 'admin'`，额外检查 `'admin' in operator.roles`，不满足则 403。其余角色（`developer`/`manager`/`ops`/业务角色）维持现状，只要 `account:users:edit` 即可分配。

这个规则的效果：
- 现有 admin（admin账号、author账号）继续可以管理谁拥有 admin，行为不变；
- manager 角色可以正常分配 developer/ops/业务角色（这是设计本意），但不能把任何人（包括自己）提升为 admin；
- 不需要新增权限码，用现有 `admin` 角色本身做这一条特例校验即可，性质上和第一批"legacy admin 全权限"、"author 硬编码保护"一样，是账号保护/防提权规则，不是新的功能授权维度。

## 测试要求

- manager 角色（只有 `account:users:*`，无 admin）尝试分配 `admin` 角色给任意账号 → 403。
- manager 角色分配 `developer`/`ops`/业务角色（如 `product:view` 对应的自定义角色）→ 200，正常生效，确认没有连带把其他角色也锁死。
- admin 角色分配/撤销 `admin` 角色给他人 → 200，行为与改动前一致。
- 撤销别人的 admin 角色同样要走这条校验（不能被 manager 用"删除权限"的方式间接把别人从 admin 降级或误操作，需要同等保护）。

## 前端配合

我这边会把"分配角色"弹窗里非 admin 操作者看到的角色列表过滤掉 `admin` 选项（即使弹窗打开时目标用户已经是 admin，也不显示可勾选的 admin 项，避免误导）。这是纵深防御，不能替代后端校验，后端必须是真正的防线。

## 提交方式

这是安全修复，建议独立提交，不要和其他功能改动混在一起，方便单独审查和回滚。照例本地测试+`compileall`+`git diff --check`，写交接文档说明修复细节和测试覆盖。不涉及数据库变更，不需要 Alembic。
