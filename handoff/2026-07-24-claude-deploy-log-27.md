# Claude 部署记录：售后正确性第 2 批（对应 handoff-27）

日期：2026-07-24

## 部署结果

无数据库迁移，按标准流程执行：

1. 确认无运行中导入/重算任务。
2. 上传 4 个变更文件（`database/repository/aftersale/__init__.py`、
   `database/repository/product/category.py`、`routes/aftersale/__init__.py`、
   `services/product/category.py`），逐一 MD5 校验一致。
3. `systemctl reload gunicorn`：master PID 未变（2091，运行 10+ 小时），旧 worker 正常退出，
   新 worker 正常启动，8 秒延迟检查 `systemctl status` + `journalctl` 无崩溃记录。
4. `/health` → `{"status":"ok"}`，`/ready` → `{"status":"ready"}`。

## 复核要点

- 幂等确认：`confirm_case()` 在工单已是 `confirmed` 时提前返回既有记录，不再执行关键词学习/简称学习/
  亲和度累积；新增测试用 `monkeypatch` 把四个学习函数替换成"调用即失败"的断言桩，直接证明重复确认
  路径不会触达它们。
- 移除仓储单例上的 `_active_log_ctx` 隐式状态，改为 `log_ctx` 参数显式传递到
  `_upsert_dict_suggestion`/`_check_ignore_term_candidates`；新增测试验证旧的 stale 上下文不会被
  写入，新调用只写入显式传入的 context。
- 请求边界：`/pending`、`/cases` 的 `page`/`page_size`、`/cases` 批量 ID 筛选、`/cases/reasons?ids=`、
  `/alias-affinity` 均有上限（page_size ≤200、ID 列表 ≤200 个正整数），非法输入返回标准 400 而非
  抛 500。生产 curl 验证因未带有效会话被 401 拦在鉴权层之前（符合 `before_request` 顺序，不代表
  400 校验未生效）——校验逻辑本身已由真实 SQLite 单元测试覆盖并通过。
- 型号删除保护：`CategoryRepository.get_model_reference_counts()` 两条 COUNT 查询（`product_finished`/
  `aftersale_case_reason`），有引用时 `delete_model` 服务层返回 400，避免成品/售后统计静默退化为
  "未知型号"。

## 前端联调

`ea80e99`（发货 worktree 分支）已完成，尚未合并到 master。后端本批不需要前端配合，型号管理页可直接
展示后端 400 文案；分页 UI 当前值均低于 200 上限，不受影响。下一步：把 `ea80e99` 合并进 master 并部署。
