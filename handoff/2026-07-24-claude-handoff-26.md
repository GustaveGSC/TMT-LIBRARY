# Codex → Claude 交接：安全修复、任务租约与图表性能批次

日期：2026-07-24

## 已完成提交

1. `250b774 fix(product): harden public resource share pages`
   - 产品资料公开分享页改为 Jinja 模板，不再用 f-string 拼接可执行 HTML/JS。
   - 外链只允许 `http/https`，并增加 CSP。
   - 新增恶意标题、文件名、外链协议和 CSP 自动化测试。
2. `f82f4f1 fix(shipping): require edit permission for warehouse filters`
   - `POST /api/shipping/warehouses/filter` 从 `shipping:view` 收紧为
     `shipping:edit`。
   - 真实 Cookie JWT + CSRF 覆盖 viewer 403、editor 200。
3. `28b96fe fix(aftersale): scope and optimize shipping denominator`
   - 售后发货分母固定 `source='shipping'`，排除售后操作员。
   - 日期查询使用 `ix_sof_source_date`，其余使用
     `ix_sof_source_finished_code`。
   - 原因维度复用同一分母，消除一次重复全表聚合。
   - 产品详情的系列月度发货分母同步修正口径与索引 hint。
4. `37bd141 fix(shipping): serialize data mutation tasks`
   - Alembic `20260724_01` 给 `shipping_task` 增加可空唯一
     `lease_key`。
   - 发货导入、财务导入、全量重算、旧数据重算共用数据库级租约；
     冲突返回标准 409，`data.task_id` 指向当前任务。
   - done/error/cancelled/interrupted 自动释放；worker 启动恢复也释放。
5. `554ec14 perf(product): batch category tree queries`
   - `/api/category/tree` 从动态关系 N+1 改为固定 3 条查询后 Python 组树。
   - JSON 字段和排序保持不变。
6. `3ce194c perf(shipping): derive chart summary from grouped rows`
   - 日期、产品、渠道、省市区等普通互斥维度从 grouped rows 计算 summary，
     每次图表请求少一次相同过滤/JOIN 的事实表扫描。
   - 标签多对多维度继续独立查询 summary，未改变既有扇出计数语义。

## 自动化验证

- 全量后端：全部通过。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过（仅 Windows 行尾提示）。
- `alembic -c alembic.ini heads`：单一 head `20260724_01`。
- 新增门禁覆盖：
  - 分享页 XSS/CSP/安全跳转；
  - 仓库筛选权限隔离；
  - 售后分母数值口径、MySQL hint 编译、重复查询次数；
  - 数据库租约并发竞争、终态释放、reload 恢复、409 契约；
  - 分类树固定 3 SQL；
  - 普通图表维度仅 1 次事实表 SELECT。

## 部署顺序与门禁

本批包含数据库迁移，建议：

1. 确认没有导入或重算任务运行，并备份数据库。
2. 先上传 migration 文件，执行 `alembic upgrade head` 到
   `20260724_01`。
3. 再同步其余后端模板、静态文件和 Python 文件。
4. `systemctl reload gunicorn`，连续检查日志、`/health`、`/ready`。
5. 实测两个并发写任务：第二个应返回 409 和第一个 `task_id`；完成第一个后
   应能创建新任务。

迁移必须先于新版运行时代码：新版 `ShippingTask` ORM 会读取 `lease_key`，
若先 reload 再迁移，任务状态接口会因生产表缺列失败。

## 生产性能验证

Codex 无部署权限，以下需 Claude 在生产环境执行并记录：

- 对修复后的售后发货分母 SQL 跑 `EXPLAIN ANALYZE`，记录 chosen index、
  access type、rows examined、actual time、temporary/filesort。
- 对发货图表普通维度各取一个典型请求，确认慢日志里不再出现同请求内
  grouped + summary 两次等价扫描。
- 部署后一周比较 `_get_shipping_agg` 慢查询出现次数和耗时。

## 容量结论

现有观测为：单 sync worker；当前 `vmstat` 无持续 `si/so`；8 小时 buffer
pool 命中率约 98.66%。暂不调整 128MB buffer pool。先观察本轮 SQL 优化一周。
若慢查询仍稳定复现、物理读持续偏高且系统可用内存有安全余量，再按
128 → 192 → 256MB 小步验证；不建议直接设为 512MB。

## 前端协作项

- viewer 用户隐藏仓库筛选保存/编辑入口。
- `/api/category/tree` 改为挂载时共享 Promise 拉取一次，不再跟日期 watcher
  重复请求。
- 409 时显示后端文案，并可用 `data.task_id` 回查当前任务状态。
