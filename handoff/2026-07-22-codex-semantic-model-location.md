# 交接说明 · Codex → Claude（周期二 P3：语义模型服务定位）

日期：2026-07-22

## 评估结论

`backend/model_manager.py` 不是产品型号/系列管理工具，也不是一次性脚本。它负责售后语义匹配使用的 bge-small-zh-v1.5 ONNX 模型下载、进程内状态、懒加载和推理，被 `app.py` 启动线程及售后 repository 的多条正式业务路径调用。

为明确职责且避免放进 `services/aftersale/` 后触发 package 初始化循环，本批将它迁到独立的 `backend/services/semantic_model.py`。

## 完成内容

- 提交：`29a038b refactor(backend): relocate semantic model service`
- 分支/worktree：`codex/semantic-model-location` / `E:/Project/tmt-library/.worktrees/codex-semantic-model`
- `backend/model_manager.py` 重命名为 `backend/services/semantic_model.py`。
- `app.py` 启动初始化和售后 repository 的 4 组延迟 import 全部改为 `from services import semantic_model`。
- 下载状态、锁、模型对象仍由唯一 canonical module 持有，没有兼容 shim，因此不会因两个模块名产生两套进程内状态。
- 模型目录 `~/.tmt-library/models/bge-small-zh-v1.5/`、OSS 路径、后台线程、懒加载及推理逻辑均未改变。
- 日志前缀从 `[model_manager]` 改为 `[semantic_model]`。
- 修正 `.claude/claude.md` 中“模型/系列管理工具”的错误描述。
- 新增测试防止根目录模块或裸 `import model_manager` 回归，并验证重复 import 返回同一模块对象。

## 验证

- `python -m pytest backend/tests -q`：112 passed。
- `python -m compileall -q backend`：通过。
- `git diff --check`：通过。
- 全仓搜索确认运行时代码不再引用 `model_manager`；业务行为和 HTTP 接口无变化。

## 部署顺序

本批需要 reload，但无数据库迁移、无前端构建：

1. 先上传新文件 `/opt/tmt-library/backend/services/semantic_model.py`。
2. 再上传更新后的 `backend/app.py` 与 `backend/database/repository/aftersale/__init__.py`。
3. 执行 `systemctl reload gunicorn`，按既有纪律延迟复查 status、journal、`/health`、`/ready`。
4. 确认新 worker 正常后，删除服务器旧文件 `/opt/tmt-library/backend/model_manager.py`；同时清理对应旧 `__pycache__/model_manager*.pyc`（若存在）。
5. 日志中若模型未安装/加载，应看到新前缀 `[semantic_model]`；模型不可用仍应自动降级，不影响售后主流程。

不要先删除旧文件再上传新文件，避免部署窗口内新 worker 找不到任何语义模块。

## 下一批建议

下一项优先只读审查 `routes/config`：先确认其接口职责、是否只是一个小型统一配置入口，以及现有测试是否足以支撑拆分；不要把它与 RD 大路由或售后 repository 大拆分放在同一个提交。

本批未部署、未 push，未修改 `src/` 或 Electron。
