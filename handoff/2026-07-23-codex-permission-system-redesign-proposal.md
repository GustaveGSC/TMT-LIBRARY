# Codex 独立方案：权限体系重做与 Claude 方案对照

日期：2026-07-23  
状态：设计定案建议，尚未修改运行时代码。

## 一、目标模型

权限体系明确分为四个域：

1. **开发者域**：用户登录日志、活跃度和用户行为分析。
2. **管理者域**：用户管理、角色管理、权限管理。
3. **运维域**：登录页配置、版本发布等运行配置。
4. **业务功能域**：产品、发货、售后、研发等现有模块。

角色只是一组权限的集合，不再参与代码分支判断。后端、前端均只根据权限码决定是否允许访问；用户名只用于账号保护或审计，不用于功能授权。

## 二、建议权限码

### 开发者

| 权限码 | 范围 |
|---|---|
| `developer:analytics:view` | 登录日志、DAU、用户登录统计 |

### 管理者

| 权限码 | 范围 |
|---|---|
| `account:users:view` | 查看用户列表和用户详情 |
| `account:users:edit` | 创建、编辑、禁用、删除、重置用户密码、分配角色 |
| `account:roles:view` | 查看角色和权限清单 |
| `account:roles:edit` | 创建/删除角色、创建/修改权限项、调整角色权限 |

用户本人修改密码只要求有效登录态和“只能改本人”的所有权校验，不要求管理权限。

### 运维

| 权限码 | 范围 |
|---|---|
| `ops:login-config:edit` | 修改登录页轮播文案 |
| `ops:release:edit` | 发布版本、上传安装包和维护版本记录 |

版本检查和版本列表如果是客户端正常运行所需，继续公开读取；写操作归运维。

### 业务功能

保留现有权限码：

- `product:view/edit`
- `shipping:view/edit/export`
- `aftersale:view/edit/export`
- `rd:view/edit/admin`

“通用工具”继续只要求正常登录，不新增业务权限码。

## 三、标准角色

建议提供三个标准角色作为默认权限包：

| 角色 | 默认权限 |
|---|---|
| `developer` | `developer:analytics:view` |
| `manager` | 四个 `account:*` 管理权限 |
| `ops` | 两个 `ops:*` 运维权限 |

业务角色继续由管理者按部门实际组合现有功能权限。

### legacy `admin` 的处理

不建议继续在 `has_permission()` 中写 `if admin: return True`。建议：

1. 暂时保留 `admin` 角色名称，作为兼容/应急全权限角色；
2. migration 将当前全部标准权限显式绑定给 `admin`；
3. 删除前后端对 `admin` 角色名的权限绕过；
4. 今后新增标准权限时，migration 必须同时决定是否加入 `admin` 权限包。

这样现有管理员行为不变，但权限来源可在数据库中审计，不再存在绕过权限表的代码后门。后续可以再决定是否将角色显示名改成“超级管理员”。

## 四、author 账号处理

不建议 Claude 方案中的：

```python
if username == 'author' and perm in (...):
    return True
```

正确方式是给 author 显式分配 `developer` 角色。若 author 当前还承担超级管理员职责，应先只读核实生产角色关联，再决定保留还是移除其 legacy `admin` 角色，不能在 migration 中盲目撤权。

`admin`、`author` 不可删除/禁用可以继续作为系统账号保护规则；这是账号生命周期保护，不是功能授权。

## 五、端点映射

### 开发者

- `GET /api/account/login-logs`
- `GET /api/account/login-stats/dau`
- `GET /api/account/login-stats/users`

要求 `developer:analytics:view`。

### 管理者

- `GET /api/account/users` → `account:users:view`
- 用户创建、更新、删除、状态、密码重置、角色分配/撤销 → `account:users:edit`
- `GET /api/account/roles`
- `GET /api/account/permissions`

以上两个读取接口要求 `account:roles:view`。

- 角色创建/删除、角色权限变更、权限创建/更新 → `account:roles:edit`

### 运维

- `PUT /api/config/login-mottos` → `ops:login-config:edit`
- 版本发布相关写接口 → `ops:release:edit`

