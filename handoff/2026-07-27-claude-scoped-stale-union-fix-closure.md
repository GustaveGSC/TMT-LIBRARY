# scoped stale 标记（union 列名修复）— 生产验证通过并已上线

日期：2026-07-27

## 结论

Codex 的 union_all 列名修复（9db6996/5447948，`codex/shipping-rename-cutover` 分支）已完整
走完两轮生产真实验证门禁，全部通过，已合并 master 并部署上线。**排序规则修复 + union 列名修复
两个问题现在都已解决**，scoped stale 标记功能正式生效。

## 验证记录

### 1. 隔离 MySQL 集成测试（真实执行，非 SQLite）
生产服务器无 pytest，沿用上次做法：在隔离目录直接调用修复后的真实函数（等价于两项
`mysql_integration` 标记测试的内容），只读事务 + rollback：
- `_order_no_join()` 编译含 `COLLATE utf8mb4_unicode_ci`，真实执行返回 5 行 —— 排序规则修复仍生效；
- `mark_stale_for_component_codes()` 三分支 union_all（component 正向 + component 销退 +
  finished_code）用不存在的编码真实执行，`count=0`，无 `AttributeError` —— union 列名修复生效。

### 2. 三入口真实 HTTP 验证（合并后部署到生产运行目录）
备份未使用（本批无 schema/数据变更），5 个运行时文件 MD5 核对后 `systemctl reload`，master PID
未变（2126），`/health`/`/ready` 正常。

| 入口 | 操作 | 结果 |
|---|---|---|
| 1. 仓库过滤配置 | 杭州售后备件仓库 排除开→关 | 两次均 `200`，`stale_pairs=6`，配置已还原 |
| 2. 成品-组件关联 | `2001JQ19-A`(488) ↔ `2101JQZT07-A`(508) 删除→重新添加 | 两次均 `200`，`stale_pairs=11`，关联已还原（`SELECT` 核实仍存在） |
| 3. 通用件对 | `1201DLZM02-A`/`1201DLZM01-A` 新增→删除 | 两次均 `200`，新增返回 `id=3`，删除后 `SELECT` 核实无残留 |

三个入口全部返回 200（无 500），且每次都真正命中了此前报错的 union/JOIN 代码路径（`stale_pairs`
非零，证明查询确实执行到底并写入了 `is_stale`）。

### 3. 清理验证产生的 stale 标记
四次真实调用（1次仓库切换×2方向 + 1次组件关联增删 + 1次通用件对增删）共标记 1352 个订单
`is_stale=1`（真实生产数据，非测试库）。这是设计上的正确行为——配置改了两次，即使净效果是
"改回原样"，解析器不知道这一点。为避免这批验证造成的 stale 标记误导后续对生产 `is_stale`
状态的观察，用产品设计的正规入口 `POST /api/shipping/resolve` 执行了一次真实
`resolve_stale`（而非直接改数据库），结果：`{"resolved": 649, "staged_rows": 1352,
"deleted_rows": 1352, "inserted_rows": 1352}`，执行后 `is_stale=1` 计数回到 0，无残留任务。

## 当前生产状态

- 三个规则变更入口（仓库过滤配置、成品-组件关联、通用件对）保存配置的同时会正确标记受影响订单
  `is_stale=True`，超过 `MAX_STALE_RESOLVE_ORDERS=10000` 时允许保存但要求 `resolve_all`（`requires_full_resolve=true`）。
- `resolve_stale`（`POST /api/shipping/resolve`）本次验证顺带证明端到端可用：能正确识别、重算并
  清空 stale 标记。
- `is_stale=0`，无活跃 `shipping_task`，生产干净。

## 时间线（本条任务线完整记录，供后续排查参考）

1. Codex 完成设计 + 实现（d926dc3）。
2. Claude 真实 HTTP 验证发现排序规则 1267 bug（三入口全部 500），回退，见
   `handoff/2026-07-27-claude-scoped-stale-collation-bug-rollback.md`。
3. Codex 修复排序规则（ff16b3f/880093c/c7781c6）。
4. Claude 隔离 MySQL 验证通过，部署；真实 HTTP 验证入口1通过，入口2暴露第二个独立 bug
  （union 后子查询列名丢失，`AttributeError: source`），回退，见
  `handoff/2026-07-27-claude-scoped-stale-second-bug-union-subquery-columns.md`。
5. Codex 用 Core `union_all` + 显式命名子查询修复（9db6996/5447948），补两项 `mysql_integration`
   门禁测试。
6. **本次**：Claude 隔离 MySQL 验证两项修复均真实执行通过，合并部署，三入口真实 HTTP 全部验证
   通过，清理验证产生的 stale 标记，功能正式上线。

## 后续

- `MAX_STALE_RESOLVE_ORDERS=10000` 上限校准现在有了真实数据起点可以参考（本次一次仓库配置
  改动就标记了 649 个不同 finished_code 对应的 1352 行，规模可控），但仍需观察真实业务使用后的
  stale 分布再决定是否调整，暂不改配置值。
- D 批生产规模压测保持用户此前决定：不建隔离同规格实例，方案停在只读设计阶段。
