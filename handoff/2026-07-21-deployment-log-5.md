# 部署记录 · 恢复暂停任务：售后导出可靠性 + 依赖锁定

日期：2026-07-21（跨天，任务从 2026-07-20 暂停到今天恢复）

## 背景

2026-07-20 因用户临时插入更紧急的业务（世界地图功能迭代）暂停了 Codex 的售后导出+依赖锁定审查/部署，记录在 [2026-07-20-paused-state.md](2026-07-20-paused-state.md)。今天按暂停时列的顺序恢复。

## 一、代码审查（`cda6f73`/`512ef65`/`ffc43aa`）

审查结论：质量扎实，采纳。

- **`aftersale_export_tasks.py`**：文件化任务状态（不再是内存字典），原子写（写 `.tmp` 再 `os.replace`），UUID 校验防路径穿越，进程存活检测（`os.kill(pid, 0)`）自动识别 reload/崩溃导致的中断任务并标记 `interrupted`，TTL 清理。设计思路和之前 `shipping_task` 一致但更轻量（用文件不是数据库表，适合这种一次性文件生成场景）。
- **`export_cases_to_file`**：从"一次性加载 5 万行 ORM + 全部塞进 Workbook"改成分页读取（`EXPORT_PAGE_SIZE` 环境变量可调）+ openpyxl `write_only=True` 流式写盘，reasons 按页批量加载而不是一次性加载全部 5 万行的，避免了之前报告里提到的内存风险。
- **下载接口**：改用 Flask `send_file` 直接流式发送磁盘文件（不再是内存 bytes 塞进 Response），下载完 `call_on_close` 自动清理文件。
- **向后兼容**：旧前端轮询状态接口只认识 done/error，新的 `interrupted` 状态被映射成 `error` 返回，不会让旧前端卡死。
- **依赖锁定工具**：`capture_requirements_lock.py` 内省当前 Python 环境已安装包的依赖闭包（不装不升级），强制要求在 Linux/Python 3.11 环境运行（防止在 Windows 生成无效锁文件），设计合理。
- 本地复跑 `python -m pytest`：67 passed。

## 二、合并 + 部署

`git merge codex/backend-p1-export-lock`（fast-forward），部署 7 个文件（`aftersale_export_tasks.py`、`routes/aftersale/__init__.py`、`services/aftersale/__init__.py`、`database/repository/aftersale/__init__.py`、`requirements.txt`、`requirements-lock.README.md`、`scripts/capture_requirements_lock.py`），md5 核对一致。

`systemctl reload gunicorn`——这次严格按之前教训的方式验证：reload 后没有立即下结论，等了几秒复查 `systemctl status` + `journalctl`，确认 master 进程没变化（运行了 12 小时没重启过）、worker 正常 booting、无崩溃退出记录。`/health` 200，登录接口正常响应。

## 三、生成生产依赖锁定快照

运行脚本时发现一个真实缺口：`requirements.txt` 声明了 `xlrd`/`xlwt`，但生产环境实际都没装：

- **`xlrd`**：全仓库搜索确认被 `backend/routes/rd/__init__.py` 用于读取旧版 `.xls` 文件——**这是真实缺口**，如果生产触发那条代码路径此前会直接 `ImportError`。已按 `requirements.txt` 声明的版本范围（`xlrd>=1.2.0,<2.0`）在生产环境补装。
- **`xlwt`**：全仓库搜索没有任何 import，是**死依赖声明**。为了让锁定脚本今天能跑通，先在生产环境装上了（纯 Python 小包，风险很低），但建议 Codex 从 `requirements.txt` 里删掉这一行——不应该保留一个从未被用到的声明依赖。

生成的 `requirements-lock-py311-linux.txt`（62 个包，含精确版本号）已带回仓库并提交。

## 四、部署后验证

| 检查项 | 结果 |
|---|---|
| `/health` | 200 |
| 登录接口（错误密码） | 400，正常响应 |
| gunicorn 进程 | reload 后持续运行无崩溃 |
| 依赖锁定脚本 | 二次运行成功，62 包写入锁文件 |

## 五、遗留给 Codex 的一条

`backend/requirements.txt` 里的 `xlwt>=1.3.0` 建议删除（死依赖，全仓库无 import）。这个不着急，下次碰这个文件时顺手处理即可，不需要专门起一个任务。

## 六、Web 端

这次没有前端改动，`dist-web` 无需重新部署。
