from types import SimpleNamespace

import numpy as np

import database.repository.aftersale as aftersale_module
from database.repository.aftersale import AftersaleRepository
from services import semantic_model


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


def _set_alias_data(monkeypatch, aliases):
    monkeypatch.setattr(
        aftersale_module, 'AftersaleShippingIgnoreTerm',
        SimpleNamespace(query=_Query([])),
    )
    monkeypatch.setattr(
        aftersale_module, 'AftersaleShippingAlias',
        SimpleNamespace(query=_Query(aliases)),
    )


def test_shipping_alias_returns_no_match_when_keyword_and_semantic_are_disabled(monkeypatch):
    _set_alias_data(monkeypatch, [
        SimpleNamespace(id=1, name='气弹簧', keywords=['气弹簧']),
    ])

    result = AftersaleRepository().match_shipping_alias(
        [{'name': '完全无关物料'}],
        semantic=False,
    )

    assert result == (None, 0.0)


def test_shipping_alias_uses_semantic_fallback_without_keyword_match(monkeypatch):
    _set_alias_data(monkeypatch, [
        SimpleNamespace(id=1, name='气弹簧', keywords=['关键词一']),
        SimpleNamespace(id=2, name='书包挂钩', keywords=['关键词二']),
    ])
    monkeypatch.setattr(semantic_model, 'get_model', lambda: object())

    def encode(texts):
        if texts == ['气弹簧', '书包挂钩']:
            return np.array([[1.0, 0.0], [0.0, 1.0]])
        assert texts == ['目标物料']
        return np.array([[1.0, 0.0]])

    monkeypatch.setattr(semantic_model, 'encode', encode)

    alias_id, score = AftersaleRepository().match_shipping_alias(
        [{'name': '目标物料'}],
        semantic=True,
    )

    assert alias_id == 1
    assert score == 1.0


def test_shipping_alias_keyword_tie_uses_remark_name_coverage(monkeypatch):
    _set_alias_data(monkeypatch, [
        SimpleNamespace(id=1, name='气弹簧', keywords=['弹簧']),
        SimpleNamespace(id=2, name='气弹簧手柄', keywords=['弹簧']),
    ])

    alias_id, score = AftersaleRepository().match_shipping_alias(
        [{'name': '弹簧'}],
        seller_remark='需要气弹簧手柄',
        semantic=False,
    )

    assert alias_id == 2
    assert score == 1.0


def test_shipping_alias_logs_semantic_failure_and_falls_back_safely(monkeypatch):
    _set_alias_data(monkeypatch, [
        SimpleNamespace(id=1, name='气弹簧', keywords=['未命中']),
    ])
    monkeypatch.setattr(semantic_model, 'get_model', lambda: object())
    monkeypatch.setattr(
        semantic_model, 'encode',
        lambda _texts: (_ for _ in ()).throw(RuntimeError('model failure')),
    )
    contexts = []
    monkeypatch.setattr(
        aftersale_module, 'report_internal_error',
        lambda context: contexts.append(context) or 'error-id',
    )

    result = AftersaleRepository().match_shipping_alias(
        [{'name': '目标物料'}],
        semantic=True,
    )

    assert result == (None, 0.0)
    assert contexts == ['售后发货简称语义匹配失败']
