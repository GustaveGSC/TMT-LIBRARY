# 管理页前端注意事项

## page-users.vue / page-permissions.vue 注意事项
- `roles` 是字符串数组，不是对象数组
- isAdminUser: `row.roles?.includes('admin')`（不是 `.some(r => r.name === 'admin')`）
- 角色tag渲染：`:key="role"` `{{ role }}`（不是 `role.id` / `role.name`）
- handleAssignRole：先 loadRoles()，再通过 name 匹配 allRoles 里的 id
- role.permissions 是字符串数组（权限码），不是对象数组
- handleBindPermissions: `currentPerms.value = row.permissions || []`（不需要 map）

## UserSettingsDrawer.vue 注意事项
- isAdmin: `userInfo.value.roles?.includes('admin')`（不是 `.some(r => r.name === 'admin')`）
