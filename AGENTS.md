# AGENTS.md — 两平米软件库 · 共享规则

本文件是 Codex 与 Claude Code 共同遵守的项目级规则入口。`.claude/CLAUDE.md` 是 Claude Code 专属的详细上下文（技术栈、模块索引、设计规范），Codex 应主动读取它和 `.claude/modules/*.md` 获取实现细节——本文件只放两个 agent 都要遵守的边界和纪律，不重复维护内容，避免两份规则分叉。

## 1. 目录所有权（写权限边界，不是认知边界）

| 目录 | 写权限 | 说明 |
|---|---|---|
| `backend/` | Codex | Claude 可只读查看，用于联调、排查、确认接口实现，但不直接改 |
| `src/`、`electron/` | Claude Code | Codex 可只读查看，用于设计接口时理解前端调用方式，但不直接改 |
| `.claude/modules/api.md`、`database.md` | 由后端变更方（Codex）发起修改 | Claude 确认前端兼容性后再依赖 |
| `.claude/modules/frontend-*.md` | Claude Code | Codex 按需只读 |
| `AGENTS.md`、`.claude/CLAUDE.md`（共识/规则部分） | 双方共同维护 | 改动前先跟对方确认，避免单方面改规则 |

**默认允许对方只读检查代码（设计接口、故障定位、安全审查、联调），禁止的是跨界写入。**

## 2. 接口契约

`api.md` 是前后端交接的核心文档。新增/修改接口时，条目至少要包含：
- 请求方法 + 路径 + 权限要求
- 请求参数：字段、类型、是否必填、默认值
- 成功响应结构（对齐 `{ success, message, data }`）
- 关键错误情况（如 404/403 触发条件）

如果字段语义、分页方式、时间格式等有歧义，直接在对应接口条目下用 `<!-- 待确认 -->` 标注，另一方看到后回应。

## 3. 部署权限

**所有部署（前端 rsync、后端 scp+reload）统一由 Claude Code 执行。** Codex 完成后端改动后只需：
1. 确保代码可运行（本地/语法层面自查）
2. 更新 `api.md` / `database.md`
3. 告知 Claude 这边"后端已就绪，可部署"，不要自己 ssh 到服务器操作

部署纪律（不可违反）：
- 后端用 `systemctl reload gunicorn`，**禁止** `fuser -k` + restart（冷启动内存压力会导致服务器卡死数小时）
- gunicorn **禁止加 `--preload`**（会导致 reload 不重载代码）
- 前端用 `rsync` 传完整 `dist-web/` 目录，不能只传部分文件（hash 会变，白屏风险）

## 4. 并行开发

如果 Codex 和 Claude Code 会在同一时间段内都活跃（而不是接力式的"一个做完另一个再做"），**必须**使用独立的 git worktree 或分支，不要在同一个工作目录里同时改动，避免看到对方未完成的改动而误提交/覆盖。

```bash
git worktree add ../tmt-library-codex codex/backend-xxx
git worktree add ../tmt-library-claude claude/frontend-xxx
```

集成到 `master` 前，双方各自 commit 到自己的分支，由发起功能需求的一方（或用户）做最终合并确认。

## 5. Git 纪律

- 优先新建 commit，不 amend 已存在的 commit
- 不跳过 hooks（`--no-verify`），不绕过签名
- 前后端改动分开提交，不要混在一个 commit 里
- 未经用户明确要求不 push 到远程

## 6. 性能与技术约束

服务器资源紧张（双核 1.675GB RAM，QueuePool size=2），后端每次改动必须评估 DB 查询数量。完整陷阱清单见 `.claude/CLAUDE.md` 的「性能与负载规范」一节（N+1、`get_cross_filter_options`/`get_chart_data` 查询数、`shipping_order_finished` 索引 hint、`get_chart_options` 缓存失效、trade_type 过滤禁止 JOIN）——改动 `backend/` 前必须读一遍。

## 7. 状态记录

阶段性交接、分工调整记录在 `handoff/` 目录，按 `YYYY-MM-DD-<对象>-handoff.md` 命名。`handoff/` 里的文件只记录"某个时间点的状态"，不是长期规则来源——长期规则改动应该落到本文件。
