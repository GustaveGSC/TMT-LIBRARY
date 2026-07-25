"""Read-only production audit for shipping resolver ambiguity.

This script creates its own SQLAlchemy engine and only issues SELECT statements.
It intentionally hashes order identifiers and metadata values in its JSON output.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text


BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIR / ".env"
if not ENV_FILE.exists():
    # Allows executing an unchanged copy from /tmp while cwd is backend/.
    ENV_FILE = Path.cwd() / ".env"
load_dotenv(ENV_FILE, override=True)


def _database_url() -> URL | str:
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    return URL.create(
        drivername="mysql+pymysql",
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.getenv("DB_NAME"),
    )


def _hash(value) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]


def _load_product_rules(connection):
    rows = connection.execute(text("""
        SELECT pf.id AS finished_id, pf.code AS finished_code,
               pp.code AS packaged_code
        FROM product_finished pf
        JOIN product_finished_packaged pfp ON pfp.finished_id = pf.id
        JOIN product_packaged pp ON pp.id = pfp.packaged_id
        ORDER BY pf.id, pp.code
    """)).mappings()
    finished = defaultdict(set)
    for row in rows:
        finished[row["finished_code"]].add(row["packaged_code"])

    equivalent_rows = connection.execute(text("""
        SELECT code_a, code_b
        FROM packaged_equivalent
        ORDER BY code_a, code_b
    """)).mappings()
    equivalents = defaultdict(set)
    equivalent_pairs = []
    for row in equivalent_rows:
        code_a, code_b = row["code_a"], row["code_b"]
        equivalent_pairs.append((code_a, code_b))
        equivalents[code_a].update((code_a, code_b))
        equivalents[code_b].update((code_a, code_b))
    return dict(finished), dict(equivalents), equivalent_pairs


def _product_ambiguity(finished, equivalents, equivalent_pairs):
    size_counts = Counter(len(codes) for codes in finished.values())
    same_size_candidate_count = sum(
        count for count in size_counts.values() if count > 1
    )
    same_size_pair_count = sum(
        count * (count - 1) // 2 for count in size_counts.values() if count > 1
    )

    exact_sets = defaultdict(list)
    for finished_code, required_codes in finished.items():
        exact_sets[tuple(sorted(required_codes))].append(finished_code)
    duplicate_groups = [
        codes for codes in exact_sets.values() if len(codes) > 1
    ]

    overlap_groups = []
    for finished_code, required_codes in finished.items():
        overlaps = []
        for left, right in itertools.combinations(sorted(required_codes), 2):
            left_supply = set(equivalents.get(left, (left,)))
            left_supply.add(left)
            right_supply = set(equivalents.get(right, (right,)))
            right_supply.add(right)
            shared = sorted(left_supply & right_supply)
            if shared:
                overlaps.append({
                    "required_code_hashes": [_hash(left), _hash(right)],
                    "shared_supply_hashes": [_hash(code) for code in shared],
                })
        if overlaps:
            overlap_groups.append({
                "finished_code_hash": _hash(finished_code),
                "required_count": len(required_codes),
                "overlap_pairs": overlaps,
            })

    return {
        "finished_with_components": len(finished),
        "component_count_histogram": dict(sorted(size_counts.items())),
        "same_size_candidate_count": same_size_candidate_count,
        "same_size_candidate_pairs": same_size_pair_count,
        "duplicate_component_set_group_count": len(duplicate_groups),
        "duplicate_component_set_finished_count": sum(map(len, duplicate_groups)),
        "duplicate_component_set_samples": [
            [_hash(code) for code in sorted(group)]
            for group in duplicate_groups[:10]
        ],
        "equivalent_pair_count": len(equivalent_pairs),
        "finished_with_overlapping_equivalent_requirements": len(overlap_groups),
        "overlapping_equivalent_requirement_samples": overlap_groups[:10],
    }


METADATA_FIELDS = (
    "shipped_date",
    "operator",
    "channel_name",
    "channel_code",
    "channel_org_name",
    "province",
    "city",
    "district",
    "customer_alias",
)


def _metadata_ambiguity(connection):
    distinct_columns = []
    for field in METADATA_FIELDS:
        if field == "shipped_date":
            expression = "COUNT(DISTINCT shipped_date)"
        else:
            expression = (
                f"COUNT(DISTINCT NULLIF(TRIM(CAST({field} AS CHAR)), ''))"
            )
        distinct_columns.append(f"{expression} AS {field}_n")

    grouped_sql = f"""
        SELECT source, ecommerce_order_no, {", ".join(distinct_columns)}
        FROM shipping_record
        WHERE record_type = 'shipping'
          AND ecommerce_order_no IS NOT NULL
          AND ecommerce_order_no != ''
        GROUP BY source, ecommerce_order_no
    """
    summary_parts = [
        f"SUM({field}_n > 1) AS {field}_conflicts"
        for field in METADATA_FIELDS
    ]
    summary_sql = f"""
        SELECT source, COUNT(*) AS order_count,
               SUM({" OR ".join(f"{field}_n > 1" for field in METADATA_FIELDS)})
                   AS any_conflicts,
               {", ".join(summary_parts)}
        FROM ({grouped_sql}) grouped
        GROUP BY source
        ORDER BY source
    """
    summary = [dict(row) for row in connection.execute(text(summary_sql)).mappings()]

    sample_sql = f"""
        SELECT source, ecommerce_order_no,
               {", ".join(f"{field}_n" for field in METADATA_FIELDS)}
        FROM ({grouped_sql}) grouped
        WHERE {" OR ".join(f"{field}_n > 1" for field in METADATA_FIELDS)}
        ORDER BY source, ecommerce_order_no
        LIMIT 20
    """
    samples = []
    for row in connection.execute(text(sample_sql)).mappings():
        samples.append({
            "order_hash": _hash(f"{row['source']}:{row['ecommerce_order_no']}"),
            "source": row["source"],
            "distinct_nonempty_counts": {
                field: int(row[f"{field}_n"]) for field in METADATA_FIELDS
            },
        })
    return {"summary": summary, "samples": samples}


def _candidate_index(sorted_finished, equivalents):
    frequency = Counter(
        required_code
        for _finished_code, required_codes in sorted_finished
        for required_code in required_codes
    )
    index = defaultdict(set)
    for position, (_finished_code, required_codes) in enumerate(sorted_finished):
        anchor = min(
            required_codes,
            key=lambda code: (
                frequency[code],
                len(equivalents.get(code, {code})),
                code,
            ),
        )
        supplies = set(equivalents.get(anchor, ()))
        supplies.add(anchor)
        for supply in supplies:
            index[supply].add(position)
    return index


def _available(code, remaining, equivalents):
    exact = remaining.get(code, Decimal("0"))
    if exact > 0:
        return exact
    return sum(
        (remaining.get(candidate, Decimal("0"))
         for candidate in equivalents.get(code, {code})),
        Decimal("0"),
    )


def _consume(code, quantity, remaining, equivalents):
    candidates = sorted(
        equivalents.get(code, {code}),
        key=lambda value: (value != code, value),
    )
    left = quantity
    for candidate in candidates:
        if left <= 0:
            break
        available = remaining.get(candidate, Decimal("0"))
        if available <= 0:
            continue
        take = min(available, left)
        remaining[candidate] -= take
        left -= take
        if remaining[candidate] <= 0:
            del remaining[candidate]


def _match(products, sorted_finished, equivalents, index, *,
           reverse_required_codes=False):
    remaining = dict(products)
    candidate_positions = set()
    for supply, quantity in remaining.items():
        if quantity > 0:
            candidate_positions.update(index.get(supply, ()))
    matched = {}
    for position in sorted(candidate_positions):
        finished_code, required_codes = sorted_finished[position]
        ordered_requirements = sorted(
            required_codes, reverse=reverse_required_codes,
        )
        if not all(
            _available(code, remaining, equivalents) > 0
            for code in ordered_requirements
        ):
            continue
        quantity = min(
            _available(code, remaining, equivalents)
            for code in ordered_requirements
        )
        if quantity <= 0:
            continue
        for code in ordered_requirements:
            _consume(code, quantity, remaining, equivalents)
        matched[finished_code] = matched.get(
            finished_code, Decimal("0"),
        ) + quantity
    return (
        tuple(sorted((code, str(quantity)) for code, quantity in matched.items())),
        tuple(sorted((code, str(quantity)) for code, quantity in remaining.items()
                     if quantity > 0)),
    )


def _candidate_orders(finished):
    current = sorted(
        ((code, tuple(sorted(required))) for code, required in finished.items()),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    ascending = sorted(
        ((code, tuple(sorted(required))) for code, required in finished.items()),
        key=lambda item: (-len(item[1]), item[0]),
    )
    descending = []
    for _size, group in itertools.groupby(ascending, key=lambda item: len(item[1])):
        descending.extend(reversed(list(group)))
    return current, ascending, descending


def _simulation(connection, finished, equivalents):
    current, ascending, descending = _candidate_orders(finished)
    current_index = _candidate_index(current, equivalents)
    ascending_index = _candidate_index(ascending, equivalents)
    descending_index = _candidate_index(descending, equivalents)
    query = connection.execution_options(stream_results=True).execute(text("""
        SELECT source, ecommerce_order_no, product_code, SUM(quantity) AS quantity
        FROM shipping_record
        WHERE record_type = 'shipping'
          AND ecommerce_order_no IS NOT NULL
          AND ecommerce_order_no != ''
          AND product_code IS NOT NULL
          AND product_code != ''
          AND quantity > 0
        GROUP BY source, ecommerce_order_no, product_code
        ORDER BY source, ecommerce_order_no, product_code
    """)).mappings()

    totals = Counter()
    candidate_order_samples = []
    current_to_stable_samples = []
    requirement_order_samples = []
    stable_output_hasher = hashlib.sha256()
    current_key = None
    products = {}

    def compare(key, order_products):
        if key is None:
            return
        source, order_no = key
        totals[f"{source}_orders"] += 1
        current_result = _match(
            order_products, current, equivalents, current_index,
        )
        stable = _match(
            order_products, ascending, equivalents, ascending_index,
        )
        stable_output_hasher.update(
            repr((source, order_no, stable)).encode("utf-8")
        )
        candidate_reversed = _match(
            order_products, descending, equivalents, descending_index,
        )
        requirement_reversed = _match(
            order_products, ascending, equivalents, ascending_index,
            reverse_required_codes=True,
        )
        candidate_diff = stable != candidate_reversed
        current_to_stable_diff = current_result != stable
        requirement_diff = stable != requirement_reversed
        if current_to_stable_diff:
            totals[f"{source}_current_to_code_ascending_differences"] += 1
        if candidate_diff:
            totals[f"{source}_candidate_order_differences"] += 1
        if requirement_diff:
            totals[f"{source}_requirement_order_differences"] += 1
        sample = {
                "order_hash": _hash(f"{source}:{order_no}"),
                "source": source,
                "distinct_product_count": len(order_products),
                "current_to_code_ascending_difference": current_to_stable_diff,
                "candidate_order_difference": candidate_diff,
                "requirement_order_difference": requirement_diff,
                "current_result_hash": _hash(current_result),
                "stable_result_hash": _hash(stable),
                "candidate_reversed_result_hash": _hash(candidate_reversed),
                "requirement_reversed_result_hash": _hash(requirement_reversed),
        }
        if candidate_diff and len(candidate_order_samples) < 10:
            candidate_order_samples.append(sample)
        if current_to_stable_diff and len(current_to_stable_samples) < 10:
            current_to_stable_samples.append(sample)
        if requirement_diff and len(requirement_order_samples) < 10:
            requirement_order_samples.append(sample)

    for row in query:
        key = (row["source"], row["ecommerce_order_no"])
        if key != current_key:
            compare(current_key, products)
            current_key = key
            products = {}
        products[row["product_code"]] = Decimal(str(row["quantity"]))
    compare(current_key, products)
    query.close()
    return {
        "counts": dict(totals),
        "stable_output_sha256": stable_output_hasher.hexdigest(),
        "current_to_code_ascending_samples": current_to_stable_samples,
        "candidate_order_samples": candidate_order_samples,
        "requirement_order_samples": requirement_order_samples,
    }


def _metadata_simulation(connection):
    fields = METADATA_FIELDS
    query = connection.execution_options(stream_results=True).execute(text(f"""
        SELECT id, source, ecommerce_order_no, {", ".join(fields)}
        FROM shipping_record
        WHERE record_type = 'shipping'
          AND ecommerce_order_no IS NOT NULL
          AND ecommerce_order_no != ''
        ORDER BY source, ecommerce_order_no, id
    """)).mappings()
    totals = Counter()
    samples = []
    current_key = None
    rows = []

    def normalized(value):
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    def compare(key, order_rows):
        if key is None:
            return
        source, order_no = key
        totals[f"{source}_orders"] += 1
        old_meta = {
            field: normalized(order_rows[0][field])
            for field in fields
        }
        for row in order_rows:
            alias = normalized(row["customer_alias"])
            if alias:
                old_meta["customer_alias"] = alias
                break

        completion_rows = sorted(
            order_rows,
            key=lambda row: (
                row["shipped_date"] is not None,
                row["shipped_date"],
                row["id"],
            ),
            reverse=True,
        )
        representative = completion_rows[0]
        new_meta = {
            field: normalized(representative[field])
            for field in fields
        }
        if not new_meta["customer_alias"]:
            new_meta["customer_alias"] = next(
                (
                    normalized(row["customer_alias"])
                    for row in completion_rows
                    if normalized(row["customer_alias"])
                ),
                None,
            )

        distinct_values = {
            field: {
                value
                for row in order_rows
                if (value := normalized(row[field])) is not None
            }
            for field in fields
        }
        ambiguous = any(
            len(values) > 1 for values in distinct_values.values()
        )
        changed_fields = [
            field for field in fields if old_meta[field] != new_meta[field]
        ]
        if not changed_fields:
            return
        totals[f"{source}_changed_orders"] += 1
        if ambiguous:
            totals[f"{source}_ambiguous_changed_orders"] += 1
        else:
            totals[f"{source}_nonambiguous_changed_orders"] += 1
        for field in changed_fields:
            totals[f"{source}_{field}_changes"] += 1
        if len(samples) < 20:
            samples.append({
                "order_hash": _hash(f"{source}:{order_no}"),
                "source": source,
                "ambiguous": ambiguous,
                "row_count": len(order_rows),
                "changed_fields": changed_fields,
                "old_value_hashes": {
                    field: _hash(old_meta[field]) for field in changed_fields
                },
                "new_value_hashes": {
                    field: _hash(new_meta[field]) for field in changed_fields
                },
            })

    for row in query:
        key = (row["source"], row["ecommerce_order_no"])
        if key != current_key:
            compare(current_key, rows)
            current_key = key
            rows = []
        rows.append(row)
    compare(current_key, rows)
    query.close()
    return {"counts": dict(totals), "samples": samples}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase",
        choices=("aggregate", "simulation", "metadata-simulation"),
        default="aggregate",
    )
    parser.add_argument(
        "--compact", action="store_true",
        help="For simulation, print only counts and the stable output digest.",
    )
    args = parser.parse_args()
    engine = create_engine(
        _database_url(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10, "read_timeout": 600},
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SET SESSION TRANSACTION READ ONLY"))
            connection.execute(text("START TRANSACTION READ ONLY"))
            finished, equivalents, equivalent_pairs = _load_product_rules(connection)
            if args.phase == "aggregate":
                report = {
                    "product_rules": _product_ambiguity(
                        finished, equivalents, equivalent_pairs,
                    ),
                    "metadata": _metadata_ambiguity(connection),
                }
            elif args.phase == "simulation":
                report = {
                    "simulation": _simulation(
                        connection, finished, equivalents,
                    ),
                }
            else:
                report = {
                    "metadata_simulation": _metadata_simulation(connection),
                }
            connection.rollback()
    finally:
        engine.dispose()
    if args.compact and args.phase == "simulation":
        simulation = report["simulation"]
        report = {
            "counts": simulation["counts"],
            "stable_output_sha256": simulation["stable_output_sha256"],
        }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
