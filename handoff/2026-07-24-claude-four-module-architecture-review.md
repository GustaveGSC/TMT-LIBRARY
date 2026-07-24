# 全模块架构审查汇总（产品库 / 发货数据 / 售后数据 / 数据管理）

日期：2026-07-24
性质：只读审查汇总，无代码变更。产品库那批已经过 Codex 独立复核（见 `handoff/2026-07-24-codex-product-library-architecture-review.md`），发货/售后/数据管理三批是本文档首次汇总，尚未经过 Codex 独立复核。

## 一、跨模块反复出现的模式（不是巧合，是系统性问题）

1. **缓存/派生数据失效点分散、靠人肉记忆维护**：产品库审查发现"产品规则/型号/分类/标签变更后 `get_chart_options` 缓存未完整失效"，这次在发货模块确认了三个新的具体遗漏点（`erp_code_rules.update`、`TagCategoryService.delete`、`TagService.delete` 均未调 `_invalidate_chart_options_cache()`）。根因是失效调用散落在各个 service 文件里，没有统一的"数据变化→通知失效"钩子。
2. **"静默吞异常"模式反复出现**：本次会话修复的 `match_shipping_alias` 语义匹配 bug（未定义变量+异常被吞）不是孤例。售后仓储里还有5处同构的裸 `except Exception: pass`（`auto_match`/`suggest_product` 的语义匹配降级路径），故障发生时完全不可观测，正是那个 bug 长期潜伏未被发现的根本原因。
3. **"上帝仓储/上帝组件"集中在售后**：售后仓储 3916 行、比 RD/账号模块拆分前更极端；`AftersaleProcess.vue` 3327行、`AftersaleReasonLib.vue` 1925行。产品库/发货的后端三层分层总体是健康的，问题集中在售后一个模块。
4. **型号删除无引用保护的连锁后果**：产品库审查发现型号删除会 `SET NULL` 掉 `product_finished.model_id`/`aftersale_case_reason.model_id`。这次在售后侧验证了具体后果：不会崩溃、不会算错总数，但历史数据会退化进"未知型号"黑洞桶且无法归因，同时分子（工单数）和分母（发货量）在型号维度上会不对称（分母因 JOIN 型号表直接消失，分子归入未知桶）——这是一个问题的两个模块表现，建议统一设计引用保护方案，不要在售后单独打补丁。
5. **前端重复请求同一模式**：产品库"每次展开详情行都重新请求分类树"，发货"每次打开看板都因 watch 联动重复请求 chart-options 和 category/tree"，都是"半静态数据没做前端缓存/去重"。

## 二、按模块的具体发现

### 产品库（已完成 Codex 独立复核，结论见专门报告）
- P0：分享页存储型XSS（`resource.py` html_title 未转义双引号）
- P1：型号删除无引用保护、`erp_code_rules`语义分裂三处矛盾、产品详情保存非原子事务、发货图表缓存失效不完整、ERP导入insert-only
- 完整内容见 `handoff/2026-07-24-codex-product-library-architecture-review.md`

### 发货数据
**值得做**：
- P1：补齐3处缓存失效遗漏（`erp_code_rules.update`、`TagCategoryService.delete`、`TagService.delete`）
- P1：`ShippingDashboard.vue` onMounted 重复请求（`loadPrefsFromStorage`赋值dateRange触发watch→调一次`loadOptions`，`onMounted`又显式调一次），且`category/tree`被绑在按日期变化的`loadOptions`里、内容却与日期无关
- P2：财务客户映射多选筛选前端拼接500条/状态上限，超限会静默丢数据且无提示（历史saga遗留半成品）
- P2：`_resolve_orders`贪心匹配在"多个候选产成品集合大小相同"时结果不确定（查询无`order_by`，MySQL返回顺序不保证稳定），无tie-break规则也无日志
- P3（不紧急）：`/equivalents`三个端点绕过service/repository直接写ORM；仓储文件1378行可按功能域拆分

**已核实无问题**：索引hint覆盖完整、导入去重UPSERT机制健全、导入失败回滚完整、trade_type过滤规范遵守
**文档层面确认**：单worker+CPU密集导入看门狗风险，**确认只是文档记录，代码层面无实质缓解**（解析循环无任何让出GIL机制）

### 售后数据
**值得做**：
- P2（成本低优先做）：5处静默吞异常补日志（`report_internal_error`），与本次修复bug同根因模式
- P2（非紧急）：仓储文件3916行按功能域拆分（原因库/工单/匹配引擎/图表/简称库治理，域间耦合低可安全拆）
- 需和产品库"型号删除引用保护"统一设计：售后侧的具体后果已验证（未知桶+分子分母不对称）
- 需要逐文件走读定拆分方案：`AftersaleProcess.vue`(3327行)/`AftersaleReasonLib.vue`(1925行)等前端大文件

**已核实无问题**：图表聚合查询数量O(维度数)、销售占比口径实现正确、导出功能健壮（任务持久化+断点恢复+流式写入）、`confirm_case`事务原子性完整（单一commit，不是产品库那种多请求部分失败模式）
**不确定**：语义编码是否阻塞请求路径（需要读`semantic_model.py`实现+基准测试才能下结论）

### 数据管理（成熟度明显高于其他三个模块）
**值得做（成本低）**：
- 解析循环加`time.sleep(0)`定期让出GIL（直接回应CLAUDE.md记录的未根治风险）
- `_resolve_orders`补`cancel_check`——目前"取消导入"在resolve阶段是摆设，点了也不会真正中断
- 格式错误行目前静默丢弃，应显式统计返回前端（"N行因格式问题跳过"）
- `EventSource`未随组件卸载清理（DataImport.vue/FinanceImport.vue）
- 把"单一大事务导入占用连接池"的取舍写进CLAUDE.md（零成本文档化）

**已核实无问题（纠正了审查前的预期）**：
- 发货/财务导入**不是**insert-only，是正确的`ON DUPLICATE KEY UPDATE` UPSERT，且有过实战踩坑修复记录
- 任务状态持久化**已经是健壮实现**（`ShippingTask`表+worker重启兜底`interrupt_running_tasks`），不是内存态
- 财务客户映射功能**现状稳定**，saga式开发已收敛，无遗留技术债

**不确定/需观察**：`ShippingOrderFinished`先删后插的并发竞态（触发条件苛刻）、SSE 300秒超时误报可能导致用户重复提交（触发条件苛刻，resolve单批次超5分钟才会撞上）

## 三、给用户的初步排序建议（未与Codex对齐，仅Claude初步意见）

1. **产品库P0 XSS** —— 已确认严重，应最先处理（Codex已给出方案）
2. **跨模块共同的"静默吞异常"和"缓存失效遗漏"** —— 建议作为一个统一的小批次处理，两类问题模式相同、修复成本都低、收益是让未来同类bug不再"悄悄发生"
3. **型号删除引用保护** —— 需要产品库+售后统一设计，不要分别打补丁
4. **各模块内部的"值得做"项** —— 按模块独立排期即可，互不阻塞
5. **仓储/组件拆分类的技术债**（售后仓储3916行、各种大前端文件）—— 优先级最低，不影响正确性，可以放到最后

建议下一步：把这份汇总也交给Codex做一次独立复核（尤其发货/售后/数据管理这三批还没有像产品库那样被"推翻式"复核过），确认有没有遗漏更严重的问题，再定最终实施顺序。
