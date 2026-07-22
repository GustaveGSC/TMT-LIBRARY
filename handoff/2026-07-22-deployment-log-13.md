# 部署记录 · 语义模型服务迁移（周期二 P3 第十五轮第二批）

日期：2026-07-22

## 背景

`backend/model_manager.py` 名字容易被误认为"产品型号/系列管理工具"，实际是售后语义匹配用的 bge-small-zh-v1.5 ONNX 模型下载/懒加载/推理服务，被 `app.py` 启动线程和售后 repository 多条正式业务路径调用。Codex 评估后确认不是脚本，迁到 `backend/services/semantic_model.py`。交接文档：`handoff/2026-07-22-codex-handoff-15.md`（第十五轮总纲）→ `handoff/2026-07-22-codex-semantic-model-location.md`。

## 审查结论

`codex/semantic-model-location`（`29a038b`）审查通过：

- 文件内容基本原样搬移（只改了日志前缀 `[model_manager]`→`[semantic_model]`），模块级单例状态（`_model`/`_state`/两把锁）保持同一个 canonical module，不会因为改名产生两套进程内状态。
- `app.py` 启动线程 + 售后 repository 里 4 处延迟 `import model_manager` 全部改成 `from services import semantic_model`，逐条比对确认调用点（`get_model()`/`encode()`）语义不变。
- 新测试直接验证：`services.semantic_model` 重复 import 返回同一模块对象（防止未来又冒出第二套状态）；`model_manager.py` 文件确实不存在；`app.py`/售后 repository 源码里不再含 `import model_manager` 字符串。这几条测试的检验方式很直接，不依赖 mock，可信度高。
- 本地复跑 `pytest`：112 passed。

## 部署

严格按 Codex 指定顺序执行（先传新文件、再传引用它的文件、最后才删旧文件，避免窗口期内 worker 找不到模块）：

1. 确认无导入/resolve 任务在跑。
2. 服务器建 `backend/services/` 目录（如果还没有），scp 上传 `semantic_model.py`，md5 核对一致。
3. scp 上传 `app.py`、`database/repository/aftersale/__init__.py`，md5 核对一致。
4. `systemctl reload gunicorn`；8秒后复查（master pid 2258 未变，新 worker 干净启动，无崩溃记录）。
5. `/health`、`/ready` 均 200。
6. 确认新 worker 正常后，删除服务器残留的 `backend/model_manager.py`，未发现对应 `.pyc` 残留。

## 部署后验证

直接在服务器上 `from services import semantic_model as sm` 并调用 `sm.is_model_installed()`/`sm.get_download_state()`：模块能从新路径正确导入，服务器上模型已安装（`installed: True`），下载状态结构正常。未触发实际推理测试（不需要为了验证 import 路径就跑一次真实语义匹配请求）。

## 影响说明

- 无接口变更、无数据库变更、无前端改动。
- 日志前缀从这次起变为 `[semantic_model]`，如果之后要 grep 日志排查语义匹配问题，用新前缀搜。

## 下一批

Codex 建议下一项只读审查 `routes/config`（先确认接口职责、是否只是小型统一配置入口、现有测试覆盖），不与 RD 大路由拆分或售后 repository 拆分放在同一批。
