# 售后确认工单物料名称：ERP 覆盖修复通过生产验证并上线

日期：2026-07-27

## 结论

Codex 第二次修复（55862e2）审查通过，正确定位到用户实际使用的路径——`get_cases()` 响应组装
阶段对 `AftersaleCase.to_dict()` 返回的 `products` 快照做读时覆盖，不修改历史 JSON 快照本身，
只批量查一次 `import_product_raw` 做名称覆盖。本地测试全绿，无迁移，同步两个文件后 reload，
真实 HTTP 用问题原始样本复测通过。

## 验证结果

`GET /api/aftersale/cases?search=20260127006` 中 `1208YJZM01-A` 的 `products[].name`：

```
悦己_桌面 (V1.1)电动1.4米橡木本色_A（1208YJZM01-A）
```

与 `import_product_raw.name` 完全一致，问题解决（上一版误判为已修复，实际改的是待处理队列；
这次改的是确认工单表格/图表抽屉共用的 `GET /api/aftersale/cases`，就是用户实际反馈的界面）。
多订单正常分页查询（无 `search`）返回 200，20 条正常。

## 当前状态

售后图片/视频导入功能相关的全部待办（六个媒体接口、has_media 筛选、物料名称 ERP 覆盖）均已
验证上线，无已知遗留问题。
