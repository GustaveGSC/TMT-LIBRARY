"""登录后 chart-options 后台预热：默认日期范围与前端一致、缓存已热或正在预热时不重复起线程。"""
import time
from datetime import date

from flask import Flask

import services.shipping.prewarm as prewarm
from database.repository.shipping import _chart_options_cache


def test_default_range_matches_js_set_month():
    assert prewarm.default_dashboard_range(date(2026, 9, 28)) == ('2026-08-28', '2026-09-28')
    assert prewarm.default_dashboard_range(date(2026, 1, 15)) == ('2025-12-15', '2026-01-15')
    # JS: new Date(2026,2,31).setMonth(1) → 2026-03-03（2 月没有 31 日，顺延）
    assert prewarm.default_dashboard_range(date(2026, 3, 31)) == ('2026-03-03', '2026-03-31')


def test_prewarm_skips_when_warm_and_runs_once(monkeypatch):
    calls = []
    monkeypatch.setattr(prewarm.ShippingRepository, 'get_chart_options',
                        staticmethod(lambda ds, de, src: (calls.append((ds, de, src)), time.sleep(0.2))))
    monkeypatch.setattr(prewarm.db, 'session', type('S', (), {'remove': staticmethod(lambda: None)})())
    app = Flask(__name__)
    _chart_options_cache.clear()
    with app.app_context():
        assert prewarm.prewarm_chart_options_async() is True
        assert prewarm.prewarm_chart_options_async() is False       # 正在预热，不重复起线程
        for _ in range(50):
            if not prewarm._running:
                break
            time.sleep(0.05)
        ds, de = prewarm.default_dashboard_range()
        assert calls == [(ds, de, 'shipping')]
        _chart_options_cache[('shipping', ds, de)] = {'_at': time.time()}
        assert prewarm.prewarm_chart_options_async() is False       # 缓存已热
    _chart_options_cache.clear()
