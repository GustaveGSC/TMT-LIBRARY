# 交接说明 · Claude → Codex（第二十三轮，admin 角色彻底停止分配）

日期：2026-07-23

用户用 author 账号（持有 admin 角色）测试，发现自己还能把 admin 分配给别的账号——这是符合上一批设计的行为（"已持有 admin 的操作者可以继续管理谁拥有 admin"），不是漏洞没堵住，我已经核实服务器上的守卫代码确实生效了。

但用户明确要求收得更紧：**按现在的权限设计，管理职责应该完全交给 manager 角色，admin 不应该再被分配给任何人（包括 admin/author 自己去分配给别人），只保留现有持有者**。

## 需要的改动

`AccountService.assign_role()`：把"分配 admin 需要操作者已经是 admin"改成"分配 admin 一律拒绝，不管操作者是谁"。即：

```python
if role.name == 'admin':
    return Result.fail(
        "admin 角色已停止分配，仅保留现有持有者",
        data={"error_code": ADMIN_ROLE_GUARD_ERROR},
    )
```

去掉原来 `'admin' not in (operator or {}).get('roles', [])` 这个条件判断，直接无条件拒绝。

**`remove_role()` 保留现状不变**：撤销 admin 角色仍然要求操作者自己持有 admin（现有逻辑），不做调整——用户这次只要求停止"新增"，没要求连"撤销"也锁死，撤销是收缩存量、降低风险的方向，继续允许现有 admin 做这件事是合理的（比如要清理一个不该有 admin 的历史账号）。

`delete_role()` 对内置 admin 角色本体不可删除的规则也不变。

## 测试要求

- admin 账号尝试分配 admin 角色给别人 → 403（之前是 200，这是本批要改的行为）。
- author 账号（持有 admin）尝试分配 admin 角色给别人 → 403（同上，这正是用户这次实测触发的场景）。
- manager 账号尝试分配 admin → 仍然 403（这条已经生效，回归确认不受影响）。
- admin 账号撤销别人的 admin 角色 → 仍然 200（确认没有被这次改动误伤）。
- 更新或新增测试断言：不管 operator 是谁，`assign_role` 对 `role.name == 'admin'` 一律走拒绝分支，仓储的 `assign_role` 函数从未被调用。

## 提交方式

小改动，可以和上一批（`0aa78fa`）的性质一样独立提交，说明是用户测试后进一步收紧的策略调整，不是修复回归。不涉及数据库变更。照例本地测试+`compileall`+`git diff --check`，写交接文档。
