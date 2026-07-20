# 优先级修正 · 用户独立核查结果（凌驾于前三份报告之上）

日期：2026-07-20
这份文档是项目负责人（用户）对前三份报告（`2026-07-20-project-issues.md`、`2026-07-20-structure-review.md`、`2026-07-20-security-consistency-review.md`）做独立核查后的修正结论。**核心判断：之前的报告偏向代码整洁问题，遗漏了更关键的生产安全与运行可靠性问题。优先级应该是：安全配置 → 鉴权失效 → 后台任务可靠性 → 目录结构。**

Codex 请按这份文档的优先级重新排期，不要按前三份文档原本的顺序处理。

---

## 先纠正一处判断

`ReturnImport.vue` 命名叫"销退导入"，但页面实际展示的是"财务数据"，调用 `/import/finance`，和当前业务说明一致，**不是接口调用错误**。真实问题是：`FinanceImport.vue` 和 `ReturnImport.vue` 高度重复，同时后端 `/import/return` 没有进入当前前端流程——这是命名和遗留接口混乱，不是 bug。

---

## 一、P0（最高优先级，立即处理）

### P0-1：桌面端明文 HTTP 传输账号密码和 JWT
[src/api/http.js:10](src/api/http.js#L10) Electron 固定连接 `http://47.99.100.138`，登录密码和 Bearer Token 都走这个明文连接。同一网络路径上的攻击者可以监听/篡改请求，比 localStorage token 风险更直接。
**建议**：后端上正式 HTTPS 域名，HTTP 只做跳转，客户端 API 地址直接写 HTTPS，上线后验证证书链和 Electron 请求。**HTTPS 完成前，不要把 localStorage token 列为优先整改项**（那是次要风险）。

### P0-2：JWT 密钥缺失时服务仍允许启动
[backend/app.py:21](backend/app.py#L21) 只打印警告，[backend/auth.py:8](backend/auth.py#L8) 继续使用公开默认字符串 `tmt-dev-secret-change-in-production`。生产环境变量一旦丢失，任何人都能伪造 admin token。
**建议**：生产环境检测到默认值直接拒绝启动；开发环境要求显式 `APP_ENV=development` 才允许用开发密钥。

### P0-3：分享签名同样存在公开默认密钥，且 og-image 路径未校验分享 token
[backend/routes/product/resource.py:14](backend/routes/product/resource.py#L14) 默认值固定为 `tmt-share-key-2024`，知道资源 ID 就能自行生成分享 token。og-image 是完全公开路径，没有校验分享 token，只按可枚举的资源 ID 读取 OSS 图片，可能泄露尚未分享的产品资料封面。
**建议**：和 JWT 问题一起改成"生产环境缺失即启动失败"，并给 og-image 补分享 token 校验。

---

## 二、P1（高优先级）

### P1-1：禁用账号/撤销权限/改密后，旧 token 仍有效
JWT 直接存角色和权限，有效期 7 天，每次请求只验证签名，不检查用户是否被禁用/改密/权限撤销/已删除。管理员禁用账号后，旧 token 最长仍可用 7 天。
**建议**（选一种）：JWT 加 `token_version`，改密/禁用/调权时递增；或每次请求读取轻量用户状态；或短时 access token + 可撤销 refresh token。过渡期先缩短 token 有效期，敏感操作复查数据库状态。

### P1-2：内存后台任务与多 worker/reload 不兼容
发货导入、全量刷新、售后导出、生命周期更新大量用 daemon thread + 模块级字典存任务状态 + 模块级 Queue 做 SSE + 内存保存完整 Excel 导出结果。位置：[shipping routes:32](backend/routes/shipping/__init__.py#L32)、[aftersale routes:10](backend/routes/aftersale/__init__.py#L10)、[lifecycle route:25](backend/routes/product/lifecycle.py#L25)。
Gunicorn 多 worker 下请求可能被不同 worker 处理，轮询/SSE 会报"任务不存在"；reload 直接丢任务；daemon thread 可能在事务中途被杀。售后导出最多 5 万行 Excel 全存在 worker 内存里，和服务器内存紧张直接冲突。
**建议（短期）**：task 状态/结果落数据库或临时文件；限制同时运行的导入/导出数量；导出文件写临时文件或 OSS，不放内存字典。中期再考虑轻量任务队列，不必一开始上 Celery。

### P1-3：启动时自动迁移数据库，且失败被吞掉
[backend/app.py:89](backend/app.py#L89) 每个应用实例启动时执行建表和 ALTER TABLE，异常只打印"可忽略"。风险：多 worker reload 可能并发执行 DDL；DDL 失败后应用仍启动，直到业务请求才暴露缺列错误；无迁移版本、无回滚记录；生产库实际结构无法可靠追踪。
**建议**：引入 Alembic，迁移作为部署前独立步骤执行，应用启动只做结构版本检查，不执行 DDL。

### P1-4：上传/导入普遍缺全局大小限制（范围比之前报告更大）
不只是产品封面和 OSS 预签名，还包括发货/财务/销退 Excel、ECR/ECN/PDM 文件、BOM 成本文件。`shipping._check_file()` 直接 `file.read()` 不限制大小，Flask 也没设 `MAX_CONTENT_LENGTH`。既可能耗尽内存，也可能长时间占用仅有的数据库/worker 资源。
**建议（分层）**：Flask 全局请求上限；不同业务类型独立上限；扩展名+MIME+真实文件头联合校验；Excel 行数/工作表数量/压缩展开大小限制；OSS 用带大小条件的上传策略而不只是签名 PUT。

### P1-5：生产连接池文档和代码默认值冲突
文档反复写 `QueuePool(size=2)`，但 [backend/app.py:37](backend/app.py#L37) 默认是 `POOL_SIZE=5` + `MAX_OVERFLOW=5`。生产环境变量缺失时，每个 worker 最多可能建 10 个连接而不是文档说的 2 个，服务器紧张时这是明显风险。
**建议**：把安全默认值设为实际生产标准；启动日志输出最终生效的 pool 配置；文档写清楚数值是"每进程"还是"整个服务"；根据 worker 数计算数据库总连接上限。

---

## 三、对前三份报告的核验结论（优先级修正）

| 原问题 | 核验结论 |
|---|---|
| SQL 拼接（`aftersale/__init__.py:690-693`） | 属实但当前不可利用，列名无法用普通绑定参数，正确修复是白名单或 SQLAlchemy 列对象。**降级为 P2**，不是最高优先级 |
| `product:delete` 权限不一致 | 已确认：权限在 `seed_permissions.py` 里定义，前端 `canDeleteProduct` 当前**没有实际使用**，后端没有"删除成品"接口（分类/标签/关系删除统一走 `product:edit`）。**结论：未启用的预留/遗留权限，不是后端漏鉴权**。需要产品决策二选一：①不支持删除成品→移除 `product:delete` 和未使用的前端变量；②未来要支持→保留权限但文档标 reserved，设计软删除/归档，不建议物理删除产品主数据 |
| CORS 判断 | 基本正确，但优先级应排在 HTTPS/JWT密钥/分享密钥之后。生产环境不允许 `CORS_ORIGINS=*`，启动时校验 |
| token 存 localStorage | 风险属实，但桌面端明文 HTTP（P0-1）更严重，HTTPS 完成后再评估 httpOnly Cookie（Electron+Web 共用认证时 Cookie 改造要同时考虑 CSRF 和跨端行为） |
| Git 体积膨胀 | 属实，但是工程效率问题，**不该排在依赖锁定/安全/后台任务之前**。建议先停止继续提交新构建产物，CI/发布流程稳定后再决定 LFS 或外部制品，历史重写放最后做，且要提前备份、冻结协作、通知所有 clone 重新同步 |
| 无测试 / 依赖未锁定 | 两项都属实，**依赖锁定应优先于完整测试体系**。最小测试集建议先覆盖：鉴权与权限守卫、财务/发货导入方向和去重、shipping resolve、售后工单创建与自动匹配、成本导入事务、上传大小/类型限制、API 响应结构 |

---

## 四、业务流程和功能归属（比之前的结构筛查更贴业务语义）

当前业务实际可分七个边界：

| 业务域 | 当前内容 | 建议归属 |
|---|---|---|
| 身份与管理 | 登录、用户、角色、权限、登录统计 | account/admin |
| 产品主数据 | 分类、系列、型号、成品、组合件、参数、标签、资料 | product |
| 物流数据接入 | 发货/财务导入、仓库过滤、操作人、订单解析 | logistics 或 shipping/ingestion |
| 发货分析 | 看板、明细、图表、等效计算 | shipping/analytics |
| 售后 | 待处理、工单、原因库、自动匹配、分析 | aftersale |
| 工程研发 | ECR、ECN、PDM转BOM、提醒 | engineering/rd |
| 成本 | BOM快照、物料价格、供应商、估算 | 独立 costing 或 rd/costing |

具体不合理之处：

1. **`EquivalentConfig` 放在 shipping 下不准确**——等效件是产品主数据关系，只是被发货计算消费。模型在 `product`，API 却在 `/api/shipping/equivalents`。建议业务所有权归 product，shipping 只读取。
2. **`LifecycleManager` 是跨域投影**——生命周期写回产品，但依据发货数据计算，不该只是普通 product CRUD。建议定义为明确的应用服务，如 `product/lifecycle-calculation`，记录计算时间、来源、状态。
3. **`dataMgmtViews` 实际是"数据接入与运营配置"**——混合发货导入、财务导入、操作人分类、仓库过滤、等效件、标签分析维度。建议拆成：数据接入（发货/财务导入+任务状态）、物流配置（操作人/仓库过滤）、产品配置（等效件）、分析配置（标签维度）。
4. **`ReturnImport.vue`/`FinanceImport.vue`/`/import/return` 是遗留分叉**——当前 UI 用 `ReturnImport.vue` 展示财务导入，另有几乎重复的 `FinanceImport.vue`；后端保留独立销退导入接口但契约文档没记录。需要 Codex/产品确认业务现状后二选一：①只允许财务表同时导入正负数量→保留 FinanceImport，删除/归档 ReturnImport 命名和未使用的 `/import/return`；②仍需独立销退清单→恢复独立入口并补齐契约与测试。
5. **RD 文件过于集中**——[backend/routes/rd/__init__.py](backend/routes/rd/__init__.py) 约 1700 行，包含 ECR、ECN、提醒、备注、PDM转换、导出。建议按用例拆（不只是为了目录对称）：`routes/rd/ecr.py`、`routes/rd/reminders.py`、`routes/rd/pdm_bom.py`、`services/rd/ecr.py`、`services/rd/pdm_bom.py`。
6. **售后 repository 是"上帝模块"**——[backend/database/repository/aftersale/__init__.py](backend/database/repository/aftersale/__init__.py) 约 3700 行，同时承担查询、图表、字典、匹配、建议、迁移、设置。**目前最值得结构性拆分的后端文件**。建议按能力拆：`aftersale/cases.py`、`aftersale/dictionaries.py`、`aftersale/matching.py`、`aftersale/analytics.py`、`aftersale/suggestions.py`。
7. **HTTP 路径风格不一致**——同属 product 的接口散落在 `/api/product`、`/api/category`、`/api/erp-code-rules`、`/api/resources`。不建议立即破坏性改 URL，可以保留旧接口、新增统一路径或 API v2，再逐步迁移。

---

## 五、其他一致性问题

- 前端路由只有少数页面设置了 `meta.permission`，管理员页和多个业务页没有统一路由权限声明。后端能挡住数据访问，但用户仍能直接进入空白/报错页面。
- HTTP 响应拦截器只把 400 转成正常业务响应；403/404 等会 reject，很多页面按 `res.success` 风格写的，错误处理体验不一致。
- 后端多处把原始异常文本直接返回客户端，可能泄露文件路径/SQL/存储细节；应该记录完整服务端日志，只向客户端返回稳定错误信息+追踪 ID。
- `/health` 只说明 Flask 进程存活，不检查数据库，建议区分 liveness 和 readiness。
- `ALLOW_REGISTER` 默认开启，即使新用户默认无权限，也允许公开创建账号污染登录/账号数据。生产环境建议默认关闭。
- 版本号文档漂移已确认存在，应该让 `package.json` 成为唯一版本来源，文档不要手工复制"当前版本"数字。

---

## 六、推荐整改顺序

**第一阶段：立即风险控制**
1. HTTPS
2. JWT 和 SHARE_SECRET 缺失时生产拒绝启动
3. 生产关闭公开注册
4. 账号禁用/权限撤销能使旧 token 失效
5. 全局上传大小限制和关键文件类型校验
6. 核实生产连接池实际值

**第二阶段：运行可靠性**
1. 后台任务状态移出进程内存
2. 导出结果改为临时文件或 OSS
3. 引入 Alembic，移除启动时自动 DDL
4. 锁定生产依赖
5. 增加关键冒烟测试

**第三阶段：业务整理**
1. 确认财务/销退导入的真实业务规则，清除重复入口
2. 等效件归入产品主数据
3. 拆分售后 repository 和 RD 路由
4. 整理前端 views/components（避免与业务整改同时大范围移动）
5. 最后处理 Git 历史和 URL 命名统一

---

## 结论

当前系统最大的风险**不是目录不够整齐**，而是明文 HTTP、默认密钥、token 不可撤销、进程内后台任务、启动时自动迁移。**Codex 负责第一、二阶段后端整改；Claude 同期处理 HTTPS 客户端地址、前端权限路由、财务/销退入口命名。结构重构放到核心流程有测试之后再做。**

本轮只做了静态审查，没有修改代码或连接生产数据库。
