# Codex 交接：admin 角色越权分配及相邻绕过修复

日期：2026-07-23  
状态：后端安全修复完成，未部署；无数据库变更。

## 一、原始漏洞

具备 `account:users:edit` 的 manager 可以直接调用角色分配接口，把 `admin` 角色授予自己或其他账号，从而获得全部显式权限。这绕过了前端角色列表隐藏，构成完整权限提升路径。

## 二、后端防线

安全检查放在 `AccountService`，路由只负责传入当前操作者并把安全拒绝转换为 HTTP 403：

- 分配 `admin`：操作者必须已经持有 `admin` 角色；
- 撤销 `admin`：操作者必须已经持有 `admin` 角色；
- 其他 developer/manager/ops/业务角色仍只要求 `account:users:edit`；
- 没有 operator 上下文时默认拒绝 admin 角色变更，避免其他 service 调用入口绕过；
- 内置 `admin` 角色本体任何人都不能删除。

错误响应保持标准 Result 格式，并带稳定的：

```json
{
  "success": false,
  "message": "...",
  "data": {"error_code": "admin_role_requires_admin"}
}
```

HTTP 状态为 403。

## 三、同权限面额外发现并修复

### 1. PUT 用户接口 mass assignment

`update_user()` 原来把请求 JSON 原样传给仓储，仓储对所有 `hasattr(User, key)` 字段赋值。manager 可绕过专用角色撤销接口，提交：

```json
{"roles": [], "token_version": 999, "is_active": false}
```

从而直接清空 admin 角色或篡改内部鉴权字段。

现在通用用户信息更新只允许 `display_name`。密码、状态、角色必须分别走已有专用安全端点；`id/username/token_version/roles` 等内部字段全部拒绝，不会进入仓储。

### 2. 受保护账号密码重置

manager 原本可以通过 reset-password 重置 admin/author 密码并接管超级管理员账号。

现在：

- 普通账号仍可由 `account:users:edit` 管理者重置；
- admin/author 受保护账号额外要求操作者持有 admin；
- admin 操作者仍可按既有流程重置受保护账号；
- 非 admin 返回标准 403，`error_code=protected_account_requires_admin`。

## 四、自动化覆盖

- manager 分配 admin → 403，仓储未调用；
- manager 撤销 admin → 403，仓储未调用；
- manager 分配 developer → 200；
- admin 分配/撤销 admin → 200；
- service 无 operator 上下文变更 admin → 拒绝；
- 删除内置 admin 角色 → 403；
- PUT roles/token_version/is_active/password → 400，仓储未调用；
- manager 重置 admin 密码 → 403；
- admin 重置 author 密码 → 200；
- 全量后端：175 passed；
- `compileall`、`git diff --check` 通过。

## 五、部署与验证

本批无 migration。

1. 上传 `services/account/__init__.py` 和 `routes/account/__init__.py`；
2. reload gunicorn，按既定方式确认 worker 稳定；
3. `/health`、`/ready`；
4. 直接使用 manager Cookie 调用 admin 角色 POST/DELETE，均应 403；
5. manager 分配 developer 应 200；
6. admin 分配后再撤销测试账号的 admin 应均为 200；
7. 清理测试账号/角色关联并记录。

前端已部署的 admin 选项隐藏属于纵深防御，本后端提交才是不可绕过的安全边界。
