# 部署记录 · 财务端国家/品牌下钻支持文本筛选（第十三轮）

日期：2026-07-22

## 背景

用户实测世界地图"按品牌"细分时，泰国/越南/柬埔寨/韩国/马来西亚/澳大利亚/沙特阿拉伯/哈萨克斯坦等国家品牌明细面板空白，而捷克/蒙古/白俄罗斯等能正常显示。排查确认：世界地图主图按 `mapping.country` 文本聚合，不依赖产品标签，数字本身正确；但"按品牌"下钻请求（`fetchTooltipBreakdown()`）要求先在 `product_tag`（地域分类）里找到该国家对应的 `tag_id` 才会发请求，找不到就静默跳过——这些国家是第一次通过客户简称人工映射识别出来的出口目的地，从未被打过产品标签，因此永远拿不到品牌细分。这是第十一轮交接文档就标注过、当时判定"不影响本批"的已知限制，这次正式修复。

交接文档：`handoff/2026-07-22-codex-handoff-13.md` → `handoff/2026-07-22-codex-finance-text-filter-handoff.md`。

## 后端审查结论

`codex/finance-text-filter`（`ac92046`）审查通过：

- `get_chart_data` 的 `tag_filters` 新增可选 `tag_names` 字段：`source='finance'` 且分类为"地域"/"品牌"时，`tag_names` 直接按人工映射文本筛选（`mapping.country`/`brand IN (...)`），不要求 `product_tag` 表有对应记录；单项去空格、限长 100 字符、最多 100 项。
- 同时传 `tag_ids` 和 `tag_names` 时取并集（OR），`tag_ids` 路径继续走原有"ID→标签名→筛人工映射"转换，两条路径不冲突。
- 非财务来源、财务端其它标签分类忽略 `tag_names`，继续只认 `tag_ids`，旧请求完全兼容，无破坏性。
- 测试新增覆盖：`mapping.country='泰国'` 但故意不建对应 `ProductTag`，验证 `tag_names:['泰国']` 仍能正确返回品牌细分——精确复现并验证了用户报告的场景。本地复跑 110 passed。
- 无 schema 变更，纯查询逻辑改动，无需迁移、无需全库备份。

## 前端改动（我方）

`ShippingDashboard.vue` 的 `fetchTooltipBreakdown()`：`dataSource.value === 'finance'` 时，不再查找 `regionDim.tags` 里的 `tagId`，直接用国家/品牌显示名构造 `{ category_id, tag_names: [item.originalName] }`；非财务来源保持原 `tag_ids` 路径不变。

## 部署步骤

1. 确认无导入/resolve 任务在跑。
2. scp 同步 `backend/database/repository/shipping/__init__.py`，md5 核对一致。
3. `systemctl reload gunicorn`；8秒后复查无异常（master pid 2258 未变）。
4. 部署完整 `dist-web/`，线上 JS hash 校验一致，`/health` 200。

## 部署后生产验证

```
GET 泰国品牌细分（source=finance, group_by=tag:品牌分类id, tag_filters=[{category_id:地域分类id, tag_names:['泰国']}]）
→ [{'label': 'SORAYA MAROM', 'quantity': 2.0, 'actual_quantity': 2.0}]
```

与配置页面"外贸-泰国-SORAYA MARON"映射记录对得上，且"泰国"确认不在 `product_tag` 表里（此前查证过），证明修复生效。

## 影响说明

- 纯查询逻辑修复，无数据变更，无破坏性接口改动（新增可选字段，旧请求不受影响）。
- 用户之后标注的任何新国家/品牌（哪怕产品库从未打过对应标签）都能正常在世界地图下钻里显示。
