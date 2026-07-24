import random

from services.shipping import (
    _build_finished_candidate_index,
    _get_finished_candidates,
    _greedy_match_finished,
)


SORTED_FINISHED = [
    ('COMPLEX', '复杂成品', frozenset({'A', 'B', 'C'})),
    ('PAIR-AB', '组合AB', frozenset({'A', 'B'})),
    ('PAIR-BC', '组合BC', frozenset({'B', 'C'})),
    ('SINGLE-A', '单品A', frozenset({'A'})),
    ('SINGLE-X', '单品X', frozenset({'X'})),
]
EQUIV_MAP = {
    'A': {'A', 'A2'},
    'A2': {'A', 'A2'},
    'B': {'B', 'B2'},
    'B2': {'B', 'B2'},
}


def _compare(products):
    legacy = _greedy_match_finished(
        products, SORTED_FINISHED, EQUIV_MAP, candidate_index=None,
    )
    candidate_index = _build_finished_candidate_index(
        SORTED_FINISHED, EQUIV_MAP,
    )
    optimized = _greedy_match_finished(
        products, SORTED_FINISHED, EQUIV_MAP, candidate_index=candidate_index,
    )
    assert optimized == legacy


def test_candidate_pruning_preserves_exact_equivalent_greedy_and_leftovers():
    cases = [
        {},
        {'A': 1},
        {'A2': 2},
        {'A': 1, 'A2': 5},
        {'A': 3, 'B': 3, 'C': 2},
        {'A2': 3, 'B2': 2, 'C': 2},
        {'A': 1, 'B': 2, 'C': 1, 'X': 4, 'UNKNOWN': 7},
    ]
    for products in cases:
        _compare(products)


def test_candidate_pruning_matches_legacy_for_deterministic_quantity_matrix():
    randomizer = random.Random(20260724)
    codes = ['A', 'A2', 'B', 'B2', 'C', 'X', 'UNKNOWN']
    for _ in range(500):
        products = {
            code: quantity
            for code in codes
            if (quantity := randomizer.randint(0, 5)) > 0
        }
        _compare(products)


def test_sparse_order_visits_only_anchor_compatible_candidates():
    finished = [
        (
            f'FINISHED-{index}',
            f'成品{index}',
            frozenset({f'PART-{index}', f'COMMON-{index % 7}'}),
        )
        for index in range(404)
    ]
    candidate_index = _build_finished_candidate_index(finished, {})
    candidates = _get_finished_candidates(
        {'PART-17': 1, 'COMMON-3': 1},
        finished,
        candidate_index,
    )

    assert candidates == [finished[17]]
    assert len(candidates) < len(finished) / 100
