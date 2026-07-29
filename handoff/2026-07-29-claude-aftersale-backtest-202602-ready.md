# 2026-02 回测试点：数据已备好，交接 Codex 做盲标

日期：2026-07-29
接收方：Codex
状态：**数据已就绪，可开始逐单预标注**
前序：`2026-07-29-claude-aftersale-dec2025-ai-preannotation.md`（原需求）、
`2026-07-29-claude-aftersale-dec2025-export-blocked.md`（阻塞说明）

## 为什么从"2025-12 未处理工单"改成"2026-02 回测"

原范围无对象可标：生产库 **不存在 `status='pending'` 的工单**（全库 2012 confirmed /
626 ignored / 0 pending），2025-12 更是只有 8 单且全部落在 `shipped_date=2025-12-31`
（全库最早日期就是这天）。详见阻塞说明文档。

用户已确认改为**回测式试点**：拿 **2026-02** 已人工处理的工单做持出集，剔除人工标签
交给 Codex 盲标，标完与人工结论逐条对比，量化准确率。这样能在真实积压到来之前先验证
方案可不可用。

与原需求的一个差异：持出集**包含该月 confirmed + ignored 全部 217 单**（不只是
confirmed 164 单），并抹掉了 `status`。因为真实场景下你面对的是一批未分类工单，
既要给原因建议、也要判断哪些"建议忽略"；只喂 confirmed 会让"建议忽略"这一路无法评估。

## 数据文件（`tmp/backtest-202602/`，未提交 Git）

| 文件 | 内容 | 量 |
|---|---|---|
| `holdout-202602-blind.json` | **盲标输入**：2026-02 全部工单，已抹掉 status 与全部人工标签 | 217 单 |
| `reference-confirmed-excl-202602.json` | 参考样本：confirmed 工单及人工标签，**已排除 2026-02** | 1865 行 / 1848 单 |
| `dict-reasons.json` | 原因词典（含 keywords / negative_keywords / use_count） | 154 |
| `dict-reason-categories.json` | 原因一级分类 | 11 |
| `dict-shipping-aliases.json` | 物料简称词典（含 keywords） | 123 |
| `dict-product-models.json` | 型号字典（code / model_code / name / 系列 / 品类） | 435 |
| `holdout-202602-truth-*.json` | **标准答案，评分用，请勿在标注阶段打开** | 217 单 / 169 原因行 |

盲标文件字段：`case_id, ecommerce_order_no, products, seller_remark, buyer_remark,
shipped_date, operator, channel_name, province, city, district`。

> `province/city/district` 是按原需求的字段清单保留的（区域级，非街道地址）。
> 按 AI 预标注原则第 5 条，**不得据此推断**，它们只用于最终 Excel 的展示。

## ★ 防泄漏（这条最关键）

参考样本**必须**是 `reference-confirmed-excl-202602.json` 这一份。原先导出的
`tmp/aftersale-2026-confirmed-samples.json` 含 2026-02 自身，用它做参考等于直接
查到持出单的答案，准确率会虚高到毫无意义。

导出时已断言校验：盲标订单号与参考样本订单号交集 = **0**。

标准答案文件请在标注**完成后**再用于自查，标注过程中不要读取。

## 需要 Codex 产出

逐单推理后输出候选 JSON：`tmp/backtest-202602/codex-predictions.json`，
一条建议一个元素（多原因工单输出多条，共享同一 `ecommerce_order_no`）：

```json
[
  {
    "ecommerce_order_no": "260201007",
    "suggested_action": "可优先审核 | 需人工判断 | 建议忽略",
    "confidence": "高 | 中 | 低",
    "reason_category_name": "主功能失效",
    "reason_name": "气弹簧漏油",
    "model_code": "JQ43FD100-YL-eliNeli-A",
    "shipping_alias_name": "气弹簧",
    "evidence": "商家备注含'气弹簧漏油'，与已确认订单 2601xxxx 备注及物料编码一致",
    "reference_order_nos": ["2601xxxx", "2603xxxx"]
  }
]
```

字段要求：
- 原因/分类/简称/型号请**取自上面四个字典里的现有值**，不要发明新标签；确实无法归入
  现有字典的，把该字段留 `null` 并在 `evidence` 里说明。
- `suggested_action='建议忽略'` 的条目允许原因/型号/简称全为 `null`。
- 证据不足、备注为空、样本冲突、仅语义相似的，必须给 `需人工判断` + 低置信度，
  不要伪造高置信度（原需求原则第 4 条）。
- 多原因订单必须拆多行，不要把整单强行归一个原因（原则第 3 条）。
- 现有 `auto_match()` / 关键词 / 简称库只作为证据之一，不得直接当答案（原则第 1 条）。

## 我收到后会做

1. **评分**：与 `holdout-202602-truth-*.json` 逐条比对，分四个维度分别算准确率
   （原因分类 / 具体原因 / 型号 / 物料简称），外加"建议忽略"判定的二分类指标。
   会按分类分别算召回——参考样本里头部三类（主功能失效 855 / 实木问题 369 /
   物料破损 273）约占 74%，只看总体命中率的话全押头部类也能拿到虚高分数。
2. **生成桌面 Excel**：`桌面/2025年12月售后工单_AI预标注_待审核.xlsx` 的同构文件
   （文件名会按实际范围改为 2026-02 回测），含待审核清单 / 统计摘要 / 规则与限制
   三个工作表，冻结首行、开启筛选、长文本换行、置信度不依赖颜色本身区分，
   并额外加一页准确率对比。

## 合规

- 本轮导出全程只读：独立 `pymysql` 连接、未经 `create_app()`、
  `SET SESSION TRANSACTION READ ONLY` 并回读 `@@transaction_read_only` 断言为 1，
  仅 `SELECT`，无任何 DML/DDL。服务器端临时脚本与中间文件已删除。
- `tmp/` 已加入 `.gitignore`（含客户备注）。
- 不写回 `aftersale_case`、`aftersale_case_reason`、原因词典、物料简称词典；
  用户审核通过前不进入任何批量写回设计。
