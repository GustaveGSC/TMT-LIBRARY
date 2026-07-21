# Codex 依赖锁定审计交接

日期：2026-07-21

## 完成内容

- 核对 `backend/requirements.txt` 与生产环境生成的 `requirements-lock-py311-linux.txt`。
- 修正两处声明范围与生产锁定版本冲突：
  - `gunicorn==26.0.0` 原先不满足 `<24.0.0`，上限调整为 `<27.0.0`。
  - `packaging==26.2` 原先不满足 `<26.0`，上限调整为 `<27.0`。
- 从直接依赖和锁定快照中移除全仓库无 import 的 `xlwt`；保留确有 `.xls` 读取调用的 `xlrd==1.2.0`。
- 增加自动化测试，逐项校验直接依赖均有精确锁定，且锁定版本满足声明范围；同时防止 `xlwt` 被误加回来。

## 验证

- `python -m pytest backend/tests -q`：通过（68 tests）。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。

## 部署说明

- 本批只修改依赖声明、锁定快照和测试，不涉及运行时代码，无需 reload。
- 生产环境当前已安装的 `xlwt` 可以暂时保留；它不再出现在后续按锁文件创建的新环境中。若要卸载，应由 Claude Code 在维护窗口单独执行并记录，不是本批部署前置条件。

## 建议的后续顺序

1. P1：统一清理直接返回给客户端的原始异常文本，避免内部实现或数据库信息泄露，并补接口错误响应测试。
2. P1：将 `/health` 保持为轻量 liveness，另增数据库 readiness 检查，避免健康检查语义混淆。
3. P2：修复售后 `q_distinct` 的 SQL 标识符拼接隐患。
4. P2：由产品侧先决定 `product:delete` 是待实现、软删除还是前端遗留权限码。
5. P2：token 从 localStorage 迁移到 httpOnly cookie 需要前后端联合设计，单独排期。
6. P3 结构调整和 Git 历史瘦身最后处理；Git 历史重写必须单独维护窗口并由用户明确批准。
