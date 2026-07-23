# RD 成本库权限门禁修复交接

日期：2026-07-23

## 修复内容

提交：`3f42557 fix(rd): enforce cost library permissions`

为独立注册的 `cost_bp` 显式增加：

```python
cost_bp.before_request(make_blueprint_guard('rd:view', 'rd:edit'))
```

现在 `/api/rd/cost` 与 RD 主 Blueprint 的权限语义一致：

- GET 等只读方法要求 `rd:view`；
- POST/PUT/PATCH/DELETE 要求 `rd:edit`；
- 原有 `@require_auth` 和写接口 `_require_edit()` 暂时保留，没有在安全修复批次做去重。

这使实现重新符合 `api.md` 和项目权限约定，因此无需修改接口文档。无数据库迁移、无响应结构变化；新增的是此前缺失的 403 权限拒绝。

## 测试

`test_rd_cost_requires_domain_permissions` 使用真实 Cookie JWT、CSRF、Flask Blueprint 和 SQLite 表验证：

1. 已登录但没有 RD 权限：读取快照返回 403；
2. 只有 `rd:view`：读取快照成功；
3. 只有 `rd:view`：POST preview 返回 403；
4. 具有 `rd:view + rd:edit`：通过门禁并进入原有“请上传 Excel 文件”业务校验。

两项提交合并后的全量：141 passed、0 warnings；`compileall`、Alembic `20260721_04 (head)`、`git diff --check` 均通过。

## Claude 审查与部署

部署前先核对生产中需要使用 BOM 成本库的角色均已分配：

- 至少 `rd:view`（查看）；
- 需要导入、编辑、删除者同时具备 `rd:edit`。

避免权限修复上线后，实际业务用户因角色种子/分配缺失被意外拦截。

部署步骤：

1. 上传 `backend/routes/rd/cost.py`；
2. reload gunicorn；
3. 检查延迟日志、master PID、`/health`、`/ready`；
4. 分别使用无 RD 权限、只读 RD、可编辑 RD 账号验证成本库。

无数据库迁移。
