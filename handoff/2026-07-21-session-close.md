# 收尾记录 · P1/P2 已形成稳定发布节点，暂停继续叠加改造

日期：2026-07-21

## 当前状态

master 工作区干净，所有已完成工作均已合并、部署、验证。截至本次收尾，P0 全部、P1 剩余项、P2 售后 SQL 拼接隐患、`product:delete` 产品决策均已处理完毕并上线，详见 `handoff/` 目录下 2026-07-20 至 2026-07-21 的各份 deployment-log 和 codex-handoff 文档（索引见 [2026-07-20-session-summary.md](2026-07-20-session-summary.md)，但注意该文件是 07-20 当天的快照，之后又完成了好几轮，最新状态以本文件 + 07-21 的几份 deployment-log 为准）。

判断：当前是一个完整且稳定的发布节点，不适合立刻叠加高风险改造。

## 后续三个独立维护周期（按顺序，不要并行）

### 周期一：Cookie/token 改造（安全收益最大，风险也最高）

涉及登录、刷新、跨域、Electron/Web 双端兼容、CSRF，**必须先做联合设计（Claude+Codex）再实施**，不能直接动手写代码。

**下一轮的起点是：只读方案评审，不直接实施。** 评审至少要覆盖：
- 现状：token 存 `localStorage`，`src/api/http.js` 拦截器读取并附加到请求头；桌面端和 Web 端共用这套机制
- 候选方案：httpOnly Cookie + CSRF token、还是维持 localStorage 但加固（比如缩短有效期+更激进的 `token_version` 检查频率）、或者短时 access token + 可撤销 refresh token（三方案在 `priority-correction.md` P1-1 里提过，当时选了 `token_version` 这个折中方案，现在要评估要不要进一步往 httpOnly Cookie 方向走）
- Electron 桌面端能不能用 httpOnly Cookie（桌面端请求走的是 Electron 内嵌浏览器环境，需要确认 Cookie 机制在这个场景下是否可靠）
- CSRF 防护方案（如果改用 Cookie，必须配套）
- 迁移路径：新旧机制过渡期怎么处理，会不会影响所有已登录用户

### 周期二：P3 结构重构

- 后端：`routes/config` 分层缺失、`rd/cost` 命名不对称、根目录脚本堆积、`model_manager.py`/`utils.py`/`auth.py` 定位模糊、`rd`/`product` 边界重叠、售后 repository 是"上帝模块"（3700行）、RD 路由文件过大（1700行）、HTTP 路径风格不统一
- 前端：`dataMgmtViews` 整体拆分、组件目录分类标准不统一、Pinia store 覆盖不全、`EquivalentConfig`/`LifecycleManager` 业务域归属问题
- 原则：**按模块小步迁移，每批保持接口不变，补回归测试**，不要一次性大重构

### 周期三：Git 历史清理（最后做，风险最高）

- 仓库体积膨胀（1.6GB+，历史里有 `backend.exe` 多版本、`ffmpeg-core.wasm`、`dist-web` 重复构建产物）
- 会重写历史、影响所有分支和 worktree（包括 `E:/Project/tmt-library-codex` 这个 Codex worktree）
- **必须专门停工窗口 + 明确批准后才能执行**：提前备份、冻结双方协作、通知重新 clone

## 给下一次会话/下一位接手者的提醒

- 恢复工作时先看这份文件和最新的几份 `deployment-log-*.md`，不要只看 `session-summary.md`（那是旧快照）
- `AGENTS.md` 的协作规则依然有效：目录写权限边界、部署统一由 Claude 执行、并行开发用独立 worktree、完成阶段性工作必须写交接报告
- Codex 侧的 worktree `E:/Project/tmt-library-codex` 当前应该是干净的（最后一次工作是 `codex/backend-p1-error-readiness-sql` 分支，已经 merge 进 master），下次给它开新任务前确认一下状态
