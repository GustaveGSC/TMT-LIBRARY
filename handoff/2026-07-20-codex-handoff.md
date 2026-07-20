# 交接说明 · Claude → Codex

日期：2026-07-20
写这份文档的原因：前后端分离协作正式开始，Claude 负责前端（`src/`、`electron/`），Codex 负责后端（`backend/`）。这里是当时的状态快照 + 协作规则交接。

**长期规则已经迁移到根目录 [AGENTS.md](../AGENTS.md)，本文件只是这次交接当下的状态记录，之后规则有调整以 AGENTS.md 为准，不要以本文件为准。**

---

## 1. 分工边界（详见 AGENTS.md）

| 范围 | 写权限 |
|---|---|
| `src/`（Vue3 前端）、`electron/`（Electron 壳层） | Claude |
| `backend/`（Flask + SQLAlchemy） | Codex |
| `.claude/modules/api.md`、`database.md` | 由后端变更方（Codex）发起 |
| `.claude/modules/frontend-*.md` | Claude 维护为主 |

边界是**写权限边界**，不是认知边界——为了设计接口、排查问题、联调，双方可以互相只读对方代码，只是不能直接写。

**接口契约是核心交接点**：谁改了路由/字段/返回结构，必须先更新 `.claude/modules/api.md`。目前 `api.md` 还只是路由索引，缺少字段类型/必填/错误码等结构化信息，后续会逐步补充模板，新增接口时按补充后的模板写。

---

## 2. 刚完成的清理（背景，写这份文档时的状态）

工作区之前有一批前后端混杂、未分组的改动，已经拆分成两次 commit：

- `48b73d7` feat(backend)：BOM成本导入 (`rd/cost.py` 相关)、产品标签 (`product/tag.py`)、发货仓储 (`shipping/__init__.py`) 改动，同步了 `api.md` / `database.md`
- `55096be` feat(frontend)：标签维度配置 (`TagDimensionConfig.vue`)、等效件配置 (`EquivalentConfig.vue`)、BOM成本页/发货看板调整，web 构建产物

这两个 commit 当时未 push（`origin/master` 落后 2 个提交），是否已推送以 `git log origin/master..master` 实际结果为准，不要假设本文件写的时间点状态仍然成立。

以后请保持这个习惯：**改完一个功能就按前后端边界分别 commit**，不要把两边改动混在一次提交里。

---

## 3. 后端性能规范（务必遵守，服务器资源极紧张）

服务器：双核云主机，1.675GB RAM，MySQL 占 ~400MB，gunicorn 占 ~190MB，SQLAlchemy QueuePool(size=2)。**每次后端开发必须评估 DB 查询数量**，否则容易把主机拖垮。

- **N+1 查询**：访问 `lazy=True` 关系属性（如 `r.category_obj.name`）会对每个对象触发一次 SELECT。用 `joinedload` / `selectinload`，或先 `with_entities` 批量拿 id 再一次性查关联表。
- **`get_cross_filter_options`**：每次调用 6 条 JOIN 查询，前端筛选变化时触发，不要在里面再加维度。
- **`get_chart_data`**：每次切 Tab / 下钻都触发一次，必须保持 O(维度数) 条查询，不能出现循环内 lazy load。
- **`auto_match`**：每次调用查全量 `AftersaleReason`，不要在循环或批量流程里频繁调用。
- **`shipping_order_finished` 低选择性索引**：`source` 列仅 2 个值（shipping/finance），MySQL 优化器不会自动选复合索引。所有对该表的查询必须加 `with_hint(sof, 'USE INDEX (...)', dialect_name='mysql')`：有日期范围用 `ix_sof_source_date`，否则用 `ix_sof_source_finished_code`。
- **`get_chart_options` 缓存**：结果已做模块级内存缓存（5 分钟 TTL，key=source+日期范围）。导入/resolve-all 完成后必须调 `_invalidate_chart_options_cache()` 清缓存，否则新数据不生效。
- **trade_type 过滤禁止走 JOIN**：`needs_trade_filter` 不得触发 JOIN 产品表。FTP 系列判断通过 `_get_ftp_finished_codes()` 缓存集合 + `finished_code IN (...)` 实现，避免每次查询都 JOIN ProductModel/ProductSeries。

## 4. 技术栈 & 关键路径（后端相关）

