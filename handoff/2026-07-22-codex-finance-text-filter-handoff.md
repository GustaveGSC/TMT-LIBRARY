# 交接说明 · Codex → Claude（财务国家/品牌文本下钻筛选）

日期：2026-07-22

## 完成内容

- 后端提交：`ac92046 fix(shipping): support text filters for finance drilldown`
- 分支/worktree：`codex/finance-text-filter` / `E:/Project/tmt-library/.worktrees/codex-finance-text-filter`
- `POST /api/shipping/chart-data` 的 `tag_filters` 新增可选 `tag_names`：

```json
{
  "source": "finance",
  "group_by": "tag:<品牌分类ID>",
  "trade_type": "foreign",
  "tag_filters": [
    {"category_id": 12, "tag_names": ["泰国"]}
  ]
}
```

- 仅在 `source=finance` 且 category 名为“地域”或“品牌”时按人工映射文本处理 `tag_names`：地域匹配 mapping.country，品牌匹配 mapping.brand。
- `tag_names` 不要求 `product_tag` 存在同名记录；单项去除首尾空格，最长100字符，最多处理100项。
- 同一过滤项同时传 `tag_ids` 和 `tag_names` 时，ID 解析出的标签名称与文本值取并集（OR）；不同 category 过滤仍为 AND。
- shipping 来源以及财务端其他标签分类忽略 `tag_names`，继续只按 `tag_ids` 走产品标签关系，旧请求完全兼容。
- 未修改主图聚合、trade_type、数据库结构或缓存逻辑。
- `.claude/modules/api.md` 已更新精确契约。

## 自动化验证

- `python -m pytest backend/tests -q`：110 passed。
- `python -m compileall -q backend`：通过。
- `python -m alembic -c alembic.ini heads`：`20260721_04 (head)`。
- `git diff --check`：通过。
- 新测试明确创建 mapping.country=“泰国”但不创建“泰国”ProductTag；使用 `tag_names:["泰国"]` 按品牌下钻后成功返回“品牌泰”，证明不依赖产品标签。

## 前端适配建议

`fetchTooltipBreakdown()` 在财务来源不再查找/依赖地域标签 ID，直接构造：

```js
const countryFilter = {
  category_id: regionDim.category_id,
  tag_names: [item.originalName],
}
```

然后把它追加到 `buildTagFilters()`。非财务来源保持原 tag ID 流程。这样泰国、越南、柬埔寨、韩国、马来西亚、澳大利亚、沙特阿拉伯、哈萨克斯坦等首次由人工映射识别的国家均能发起细分请求。

## 合并、部署与验证

1. 合并 `ac92046` 和 Claude 的前端提交，运行后端测试及 `npm run build:web`。
2. 本批无迁移；部署后端后只需按纪律 reload gunicorn，并持续检查日志、`/health`、`/ready` JSON。
3. 部署完整 web 构建。
4. 财务端世界地图切到“按品牌”，逐一验证至少泰国、越南、柬埔寨及一个原本已有产品标签的国家：新旧国家均应显示品牌明细，主图总量不得变化。
5. 在浏览器 Network 中确认新国家确实发送 chart-data 请求，body 含国家文本 `tag_names`，不再因找不到 tag ID 跳过。

本批未部署、未 push，未修改 `src/` 或 Electron。
