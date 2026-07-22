# 交接说明 · Claude → Codex（第十三轮，财务端国家下钻不认没建过产品标签的新国家）

日期：2026-07-22

用户反馈：世界地图（财务端外贸数据）主图上，泰国/越南/柬埔寨/韩国/马来西亚/澳大利亚/沙特阿拉伯/哈萨克斯坦这些国家的净发货总量显示正确，但点开"按品牌"细分模式后，这些国家的品牌明细面板是空的——而捷克/蒙古/白俄罗斯/阿根廷/印度尼西亚/新加坡/墨西哥/美国这些国家能正常显示品牌明细。

这正是第十一轮交接文档（`handoff/2026-07-21-codex-handoff-11.md`）"注意点"里提前标注过、当时说"这次不影响主聚合"的那个限制，现在真的被用户的实际数据踩到了，需要处理。

## 根因（前端代码已确认）

`ShippingDashboard.vue` 的 `fetchTooltipBreakdown()`：地图主图上每个有数据的国家，要拉一份"按品牌"细分数据时，是这样构造请求的：

```js
const tagId = regionDim.tags?.find(t => t.name === item.originalName)?.id
if (tagId == null) return   // 找不到对应产品标签 id，直接跳过这个国家，不发请求
const tagFilters = [...buildTagFilters(), { category_id: regionDim.category_id, tag_ids: [tagId] }]
```

`regionDim.tags` 来自 `GET /api/shipping/chart-options` 返回的 `tag_dimensions`，这份列表本质是"已经在产品上打过标签、且启用为发货维度"的地域标签，和这次财务客户人工映射（`shipping_finance_customer_mapping.country`）完全是两套数据。如果某个国家从来没有作为产品标签存在过（比如用户这次通过客户简称映射才第一次识别出"泰国"这个出口目的地，但从来没有产品被打过"泰国"这个地域标签），`regionDim.tags` 里就找不到对应的 `tagId`，前端直接 `return` 跳过，这个国家永远拿不到品牌细分——主图本身不受影响（主图是直接按 `mapping.country` 文本聚合的，不依赖标签），只有"点进去看这个国家具体是哪些品牌"这个下钻请求受影响。

## 需要的后端改动

`get_chart_data`（`backend/database/repository/shipping/__init__.py`）目前对 `tag_filters` 的处理是：`source='finance'` 且分类名是"地域"/"品牌"时，把传入的 `tag_ids` 转换成标签**名称**（`ProductTag.name`），再用名称去筛 `shipping_finance_customer_mapping.country`/`brand`。这个转换本身没问题，问题是前端**拿不到 tag_id 就没法进入这个转换流程**。

麻烦加一个新的筛选方式，绕开"必须先有一个真实 tag_id"这个前提。具体怎么设计你决定，我这边的诉求是：**财务端"地域"/"品牌"维度的 tag_filters，能不能直接接受文本值，而不是必须先在 product_tag 表里有一条对应记录**。比如：

- 给 `tag_filters` 的每一项加一个可选字段，如 `{category_id, tag_ids?: [...], tag_names?: [...]}`，`tag_names` 直接是字符串数组；`source='finance'` 且命中"地域"/"品牌"分类名时，如果 `tag_names` 非空就直接用它筛 `mapping.country`/`brand IN (...)`，不需要 `tag_ids` 也不需要查 `product_tag` 表。`tag_ids` 路径保留给非财务场景/其它标签维度，两条路径互不影响。
- 或者你觉得有更简洁的方案（比如财务端这两个维度的 `tag_filters` 干脆整体单独开一个字段），也可以，反正前端会按你定的契约来传，麻烦更新 `api.md` 写清楚新契约。

## 不需要动的部分

- 主图（国家/品牌总量聚合）逻辑不用改，本来就是按 `mapping.country`/`brand` 文本聚合的，不依赖 `product_tag`，这次用户反馈的主图数据本身是对的。
- `trade_type`（内外销）判断逻辑不用改。
- 迁移：这次不涉及 schema 变化，纯查询逻辑改动。

## 验证要求

- 用一个"从未在 product_tag 里出现过、但在 shipping_finance_customer_mapping.country 里存在"的国家（比如"泰国"，可以先查一下生产库确认它确实不在 product_tag 里）验证下钻能正常返回品牌明细。
- 照例 `python -m pytest` + `compileall` + `git diff --check`，建议补一条测试专门覆盖"tag_names 直接命中人工映射，不依赖 product_tag 表"这个路径。

## 前端配合（我这边，等接口定下来再改）

`fetchTooltipBreakdown()` 里，`dataSource.value === 'finance'` 时，`tagId` 找不到就不再 `return` 跳过，改成直接把国家名/品牌名以文本形式塞进 `tag_filters`（用你定的新契约字段），非财务端场景保持原样不变。

## 协作方式

独立 worktree/分支，完成后写交接文档。这次改动范围小（一个查询函数内部逻辑），不涉及生产数据变更，不需要额外的部署前置检查，正常走"合并→部署→reload→验证"流程即可。
