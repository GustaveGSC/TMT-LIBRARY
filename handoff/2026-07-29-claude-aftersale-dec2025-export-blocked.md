# 2025-12 售后 AI 预标注：只读导出完成，但试点范围不成立（阻塞，待用户决策）

日期：2026-07-29
对应需求：`2026-07-29-claude-aftersale-dec2025-ai-preannotation.md`（93b8fef）
执行方：Claude Code
状态：**A 集为空，无法按原范围开展试点**；B 集已按要求导出可用。

## 结论先说

按需求文档指定的过滤条件导出，**待预标注对象为 0 条**。原因不是导出写错，而是
**生产库里根本不存在 `status='pending'` 的工单**——积压已全部处理完毕：

| status | 全库数量 |
|---|---|
| confirmed | 2012 |
| ignored | 626 |
| **pending** | **0** |

`pending` 是合法枚举值（`Enum('pending','confirmed','ignored')`），只是零行。

而且 **2025 年 12 月本身只有 8 单**，且全部落在 `shipped_date = 2025-12-31` 这一天，
均已处理（5 confirmed / 3 ignored）：全库最早 `shipped_date` 就是 2025-12-31，
所以"2025 年 12 月"实际上只是数据的最后一天，不是一个完整月份。

数据实际覆盖区间：`shipped_date` 2025-12-31 → 2026-06-30（`created_at` 最早
2026-04-24，即这批数据是 4 月导入的）。

结论：**原范围（2025-12 未处理工单）无对象可标注**，需要重新确定试点范围后再继续。

## 已完成的导出

### A. 待预标注对象（2025-12, `status='pending'`）
- 文件：`tmp/aftersale-dec2025-input.json`
- **0 条**（文件内容为 `[]`）
- 2025-12 全月按状态：`{confirmed: 5, ignored: 3}`

### B. 参考样本（2026, `status='confirmed'`）
- 文件：`tmp/aftersale-2026-confirmed-samples.json`（1.6 MB, UTF-8）
- **2029 条原因行 / 2007 个工单**，其中多原因工单 22 个
- 未做时间截断，按需求要求全量导出（避免时间偏差）
- 字段：`case_id, ecommerce_order_no, products, seller_remark, buyer_remark,
  shipped_date, channel_name, case_reason_id, reason_id, reason_name,
  reason_category_id, reason_category_name, model_id, model_code, model_name,
  shipping_alias_id, shipping_alias_name, purchase_date, days_since_purchase`
- 一级分类口径与应用一致：优先经 `reason_id → aftersale_reason.category_id`，
  `reason_id` 为空时回落 `case_reason.reason_category_id`（对应
  `AftersaleCaseReason.to_dict()` 的逻辑），未简单取单一外键。
- 额外带了 `purchase_date`/`days_since_purchase`（文档写的是"至少包含"，这两个字段
  对判断"是否过保""使用年限"有用，且不属于个人信息）。

两个文件都在 `tmp/`，**已把 `tmp/` 加入 `.gitignore`**（含客户备注，用结构约束保证
不会被误提交，而非靠人工记得）。未导出地址街道等本任务不需要的个人信息。

## 只读合规确认

- 独立 `pymysql` 连接，**未经过 `create_app()`**（按要求，它会处理遗留任务状态）。
- 连接后立即 `SET SESSION TRANSACTION READ ONLY`，并回读
  `SELECT @@transaction_read_only` 断言为 `1` 才继续，否则中止。
- 全程只有 `SELECT`，**未执行任何 DML/DDL**，未触碰 `aftersale_case`、
  `aftersale_case_reason`、原因词典、物料简称词典。
- 服务器端临时脚本与中间文件已删除。

## 数据质量

样本集质量很好，没有需要特别处理的脏数据：

| 检查项 | 结果 |
|---|---|
| 商家备注为空 / 买家留言为空 | 0 / 0 |
| 无物料（products 为空） | 0 |
| products JSON 解析失败 | 0 |
| 样本 `reason_id` / 分类 / `model_id` / `shipping_alias_id` 为空 | 0 / 0 / 0 / 0 |

即 2029 条参考行的四类标签全部完整，可直接作为监督样本。

补充两点对设计有影响的观察：

1. **`ignored` 工单基本没有原因标注**：626 个 ignored 工单只对应 22 条原因行。
   也就是说 ignored 表达的是"无需处理"，不带原因标签——它可以作为"建议忽略"这个
   判定的正样本，但无法用于评估原因/型号/简称的准确率。
2. **原因分类分布高度集中**：主功能失效 855 / 实木问题 369 / 物料破损 273 /
   次功能失效 152 / 错漏件 127 / 异响 69 / 钣金问题 67 / 外观不良 51 / 其他 38 /
   安装问题 33。头部三类占约 74%，评估准确率时要看分类级别的召回，不能只看总体
   命中率，否则全押"主功能失效"也能拿到虚高分数。

## 建议的替代试点方案（待用户选择）

**方案一（推荐）：回测式试点。** 从已确认工单里选一个月作为"持出集"，我导出该月
工单时**剔除人工标签**交给 Codex 盲标，标完再与人工标签逐条比对，直接得出准确率
（分类/原因/型号/简称四个维度分别算）。这样能在真实积压到来之前先量化 AI 方案到底
可不可用，而不是等有了待处理单再赌一次。各月可用量：

| 月份 | confirmed 工单 | 原因行 |
|---|---|---|
| 2026-01 | 317 | 319 |
| 2026-02 | 164 | 169 |
| 2026-03 | 432 | 435 |
| 2026-04 | 298 | 299 |
| 2026-05 | 366 | 374 |
| 2026-06 | 430 | 433 |

建议先用 **2026-02（164 单）**：是最小的完整月份，一轮成本最低；验证流程跑通、
指标可信后再扩到大月份。

**方案二：等新数据。** 若近期会导入新的未处理工单，此试点推迟到那时再做，现在不动。

**方案三：只试"是否需要处理"的判定。** 用 626 个 ignored + confirmed 做二分类
回测，验证 AI 能否正确挑出"建议忽略"。但如上所述 ignored 缺原因标签，这一路只能
评估忽略判定，评不了原因准确率。

## 下一步

等用户确认试点范围。确认后我会：
1. 按选定范围导出盲标输入（不含人工标签）+ 单独保存标准答案用于评分；
2. 交给 Codex 做逐单预标注；
3. 收到候选结果后生成桌面 Excel（冻结首行、开启筛选、长文本换行、置信度不依赖
   颜色区分），并附准确率对比页。

全程不写回数据库。
