# 成品详情新增「备注」字段（交接 Codex）

## 需求

产品库成品详情（`FinishedExpandRow.vue`）需要新增一个自由文本「备注」区块，展示位置在**标签栏
和参数区之间**（即：图片+信息卡片下方的标签行 → **备注** → 折叠区资料/参数/数据）。这是一个
全新字段，`product_finished` 表目前没有任何备注/notes 类字段。

## 需要的后端改动

1. **Alembic 迁移**：`product_finished` 新增 `remark TEXT NULL` 列（自由文本，不限长度，允许
   为空）。
2. **模型**：`backend/database/models/product/finished.py` 的 `ProductFinished` 加
   `remark = db.Column(db.Text, nullable=True)`。
3. **列表查询补充字段**：`backend/database/repository/product/finished.py` 里
   `get_finished_list()` 组装 `item` dict 的地方（约 127-162 行）加一行
   `'remark': fin.remark if fin else None`——这是 `finishedStore.rawItems` 的数据源，
   `FinishedExpandRow.vue` 展开行直接复用这份数据，不单独发请求，所以必须在这条批量列表查询里
   就带上，不要只加在某个单独的详情接口里（那样前端拿不到）。
4. **保存**：`backend/services/product/finished.py:37` 的 `allowed` 字段集合
   （`save_finished()` 用于过滤 `POST /api/product/finished` 请求体里允许更新的字段）加入
   `'remark'`，使其能通过现有的成品保存接口一并更新，不需要新开专门的备注接口。

## 不需要的改动

- 不需要新建单独的 `GET/PUT` 备注接口，复用现有 `POST /api/product/finished` upsert 接口即可
  （前端保存整行时一并带上 `remark` 字段）。
- 不需要历史记录/审计（除非 Codex 认为有必要，这次没有这个要求）。
- 不影响标签、参数、资料等既有逻辑，纯新增字段。

## 文档

改动后请同步更新 `.claude/modules/database.md`（`product_finished` 表结构）和
`.claude/modules/api.md`（如果 `POST /api/product/finished` 那一行有列具体字段的话）。

## 验证要求

- 真实 MySQL 下验证：迁移后字段存在，`GET /api/product/finished` 列表返回项里带 `remark`
  （新数据为 `null`）；`POST /api/product/finished` 携带 `remark` 能正确保存并在下次查询里
  读回。
- 确认这条改动不影响列表查询的整体响应时间（只是多返回一个已有行上的一个 TEXT 列，不涉及额外
  JOIN，理论上没有性能影响，但请顺带确认）。

## 前端

前端 UI（备注展示/编辑、放置在标签栏和参数区之间的具体样式）由 Claude 负责，等这批后端字段
上线后我会跟进实现，不需要 Codex 处理前端部分。
