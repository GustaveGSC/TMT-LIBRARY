# 交接说明 · Claude → Codex（第二十四轮，批准第0批+第1批立即执行）

日期：2026-07-24

已读完 `handoff/2026-07-24-codex-shipping-aftersale-data-management-review.md`，独立核实了本轮最关键的新发现（`/warehouses/filter` 越权），确认真实：`_VIEW_POST = ('/chart-data', '/chart-options', '/warehouses/filter')`（`backend/routes/shipping/__init__.py:20`）让这个批量保存仓库排除配置的写接口只需要 `shipping:view` 就能调用，而这个白名单设计初衷是给 `chart-data`/`chart-options` 这类"查询型POST"用的（`auth.py:140` 注释写的很清楚）。`save_warehouse_filters`（`:352-362`）是真实写操作，会改变后续财务销退导入口径。批准立即修复，不用再等我进一步确认。

用户已确认按你报告的排序推进，第0批+第1批现在授权你开始。

## 第0批：产品分享页XSS

沿用 `handoff/2026-07-24-codex-product-library-architecture-review.md` 里的方案，不重复说明。这批仍是全系统第一优先级，先做。

## 第1批：发货权限与任务准入

### 1.1 修复 `/warehouses/filter` viewer 越权

- 从 `_VIEW_POST` 删除 `/warehouses/filter`，让它回到默认的 `shipping:edit` 门槛（和其余写接口一致）。
- 顺手检查 `_VIEW_POST` 里 `/chart-options` 这一项是否还有实际路由匹配到（你报告里提到"检查`_VIEW_POST`中无效的`/chart-options`项并清理"），如果是历史遗留的死配置就一并清掉，不需要单独开一批。
- 补真实 Cookie JWT 权限测试：只有 `shipping:view` 的账号调这个接口应该 403，有 `shipping:edit` 的应该 200。

### 1.2 导入/重算任务建立数据库级互斥租约

- 目标：`import_shipping`/`import_finance`/`resolve_all`/`resolve_stale` 同一时刻只允许一个在跑。
- 租约状态放数据库（不能只是进程内字典，会因为多线程/reload失效），获取租约要原子化（不能"先查再插"两步式，会有竞态窗口）。
- 冲突时返回标准 409，body 里带当前占用租约的任务ID，方便前端跳转去看那个任务的进度。
- 具体用什么机制（新表/复用`ShippingTask`加状态字段/`SELECT...FOR UPDATE`）你自己判断，只要满足"两个并发请求只能有一个拿到租约"这个契约。

### 1.3 测试要求

- 权限：viewer 调 `/warehouses/filter` 返回 403，editor 返回 200。
- 并发：模拟两个并发请求同时申请任务租约，断言只有一个成功、另一个收到 409 且能读到占用者的任务ID。
- reload 场景：worker reload 后（模拟租约持有者进程消失），租约能被正确判定为可恢复/可抢占，不会永久卡死（参考你们已有的 `interrupt_running_tasks` 机制思路）。

## 我这边同步要做的事

第1批后端契约稳定后，我会把前端"发货数据/数据管据"相关页面里 viewer 权限账号能看到但点了才 403 的写按钮（导入、重算、仓库过滤保存等）改成按 `canEditShipping` 直接隐藏/禁用，不用等你，我可以在你这批合并部署后单独跟进，不阻塞你现在开始。

## 提交方式

沿用一贯纪律：每个正确性修复独立提交，不要和后续批次混在一起。本地 `pytest`+`compileall`+`git diff --check`；权限测试必须走真实 Cookie JWT + CSRF；任务租约测试要覆盖"两个并发请求只有一个拿到"和"reload后租约可恢复"两种场景。写交接文档说明改了什么、为什么、测试覆盖了哪些场景。这批不涉及数据库结构变更（如果你选择用新表存租约状态则需要，按老规矩备份+Alembic）。

完成后按你报告里的顺序继续第2批（售后正确性），不需要再等我确认，除非你在做的过程中发现新的需要讨论的判断点。
