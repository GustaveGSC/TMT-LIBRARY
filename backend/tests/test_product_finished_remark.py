from types import SimpleNamespace

from database.repository.product.finished import FinishedRepository
from services.product.finished import FinishedService


def test_finished_save_accepts_remark_and_returns_it(monkeypatch):
    existing = SimpleNamespace(code='FIN-1')
    captured = {}
    saved = SimpleNamespace(to_dict=lambda: {'code': 'FIN-1', 'remark': '自由备注'})
    monkeypatch.setattr(FinishedRepository, 'get_finished_by_code', lambda _code: existing)
    monkeypatch.setattr(
        FinishedRepository, 'update_finished',
        lambda obj, **kwargs: captured.update(obj=obj, **kwargs) or saved,
    )

    result = FinishedService().save_finished('FIN-1', remark='自由备注', ignored='discarded')

    assert result.success
    assert captured == {'obj': existing, 'remark': '自由备注'}
    assert result.data['remark'] == '自由备注'
