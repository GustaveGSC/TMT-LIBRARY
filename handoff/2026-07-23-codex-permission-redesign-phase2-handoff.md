# Codex 交接：权限体系重做第二批（后端显式鉴权切换）

日期：2026-07-23  
状态：后端完成，未部署；等待 Claude 前端第三批后连续部署。

## 一、运行时授权原则

后端功能授权现在只检查 JWT 中的显式权限码：

- `admin` 角色名不再自动放行；
- `author` 用户名不再获得功能豁免；
- admin 的兼容权限来自第一批已经落库的 17 条显式角色权限；
- author 的开发者权限来自第一批显式分配的 `developer` 角色；
- `admin`、`author` 不可删除/禁用继续保留，这是系统账号保护，不是功能授权。

唯一刻意保留的角色名鉴权是冻结的 version 蓝图；按已确认范围，本批不动，留待 Electron 死功能清理。

## 二、后端端点权限矩阵

### 开发者

| 端点 | 权限 |
|---|---|
| `GET /api/account/login-logs` | `developer:analytics:view` |
| `GET /api/account/login-stats/dau` | `developer:analytics:view` |
| `GET /api/account/login-stats/users` | `developer:analytics:view` |

### 管理者：用户

| 端点 | 权限 |
|---|---|
| `GET /api/account/users` | `account:users:view` |
| 用户创建、更新、删除、状态、重置密码 | `account:users:edit` |
| 用户角色分配、撤销 | `account:users:edit` |
| 修改本人密码 | 有效登录态 + 本人所有权 |
| 修改他人密码 | `account:users:edit` |

### 管理者：角色和权限

| 端点 | 权限 |
|---|---|
| `GET /api/account/roles`、`GET /permissions` | `account:roles:view` |
| 角色创建/删除、角色权限调整 | `account:roles:edit` |
| 权限项创建/更新 | `account:roles:edit` |

### 运维

| 端点 | 权限 |
|---|---|
| `PUT /api/config/login-mottos` | `ops:login-config:edit` |
| `GET /api/config/login-mottos` | 继续公开 |

### 业务模块

- `is_rd_admin()` 现在只认 `rd:admin`。
- 资料类型创建/修改/删除移除额外的 admin 硬编码，统一按所属产品模块的 `product:edit`；此前合法产品编辑者会被第二层 admin 检查误拒绝。
- 其余业务权限矩阵不变。

## 三、前端第三批必须同步

搜索确认尚存以下授权分支：

1. `src/composables/usePermission.js`
   - 删除 `isAdmin` 对 `can()` 的全局放行。
2. `src/routers/index.js`
   - 用户管理：`account:users:view`
   - 权限管理：`account:roles:view`
   - 用户分析：`developer:analytics:view`
   - 登录页配置入口对应 `ops:login-config:edit`
   - 删除 `adminOnly`、`authorOnly` 和路由守卫中的角色/用户名放行。
   - 冻结的版本发布页面按 Electron 停止支持决策处理：不要为它新增 ops 权限；可以继续隐藏，死代码清理另排。
3. `src/components/user/UserSettingsDrawer.vue`
   - 各入口改用上述具体权限。
   - 角色展示可保留纯展示，但不能参与功能授权。
4. `src/views/indexViews/page-index.vue`
   - “开发者工具/用户分析”从 author 判断改为 `developer:analytics:view`。
5. `src/views/productViews/ProductResources.vue`
   - “管理类型”按钮从 `isAdmin` 改成 `canEditProduct`，与后端 `product:edit` 对齐。
6. `src/views/adminViews/page-users.vue`
   - admin/author 判断仅可用于受保护账号的按钮状态或展示，不可作为页面进入权限。

## 四、测试结果

- 全量后端：165 passed。
- 新增真实 Cookie 权限测试：
  - admin 角色名但无权限码不能查看用户；
  - author 用户名但无 developer 权限不能看分析；
  - users/roles 的 view/edit 精确隔离；
  - ops 可写登录页配置，普通用户不能；
  - admin 角色名不能管理资料类型，`product:edit` 可以；
  - `rd:admin` 不再被 admin 角色名替代。
- 既有 Cookie/CSRF、token revocation、业务模块测试全部通过。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。

## 五、连续部署顺序

第一批已经使生产 admin/author 重新登录并取得显式权限，第二批具备上线前提。

建议：

1. Claude 先完成并本地构建前端第三批；
2. 上传后端第二批文件；
3. reload gunicorn，并检查 worker 稳定、`/health`、`/ready`；
4. 用当前 admin/author 实测用户列表、权限页 API、登录分析 API、登录文案保存；
5. 立即部署完整 `dist-web/`；
6. 用 developer、manager、ops 权限账号分别验收页面入口和 API；
7. 核对无权限交叉访问均为 403。

本批无数据库变更，不需要 Alembic；不要触碰 version 蓝图。
