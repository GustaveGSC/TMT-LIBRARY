"""
售后工单确认日志工具
每次工单确认后将结构化日志追加到 logs/aftersale/YYYY-MM-DD.jsonl
"""
import json
import os
import sys
from datetime import datetime

# 打包后 sys.executable 所在目录；开发时取本文件目录
if getattr(sys, 'frozen', False):
    _BASE = os.path.dirname(sys.executable)
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))

_LOG_DIR = os.path.join(_BASE, 'logs', 'aftersale')


def write_confirm_log(data: dict):
    """将 data 序列化为一行 JSON 追加到当日日志文件。"""
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        date_str = datetime.now().strftime('%Y-%m-%d')
        path = os.path.join(_LOG_DIR, f'{date_str}.jsonl')
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2, default=str) + '\n\n')
    except Exception:
        pass   # 日志写失败不影响主流程
