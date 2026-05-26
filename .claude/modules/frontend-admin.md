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

## page-version-release.vue 注意事项
- 安装包直传 OSS（不经服务器）：先调 `/api/version/presign` 拿预签名 URL，再用 XHR PUT 直传
- OSS bucket 已配置 CORS 允许 PUT（origins: *，methods: GET/PUT/HEAD）
- CSP `connect-src` 包含 `http://tmt-oss.oss-cn-hangzhou.aliyuncs.com` 和 `https://` 两种（presign URL 为 http）
- 发布流程：presign → PUT to OSS → POST `/api/version/` 写数据库
