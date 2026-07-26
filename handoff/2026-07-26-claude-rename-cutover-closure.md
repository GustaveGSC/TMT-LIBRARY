# resolve_all rename-table cutover：门禁通过，正式上线

日期：2026-07-26

## 结论

`resolve_all` 全量重建功能正式重新开放。`ALLOW_FULL_RESOLVE=true` 已作为生产常态配置保留，
`resolve-all` 接口不再返回 503。前端"重建全部成品组合"按钮已恢复。

## 完整时间线

1. 第一次真实门禁：初版脚本 bug（监控连接未 autocommit）把被测代码自己的 `TRUNCATE` 卡到超时；
2. 第二次：脚本中途重复调用 `create_app()`，触发启动恢复逻辑误杀正在运行的任务；
3. 第三次（脚本修正后）：391.7s 完成 692,003 行全量重算，`/health`/`chart-data` 全程无失败，
   rename 本身约5秒。**但**用未加权求和比较原始组件数量与成品件数，误判 13 个 finance 订单"丢失"
   149 件数量，触发保守回滚；
4. Codex 独立只读复核：13 个订单全部满足"原始组件数量 = Σ(成品数量×组件数) + 未匹配数量"，证明是
   验收方法错误，不是数据丢失；Claude 独立复核确认（直接查 `product_finished_packaged` 验证组件
   关系，自己重新写验证脚本核对 13 单，结果一致）；
5. 用户确认后，第四次门禁（同样的修正版脚本 + 组件守恒公式）：386.9s 完成，同样 691,990 行，与
   第三次结果**完全一致**（确定性验证）；全量 133,701 个 shipping 订单 + 116,864 个 finance 订单
   逐单组件守恒校验，0 不一致；
6. 清理旧代（`cleanup_shipping_retired_generation.py`），保留 `ALLOW_FULL_RESOLVE=true`；
7. 前端恢复入口，6 个此前 skip 的 Playwright 用例全部取消 skip 并通过，全量 71 passed / 0 skipped。

## 当前生产状态

- `shipping_order_finished`：691,990 行（新一代确定性重算结果），shipping=358,460，
  finance=333,530；
- `ALLOW_FULL_RESOLVE=true` 常驻 `.env`；
- `shipping_order_finished_next`/两个代际标记表：已清空，等待下一次全量重建使用；
- 前端"重建全部成品组合"入口正常可用，取消能力（A/B/C 批）覆盖此功能；
- resolve_stale 的 `MAX_STALE_RESOLVE_ORDERS=10000` 上限仍保留（当前生产 stale=0，未被压测验证，
  维持原判断不变）。

## 经验教训（已记入项目 memory）

- `feedback_production_gate_test_script_pitfalls.md`：监控连接必须 autocommit；门禁测试期间
  `create_app()` 只能调用一次；
- `feedback_multi_component_conservation_check.md`：校验发货成品数量必须按组件数加权，不能直接比较
  原始组件数与成品件数总和。

## 后续

- D 批生产规模压测仍未开始，保持原计划（等 resolve_stale 真实压测数据支撑其安全边界后再排期）；
- 本轮涉及的 `report_internal_error()` 签名修复、失败清理重试逻辑均已在本批一并上线，不需要额外
  批次。