- Python Flask + SQLAlchemy + PyMySQL，端口 8765
- MySQL host: 47.99.100.138，库名 `tmt_db`
- 存储：阿里云 OSS（tmt-oss，华东1杭州），`OSS_BASE_URL=https://tmt-oss.oss-cn-hangzhou.aliyuncs.com/tmt-library`
  - **陷阱**：`OSS_BASE_URL` 已含 `/tmt-library`，拼 key 时不能再加前缀，否则 404
- `backend/app.py`：Flask 工厂，QueuePool(size=2, pre_ping, recycle=1800) + connect/read/write 超时
- `backend/result.py`：`Result.ok/fail` → `{ success, message, data }`，所有接口统一走这个格式
- `backend/create_reason_keyword_rules.py`：售后「原因词典」相关表初始化
- `backend/create_ecr_reminders.py`：研发工具「ECR提醒」相关表初始化
- 服务器 Python 版本：**pip 默认指向 3.9，装包必须用 `pip3.11`**

## 5. 部署权限（重要变更）

**部署统一由 Claude Code 执行，Codex 不要自己 ssh 到服务器部署。** Codex 完成后端改动、更新完 `api.md`/`database.md` 后，告知"后端已就绪可部署"即可，交给 Claude 那边跑：

```bash
# SSH 配置（~/.ssh/config）：Host tmt → 47.99.100.138，User root，密钥 id_ed25519
# 后端部署（按需上传修改的文件，然后 reload）
scp backend/路径/xxx.py tmt:/opt/tmt-library/backend/路径/xxx.py
ssh tmt "systemctl reload gunicorn"
```

- **必须用 `reload`（SIGHUP 优雅替换 worker），绝对不要用 `fuser -k` + restart（SIGKILL 冷启动）**——服务器内存紧张，冷启动需要申请 190MB 但仅剩约 120MB 空余，会导致 SSH/VNC 卡死数小时。
- **绝对不要给 gunicorn 加 `--preload`**——会导致 `reload` 不重载代码，改了代码 reload 也不生效，排查起来很隐蔽。

## 6. 权限设计（后端要遵守的约定）

权限码：`product:view/edit/delete`、`shipping:view/edit/export`、`aftersale:view/edit/export`、`rd:view/edit`

- admin 角色后端直接放行；前端判断用 `userInfo.roles?.includes('admin')`
- `username==='admin'` 或 `'author'`：不可删除/禁用（后端要拦截）
- 只读 POST 接口（比如查询类但用了 POST 方法的）需要加入 `make_blueprint_guard` 的 `view_post_paths` 白名单，否则只有 view 权限的用户会被拦成 403 —— 这是个容易漏掉的点

## 7. HTTP 响应规范（前后端共同约定，后端要严格遵守）

```javascript
// 后端统一返回 { success, message, data }
const res = await http.get('/api/...')
if (res.success) { /* use res.data */ } else { errorMsg = res.message }
```

## 8. 文档维护规范

架构/功能/接口/数据库变更时必须同步更新对应模块文档（`.claude/modules/*.md`）。`.claude/CLAUDE.md` 本身只保留全项目共识，不要把接口字段、表结构全文写进那份文件——写在对应 module 里。

- `database.md` — 数据库表结构
- `api.md` — 后端接口列表

## 9. Git 操作纪律

- 优先创建新 commit，不要 amend 已存在的 commit（除非明确要求）
- 不要跳过 hooks（`--no-verify`）、不要绕过签名
- 涉及 `backend/` 目录外的改动（比如为了联调改了 `api.md` 之外的前端文件）要先跟 Claude 这边确认，避免两边同时改同一文件互相覆盖
- **如果同一时间段内 Codex 和 Claude 都在活跃工作，必须用独立的 git worktree 或分支**（不是"建议"），避免在同一工作目录里看到对方未完成的改动导致误提交/覆盖。接力式的"一个做完再做另一个"不受此限制。

## 10. AGENTS.md 是长期规则来源

Codex 请把根目录 `AGENTS.md` 当作项目级持久规则读取（而不只是这份 dated handoff）。以后规则调整会改 `AGENTS.md`，`handoff/` 目录只累积阶段性状态记录，不代表当前规则。

---

有问题或者接口设计需要前端配合确认的，写在 `api.md` 里对应接口条目下面加一段「待确认」说明即可，Claude 这边会看到。
