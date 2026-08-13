"""Verify a restored instance against the source it was restored from.

`00-charter.md` invariant 35: a backup that has never been restored is not a
backup. This is what turns a restore into a verified restore, and it is the check
`04-layer-0.md` WP-0.3 requires on a cadence.

Three things are compared, because a restore can succeed and still be wrong:

1. **Row counts per table.** The blunt check, and the one that catches a restore
   from the wrong point in time.
2. **Referential integrity.** Every foreign key on the restored instance
   actually resolves. A dump/restore can leave a dangling reference that the
   database will not re-check on its own.
3. **Capture-table continuity.** `model_calls`, `execution_events`, and
   `deliberations` feed machinery that arrives at Layers 3 and 5 and cannot be
   backfilled. A gap in them is the failure that matters most and the one least
   likely to be noticed, so their extent and count are compared directly.

Usage:

    verify_restore.py --source postgresql://... --restored postgresql://...

Exit code 0 means the restore is verified. Exit code 1 means it is not, and the
backup it came from must not be trusted until the difference is explained.
"""

import argparse
import sys
from typing import Any

from sqlalchemy import create_engine, text

from val_domain.schema import SPECIFIED_TABLES

CAPTURE_TABLES = ("model_calls", "execution_events", "deliberations")


def _scalar(url: str, statement: str) -> int:
    """Run a statement returning one integer."""
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return int(connection.execute(text(statement)).scalar_one())
    finally:
        engine.dispose()


def _rows(url: str, statement: str) -> list[tuple[Any, ...]]:
    """Run a statement returning rows."""
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(statement))]
    finally:
        engine.dispose()


def compare_row_counts(source: str, restored: str) -> list[str]:
    """Every table holds the same number of rows on both sides."""
    problems: list[str] = []
    for table in sorted(SPECIFIED_TABLES):
        before = _scalar(source, f"select count(*) from {table}")  # noqa: S608
        after = _scalar(restored, f"select count(*) from {table}")  # noqa: S608
        marker = "ok" if before == after else "MISMATCH"
        print(f"  {table:<18} source={before:<8} restored={after:<8} {marker}")
        if before != after:
            problems.append(f"{table}: source has {before} rows, restored has {after}")
    return problems


def check_referential_integrity(restored: str) -> list[str]:
    """Every foreign key on the restored instance resolves.

    PostgreSQL trusts its own constraints after a restore rather than re-checking
    them, so a corrupted or partial restore can leave a reference pointing at
    nothing. This walks every foreign key and looks.
    """
    constraints = _rows(
        restored,
        """
        select c.conname, tc.relname, ac.attname, tr.relname, ar.attname
        from pg_constraint c
        join pg_class tc on tc.oid = c.conrelid
        join pg_class tr on tr.oid = c.confrelid
        join unnest(c.conkey) with ordinality as k(attnum, ord) on true
        join unnest(c.confkey) with ordinality as f(attnum, ord) on f.ord = k.ord
        join pg_attribute ac on ac.attrelid = c.conrelid and ac.attnum = k.attnum
        join pg_attribute ar on ar.attrelid = c.confrelid and ar.attnum = f.attnum
        where c.contype = 'f'
        """,
    )
    problems: list[str] = []
    for name, child, child_column, parent, parent_column in constraints:
        dangling = _scalar(
            restored,
            f"select count(*) from {child} c "  # noqa: S608
            f"left join {parent} p on p.{parent_column} = c.{child_column} "
            f"where c.{child_column} is not null and p.{parent_column} is null",
        )
        marker = "ok" if dangling == 0 else "DANGLING"
        print(f"  {name:<42} {dangling} dangling {marker}")
        if dangling:
            problems.append(f"{name}: {dangling} rows reference a row that is not there")
    return problems


def check_capture_continuity(source: str, restored: str) -> list[str]:
    """The three capture tables are continuous, with no gap at the tail.

    These cannot be backfilled at any price. A restore that quietly lost the last
    hour of them is the expensive failure.
    """
    problems: list[str] = []
    for table in CAPTURE_TABLES:
        statement = f"select count(*), min(created_at), max(created_at) from {table}"  # noqa: S608
        before = _rows(source, statement)[0]
        after = _rows(restored, statement)[0]
        marker = "ok" if before == after else "DISCONTINUOUS"
        print(f"  {table:<18} source={before[0]} rows {before[1]}..{before[2]}")
        print(f"  {'':<18} restored={after[0]} rows {after[1]}..{after[2]}  {marker}")
        if before != after:
            problems.append(
                f"{table}: source holds {before[0]} rows spanning {before[1]}..{before[2]}, "
                f"restored holds {after[0]} spanning {after[1]}..{after[2]}"
            )
    return problems


def main() -> int:
    """Compare a restored instance against its source."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="URL of the instance backed up")
    parser.add_argument("--restored", required=True, help="URL of the restored scratch instance")
    arguments = parser.parse_args()

    print("Row counts per table")
    problems = compare_row_counts(arguments.source, arguments.restored)
    print("\nReferential integrity on the restored instance")
    problems.extend(check_referential_integrity(arguments.restored))
    print("\nCapture-table continuity")
    problems.extend(check_capture_continuity(arguments.source, arguments.restored))

    if problems:
        print(f"\nRESTORE NOT VERIFIED — {len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            "\nThe backup this came from must not be trusted until the difference is "
            "explained (00-charter.md invariant 35).",
            file=sys.stderr,
        )
        return 1

    print(
        "\nRESTORE VERIFIED: row counts match, no dangling references, capture tables continuous."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
