#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Validate tsa.csv: correct CSV shape and clean date,passengers rows.

Exits 0 if the file is clean, 1 if any problem is found. Run as an extra
quality gate after `tsa.py export` / `update` / `backfill`.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

EXPECTED_HEADER = ["date", "passengers"]


def validate(path: Path) -> list[str]:
    """Return a list of human-readable problems. Empty list means clean."""
    problems: list[str] = []

    if not path.exists():
        return [f"file not found: {path}"]

    with open(path, newline="") as f:
        reader = csv.reader(f)
        try:
            rows = list(reader)
        except csv.Error as e:
            return [f"not valid CSV: {e}"]

    if not rows:
        return ["file is empty (no header, no rows)"]

    # Header must be exactly date,passengers.
    header = rows[0]
    if header != EXPECTED_HEADER:
        problems.append(
            f"line 1: header is {header!r}, expected {EXPECTED_HEADER!r}"
        )

    seen_dates: dict[str, int] = {}
    prev_date: date | None = None

    # csv line numbers are 1-based; data starts at line 2.
    for lineno, row in enumerate(rows[1:], start=2):
        if len(row) != 2:
            problems.append(
                f"line {lineno}: expected 2 columns, got {len(row)}: {row!r}"
            )
            continue

        raw_date, raw_num = row[0], row[1]

        # Column 1: strict ISO YYYY-MM-DD calendar date.
        d: date | None = None
        try:
            d = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            problems.append(
                f"line {lineno}: bad date {raw_date!r} "
                "(want ISO YYYY-MM-DD)"
            )

        # Column 2: a plain non-negative integer, no commas/signs/decimals.
        if not raw_num.isdigit():
            problems.append(
                f"line {lineno}: bad passengers {raw_num!r} "
                "(want a non-negative integer with no separators)"
            )

        if d is not None:
            if raw_date in seen_dates:
                problems.append(
                    f"line {lineno}: duplicate date {raw_date} "
                    f"(first seen on line {seen_dates[raw_date]})"
                )
            else:
                seen_dates[raw_date] = lineno

            if prev_date is not None and d < prev_date:
                problems.append(
                    f"line {lineno}: date {raw_date} is out of order "
                    f"(previous row was {prev_date.isoformat()})"
                )
            prev_date = d

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv",
        nargs="?",
        type=Path,
        default=Path("tsa.csv"),
        help="Path to the CSV to validate (default: tsa.csv)",
    )
    args = parser.parse_args(argv)

    problems = validate(args.csv)
    if problems:
        print(f"{args.csv}: FAILED — {len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    # Re-read just for the row count in the success message.
    with open(args.csv, newline="") as f:
        data_rows = max(sum(1 for _ in f) - 1, 0)
    print(f"{args.csv}: OK — {data_rows} valid date,passengers rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
