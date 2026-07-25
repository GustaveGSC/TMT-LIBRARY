# 发货解析确定性修复实施交接

## 提交与范围

实现提交：`83aa736 fix(shipping): make order resolution deterministic`

分支：`codex/shipping-determinism-audit`

本批完成：

1. 成品候选固定为“组件数量降序 → `finished_code` 升序”。
2. 每个成品的要求组件固定为编码升序 `tuple`，不再遍历 `frozenset`。
3. 订单元数据采用已确认的“完成发货”口径：
   - 代表行比较键为 `shipped_date` 降序、`shipping_record.id` 降序；
   - operator/channel/地域等字段全部取同一代表行；
   - `customer_alias` 仅在代表行为空时，按相同顺序回退首个非空值。
4. 财务导入结果新增客户简称冲突统计，不阻断导入。
5. 只读审计工具增加元数据新旧对比和全量稳定结果 SHA-256。

没有数据库结构变更，没有 Alembic migration，没有部署。

## 已稳定的财务导入契约

`import_finance` 的 `done.result` 新增：

```json
{
  "customer_alias_conflicts_count": 18,
  "customer_alias_conflicts_order_nos": ["ORDER-001", "ORDER-002"],
  "customer_alias_conflicts_truncated": false
}
```

- `customer_alias_conflicts_count`: 本次上传文件涉及的财务发货订单中，UPSERT 后存在多个不同非空
  客户简称的订单总数。
- `customer_alias_conflicts_order_nos`: `string[]`，订单号升序，最多 100 项。
- `customer_alias_conflicts_truncated`: 总数大于返回数组长度时为 `true`。
- 只统计 `shipping_record(source='finance', record_type='shipping')`；销退行不决定订单派生元数据。
- 查询在导入业务事务内执行，能看到尚未提交的本批 UPSERT；任何异常或取消仍随整批回滚。
- 分块为 2,000 个订单，避免超大 `IN`，同时减少大文件的数据库往返次数。

`.claude/modules/api.md` 和 `database.md` 已同步更新。Claude 可以据此开始前端实现，但前端不能早于
后端运行时代码部署。

## 自动化测试

- 全量后端：229 项通过。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。
- 新增覆盖：
  - 同组件数量候选按编码升序；
  - 要求组件为排序 tuple；
  - 两个要求组件共享等效供给时结果稳定；
  - 3 个明确 `PYTHONHASHSEED` 的合成解析输出 hash 一致；
  - 输入行乱序时仍选完成发货代表行；
  - 代表行简称为空时按完成发货顺序回退；
  - 客户简称冲突总数 102、返回清单恰好截断为前 100 项；
  - 财务导入三个新增字段形状。

## 生产只读全量门禁

### 候选结果

全量覆盖：

- shipping：133,701 单；
- finance：116,864 单。

三个明确 seed：`1`、`20260725`、`314159`，稳定输出 SHA-256 均为：

```text
58033992d6f93966a3f333c15e2cc80d93bb56c8e134abdd65fa90b8ce17f825
```

每轮统计也完全一致：

- 同规模候选升序/降序差异：shipping 726、finance 720；
- 当前近似主键顺序改为编码升序：shipping 1、finance 1。

因此新规则不再受 Python hash seed 影响；除已审计的候选歧义订单外没有额外结果变化。

### 元数据结果

按当前近似主键首行与“完成发货”规则全量对比：

| source | 元数据变化订单 | 已知多非空值歧义 | 缺失性歧义 |
|---|---:|---:|---:|
| shipping | 879 | 873 | 6 |
| finance | 4,554 | 4,541 | 13 |

主要字段变化：

- shipping：日期 755、操作人 220、渠道名 52、渠道编码 58、渠道组织 60、省 65、市 77、区 79；
- finance：日期 4,529、渠道名 4、省 40、市 43、区 57、客户简称 14。

新增发现的 19 单“缺失性歧义”指：代表行字段为空、同订单其他行只有一个非空值。第一轮审计只统计
“多个不同非空值”，因此没有包含它们；它们仍属于元数据不一致。实现严格遵守已经确认的
“其余字段取同一代表行”，不对这些字段逐项回退；只有 customer_alias 按决策允许回退。

所有生产审计均为 `START TRANSACTION READ ONLY`，临时脚本已从 `/tmp` 删除。结束后 gunicorn active，
`/health` 2ms、`/ready` 8ms。

## 历史派生数据与部署决策

**仅 reload 新代码不会主动修正已有 `shipping_order_finished`。**

新规则会在之后的增量导入/重算中作用于被触及订单，因此如果只部署代码、不重建历史数据，会暂时形成
新旧元数据口径混用。要让历史数据统一，需要对 shipping 和 finance 全量重新解析。

当前 `resolve_all` 仍是分块提交、不可取消的旧执行模型；运行中失败可能留下部分新规则、部分旧规则。
因此建议：

1. 本提交可以先审查、合并；
2. **不要单独 reload 到生产后立即用旧 `resolve_all` 冒险重建**；
3. 将运行时代码部署与下一批 C（staging/cutover 安全重算）放在同一发布窗口；
4. C 批切换成功后，再以新规则一次性替换全部历史派生结果。

如果业务坚持在 C 批前部署，必须明确接受短期混合口径，并在完整备份、无其他写任务、禁止 reload 的
维护窗口运行旧全量重建；这不是推荐路径。

## 给 Claude 的下一步

1. 复核提交与本报告。
2. 可以开始三个字段的前端结果卡片实现：数量、展开订单号、截断提示。
3. 前端提交先不单独部署，等待后端与 C 批 cutover 的最终部署窗口。
4. 本批未实现或开放 `resolve_all/resolve_stale` 取消；不要提前显示取消按钮。

