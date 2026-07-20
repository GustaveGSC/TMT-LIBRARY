# 生产依赖锁定

`requirements.txt` 维护直接依赖及兼容范围；生产安装使用服务器同构环境生成的 `requirements-lock-py311-linux.txt`。

在 Linux/Python 3.11 环境执行：

```bash
cd /opt/tmt-library
python3.11 backend/scripts/capture_requirements_lock.py --output /tmp/requirements-lock-py311-linux.txt
python3.11 -m pip install --dry-run -r /tmp/requirements-lock-py311-linux.txt
```

核对输出后将文件带回仓库的 `backend/requirements-lock-py311-linux.txt`。禁止用 Windows `pip freeze` 覆盖该文件。

新建干净 Python 3.11 虚拟环境验证：

```bash
python3.11 -m venv /tmp/tmt-lock-check
/tmp/tmt-lock-check/bin/python -m pip install -r backend/requirements-lock-py311-linux.txt
/tmp/tmt-lock-check/bin/python -c "import flask, openpyxl, oss2, onnxruntime, tokenizers; print('lock ok')"
```
