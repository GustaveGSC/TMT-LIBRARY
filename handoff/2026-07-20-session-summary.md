# 交接总结 · 2026-07-20 全天工作汇总

日期：2026-07-20
这份是当天所有工作的汇总索引，方便任何一方（包括未来的 Claude/Codex 会话）快速了解"现在项目在哪"，不需要翻遍所有 `handoff/` 文件重建上下文。

---

## 一、协作规则（已建立，长期有效）

- **[AGENTS.md](../AGENTS.md)**：Codex 与 Claude 共同遵守的持久规则——目录写权限边界（写权限归属，只读检查双方都允许）、接口契约要求、部署权限（统一由 Claude 执行）、并行开发必须用独立 worktree、"完成阶段性工作后必须写交接报告"的规则
- **`.claude/claude.md`**（注意实际文件名是小写 `claude.md`，Windows 大小写不敏感容易踩坑）：Claude 专属详细上下文，本次已更新连接池基线描述、部署命令（tar+scp 替代本机缺失的 rsync）、reload 后验证注意事项、版本号不再手工维护

## 二、已完成并部署验证的工作（按时间顺序）

| 项目 | 内容 | 记录 |
|---|---|---|
| P0-1 | 桌面端/前端改用 HTTPS（`tmt-library.cn`），发现并修复了桌面端生产环境完全打不开的问题 | claude-progress.md |
| P0-2/P0-3 | JWT/分享密钥生产环境缺省值 fail-fast，og-image 分享 token 校验 | deployment-log.md |
| — | 注册功能默认关闭（后来用户手动改回开放，是业务决策非回归） | registration-reopened.md |
| P1-1 | 账号禁用/改密/撤权后旧 token 立即失效（`token_version` 机制） | deployment-log-2.md |
| P1-3 | Alembic baseline 建立，三轮核验（39→12→0 差异），移除 `app.py` 隐式 DDL，改为启动时 revision 门禁 | deployment-log-3.md（含三份 alembic-check-result 核验记录） |
| P1-2 | 发货任务持久化 + 导入原子性（新表 `shipping_task`）+ 前端 SSE 断线回查 | deployment-log-3.md、incident-startup-crash.md（含一次约1分45秒的部署事故记录） |
| P1-4 | 上传大小限制 + 文件真实性校验 + zip bomb 防护，前端预签名接口适配 | deployment-log-4.md |
| 文档 | 连接池基线、版本号维护方式两处文档过期问题已修复 | 本次会话直接提交 |
| 前端结构 | 财务/销退导入组件命名统一（`ReturnImport.vue`→`FinanceImport.vue`）、前端路由权限补全、桌面端下载入口隐藏 | claude-progress.md |

**当前 master 分支工作区干净，所有改动已提交，前后端均已部署验证一致。**

## 三、当前分派给 Codex、正在处理中的任务

**[2026-07-20-codex-handoff-7.md](2026-07-20-codex-handoff-7.md)**：
1. `backend/requirements.txt` 依赖锁定（全是 `>=`，无 lock 文件）
2. 售后导出的内存风险（最多 5 万行 Excel 存内存字典，和已解决的发货任务持久化是同一类问题，售后那边还没处理）

## 四、还没排期的已知问题（按之前梳理的优先级）

### P1（剩余）
- 后端多处把原始异常文本直接返回客户端，可能泄露内部细节
- `/health` 只是 liveness，不区分 readiness（不检查数据库连接）

### P2（次要/待决策）
- `product:delete` 权限码：确认是预留/遗留权限，**需要你做业务决策**——彻底删除还是保留标 reserved 并设计软删除方案
- `aftersale/__init__.py` 的 `q_distinct` 函数有 SQL 字符串拼接隐患（目前不可利用，是潜在隐患）
- 前端 token 存 localStorage 的 XSS 风险：之前说"等 HTTPS 上线后重新评估"，**HTTPS 现在已经上线，可以重新评估要不要改成 httpOnly Cookie**（需要前后端配合，涉及鉴权机制改动，不是小事）

### P3（结构性重构，一直被有意后置，建议等 P1/P2 稳定后再排期）
- 后端：`routes/config` 分层缺失、`rd/cost` 命名不对称、根目录脚本堆积未归类、`model_manager.py`/`utils.py`/`auth.py` 定位模糊、`rd`/`product` 边界重叠、**售后 repository 是"上帝模块"（3700行）**、**RD 路由文件过大（1700行）**、HTTP 路径风格不统一
- 前端：`dataMgmtViews` 整体拆分（财务导入命名已理清，但目录级拆分未做）、组件目录分类标准不统一、Pinia store 覆盖不全、`EquivalentConfig`/`LifecycleManager` 业务域归属问题

### 独立风险项（一直排在最后，风险最高）
- **Git 仓库体积膨胀**（1.6GB+，历史提交了大量二进制构建产物）：清理需要改写历史，涉及备份、冻结协作、通知所有 clone 重新同步，只有你本人可以决定何时启动

## 五、这次会话踩过的坑（供以后避免重演）

1. Windows 文件系统大小写不敏感导致 `git add .claude/CLAUDE.md`（大写）没有正确识别对已跟踪的小写 `.claude/claude.md` 的修改，一度导致改动本地未提交却不自知
2. 本机 Git Bash 没有 `rsync`，前端部署流程改用 tar+scp
3. `reload gunicorn` 后不能只看一次 `systemctl is-active` 就下结论——真实发生过 worker 启动瞬间崩溃、进入自动重启循环，但第一次查询恰好落在重启间隙显示 `active`
4. 部署顺序遗漏过一次：后端要求新参数（`file_size`）但前端还没跟着部署，会导致接口断裂——以后前后端契约变化的部署要检查双端是否同步
5. 验证"写型"接口（比如注册功能是否生效）时，直接调用测试产生了真实的生产数据，用完要记得清理

---

以上是全天工作的汇总索引。逐项细节请查对应的 `handoff/*.md` 文件，本文件不重复贴细节内容。
