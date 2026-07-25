# 交接说明 · Claude → Codex（第三十一轮，业务口径已确认，批准实施确定性修复批次）

日期：2026-07-25

## 复核结论

B 批只读审计的三项统计已完成双重验证：

- 元数据冲突总数（shipping 133,701/2,219，finance 116,864/4,546）用一条结构完全不同的独立 SQL
  （单趟 `GROUP BY ... HAVING`，非审计脚本自己的分组子查询+汇总写法）在生产重新算了一遍，三个
  关键数字（含 finance customer_alias 冲突数 18）逐位对上；
- 审计脚本的候选匹配模拟代码（`_available`/`_consume`/`_candidate_index`）逐行比对过
  `services/shipping/__init__.py` 里真实的 `_available_packaged_quantity`/
  `_consume_packaged_quantity`/`_build_finished_candidate_index`，确认是精确复刻，不是近似实现，
  不需要重跑一次 90 秒的全量模拟来验证 726/720 这两个数字；
- 脚本的只读边界不只是"代码里只写了 SELECT"，`SET SESSION TRANSACTION READ ONLY` 是 MySQL 会话级
  强制拒绝写操作，比单纯约定更可靠。

B 批可以视为已通过双重验证，接受报告的两条建议规则（候选：组件数降序→`finished_code`升序；
要求组件固定为排序 tuple，当前 0 命中但作为预防性修复）。

## 业务决策：已确认

元数据代表行口径确认为 **完成发货**：

```text
shipped_date = MAX(shipped_date)
其余字段 = 按 shipped_date DESC, id DESC 排序后的同一条代表行（不分字段独立取值）
customer_alias 仍在此基础上，若代表行为空则回退取同订单内任一非空值（与现有"取首个非空值"语义保持
最大兼容，只是"首个"的定义从"偶然遇到顺序"改成"完成发货代表行优先，其后按同一确定性顺序回退"）
```

用户明确选择"完成发货"而非"首次发货"，理由与 Codex/Claude 两边独立判断一致：整套成品组合应归属
"最终完成发货"这个时间点，且各字段统一取自同一条代表行，不再是拼接结果。

## 客户简称冲突接口边界：已确认

财务导入结果新增：

```text
customer_alias_conflicts_count       — 冲突订单总数
customer_alias_conflicts_order_nos   — 最多前 100 个冲突订单号
customer_alias_conflicts_truncated   — 是否被截断（总数超过100时为 true）
```

不阻断导入；暂不建设独立管理页面。前端展示数量 + 支持展开清单，若 `truncated=true` 额外提示"仅展示前
100 单，完整清单请…"（具体文案由 Claude 定，不需要再等后端确认）。

## 现在可以开始的批次

Codex 按报告"四、下一步门禁"顺序实施：

1. 候选顺序（组件数降序→编码升序）+ 要求组件排序 tuple；
2. 元数据代表行改为"完成发货"口径（`shipped_date DESC, id DESC` 单一代表行，不分字段独立取值）；
3. 财务导入结果新增 `customer_alias_conflicts_count`/`customer_alias_conflicts_order_nos`（≤100）/
   `customer_alias_conflicts_truncated`；
4. 至少 3 个不同 `PYTHONHASHSEED` 重复运行，输出 hash 一致；
5. 生产真实 shipping/finance 全量比较新旧结果：非歧义订单 0 不一致，候选歧义订单（726+720，含之前
   报告里那 2 条会实际变化的样本）单独列出，元数据冲突订单按新口径单列并附变化前后对比；
6. 补合成测试覆盖两个要求组件共享同一供给集合的场景（即使当前生产 0 命中）。

本批不涉及 resolve_all/resolve_stale 取消，不涉及 C 批 staging。部署仍按既有纪律：无数据库结构变更
的话直接文件同步+reload；若元数据口径改动需要一次性重算历史数据以修正既有派生结果的日期，需要单独
在交接文档里说明是否需要、范围多大、能否用现有"重建全部成品组合"完成，不要在这批悄悄触发大范围重算。

## Claude 这边

等后端契约稳定（尤其是财务导入结果新增的三个字段名和 `customer_alias_conflicts_order_nos` 的元素
形状）后开始前端：导入结果卡片展示冲突数量+可展开清单+截断提示。契约稳定前不预先写代码。
