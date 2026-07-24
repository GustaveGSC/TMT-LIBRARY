# Claude 部署记录：财务导入工作流 C 批（成品匹配候选剪枝）

日期：2026-07-24

## 部署流程（按交接文档强制门禁执行）

1. 备份生产 `backend/services/shipping/__init__.py`
   （`/root/backups/services_shipping_init_pre_eec2330_20260724_145617.py`）。
2. 上传新文件，**暂不 reload**（运行中 worker 仍是旧内存代码）。
3. 在独立进程（`PYTHONPATH` 直接跑脚本，不经过 gunicorn）内，用生产真实 `sorted_finished`
   （404 个成品）/`equiv_map` 构造，分别抽取 1,000 个真实 `shipping` 来源订单和 1,000 个真实
   `finance` 来源订单，用 `_greedy_match_finished(..., candidate_index=None)` 和
   `_build_finished_candidate_index()` 之后的路径逐订单精确比较：

   ```
   sorted_finished: 404 个成品
   equiv_map: 4 个物料参与等效映射

   source=shipping: 1000 单，旧 0.4520s / 新 0.0052s，不一致 0
   source=finance:  1000 单，旧 0.4481s / 新 0.0115s，不一致 0

   候选数量分布（2000 单）：min=0 P50=0 P95=1 max=19
   总结：2000 个真实订单，不一致 0 个 → PASS
   ```

   验证脚本只调用纯函数 helper，未调用 `_resolve_orders()`，零写入。
4. 全部一致后才 `systemctl reload gunicorn`；master PID 未变，8 秒延迟检查
   `systemctl status`+`journalctl` 无崩溃记录，`/health`/`/ready` 正常。
5. 额外做了一次真实写入路径验证（超出交接文档要求）：在 `app.app_context()` 内对一个真实
   `shipping` 订单实际调用 `_resolve_orders([order_no], commit_chunks=False)`——这是
   `resolve_all`/`import_shipping`/`import_finance` 生产实际会执行的同一条代码路径——比较
   写入前后 `shipping_order_finished` 快照完全一致（5 行逐字段相同），随后 `db.session.rollback()`
   撤销所有改动，并二次查询确认数据库状态与 rollback 前一致。这一步补充验证了完整写入管线
   （非仅匹配算法本身）在新代码下行为不变，且全程未提交任何改动到生产。

## 结论

新旧算法在 2000+1 个真实生产订单上逐字段完全一致，候选剪枝速度提升在真实数据上约 87 倍
（shipping）/39 倍（finance），远超本机合成基准估计的方向性结论。已安全部署，无需回滚。

## 下一步

按计划进入 D 批：长任务进度从 SSE 改为短轮询，解决单 sync worker 被长连接占住的问题。
