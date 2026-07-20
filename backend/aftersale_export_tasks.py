"""售后导出任务的磁盘状态与结果文件存储，跨 worker reload 可查询。"""

import json
import os
import tempfile
import time
import uuid
from pathlib import Path


TASK_TTL_SECONDS = 1800


def export_dir() -> Path:
    path = Path(os.getenv(
        'AFTERSALE_EXPORT_DIR',
        str(Path(tempfile.gettempdir()) / 'tmt-library-aftersale-exports'),
    )).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _meta_path(task_id: str) -> Path:
    return export_dir() / f'{_safe_task_id(task_id)}.json'


def result_path(task_id: str) -> Path:
    return export_dir() / f'{_safe_task_id(task_id)}.xlsx'


def _safe_task_id(task_id: str) -> str:
    parsed = uuid.UUID(str(task_id))
    if str(parsed) != str(task_id).lower():
        raise ValueError('invalid task id')
    return str(parsed)


def _write(task_id: str, data: dict) -> None:
    target = _meta_path(task_id)
    temporary = target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, target)


def create(task_id: str) -> None:
    cleanup()
    now = time.time()
    _write(task_id, {
        'task_id': task_id,
        'status': 'pending',
        'message': '',
        'created_at': now,
        'updated_at': now,
        'pid': None,
    })


def update(task_id: str, status: str, message: str = '') -> None:
    data = get(task_id, recover_interrupted=False) or {
        'task_id': task_id,
        'created_at': time.time(),
    }
    data.update({
        'status': status,
        'message': message,
        'updated_at': time.time(),
        'pid': os.getpid() if status == 'running' else None,
    })
    _write(task_id, data)


def _process_alive(pid) -> bool:
    if not pid:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except (OSError, ValueError, TypeError):
        return False


def get(task_id: str, *, recover_interrupted: bool = True):
    try:
        path = _meta_path(task_id)
    except (ValueError, TypeError):
        return None
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    if recover_interrupted and data.get('status') == 'running' and not _process_alive(data.get('pid')):
        data.update({
            'status': 'interrupted',
            'message': '导出因服务重启或 reload 中断，请重新发起',
            'updated_at': time.time(),
            'pid': None,
        })
        _write(task_id, data)
    return data


def delete(task_id: str) -> None:
    try:
        paths = (_meta_path(task_id), result_path(task_id))
    except (ValueError, TypeError):
        return
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def cleanup() -> None:
    cutoff = time.time() - TASK_TTL_SECONDS
    for meta_path in export_dir().glob('*.json'):
        try:
            if meta_path.stat().st_mtime < cutoff:
                delete(meta_path.stem)
        except OSError:
            continue
