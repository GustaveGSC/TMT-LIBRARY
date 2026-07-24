# Codex → Claude 交接：财务导入工作流 C 批（匹配候选剪枝）

日期：2026-07-24

提交：`eec2330 perf(shipping): prune impossible resolve candidates`

## 实现

原算法对每个订单遍历全部成品组合。本批为每个成品选择一个必要物料作为“锚点”，建立：

```text
实际可用物料编码 → 可能满足锚点的成品索引
```

每个订单只取其现有物料命中的候选，再按原 `sorted_finished` 索引排序，继续执行原有：

- 复杂组合优先顺序；
- 精确编码优先；
- 精确码缺货时等效码兜底；
- 等效码字典序消耗；
- 最小可用数量贪心匹配；
- 剩余物料输出。

锚点是成品所有必要物料中，在全成品库出现频率最低的一个；任何合法匹配都必须满足该锚点，因此剪枝不会
去掉可能匹配的成品。

## 自动化等价性

新增测试同时保留两种执行方式：

- `candidate_index=None`：遍历全部成品的旧基准；
- 传入倒排索引：新剪枝路径。

逐订单精确比较：

```text
({finished_code: quantity}, {remaining_product_code: quantity})
```

覆盖：

- 精确码；
- 等效码；
- 精确码和等效码同时存在；
- 复杂组合与简单组合竞争；
- 多成品消耗冲突；
- 未知/剩余物料；
- 500 组固定种子的数量矩阵。

全部逐项一致，不是只比较汇总数量。

404 个合成成品的稀疏订单，只进入 1 个候选。

## 本机合成基准

环境为开发机、404 个三物料成品、稀疏订单：

| 场景 | 耗时 |
|---|---:|
| 旧全遍历 1,000 单 | 0.2669s |
| 新剪枝 1,000 单 | 0.0036s |
| 1,000 单加速 | 约 74x |
| 新剪枝 10,000 单 | 0.0381s |

该数字只证明复杂度方向，不代表生产绝对耗时。生产还包含 DB 加载、对象构建和写入。

全量 pytest、compileall、git diff --check 均通过。

## 生产部署前强制门禁

这批改变核心匹配循环，不能直接 reload。建议：

1. 备份生产 `backend/services/shipping/__init__.py`；
2. 上传新文件，但暂不 reload（现有 worker 仍运行旧内存代码）；
3. 在独立 `app.app_context()` 进程中：
   - 按生产产品库构造 `sorted_finished/equiv_map`；
   - 分别取 shipping、finance 各至少 1,000 个真实订单；
   - 用 `_greedy_match_finished(..., candidate_index=None)` 跑旧基准；
   - 用 `_build_finished_candidate_index()` 后跑新路径；
   - 对每个订单比较 matched 和 remaining 完全相等；
   - 分别记录耗时、候选数量分布（min/P50/P95/max）；
4. 任一订单不一致，立即恢复备份文件，不 reload；
5. 全部一致后再 reload；
6. 连续检查 `/health`、`/ready`、gunicorn 日志；
7. 用一个受控的小批导入验证任务完成和派生数量。

验证脚本必须只调用匹配 helper，禁止调用 `_resolve_orders()`，避免写生产派生表。

## 风险与回滚

- 无数据库迁移、无接口变化；
- 唯一运行时文件为 `backend/services/shipping/__init__.py`；
- 回滚为恢复旧文件并 reload；
- 不要用全量 `resolve-all` 作为本批首次验证，它会扩大故障面。

## 下一步

C 批稳定后进入 D 批：将长任务进度从 SSE 改为短轮询，解决单 sync worker 被长连接占住的问题。
