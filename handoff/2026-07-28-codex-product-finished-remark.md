# 产品库成品备注字段：后端实施交接

## 已完成

- 新增 Alembic `20260728_01`：生产已有 `product_finished` 表时新增可空 `remark TEXT` 列。
- `ProductFinished` ORM 与 `to_dict()` 已加入 `remark`。
- 成品列表 `GET /api/product/finished` 的现有批量 query item 已加入 `remark`，展开行复用 rawItems 时无需额外请求。
- 既有 `POST /api/product/finished` 的允许字段集合已加入 `remark`；没有新增接口。
- 同步更新 `.claude/modules/database.md` 和 `api.md`。

## 验证

- 新增服务测试：`remark` 能通过既有保存接口写入、未允许字段仍被过滤、保存响应包含 remark。
- Alembic 线性 head/baseline 测试同步更新；迁移在空 baseline 测试中不假定业务表存在，在生产已存在的 `product_finished` 上才执行加列。
- `pytest backend/tests -q`：通过（含 2 个既有 skip）。
- `python -m compileall -q backend`、`git diff --check`：通过。

## Claude 部署验收

1. 备份数据库后执行 `alembic upgrade head`，确认 revision 为 `20260728_01`，并用 `SHOW COLUMNS FROM product_finished LIKE 'remark'` 核对 TEXT NULL。
2. reload 后，现有 GET 成品列表返回的每项应包含 `remark: null`。
3. 用既有 POST 保存接口提交 `{code, remark:"测试备注"}`，再 GET 验证读回；清空时传 `remark:null`，验证可保存为空。
4. 本批没有新 JOIN 或额外列表查询，确认列表响应正常即可。
