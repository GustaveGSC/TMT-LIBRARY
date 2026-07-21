# 暂停归档 · 2026-07-20（更紧急业务插入，本任务链暂停）

日期：2026-07-20
用户有更紧急的业务需要处理，本任务链在此暂停，未审查、未合并、未部署。恢复时从这里接续。

## 暂停时的状态

**Codex 分支**（`E:/Project/tmt-library-codex`，具体分支名待确认，未 push）已完成 3 个提交：

- `cda6f73` 售后导出改为分页、write-only、磁盘任务
- `512ef65` 补齐直接依赖并增加生产锁定工具
- `ffc43aa` 交接与服务器核验说明

内容摘要（Codex 自述，**我这边还没有做代码审查**）：
- 售后导出不再把 5 万行 ORM 数据/Workbook/最终 xlsx bytes 同时留内存，改分页查询+批量加载 reasons，xlsx 直接写临时文件流式下载，状态跨 reload 保留，中断会向旧前端返回 error
- 无新增表、无 `create_app()` 顶层调用（按之前教训主动排查过）
- 依赖锁定：直接依赖已补齐，生产快照文件 `requirements-lock-py311-linux.txt` **还没生成**——不能在 Windows 生成，需要我按交接文档在服务器隔离目录跑只读脚本生成后带回仓库，过程不能执行实际安装/升级
- 自动化验证：67 passed，编译/diff check 通过，worktree 干净，未部署未 push

详细交接文档：`E:/Project/tmt-library-codex/handoff/2026-07-20-codex-export-lock-progress.md`（Codex 侧 worktree 里，还没同步进主仓库）

## 恢复时要做的事（按顺序）

1. **代码审查**：审查 `cda6f73`/`512ef65`/`ffc43aa` 三个提交的实际 diff（不要只信任 Codex 的自述），本地跑一遍测试确认 67 passed
2. **生成生产依赖快照**：按 `2026-07-20-codex-export-lock-progress.md` 的说明，在服务器隔离目录（参考之前 `/opt/alembic_verify/` 的隔离核实做法，避免碰生产运行目录）跑只读脚本生成 `requirements-lock-py311-linux.txt`，全程不能实际安装/升级依赖，带回仓库
3. **合并部署**：售后导出改动没有新表、没有 `create_app()` 顶层调用，风险相对低，但仍要走完整流程——merge → 部署 → reload → 用之前教训过的方式验证（不能只看一次 `is-active`）
4. **写交接文档**：完成后照例记录到 `handoff/`

## 未处理的其他事项（暂停前的待办列表，见 session-summary.md）

`handoff/2026-07-20-session-summary.md` 里列的 P1 剩余项、P2、P3、Git 体积清理都还没排期，恢复工作后继续按之前的优先级顺序处理。
