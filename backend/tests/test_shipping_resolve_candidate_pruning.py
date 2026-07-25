import os
import random
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from services.shipping import (
    _build_finished_candidate_index,
    _build_sorted_finished_rules,
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


def test_finished_rules_use_component_count_then_code_and_sorted_tuple():
    finished = [
        SimpleNamespace(
            code='Z-FINISHED',
            model=SimpleNamespace(name='Z'),
            packaged_list=[
                SimpleNamespace(code='PART-B'),
                SimpleNamespace(code='PART-A'),
            ],
        ),
        SimpleNamespace(
            code='A-FINISHED',
            model=SimpleNamespace(name='A'),
            packaged_list=[
                SimpleNamespace(code='PART-C'),
                SimpleNamespace(code='PART-A'),
            ],
        ),
        SimpleNamespace(
            code='SINGLE',
            model=SimpleNamespace(name='S'),
            packaged_list=[SimpleNamespace(code='PART-Z')],
        ),
    ]

    rules = _build_sorted_finished_rules(finished)

    assert [rule[0] for rule in rules] == [
        'A-FINISHED', 'Z-FINISHED', 'SINGLE',
    ]
    assert rules[1][2] == ('PART-A', 'PART-B')
    assert isinstance(rules[1][2], tuple)


def test_overlapping_equivalent_requirements_have_stable_consumption_order():
    # PART-A/PART-B can both consume SHARED. The sorted requirement tuple makes
    # this otherwise ambiguous allocation reproducible across hash seeds.
    finished = [
        ('FINISHED', '成品', ('PART-A', 'PART-B')),
    ]
    equivalents = {
        'PART-A': {'PART-A', 'SHARED', 'SUPPLY-A'},
        'PART-B': {'PART-B', 'SHARED', 'SUPPLY-B'},
    }
    products = {'SHARED': 1, 'SUPPLY-A': 2, 'SUPPLY-B': 1}
    candidate_index = _build_finished_candidate_index(finished, equivalents)

    first = _greedy_match_finished(
        products, finished, equivalents, candidate_index,
    )
    second = _greedy_match_finished(
        products, finished, equivalents, candidate_index,
    )

    assert first == second
    assert first == ({'FINISHED': 2}, {'SUPPLY-A': 1})


def test_resolver_output_is_identical_across_python_hash_seeds():
    backend_dir = Path(__file__).resolve().parents[1]
    script = r"""
import hashlib
from types import SimpleNamespace
from services.shipping import (
    _build_finished_candidate_index,
    _build_sorted_finished_rules,
    _greedy_match_finished,
)

finished = [
    SimpleNamespace(
        code=code,
        model=SimpleNamespace(name=code),
        packaged_list=[
            SimpleNamespace(code=part)
            for part in set(parts)
        ],
    )
    for code, parts in [
        ('Z-FINISHED', ('PART-B', 'PART-A')),
        ('A-FINISHED', ('PART-C', 'PART-A')),
    ]
]
rules = _build_sorted_finished_rules(finished)
equivalents = {
    'PART-A': set(('PART-A', 'SHARED', 'SUPPLY-A')),
    'PART-B': set(('PART-B', 'SHARED', 'SUPPLY-B')),
}
index = _build_finished_candidate_index(rules, equivalents)
result = _greedy_match_finished(
    {'SHARED': 1, 'SUPPLY-A': 2, 'SUPPLY-B': 1, 'PART-C': 1},
    rules,
    equivalents,
    index,
)
print(hashlib.sha256(repr((rules, result)).encode()).hexdigest())
"""
    hashes = []
    for seed in ('1', '20260725', 'random'):
        env = os.environ.copy()
        env['PYTHONHASHSEED'] = seed
        env['PYTHONPATH'] = str(backend_dir)
        completed = subprocess.run(
            [sys.executable, '-c', script],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        hashes.append(completed.stdout.strip())

    assert len(set(hashes)) == 1
