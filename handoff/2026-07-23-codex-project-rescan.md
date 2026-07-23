# 全项目复查报告（去重版）

日期：2026-07-23

## 范围与基线

本轮只读复查当前 master，没有修改运行代码、接口或数据库。

验证基线：

- `python -m pytest backend/tests -q`：136 passed
- `python -m compileall -q backend`：通过
- `python -m alembic -c alembic.ini heads`：`20260721_04 (head)`
- `git diff --check`：通过

已排除已经上线的旧问题：HTTPS、生产默认密钥、Cookie/CSRF、token_version 撤销、任务持久化、Alembic baseline/revision guard、上传限制、异常信息收紧、readiness、售后 SQL 列拼接、RD 服务端路径读取等不再重复列入。

## P0：已发生的售后自动匹配故障

位置：`backend/database/repository/aftersale/__init__.py:3343-3452`

`match_shipping_alias(self, products, seller_remark=None, buyer_remark=None)` 内部使用了未定义变量 `semantic`：

```python
model = semantic_model.get_model() if semantic else None
```

该 `NameError` 被外层 `except Exception: pass` 静默吞掉，因此：

1. 发货物料简称的语义评分分支实际上无法运行；
2. `sem_scores` 保持为空；
3. 如果关键词也没有命中，`best_kw_matched == 0`，代码进入 `if best_kw_matched >= 2 or not sem_scores`；
4. `top_candidates` 为空，随后访问 `top_candidates[0]` 抛 `IndexError`。

这与生产日志里已经出现的 `top_candidates[0][0] IndexError` 完全吻合，不是理论风险。

建议作为下一批单独修复：

- 明确 `semantic` 的来源：大概率应作为参数从 `suggest_product(..., semantic=...)` 透传，或明确该函数始终允许语义。
- 无论是否启用语义，都必须对空 `kw_scores` / `top_candidates` 返回 `(None, 0.0)`。
- 不再用宽泛 `except Exception: pass` 隐藏模型分支编程错误；至少记录异常编号/日志。
- 补三类测试：无关键词且无语义、无关键词但有语义、关键词并列 tie-break。

## P1：RD 成本库权限边界缺口

位置：`backend/routes/rd/cost.py`、`backend/app.py`

`cost_bp` 作为独立 Blueprint 注册到 `/api/rd/cost`，没有继承 `rd_bp.before_request(make_blueprint_guard('rd:view', 'rd:edit'))`。成本库接口普遍只有 `@require_auth`；写接口额外调用 `_require_edit()`，但读接口不检查 `rd:view`。

结果是：任何有效登录账号（包括仅有其他模块权限或 guest 身份的账号）理论上都能读取成本快照、BOM、节点、供应商、价格等 RD 成本数据。这与 `api.md` 和全局权限约定“rd 读需 rd:view”不一致。

建议：

- 给 `cost_bp` 显式增加 `make_blueprint_guard('rd:view', 'rd:edit')`，不要假设 URL 前缀会继承另一个 Blueprint 的 guard。
- 先补真实 Cookie JWT 权限测试：无 `rd:view` 返回 403、`rd:view` 可读、无 `rd:edit` 不可写。
- 核对 `_require_edit()` 与 Blueprint guard 是否重复后再简化，先保证行为正确。

## P1：人工客户映射更新后统计不会自动刷新

位置：

- `backend/routes/shipping/__init__.py:380`
- `backend/services/shipping/__init__.py:743`
- `backend/database/repository/shipping/__init__.py:111`

保存 `shipping_finance_customer_mapping` 只更新映射表，没有把受影响的 finance 来源 `shipping_order_finished` 标记为 `is_stale=True`，也没有自动触发 resolve。用户修改国家、品牌或四态状态后，图表仍可能继续展示旧结果，直到人工执行 resolve-all。

这是数据新鲜度/业务一致性问题。建议保存映射时：

- 仅将对应 `customer_alias + source='finance'` 的聚合记录标 stale；
- 清理相关 chart-options 缓存；
- 返回受影响记录数，前端明确提示“已保存，正在/需要刷新”；
- 避免每次映射修改直接同步重算全库。

## P1/P2：单 worker 的 CPU 密集导入仍可能被 watchdog 杀死

当前生产为单 sync worker，Excel 解析在后台线程执行。任务状态和数据库写入原子性已经解决，但大 Excel 的 Python 解析仍可能长时间占用 GIL，使 worker 无法及时响应 Gunicorn arbiter；把 timeout 提高到 1800 秒只是延后触发。

建议先用生产样本记录解析阶段耗时和最大文件规模，再决定：

- 把 CPU 解析放到独立进程/任务 worker；或
- 在解析循环中安全让出执行权；或
- 对不同导入类型设置更保守的解压后行数/工作量上限。

不建议在没有压测数据时直接改 worker 数量，服务器内存不足。

## P2：RD cost 两处“先全量加载、后 Python 分页”

位置：

- `backend/routes/rd/cost.py:37-75`：快照列表 `.all()` 后按 finished_code 分组分页；
- `backend/routes/rd/cost.py:351-410`：节点列表先 `.all()`、Python 丰富/正则过滤后再切片。

数据量增长后会增加请求内存、ORM 对象数量和响应延迟。`page/per_page` 也没有统一的下限/上限约束。

建议先补 cost API 行为与查询测试，再分别设计：

- 快照：先分页 distinct finished_code，再批量读取当前页订单；
- 节点：可下推的过滤/排序下推 SQL，必须保留的正则过滤评估单独索引或预计算字段；
- `per_page` 设置合理上限。

## P2：财务相关表排序规则仍不一致