### 公开与本人操作

- login/register/logout 契约不变；
- 登录页文案读取公开；
- 本人改密只要求有效会话和所有权；
- 版本检查所需 GET 继续公开。

## 六、前端必须同步移除的特殊判断

- `isAdmin` 不能再让 `can()` 对所有权限直接返回 true；
- 路由的 `adminOnly`、`authorOnly` 改成具体 `meta.permission`；
- 用户抽屉：
  - 用户管理入口看 `account:users:view`；
  - 权限管理入口看 `account:roles:view`；
  - 登录页配置入口看 `ops:login-config:edit`；
  - 版本发布入口看 `ops:release:edit`；
  - 用户分析入口看 `developer:analytics:view`。
- 首页“开发者工具”不再根据 `username === author` 判断。
- `rd:admin` 只认权限码，不再因 admin 角色名直接通过。

## 七、与 Claude 方案对照

| 项目 | Claude 方案 | Codex 判断 |
|---|---|---|
| 开发者分析 | `analytics:view` | 方向正确；建议放入明确域名 `developer:analytics:view` |
| 登录页配置 | `ops:edit` | 方向正确，但过宽；建议 `ops:login-config:edit` |
| 版本发布 | 暂留未来扩展 | 应在本次归入 `ops:release:edit`，否则运维模块仍不完整 |
| 用户管理 | 继续只认 admin | 与“属于管理者”冲突，必须新增 `account:users:view/edit` |
| 权限管理 | 继续只认 admin | 与“属于管理者”冲突，必须新增 `account:roles:view/edit` |
| admin | 永久全局绕过 | 不建议；应改为数据库显式全权限包 |
| author | 用户名硬编码两个豁免 | 不建议；应显式分配 developer 角色 |
| 前端 | 部分 `isAuthor` 改权限码 | 不完整；`isAdmin/adminOnly/authorOnly` 都必须退出授权逻辑 |
| 业务模块 | 保持现状 | 同意 |

结论：Claude 的两个权限码可以作为局部修补思路，但不能直接作为整体方案实施。建议采用本文的显式权限模型。

## 八、实施批次

### 第一批：数据库与兼容映射

- migration 新增权限码和 `developer/manager/ops` 标准角色；
- 为标准角色绑定默认权限；
- 将全部标准权限显式绑定 legacy `admin`；
- 只读核实生产 admin/author 当前角色后，显式为 author 添加 developer；不盲目撤销其他角色；
- 更新 seed、`api.md`、`database.md`；
- 此时先保留旧鉴权，确保数据准备完成但行为不变。

### 第二批：后端权限切换

- `has_permission()` 删除 admin/author 功能授权特例，只检查权限集合；
- account 蓝图由整体 admin 守卫改成端点权限矩阵；
- config、version、用户分析端点切到新权限码；
- `is_rd_admin()` 去掉 admin 角色绕过；
- 真实 Cookie 权限测试覆盖每类允许/拒绝路径。

### 第三批：前端同步切换

- Claude 清理 `isAdmin/isAuthor/adminOnly/authorOnly` 授权逻辑；
- 所有入口和路由改用具体权限码；
- 后端第二批和前端第三批应安排连续部署，压缩界面权限显示与后端不一致的窗口。

### 第四批：生产权限审计

- 列出生产所有用户→角色→权限的最终展开结果；
- 重点确认 admin、author 和现有业务账号没有意外撤权或扩权；
- 用 manager、developer、ops 各一个测试账号做端到端验收；
- 删除测试账号并留部署记录。

## 九、自动化测试最低要求

- Alembic 线性 head、幂等迁移、现有角色关联保留；
- 标准角色权限包精确匹配；
- legacy admin 通过显式权限而非角色名绕过；
- author 无对应角色时不得凭用户名越权；
- account 每组端点分别覆盖无权限 403、只读权限、编辑权限；
- developer 不能管理用户，manager 不能看开发者分析，ops 不能进入用户管理；
- 业务模块现有权限回归；
- 角色/权限变更后旧 token 立即失效；
- 前端路由和入口不再依赖 `adminOnly/authorOnly`。
