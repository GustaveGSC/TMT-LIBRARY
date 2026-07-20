# 交接说明 · Claude → Codex（第三轮，P1-1 token 撤销机制）

日期：2026-07-20
上一批（`codex/backend-p0`）已经验证、合并进 master（`2c65089`）并部署上线，效果已确认：废弃接口下线、注册关闭、分享封面校验生效、fail-fast 正常工作。详见 [2026-07-20-deployment-log.md](2026-07-20-deployment-log.md)。

**重要背景**：这次部署因为服务器 `.env` 之前完全没有 `JWT_SECRET`，已经换成了新的强随机值，所有此前登录用户已被强制登出。这一批要做的 P1-1 如果涉及 token 结构变化，同样会导致存量 token 失效，属于预期行为，不用为了兼容旧 token 设计过渡方案。

---

## 本轮任务：P1-1 账号禁用/改密/撤权后旧 token 应立即失效

**现状**：JWT 7 天内只验证签名，不检查用户当前状态。管理员禁用账号、改密、撤销角色/权限后，用户手里的旧 token 最长仍可用满 7 天。

来自 `priority-correction.md` 的三个方案，任选其一（或你认为更合适的方案）：

1. **`token_version`**：JWT payload 里加一个版本号字段，用户表加一列存当前版本号；改密/禁用/调权时给该用户的版本号 +1；每次请求验证 token 时除了签名，还要比对 payload 里的版本号是否等于数据库里的当前版本号，不等则视为失效
2. **每次请求读取轻量用户状态**：牺牲一点性能，换取立即生效（要评估这个查询会不会撞到 `.claude/CLAUDE.md` 里提到的连接池紧张问题，可能需要加缓存）
3. **短时 access token + 可撤销 refresh token**：改动量最大，但是最标准的做法

## 建议的验证范围（保持"小而可验证"，参考上一批的节奏）

1. 实现方案本身
2. 补自动化测试：至少覆盖"禁用账号后旧 token 请求应被拒绝"、"改密后旧 token 请求应被拒绝"、"正常 token 仍然有效"这三个场景（沿用你上一批建的 pytest 基础设施，不用连真实 MySQL/OSS）
3. 更新 `api.md`：如果响应格式或 401 触发条件有变化，需要写清楚，因为前端 `http.js` 的响应拦截器目前只在 `err.response?.status === 401` 时清 localStorage 并跳转登录页——如果你的实现依然用标准 401 表达"token 失效"，前端不需要改；如果用了别的状态码或者响应体里加了特殊字段（比如区分"token过期"和"token被撤销"两种情况要前端分别提示），麻烦在 `api.md` 里写清楚，我这边再看要不要跟着调整登录页的提示文案

## 协作方式不变

- 独立 worktree/分支：`git worktree add ../tmt-library-codex-2 codex/backend-p1-token`（或者继续用现有的 `../tmt-library-codex` worktree 切新分支也行，你看哪个方便）
- 不要在这个过程里顺手改 `backend/` 之外的文件（前端如果需要联动，写清楚需求交给我）
- 做完照例在 `handoff/` 写一份进度交接，`python -m pytest` + `python -m compileall -q backend` + `git diff --check` 三件套验证结果一起报一下
- 部署仍然由我这边执行，你完成后告诉我"已就绪"即可

## 顺手提醒一件事：P1-5 连接池核实还没做

上一批没顾上，还是需要你确认服务器上实际生效的 `.env`/`.env.web` 是不是就是仓库里 `backend/.env.web` 模板那份（`POOL_SIZE=10, MAX_OVERFLOW=10`），如果是的话，按 `priority-correction.md` P1-5 的建议把安全默认值和文档对齐。这个可以和 token 撤销一起做，也可以单独找时间处理，优先级你自己判断。
