import pytest

import services.shipping as shipping_module


def test_stale_resolve_rejects_unbenchmarked_large_scope(monkeypatch):
    monkeypatch.setenv('MAX_STALE_RESOLVE_ORDERS', '2')
    monkeypatch.setattr(
        shipping_module.shipping_repository,
        'get_stale_order_nos',
        lambda: [
            ('ORDER-1', 'shipping'),
            ('ORDER-2', 'shipping'),
            ('ORDER-3', 'finance'),
        ],
    )
    monkeypatch.setattr(
        shipping_module.shipping_service,
        '_run_staged_resolve',
        lambda *_args, **_kwargs: pytest.fail(
            'oversized stale scope must fail before staging'
        ),
    )

    with pytest.raises(
        shipping_module.StaleResolveScopeTooLarge,
        match='超过当前安全上限 2 条',
    ):
        shipping_module.shipping_service.resolve_stale('task-stale-limit')


def test_stale_resolve_allows_scope_at_configured_limit(monkeypatch):
    pairs = [('ORDER-1', 'shipping'), ('ORDER-2', 'finance')]
    monkeypatch.setenv('MAX_STALE_RESOLVE_ORDERS', '2')
    monkeypatch.setattr(
        shipping_module.shipping_repository,
        'get_stale_order_nos',
        lambda: pairs,
    )
    monkeypatch.setattr(
        shipping_module.shipping_service,
        '_run_staged_resolve',
        lambda task_id, actual_pairs, **_kwargs: {
            'task_id': task_id,
            'pairs': actual_pairs,
        },
    )

    assert shipping_module.shipping_service.resolve_stale(
        'task-stale-safe',
    ) == {
        'task_id': 'task-stale-safe',
        'pairs': pairs,
    }