`return_record` 为 `utf8mb4_0900_ai_ci`，其他相关表/映射使用 `utf8mb4_unicode_ci`。当前查询已用显式 `.collate('utf8mb4_unicode_ci')` 修复已知 UNION/JOIN，但未来新增跨表字符串比较仍可能再次出现 “Illegal mix of collations”。

两种可选策略：

1. 维护窗口执行 Alembic 表级 collation 统一，并评估锁表/索引重建；
2. 暂不改表，但在 `database.md` 明确记录差异，并为跨表查询加测试。

## P2：登录页 resize 监听器无法卸载

位置：`src/views/loginViews/page-login.vue:218-241`

注册：

```js
window.addEventListener('resize', () => { refreshRects(); updateAllPoses(lastMx, lastMy) })
```

卸载：

```js
window.removeEventListener('resize', refreshRects)
```

两者不是同一个函数引用，因此监听器不会移除。反复进入/离开登录页会累积 resize 回调和姿态计算。应提取具名 `onResize`，注册和卸载使用同一引用。

## P2：自动化测试仍集中在后端基础设施，核心业务覆盖不足

当前 136 项测试质量较好，但覆盖集中在安全、迁移、任务可靠性、客户映射和 RD 护栏。以下高风险业务仍缺少直接回归：

- 售后 `match_shipping_alias` / `suggest_product` / `confirm_case`；
- shipping 图表聚合、索引 hint、trade_type、缓存失效；
- RD cost 26 个接口的权限与 CRUD 行为；
- 产品导入/分类/标签/参数主要流程；
- 前端完全没有测试脚本或测试文件，`package.json` 也没有 lint/typecheck/test 命令。

建议先补已发生故障和高频写流程，不追求一次性覆盖率指标。

## P3：已停用 Electron 的不兼容分支仍在前端

后端已经删除 RD 服务端路径读取协议，但以下停用 Electron 分支仍发送旧 JSON 字段：

- `src/components/rdTools/EcnForm.vue`：`ecr_path`
- `src/components/rdTools/EcrForm.vue`：`bom_before_path` / `bom_after_path`
- `src/components/rdTools/PdmToBomForm.vue`：`file_path`

Web 不会触发，当前不构成线上漏洞；但任何人误启动旧 Electron 客户端都会稳定失败。既然已经正式停止 Electron 支持，建议删除这些 RD 分支，统一走 File + multipart，或至少加显式不可用提示，避免保留看似受支持但实际坏掉的代码。

同时 `package.json` 默认 `dev/build/dist` 仍以 Electron 为主，容易让新维护者走错入口。可在后续维护周期调整默认脚本或加醒目标记，但不要与业务修复混批。

## P3：大型模块仍是主要维护成本

当前较突出的“大文件/上帝模块”：

- `backend/database/repository/aftersale/__init__.py`：3907 行、约 189 KB；
- `backend/database/repository/shipping/__init__.py`：1378 行；
- `backend/routes/rd/cost.py`：约 33 KB，26 个端点直接操作 ORM；
- `src/views/shippingViews/ShippingDashboard.vue`：约 187 KB；
- `src/views/aftersaleViews/AftersaleProcess.vue`：约 137 KB；
- `src/components/product/FinishedExpandRow.vue`：约 118 KB。

结构问题本身不应抢在真实故障前处理。建议顺序仍是：先补行为护栏，再按单一职责小步拆分，禁止整体重写。

## 仓库与部署卫生（独立维护窗口）

### Git 历史和构建产物

- `git count-objects -vH`：当前 loose objects 约 1.17 GiB；
- 历史中至少有多版 27–40 MB 的 `electron/resources/python-backend/backend.exe`；
- 当前仍跟踪 `dist-web` / `dist-web-build` / Electron 资源下共 185 个文件，约 58 MB；
- `dist-web-build/` 是曾用于绕过 VS Code 锁定的临时构建目录，却仍在版本控制；
- 两个 `electron.vite.config.<timestamp>.mjs` 生成文件仍被跟踪。

建议分两阶段：

1. 普通提交先清理当前不应跟踪的 `dist-web-build` 和临时 mjs，并更新 `.gitignore`；是否继续提交 `dist-web` 需要结合现有部署方式单独决定。
2. 历史重写用 `git filter-repo` 独立维护窗口执行，需用户明确批准、全员停写、完整备份并重新克隆；不能与功能开发并行。

### 服务器非 Git 残留

此前部署记录确认生产目录有 `add_2m2kids_tag.py`、`replace_tms.py`、`resource.py` 三个未纳入 Git 的文件。本轮没有连接生产机，无法确认现状。若清理，必须先只读查看内容、mtime、是否被 systemd/import/cron 引用，再决定归档或删除。

## 接口文档完整度

当前代码扫描到约 220 个路由装饰器，`api.md` 中按标准 `METHOD /api/...` 格式识别到约 165 条。部分差异可能来自同一路由多方法或非 `/api` 端点，但文档仍明显不是逐接口完整契约；不少条目只有一行索引，没有参数类型、必填项和错误条件。

建议以后继续“改到哪补到哪”，并优先补：

- 售后自动匹配；
- RD cost；
- shipping 图表/映射/任务；
- 产品资源预签名上传。

## 推荐处理顺序

1. **立即修复售后 `match_shipping_alias` 未定义 `semantic` + 空候选越界，并补测试。**
2. **修复 `/api/rd/cost` 的 `rd:view/rd:edit` 权限 guard，并补真实权限测试。**
3. 设计客户映射保存后的局部 stale/cache 失效机制。
4. 修复登录页 resize 监听泄漏。
5. 为 RD cost 分页优化和售后/shipping 核心业务补测试。
6. 决定 collation 是迁移统一还是文档化维持。
7. 清理 Electron 死分支、临时构建产物和生成配置。
8. Git 历史瘦身最后单独排期。

