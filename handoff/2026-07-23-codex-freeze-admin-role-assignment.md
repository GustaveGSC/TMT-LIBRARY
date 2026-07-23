# Codex 交接：admin 角色停止新增分配

日期：2026-07-23  
状态：策略收紧完成，未部署；无数据库变更。

## 最终规则

`admin` 是历史兼容/应急角色，现有持有者暂时保留，但角色集合只能缩小、不能扩大：

| 操作 | 规则 |
|---|---|
| 分配 admin | 一律 403，任何操作者都不允许，包括 admin 和 author |
| 撤销 admin | 仅当前持有 admin 的操作者允许 |
| 删除 admin 角色本体 | 一律 403 |
| 分配/撤销其他角色 | 具备 `account:users:edit` 即可 |

管理职责由 `manager` 角色承担，不再通过新增 admin 实现。

## 实现

`AccountService.assign_role()` 只要目标 `role.name == 'admin'` 就直接返回：

```json
{
  "success": false,
  "message": "admin 角色已停止分配，仅保留现有持有者",
  "data": {"error_code": "admin_role_requires_admin"}
}
```

HTTP 403，且不会调用 `UserRepository.assign_role()`。

`remove_role()` 和内置角色删除保护保持上一批规则不变。

## 测试

- manager 分配 admin → 403；
- admin 分配 admin → 403；
- author（持有 admin+developer）分配 admin → 403；
- 三种路径均证明仓储分配函数未调用；
- admin 撤销别人 admin → 200；
- manager 分配 developer 等普通角色 → 200；
- 全量后端测试、compileall、diff check。

## 部署

仅需上传 `backend/services/account/__init__.py` 和同步文档后 reload；无 Alembic。生产可用 author Cookie 直接复测原操作，预期从上一版的 200 变为 403，再确认撤销测试账号 admin 仍为 200。
