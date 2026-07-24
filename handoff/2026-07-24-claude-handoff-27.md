# Codex → Claude 交接：售后正确性第 2 批

日期：2026-07-24

提交：`b06150b fix(aftersale): enforce confirmation and request invariants`

## 变更内容

### 1. 确认接口幂等

`POST /api/aftersale/cases` 仍用于确认待处理订单。若相同订单已经是
`confirmed`：

- 成功返回已有工单；
- 不覆盖第一次确认的数据；
- 不重复增加原因 `use_count`；
- 不再次执行关键词候选、简称关键词、词典建议或原因—简称亲和度学习。

显式修改已确认工单继续使用 `PUT /api/aftersale/cases/:id`。

### 2. 移除共享请求状态

删除 `AftersaleRepository` 单例上的 `_active_log_ctx` 隐式通信。
确认日志上下文改为参数逐层显式传给关键词学习和词典建议函数，异常或并发请求不会再污染其他请求日志。

### 3. 请求资源边界

- `/pending`、`/cases`：`page >= 1`，`page_size` 为 `1..200`；
- 非整数或越界值返回标准 400，不再抛 500；
- `/cases` 的批量 ID 筛选、`/cases/reasons?ids=`、`/alias-affinity`
  均限制为最多 200 个正整数；
- 非法 ID 返回标准 400。

### 4. 型号删除引用保护

`DELETE /api/category/models/:id` 在型号仍被以下数据引用时返回 400：

- `product_finished` 成品；
- `aftersale_case_reason` 历史售后内容。

错误文案：`型号仍被成品或售后工单引用，不能删除；请先迁移关联数据`。
这避免删除后成品和售后统计静默退化到未知型号。

## 验证

- 全量后端 pytest：通过；
- `python -m compileall -q backend`：通过；
- `git diff --check`：通过（仅 Windows 行尾提示）；
- 新增测试直接覆盖：
  - 重复确认不进入任何学习函数且不覆盖原内容；
  - 显式日志上下文不会写入仓储对象上的旧上下文；
  - 分页、批量 ID、亲和度 ID 的非法/超限响应；
  - 有引用拒绝删除、无引用允许删除。

## 部署说明

- 无数据库迁移；
- 只需同步后端文件并 reload；
- 部署后建议实测：
  1. 对同一已确认订单重复发送原 POST，请求仍为 200，原因计数不变；
  2. `/api/aftersale/cases?page_size=201` 返回 400；
  3. 尝试删除仍有关联成品或售后记录的型号，返回 400；
  4. `/health`、`/ready` 和 gunicorn 日志正常。

## 前端兼容性

现有确认流程无需修改。型号管理页可直接展示后端删除失败文案；分页 UI 当前值低于 200，不受影响。
