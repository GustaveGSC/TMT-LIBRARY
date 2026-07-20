# 交接说明 · Claude → Codex（第二轮，前端 P0/P3 项已完成）

日期：2026-07-20
背景文档（按顺序阅读）：[2026-07-20-priority-correction.md](2026-07-20-priority-correction.md)（优先级权威来源）→ [2026-07-20-claude-progress.md](2026-07-20-claude-progress.md)（前端处理细节）→ 本文件（汇总 + 待办清单）。

这一轮我（Claude）按 `priority-correction.md` 里"Claude 同期处理 HTTPS 客户端地址、前端权限路由、财务/销退入口命名"的分工，把分配到自己的前端项都处理完了。后端第一、二阶段完全没动（按 [AGENTS.md](../AGENTS.md) 边界，不该我碰），现在交给你处理或核验。

---

## 一、我这边已完成的事（供你了解上下文，不需要你验证前端部分）

1. **P0-1 HTTPS 客户端地址**：`src/api/http.js`、`electron/main/window.ts`、`electron/main/index.ts`、`src/index.html`(CSP)、`vite.config.web.ts` 五处硬编码的 `http://47.99.100.138` 全部改成 `https://tmt-library.cn`。核实发现桌面端在当前生产环境下应该是完全打不开的（nginx 只在 443 vhost 代理，plain HTTP 80 端口对这个 domain/IP 一律 404），不只是安全问题，是功能性故障。
2. **桌面端下载入口隐藏**：`page-index.vue` 里"下载桌面版"按钮改 `v-if="false"`，路由和页面代码保留没删。
3. **前端路由权限补全**：`/product`、`/shipping`、`/data-mgmt`、`/aftersale` 补了 `meta.permission`；`/admin/*` 三个页面加了 `adminOnly`，`/admin/login-logs` 加了 `authorOnly`；路由守卫相应扩展。之前这些页面完全没有路由层拦截，未授权用户能直接进空白页。
4. **财务导入命名整理**：确认在用的是 `ReturnImport.vue`（实际展示财务数据，调 `/import/finance`），已改名为 `FinanceImport.vue`；同名但未使用的旧 `FinanceImport.vue`（死代码）已删除。

这些改动都还**没有部署，没有 push**，只是本地 commit 前的工作区状态（还没 commit，等你这边也处理完一起交代）。

## 二、需要你处理或核验的事——按优先级

### 需要你直接处理（P0，最高优先级，backend/ 范围）

来自 `priority-correction.md` 第一阶段：

1. **JWT 密钥缺失时仍允许服务启动**（`backend/app.py:21`、`backend/auth.py:8`）——生产环境检测到默认值 `tmt-dev-secret-change-in-production` 应直接拒绝启动
2. **分享签名默认密钥**（`backend/routes/product/resource.py:14`，默认值 `tmt-share-key-2024`）——同样要求生产环境缺失即拒绝启动；另外 **og-image 路径完全公开、没校验分享 token**，只按可枚举资源 ID 读 OSS 图片，需要补校验
3. **生产关闭公开注册**——确认 `ALLOW_REGISTER` 生产环境默认值，建议默认关闭
4. **账号禁用/改密/撤权后旧 token 应失效**——目前 JWT 7 天内签名有效就能用，不检查用户当前状态，需要实现 `token_version` 或轻量状态复查机制（三选一方案见 `priority-correction.md` P1-1）

### 需要你核验（我发现的疑点，需要确认是否属实/是否已过期）

1. **连接池实际配置比文档写的更夸张**：`backend/.env.web` 里 `POOL_SIZE=10` `MAX_OVERFLOW=10`（注释算法算下来 4 worker 峰值到 80 连接），但 `.claude/CLAUDE.md` 文档写的是 `QueuePool(size=2)`。麻烦确认服务器上实际生效的是不是这份 `.env.web`，还是有另一份手工改过的配置，然后把安全默认值和文档对齐（`priority-correction.md` P1-5）
2. **后端 `/import/return` 接口现在确认前端完全不调用**（见上面第四条），按业务决策"只保留财务表导入"，需要确认后端是否还有其他调用方（定时任务/脚本），没有的话可以清理，并同步更新 `api.md`
3. **`product:delete` 权限码**：已确认是前端定义了但后端没有对应删除接口的预留/遗留权限。需要产品决策：①不支持删除成品→清理前端未使用的 `canDeleteProduct` 和这个权限码；②未来要支持→权限保留但标注 reserved，设计软删除方案（不建议物理删除产品主数据）

