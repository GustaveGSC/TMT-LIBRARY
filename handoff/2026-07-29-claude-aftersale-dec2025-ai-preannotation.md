# 交接：2025 年 12 月售后工单 AI 预标注（只读导出）

日期：2026-07-29  
接收方：Claude Code  
优先级：当前任务  
状态：请执行**数据准备与 Excel 交付**；不得写入生产售后工单。

## 目标

用户已人工处理 2026 年售后工单；希望先以 **2025 年 12 月** 为试点，使用已处理工单作为参考，由 Codex 进行逐单 AI 预标注，而不是仅套现有关键词/自动匹配规则。

最终交付是一份供用户逐行审核的 Excel，保存到用户桌面。它是建议清单，不是数据库导入文件：不得自动确认、不得修改 `aftersale_case`、`aftersale_case_reason`、原因词典或物料简称词典。

## 分工

| 工作 | 负责人 |
|---|---|
| 用生产库**只读**连接提取最小数据集 | Claude Code |
| 结合样本逐单推理、生成推荐和判断依据 | Codex |
| 生成 Excel 到桌面、确认文件可打开 | Claude Code（或在 Codex 完成候选数据后执行） |
| 用户人工审核与决定是否写回 | 用户 |

Codex 无生产数据库操作/部署权限。Claude 如需在服务器取数，只能使用独立连接并先执行：

```sql
SET SESSION TRANSACTION READ ONLY;
```

禁止通过 `create_app()` 取数：它会处理遗留任务状态，不是只读入口。

## 需要导出的数据

### A. 待预标注对象：2025-12 未处理工单

从 `aftersale_case` 取：

```text
id, ecommerce_order_no, products, seller_remark, buyer_remark,
shipped_date, operator, channel_name, province, city, district, status
```

过滤条件：

```sql
status = 'pending'
AND shipped_date >= '2025-12-01'
AND shipped_date <  '2026-01-01'
```

不要导出地址、街道等本任务不需要的个人信息。导出为 UTF-8 JSON 或 CSV，放在工作区临时目录（例如 `tmp/aftersale-dec2025-input.json`），不要提交 Git。

### B. 参考样本：已确认工单及人工标签

导出 2026 年 `confirmed` 工单，关联 `aftersale_case_reason`、`aftersale_reason`、`aftersale_reason_category`、`aftersale_shipping_alias`、`product_model`。每条原因行至少包含：

```text
case_id, ecommerce_order_no, products, seller_remark, buyer_remark,
shipped_date, channel_name,
reason_id, reason_name, reason_category_id, reason_category_name,
model_id, model_code, model_name,
shipping_alias_id, shipping_alias_name
```

如 2026 参考样本量过大，先全量导出元数据；由 Codex 按待处理订单涉及的物料/备注词选择相关样本。不能只导出最近 150 条，因为那会引入时间偏差。

## AI 预标注原则

1. 现有 `auto_match()`、关键词、简称库只作为证据之一；不得把其返回值直接当答案。
2. 每个订单必须结合：商家备注、买家留言、物料编码/名称、同类已确认案例、当前原因/简称/型号字典来判断。
3. 多原因订单必须允许输出多行建议；不能把整单备注强行归为唯一原因。
4. 备注为空、样本冲突、证据不足或仅语义相似的订单必须标为“需人工判断”，不可伪造高置信度。
5. 不根据买家姓名、地址等个人信息推断。

## Excel 输出要求

文件名：`桌面/2025年12月售后工单_AI预标注_待审核.xlsx`

建议工作表：

1. **待审核清单**（一条建议一行）
   - 订单号、发货日期、渠道
   - 原始物料、商家备注、买家留言
   - 建议原因分类、建议原因
   - 建议型号、建议发货物料简称
   - 置信度（高/中/低）
   - 建议动作（`可优先审核` / `需人工判断` / `建议忽略`）
   - 判断依据（简短、可读，例如“与已确认订单 X 的备注和物料编码一致”）
   - 参考案例订单号（可多个）
   - 用户审核列：`用户结论`、`用户备注`

2. **统计摘要**
   - 总订单数、可推荐数、按置信度和建议动作分组计数；
   - 推荐原因/型号/简称分布；
   - 明确说明：所有结果均未写回数据库。

3. **规则与限制**
   - 记录本轮采用的证据层级、置信度标准、已知歧义。

Excel 中需冻结首行、开启筛选、长文本自动换行；高/中/低置信度使用清晰但不依赖颜色本身的标识。

## 交接与验收

Claude 完成数据导出后，在本文件或新 handoff 中记录：

- 待处理订单总数、已确认参考原因行数；
- 导出文件位置和字段说明；
- 已确认连接只读、未对生产表执行 DML；
- 是否存在空备注、无物料、异常 JSON 等数据质量问题。

Codex 完成预标注后会记录：推荐覆盖率、各置信度数量、代表性歧义，以及生成的候选文件位置。用户审核通过前，不进入任何批量写回设计。

