# 部署记录 · admin 角色停止新增分配（只减不增）

日期：2026-07-23

## 背景

用户用 author 账号（持有 admin 角色）实测，发现自己还能把 admin 分配给别的账号——这是上一批（`0aa78fa`）"已持有 admin 的操作者可以继续管理 admin"这条设计的正常行为，不是漏洞未修复。用户明确要求进一步收紧：管理职责完全交给 manager 承担，admin 角色停止新增分配，只保留现有持有者。交接文档：`handoff/2026-07-23-codex-freeze-admin-role-assignment.md`（提交 `7133021`，直接提交在 master）。

## 审查结论

审查通过，改动精准、范围克制：

- `AccountService.assign_role()` 的判断条件从 `role.name == 'admin' and 'admin' not in operator.roles`（有条件拒绝）简化为 `role.name == 'admin'`（无条件拒绝），不再看操作者是谁。
- `remove_role()`（admin 持有者可撤销他人 admin）和 `delete_role()`（内置 admin 角色本体不可删除）都保持上一批规则不变，符合用户"只要求停止新增，没要求连撤销也锁死"的意图。
- `.claude/modules/api.md` 同步更新，`POST .../roles/:id` 端点说明改为"admin 为冻结存量角色，任何操作者均不可再分配"。
- 测试精确覆盖用户实测触发的具体场景：`admin` 账号分配 admin → 403；`author`（持有 `admin`+`developer`）分配 admin → 403（这正是用户报告的场景）；两条路径都断言仓储 `assign_role` 从未被调用；admin 撤销他人 admin → 200（确认没被误伤）；manager 分配 developer 等普通角色 → 200（确认业务角色分配不受影响）。
- 本地复跑：`pytest` 176 passed；`compileall` 通过。

## 部署

本批无数据库变更，不需要 Alembic：

1. 确认服务器无导入/resolve 任务在跑。
2. 上传 `services/account/__init__.py`，md5 核对一致。
3. `systemctl reload gunicorn`；8秒后复查：master pid 2151 未变，新 worker（16217）干净启动，无崩溃记录。
4. `/health`、`/ready` 均 200。

## 需要你验证

Codex 建议的生产复测方式是"用 author 的真实 Cookie 直接复测原操作，预期从上一版的 200 变为 403"——这一步需要你登录后的真实会话，我这边没有签名密钥无法伪造有效 Cookie 代为验证。**麻烦你用 author 账号重新尝试一次"给某个测试账号分配 admin 角色"，确认现在返回"admin 角色已停止分配，仅保留现有持有者"而不是分配成功**。如果方便，也可以顺手验证一下撤销别人的 admin 仍然正常（避免这次改动误伤了撤销功能）。

## 影响说明

- 从这次起，无论谁登录（包括 admin 账号本人），都无法再通过应用内 UI/API 把 `admin` 角色分配给任何账号；现有持有者（admin 账号、author 账号）不受影响，继续保留。
- 如果将来确实需要新增一个 admin 账号（极端应急场景），只能通过直接操作数据库完成，不再有应用内路径——这是有意为之的设计，管理职责已经完全转移给可以正常分配的 `manager` 角色。
