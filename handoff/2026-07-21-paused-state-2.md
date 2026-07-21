# 暂停归档 · 2026-07-21（Cookie/CSRF 改造暂停，新任务插队）

日期：2026-07-21
用户有新任务插队，本任务链在此暂停，未部署。恢复时从这里接续。

## 暂停时的状态

- **联合设计已定稿**：[2026-07-21-token-cookie-joint-design.md](2026-07-21-token-cookie-joint-design.md)（已并入 Codex 后端评审意见）
- **前端已实施完成，已提交，未部署**：详见 [2026-07-21-frontend-cookie-impl-status.md](2026-07-21-frontend-cookie-impl-status.md)，master 分支最新提交 `a0554fa`（build web）/ `3654f4c`（前端源码）
- **后端：Codex 那边状态未知**——上次交接是"设计定稿可以开始实施"，还没收到 Codex 完成后端实施的消息，不确定进度到哪一步了

## 恢复时要做的事（按顺序）

1. 确认 Codex 后端 Cookie/CSRF 实施进度（如果已完成，先走标准审查流程：读 diff、本地跑 pytest，不能只信自述）
2. 核对 [2026-07-21-frontend-cookie-impl-status.md](2026-07-21-frontend-cookie-impl-status.md) 里列的 3 个接口细节（登出接口路径、登录响应体不含 token、CSRF Cookie 的 Path 范围）
3. 按直接切换方案部署：后端先部署验证 `/health`+`/ready`+登录接口正常，立刻紧跟着部署前端，压缩不兼容窗口
4. 部署后验证：完整登录流程（Set-Cookie 头属性核对）、写操作过 CSRF 校验、登出正确清 Cookie
5. 写交接文档

## 未处理的其他事项

`2026-07-20-session-summary.md`/`2026-07-21-session-close.md` 里列的周期二（P3 结构重构）、周期三（Git 历史清理）还没排期，按之前定的顺序排在 Cookie/token 改造完成之后。