### 第二阶段（运行可靠性，P1，backend/ 范围，你可以按自己节奏排期）

见 `priority-correction.md` 完整清单，摘要：
- 内存后台任务与多 worker/reload 不兼容（发货导入/售后导出/生命周期更新用 daemon thread + 模块级字典/Queue，reload 会丢任务，导出还把最多 5万行 Excel 全放内存）
- 启动时自动建表/ALTER TABLE，失败被静默吞掉，建议引入 Alembic
- 上传/导入普遍缺全局大小限制（不只是产品封面和资料库，还有 Excel 导入、ECR/ECN/PDM、BOM成本文件）
- `requirements.txt` 全部 `>=` 不锁版本

### 第三阶段（结构整理，优先级最低，等前两阶段完成/有测试兜底后再做）

见 `2026-07-20-structure-review.md`：`routes/config` 分层缺失、`rd/cost` 命名不对称、根目录脚本堆积、`rd`/`product` 边界模糊、售后 repository 是"上帝模块"（3700行，建议拆成 cases/dictionaries/matching/analytics/suggestions）、RD 路由文件过大（1700行，建议按 ecr/reminders/pdm_bom 拆分）。

---

## 提交记录（已收口）

前端这批改动已经拆成 4 个 commit 提交到本地 master（未 push）：

- `1ec0ae7` fix(frontend): 使用 HTTPS 客户端地址并补齐路由权限
- `be37719` refactor(frontend): 统一财务导入组件命名
- `ddfcbf9` build(web): 更新 dist-web 构建产物
- `0a579ab` docs: 添加项目审查与前端处理进度记录

说明：前两个 commit 的边界和最初设想略有出入——财务组件重命名的主体内容意外被打包进了第一个 commit（`git add` 时机问题），第二个 commit 实际只补了一处残留的 CSS class 名和两个漏提交的文件（`page-index.vue`、`page-data-mgmt.vue`）。内容都是对的，只是两个 commit 之间的切分不如预想干净，供你核对时知情。

**没有部署，没有打桌面端安装包，没有 push。** Web 构建产物已经在 `ddfcbf9` 里更新，但只是本地 commit，实际部署（rsync 到服务器）还没做，等后端 P0（尤其 JWT/分享密钥、连接池）一起核实后再统一部署发布。

你现在可以在**独立的 worktree/分支**里开始后端工作，不要在当前工作目录改，避免和我这边正在进行的后续工作冲突：

```bash
git worktree add ../tmt-library-codex codex/backend-p0
```

第一批建议做：
1. 删除 `/api/shipping/import/return` 路由和 `shipping_service.import_return()`（已核实前端和其他调用方都不再使用，保留被其他流程依赖的 repository 公共方法）
2. 更新 `api.md`，加一句"独立销退导入已废弃，统一走 `/import/finance`"
3. 补最小测试覆盖 `/import/finance` 正负数量逻辑
4. 然后进入 JWT/分享密钥生产 fail-fast、关闭公开注册、上传大小限制

## 三、协作提醒

- 部署仍然统一由我这边执行（按 `AGENTS.md`），你这边改完后端代码后告诉我"已就绪"就行，不用自己 ssh
- 你处理完 P0/P1 之后，麻烦也照这个格式给我写一份交接/进度说明放到 `handoff/`，方便我了解后端那边做了什么、我这边前端有没有需要联动的改动（比如 token 机制改了，前端登录/401 处理逻辑可能要跟着调整）
- 所有报告和这次的改动目前都还没 commit，等你这边也处理到一个阶段，我们一起确认后统一提交
