# 交接说明 · Codex → Claude（客户简称映射四态）

日期：2026-07-21

## 命名结论

原交接中的“确认都不是”统一改名为 **“非销售客户”**，接口值为 `non_sales`。它表示已经人工审核，但该简称不应归入内销或外贸销售统计；与尚未处理的 `pending` 有明确区别。

四态最终契约：

| status | 前端文案 | 统计含义 |
|---|---|---|
| `pending` | 未审核 | 只在全部数据中出现 |
| `export` | 外贸客户 | 进入外贸、国家、品牌统计 |
| `domestic` | 内销客户 | 进入内销统计 |
| `non_sales` | 非销售客户 | 已审核，但只在全部数据中出现 |

## 后端完成内容

- 实现提交：`530b4e5 feat(shipping): add customer review statuses`
- 分支/worktree：`codex/backend-customer-status` / `E:/Project/tmt-library-codex`
- 新迁移 `20260721_04`：新增 `status VARCHAR(20) NOT NULL DEFAULT 'pending'`，将旧 `is_export=true` 转为 `export`、旧 `false` 转为 `non_sales`，然后删除 `is_export`。
- ORM、保存接口和查询响应均已移除 `is_export`，改用 `status`。
- 财务图表：foreign 只匹配 export，domestic 只匹配 domestic；pending、non_sales、无 mapping 三类均不进入二者，但仍保留在 all。
- 国家/品牌聚合和地图筛选只匹配 export。
- `GET /api/shipping/finance-customer-aliases` 新增可选 `status` 参数：
  - `status=pending` 同时包含无 mapping 的简称和显式 pending。
  - export/domestic/non_sales 只返回相应已映射记录。
  - 非法值返回 400。
- `POST /api/shipping/finance-customer-aliases/mapping` 请求体改为 `status` 四选一；旧 `is_export` 请求会返回 400。
- 已更新 `.claude/modules/api.md` 和 `database.md`。

## 自动化验证

- `python -m pytest backend/tests -q`：110 passed。
- `python -m compileall -q backend`：通过。
- `python -m alembic -c alembic.ini heads`：`20260721_04 (head)`。
- `git diff --check`：通过。
- 测试覆盖旧数据迁移、非法状态、四态统计隔离、国家/品牌仅 export、GET pending 筛选接口契约。

## 前端需要同步

这是破坏性接口改动，前后端必须同批上线：

- 四态选择器显示“未审核 / 外贸客户 / 内销客户 / 非销售客户”，不要再出现“确认都不是”或 `excluded`。
- 草稿和请求字段使用 `status`，不再读写 `is_export`。
- “仅看未审核”直接请求 `status=pending`，无需前端在当前页二次过滤。
- 默认关键字为空。
- GET 返回的无 mapping 项仍为 `mapping: null`；前端编辑初始化时把它视为 `pending`。

## 合并部署与核验

1. 合并 `530b4e5` 和 Claude 的对应前端提交，先跑后端测试及 web 构建。
2. 迁移前查询并记录旧值数量：`SELECT is_export, COUNT(*) ... GROUP BY is_export`，预期 true=4、false=3。
3. 执行 `alembic upgrade head`；迁移后查询 `status, COUNT(*)`，预期 export=4、non_sales=3、NULL=0，domestic/pending 暂无记录。
4. 部署后端并 reload，立即部署完整 web 构建，压缩破坏性接口的不兼容窗口。
5. 持续检查 gunicorn/nginx 日志，并验证 `/health`、`/ready` 返回 JSON。
6. 联调保存四种状态、`status=pending` 分页筛选及图表：当前生产没有 domestic mapping，因此“内销”图表为空是预期结果，不是故障；foreign 应保持现有 4 条外贸映射的数据。
7. 执行生产 `alembic current` 和 `alembic check`，确认 current/head 均为 `20260721_04` 且无模型差异。

本批未部署、未 push，未修改 `src/` 或 Electron。
