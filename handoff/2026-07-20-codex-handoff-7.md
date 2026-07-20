# 交接说明 · Claude → Codex（第七轮，依赖锁定 + 售后导出内存风险）

日期：2026-07-20
P1-2/P1-3/P1-4 都已部署验证，详见前几份 deployment-log。这轮按优先级继续处理 P1 阶段剩下的两项：依赖锁定、售后导出的内存风险（和刚做完的 `shipping_task` 持久化是同一条线，但售后那边还没处理）。

---

## 任务一：依赖锁定

`backend/requirements.txt` 全部用 `>=`：

```
flask>=3.0.0
flask-sqlalchemy>=3.1.0
flask-cors>=4.0.0
pymysql>=1.1.0
python-dotenv>=1.0.0
bcrypt>=4.1.0
PyJWT>=2.8.0
onnxruntime>=1.18.0
tokenizers>=0.19.0
xlwt>=1.3.0
xlrd>=1.2.0,<2.0
pillow>=9.0.0
alembic>=1.18.5,<2.0.0
```

生产环境重新 `pip install` 时可能因为依赖版本漂移导致行为和本地不一致，尤其 `onnxruntime`/`tokenizers` 这类经常有 breaking change 的包。

**建议**：生成一份锁定版本的文件（`pip freeze` 或者用 `pip-compile`），生产部署用锁定版本安装，开发环境可以继续用范围版本。注意服务器当前 Python 是 3.11（`pip3.11`），锁定文件要基于服务器实际环境生成或至少交叉验证一遍版本兼容性，不要直接从本机 Windows 环境 `pip freeze`。

## 任务二：售后导出的内存风险

`priority-correction.md` P1-4 提过："售后导出把最多 50,000 行 Excel 全部保存在 worker 内存字典里"，这次 `shipping_task` 持久化方案只覆盖了发货相关任务（`import_shipping`/`import_finance`/`resolve_all`/`resolve_stale`），售后导出用的是另一套机制，没有跟着改。

麻烦先定位一下售后导出具体在哪个文件/函数（大概率在 `routes/aftersale/__init__.py` 或 `services/aftersale/__init__.py` 附近，用类似的内存字典存导出任务结果），确认现状后决定方案：

- 如果售后导出的任务量/触发频率比发货导入小很多，可以做成一个更轻量的版本（比如直接把生成的 Excel 写临时文件或 OSS，不放内存字典，任务状态可以复用或参考 `shipping_task` 的设计思路，不需要完全另起一套）
- 如果售后模块已经有自己的任务表/机制，也可以直接在现有基础上改，不用非得照抄 `shipping_task`

## 建议的验证范围

1. 依赖锁定：确认锁定文件在服务器环境能正常 `pip install`（可以在只读核实阶段让我配合验证，不用你自己连生产）
2. 售后导出：补测试覆盖"导出任务被打断后不会占用过多内存/能查到最终状态"这类场景，参考 `test_shipping_task_reliability.py` 的思路
3. 照例 `python -m pytest` + `python -m compileall -q backend` + `git diff --check`
4. **再次提醒**：这次如果售后导出改动涉及 `create_app()` 里新增顶层调用，务必检查 `app.app_context()` 包裹（上次那个漏包裹的 bug 就是在这类改动里出的）

## 协作方式不变

独立 worktree/分支，部署我这边执行，完成后照例写交接文档到 `handoff/`。这两个任务如果你觉得依赖锁定更简单可以先做，售后导出需要先调研现状再定方案，顺序你自己安排。
