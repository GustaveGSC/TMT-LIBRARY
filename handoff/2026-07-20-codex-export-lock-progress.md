# Codex · 售后导出可靠性与依赖锁定

日期：2026-07-20  
分支：`codex/backend-p1-export-lock`

## 售后导出：已完成

提交：`cda6f73 fix(backend): 售后导出改为分页磁盘任务`

- 删除模块级 `_export_tasks` 大字节字典。
- 导出任务元数据以原子 JSON 文件保存，xlsx 直接写临时目录；默认目录为系统临时目录下 `tmt-library-aftersale-exports`，可用 `AFTERSALE_EXPORT_DIR` 覆盖。
- worker reload 后状态仍可查询；若生成进程已消失，running 自动恢复为 interrupted，并对旧前端映射成它已支持的 error。
- 下载使用 `send_file` 流式返回，不把完整 xlsx 重新读入 Python bytes；响应关闭后清理任务文件。
- 任务/文件 30 分钟 TTL，在新建任务时清理过期文件。
- Excel 改用 openpyxl write-only 模式，不缓存历史单元格。
- 工单按页查询，默认 `EXPORT_PAGE_SIZE=1000`；每页批量加载 reasons，写完释放 ORM identity map。
- 只在第一页执行总数 count，后续页跳过重复 count；仍保留 `EXPORT_MAX_ROWS=50000` 截断提示。
- 没有数据库结构变化，不需要 Alembic migration，也没有新增 `create_app()` 顶层调用。

## 依赖锁定：代码侧准备完成，等待生产版本快照

提交：`512ef65 build(backend): 补齐依赖声明和生产锁定工具`

- `requirements.txt` 补入此前代码/部署实际依赖但未声明的 `openpyxl`、`oss2`、`gunicorn`、`packaging`。
- 新增 `backend/scripts/capture_requirements_lock.py`：从直接依赖出发遍历当前环境已安装的传递依赖，生成全 `==` 的闭包锁文件。
- 脚本默认拒绝非 Linux/Python 3.11，防止 Windows 环境污染生产锁。
- 目标文件名：`backend/requirements-lock-py311-linux.txt`。

### Claude 需要在服务器执行的只读步骤

先只上传生成脚本和更新后的 `requirements.txt` 到隔离目录，不替换运行目录：

```bash
mkdir -p /opt/lock_verify/backend/scripts
# 将 requirements.txt 和 capture_requirements_lock.py 放到对应隔离路径
cd /opt/lock_verify
python3.11 backend/scripts/capture_requirements_lock.py \
  --output /tmp/requirements-lock-py311-linux.txt
python3.11 -m pip install --dry-run -r /tmp/requirements-lock-py311-linux.txt
```

把 `/tmp/requirements-lock-py311-linux.txt` 原样带回并加入仓库。不要在生产环境执行实际 install/upgrade；`--dry-run` 只用于解析验证。Codex 收到文件后会检查：

1. 所有直接依赖均存在且为精确 `==`。
2. `openpyxl/oss2/gunicorn/onnxruntime/tokenizers/alembic` 版本与生产当前安装一致。
3. 没有 Windows 专属包或本地路径引用。
4. 再补自动化 lock 完整性测试后，依赖锁定任务才算正式完成。

## 当前验证

```text
python -m pytest backend/tests -q
67 passed
python -m compileall -q backend
通过
git diff --check
通过
```

## 部署建议

- 依赖锁文件尚未回填前，不执行任何 pip 安装或升级。
- 售后导出代码可独立审查部署；reload 前确认没有导出任务正在运行。
- reload 后不能只看一次 is-active：继续检查 `systemctl status`、journal、`/health` 和登录接口。
- 实测发起一次小范围导出，轮询 done、下载成功，并确认临时目录文件在响应关闭后清理。

未部署、未 push。工作区提交前干净。
