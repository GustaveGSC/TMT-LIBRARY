# Codex 交接：权限体系重做第一批（数据与兼容映射）

日期：2026-07-23  
状态：第一批完成，未部署；没有切换运行时鉴权规则。

## 一、本批边界

本批只完成数据库权限数据、标准角色和过渡兼容映射，为第二批后端鉴权切换做准备。

明确未做：

- 没有修改 `has_permission()` 的 admin 绕过；
- 没有修改 author 特殊入口；
- 没有拆 account 蓝图权限矩阵；
- 没有修改 config/version 运行时权限；
- 没有修改前端；
- 没有新增 `ops:release:edit`，也没有触碰已冻结的 version 蓝图。

## 二、权限域和标准角色

| 权限域 | 权限码 | 标准角色 |
|---|---|---|
| 开发者 | `developer:analytics:view` | `developer` |
| 管理者 | `account:users:view` | `manager` |
| 管理者 | `account:users:edit` | `manager` |
| 管理者 | `account:roles:view` | `manager` |
| 管理者 | `account:roles:edit` | `manager` |
| 运维 | `ops:login-config:edit` | `ops` |

业务模块原有权限全部保留。

## 三、Alembic 迁移

新增 `20260723_02_prepare_permission_domains.py`，down revision 为 `20260723_01`。

upgrade 顺序：

1. 幂等新增 6 个权限码；
2. 幂等新增 `developer`、`manager`、`ops` 三个标准角色；
3. 精确绑定各标准角色权限包；
4. 给既有 `admin` 角色显式绑定数据库中当前全部权限；
5. 给 username=`author` 的既有账号追加 `developer` 角色，不撤销任何既有角色；
6. 递增 admin 角色用户和 author 的 `token_version`。

第 6 步是必要的 JWT 衔接：token 内嵌角色/权限。如果不失效旧 token，第二批移除代码绕过时，管理员可能继续携带迁移前的空/旧权限集合而被意外锁出。迁移完成后 admin/author 需要重新登录一次；普通业务账号不受影响。

## 四、生产部署前只读核对

升级前建议保存以下结果到部署记录：

```sql
SELECT u.id, u.username, u.token_version, GROUP_CONCAT(r.name ORDER BY r.name) AS roles
FROM users u
LEFT JOIN user_roles ur ON ur.user_id = u.id
LEFT JOIN roles r ON r.id = ur.role_id
WHERE u.username IN ('admin', 'author')
GROUP BY u.id, u.username, u.token_version;

SELECT r.name, GROUP_CONCAT(p.code ORDER BY p.code) AS permissions
FROM roles r
LEFT JOIN role_permissions rp ON rp.role_id = r.id
LEFT JOIN permissions p ON p.id = rp.permission_id
WHERE r.name IN ('admin', 'developer', 'manager', 'ops')
GROUP BY r.id, r.name;
```

这一步只用于留档和确认现状，不是要求人工修改数据。迁移不会撤销 author 的任何既有角色。

## 五、部署顺序

1. 全量备份数据库；
2. 上传新 migration、更新后的 seed 和文档；
3. 运行 `alembic upgrade head` 到 `20260723_02`；
4. 核对 `alembic current` 和上述角色权限矩阵；
5. 确认 admin/author 旧会话收到 401，重新登录后能正常使用原功能；
6. `/health`、`/ready` 正常。

本批没有 Python 运行时代码变化，数据库升级后无需为了本批单独 reload；但 migration 文件上传后，数据库 revision 必须及时升级，否则下一次任何原因触发 worker reload 时会被 revision guard 拒绝启动。

## 六、自动化测试

- 全量后端：155 passed。
- Alembic：
  - 唯一线性 head 为 `20260723_02`；
  - 三个标准角色权限包精确匹配；
  - legacy admin 显式拥有全部当前权限；
  - author 得到 developer 且保留原 admin；
  - 普通账号既有角色关联不变；
  - 未出现 `ops:release:edit`；
  - admin/author token version 过渡逻辑生效。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。

## 七、第二批入口

第一批部署并核对后，Codex 再开始第二批：

- 删除 `has_permission()` 的 admin 角色名绕过；
- account 端点切换到 users/roles view/edit 权限矩阵；
- 用户分析切到 `developer:analytics:view`；
- 登录页配置写操作切到 `ops:login-config:edit`；
- `is_rd_admin()` 只认 `rd:admin`；
- version 蓝图保持不动。

第二批后端完成后应与 Claude 的第三批前端切换连续部署。
