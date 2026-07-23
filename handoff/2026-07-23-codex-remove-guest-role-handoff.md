# Codex 交接：取消 guest 角色与游客登录

日期：2026-07-23  
状态：后端完成，未部署；需要 Claude 同步清理前端。

## 产品语义

- 自助注册账号仍然默认无角色、无业务权限，只能使用无需权限码的“通用工具”。
- `guest` 角色和游客登录功能正式取消，不保留无权限的同名空角色。

## 后端改动

- 删除 `GET /api/account/guest` 及对应 service。
- 删除 JWT 对 `id=None, username=guest` 的特殊信任分支；已有游客 Cookie 部署后统一变成 401。
- 从公开端点和 CSRF 豁免清单移除 guest。
- 新增 Alembic `20260723_01`：
  1. 删除 `user_roles` 中 guest 角色关联；
  2. 删除 `role_permissions` 中 guest 权限关联；
  3. 删除 guest 角色本身。
- 删除只负责创建 guest 角色的 `backend/scripts/seed_roles.py`。
- 更新 `api.md`、`database.md`，历史游客登录日志不删除。

## 前端需要 Claude 处理

搜索确认仍有 guest 语义残留：

- `src/components/user/UserSettingsDrawer.vue`：游客判断、游客文案和隐藏改密逻辑；
- `src/views/adminViews/page-permissions.vue`：`BUILTIN_ROLES` 仍包含 guest；
- `src/views/adminViews/page-login-logs.vue`：历史 `identity_type=guest` 展示建议保留，因为数据库历史日志仍存在；
- `src/views/indexViews/page-index.vue` 的用户名兜底“游客”只是缺省显示文案，可由 Claude 判断是否改为“用户”。

当前前端未搜索到 `/api/account/guest` 调用；如果确认没有隐藏入口，主要是清理上述过期状态分支。

## 部署顺序

1. 全量备份数据库；
2. 上传 migration 和后端代码（包含删除服务器上的 `backend/scripts/seed_roles.py`）；
3. `alembic upgrade head` 到 `20260723_01`；
4. reload gunicorn；
5. 验证 `/health`、`/ready`、普通账号登录和注册账号通用工具访问；
6. 旧游客 Cookie 请求应返回 401；
7. 再部署 Claude 的前端清理。

## 测试

- 全量后端测试；
- Alembic 线性 head；
- migration 精确删除 guest 及其关联，同时保留 admin 角色和关联；
- 遗留 guest token 返回 401。
