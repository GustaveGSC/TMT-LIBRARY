# 发货域信息架构迁移 + 产品生命周期任务复核

日期：2026-07-24  
对象：Claude Code  
性质：方案确认与前端实施交接；本批尚未修改运行时代码

## 结论

1. 同意移除首页独立的“数据管理”一级入口。当前页面没有独立业务域，所有能力都属于发货数据的导入、规则或维护。
2. Claude 可以开始前端迁移；本批不改后端接口、不改权限码、不重写已经稳定的导入与任务轮询逻辑。
3. 产品生命周期 SSE 不插队到本次 UI 迁移之前，但应作为迁移后的下一项后端工作处理，不再无限后移。

## 一、数据管理入口的最终归属

推荐把“发货数据”改成一个带子路由的业务壳：

| 路径 | 页面名称 | 现有内容 |
|---|---|---|
| `/shipping` | 分析看板 | `ShippingDashboard` |
| `/shipping/orders` | 订单明细 | `ShippingTable` |
| `/shipping/imports` | 数据接入 | `DataImport`、`FinanceImport` |
| `/shipping/settings` | 规则设置 | 操作人分类、仓库过滤、产成品通用件、标签分析维度、客户匹配 |
| `/shipping/maintenance` | 数据维护 | “重建全部成品组合（高级）” |

设置页内部继续用 Tab 即可，但建议按语义分组展示：

- 来源与口径：操作人分类、仓库过滤、客户匹配；
- 匹配规则：产成品通用件；
- 分析设置：标签分析维度。

“重建全部成品组合”必须独立放在数据维护页，保留二次确认和低峰期提示，不应重新放回日常导入或设置页的常驻区域。

## 二、本批实施边界

### 应做

- 抽取或复用统一的发货页面壳，让上述五个路径共享返回按钮、标题和顶部导航；
- 将当前首页“数据管理”卡片移除，只保留“发货数据”入口；
- `/data-mgmt` 做兼容重定向到 `/shipping/imports`，至少保留一个发布周期；
- 子路由全部使用 `shipping:view` 作为进入权限；
- 所有导入、保存、重算按钮继续以 `shipping:edit` 为真实交互门禁；
- viewer 可以读取设置内容，但看不到或不能操作写按钮，不能仅依赖后端返回 403；
- 页面切换继续懒加载，不能因为合并导航而在进入 `/shipping` 时同时加载导入和所有设置接口；
- 同步更新 `.claude/modules/frontend-data-mgmt.md`，删除 SSE、旧页面结构和“外贸客户匹配”等已经过期的描述。

### 不应做

- 不改任何 `/api/shipping/*` 或产品标签接口契约；
- 不在本批新增 `shipping:import/config/rebuild` 等细权限；
- 不重写 `pollShippingTask`，也不恢复 EventSource；
- 不同时做组件内部大重构；
- 不要求本批物理移动所有 `dataMgmtViews` 文件。先完成路由和页面归属，目录搬移可在行为稳定后单独做，避免 diff 混入无关移动。

## 三、兼容与交互细节

- 旧 `/shipping` 默认进入分析看板，保持现有书签行为；
- 原“图表 / 数据”改成“分析 / 订单 / 数据接入 / 规则设置 / 数据维护”；
- 窄屏时顶部导航必须可横向滚动或折叠为菜单，不能把页面标题和操作区挤变形；
- 若设置页使用 query 保存 Tab（例如 `?tab=customer`），刷新页面后应保持当前 Tab；
- `router.back()` 不应把用户困在 `/shipping/*` 子页之间。建议页面壳返回首页，子页切换使用明确导航，而不是历史栈回退。

## 四、Playwright 验收

至少覆盖：

1. `/data-mgmt` 自动跳到 `/shipping/imports`；
2. 首页不再出现独立“数据管理”卡片；
3. `shipping:view` viewer 能进入分析、订单、数据接入和设置页，但不能触发导入/保存/重算；
4. `shipping:edit` editor 能看到对应写入口；
5. 直接访问五个子路由时激活态正确，刷新后不丢失页面；
6. 导入任务的 409 接管与短轮询用例继续通过；
7. 至少覆盖 1920×1080、1093×614、844×390 三档，顶部导航和设置页无横向溢出、关键操作可滚动到达；
8. 切换页面不会重复挂载轮询器或产生未打桩接口/控制台错误。

构建、完整 Playwright、`git diff --check` 全部通过后再交回审查。前端由 Claude 提交和部署，Codex 不跨目录写入。

## 五、产品生命周期审计复核

Claude 的风险定性正确，但规模表述需保持准确：

- 生产数据是约 66 万条 `shipping_order_finished`；
- 233 个型号有发货聚合结果；
- 403 个型号进入生命周期处理循环；
- 因此当前是约 403 次逐型号 `commit()`，不是 233,403 次。

即使任务本身只运行十几到三十秒，SSE 的阻塞读取仍会占住唯一 sync worker；reload 还会让内存队列和最终状态丢失。因此必须修，但优先级排在本次纯前端入口迁移之后。

### 持久化表决策

不直接扩展 `shipping_task`：

- `shipping_task` 已有 shipping 专属租约、接口和恢复语义；
- 把产品任务塞进去会让 product 路由依赖 shipping 的任务模型；
- 为了复用一张表而给已稳定的 shipping 流程增加 `domain` 迁移，收益小于回归面。

下一批建议新增最小的 `product_lifecycle_task` 表（Alembic），字段与通用状态契约对齐：

- `id`、`status`、`progress`、`result`、`message`；
- `created_at`、`updated_at`、`finished_at`；
- 单例 `lease_key` 或等价唯一约束，重复启动返回标准 409 和当前 `task_id`。

虽然触发频率低，仍应阻止两个生命周期线程同时更新相同产品；这项互斥不应省略。

接口建议：

- `POST /api/product/lifecycle/update`：路径保留；
- `GET /api/product/lifecycle/tasks/<task_id>`：短轮询、`Cache-Control: no-store`；
- 旧 `/progress/<task_id>` 在前后端同批切换后移除，不再保留会占 worker 的 SSE 兼容层。

### 查询与事务决策

三条聚合查询不应原样保留：

- `qty_query` 已经按“型号 + 月份”返回数量；
- 可从这一份结果在 Python 中同时推导 `months_by_model`、首月和末月；
- 因此 `agg_query` 和 `months_query` 可删除，把三次重复 JOIN/扫描收敛为一次。

事务也不应每个型号提交一次。403 个型号、约 403 个成品的规模不构成“大事务”理由，建议统一计算后一次提交；若未来规模扩大，可按明确批量（例如 100 个型号）提交，而不是逐行提交。

已有 `ix_sof_finished_code_date(finished_code, shipped_date)` 是本查询最可能使用的索引。不要凭经验直接加 `USE INDEX` 或创建新索引：

1. 先对合并后的 SQL 在生产同结构数据上跑 `EXPLAIN ANALYZE`；
2. 比较默认计划和 `USE INDEX (ix_sof_finished_code_date)`；
3. 只有 hint 稳定更优才固化，并补 SQL 生成/回归测试。

这三项（持久化、三查合一、批量提交）应在同一个生命周期专项中一起完成，否则只改 SSE 后，后台线程仍会制造不必要的数据库压力。

## 六、后续顺序

1. Claude：完成本文件的数据管理入口迁移并交回审查；
2. Codex：实施产品生命周期持久化、短轮询、聚合合并和事务收敛；
3. Claude：后端契约稳定后，把 `page-product.vue` 的 EventSource 改为短轮询；
4. 再回到既定的任务取消/确定性解析、缓存与结构拆分队列。

