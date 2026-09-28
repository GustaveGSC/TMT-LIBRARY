"""登录后在后台线程预热发货看板的 chart-options 缓存。

为什么放在后端线程而不是前端预热请求（2026-09-28）：
- 服务器内存紧张，MySQL 数据页空闲一段时间后被换到交换区；登录后第一次查 chart-options
  要从磁盘换回，约 11 秒（热缓存时约 1 秒）。
- gunicorn 只有 1 个 sync worker，前端发预热请求会占住唯一的 worker 11 秒，登录后的 /me、
  主页和用户点开的下一个页面全被堵在后面（「登录要按两下」就是这么来的）。
- 后台线程等数据库时会释放 GIL，worker 照常处理其他请求；结果写进模块级 5 分钟缓存，
  所有用户共享，用户打开发货看板时直接命中。
"""
import threading
from datetime import date, timedelta

from flask import current_app

from database.base import db
from database.repository.shipping import ShippingRepository, _chart_options_cache, _CHART_OPTIONS_TTL

_lock = threading.Lock()
_running = False


def default_dashboard_range(today=None):
    """与发货看板默认日期范围一致：JS 的 setMonth(month - 1)（日期溢出时顺延，如 3/31 → 3/3）到今天。"""
    today = today or date.today()
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    start = date(year, month, 1) + timedelta(days=today.day - 1)
    return start.isoformat(), today.isoformat()


def _is_warm(key):
    import time
    cached = _chart_options_cache.get(key)
    return bool(cached) and time.time() - cached['_at'] < _CHART_OPTIONS_TTL


def prewarm_chart_options_async():
    """已有有效缓存或已有预热在跑时直接返回；否则起一个后台线程算一次默认范围的 chart-options。"""
    global _running
    date_start, date_end = default_dashboard_range()
    if _is_warm(('shipping', date_start, date_end)):
        return False
    with _lock:
        if _running:
            return False
        _running = True
    app = current_app._get_current_object()

    def run():
        global _running
        try:
            with app.app_context():
                try:
                    ShippingRepository.get_chart_options(date_start, date_end, 'shipping')
                except Exception as exc:   # 预热失败无所谓，用户打开看板时会正常查询
                    print(f'[prewarm] chart-options 预热失败: {exc}', flush=True)
                finally:
                    db.session.remove()
        finally:
            with _lock:
                _running = False

    threading.Thread(target=run, daemon=True, name='prewarm-chart-options').start()
    return True
