#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "beautifulsoup4"]
# ///
"""Fetch TSA checkpoint passenger volumes into a local SQLite database."""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

CURRENT_URL = "https://www.tsa.gov/travel/passenger-volumes"
YEAR_URL = "https://www.tsa.gov/travel/passenger-volumes/{year}"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS passenger_volumes (
    date        TEXT PRIMARY KEY,
    passengers  INTEGER NOT NULL,
    source_url  TEXT NOT NULL,
    fetched_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pv_date ON passenger_volumes(date);
"""


def fetch_page(session: requests.Session, url: str) -> str:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_table(html: str) -> list[tuple[date, int]]:
    soup = BeautifulSoup(html, "html.parser")
    table = None
    for candidate in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in candidate.find_all("th")]
        if "date" in headers and "numbers" in headers:
            table = candidate
            break
    if table is None:
        raise ValueError("Could not find passenger volumes table on page")

    rows: list[tuple[date, int]] = []
    for tr in table.find("tbody").find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) != 2:
            continue
        raw_date = cells[0].get_text(strip=True)
        raw_num = cells[1].get_text(strip=True).replace(",", "")
        d = datetime.strptime(raw_date, "%m/%d/%Y").date()
        rows.append((d, int(raw_num)))
    return rows


def init_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def upsert(
    conn: sqlite3.Connection,
    rows: list[tuple[date, int]],
    source_url: str,
) -> tuple[int, int, int]:
    """Insert/update rows. Returns (inserted, updated, unchanged)."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inserted = updated = unchanged = 0
    cur = conn.cursor()
    for d, n in rows:
        iso = d.isoformat()
        existing = cur.execute(
            "SELECT passengers FROM passenger_volumes WHERE date = ?", (iso,)
        ).fetchone()
        if existing is None:
            cur.execute(
                "INSERT INTO passenger_volumes (date, passengers, source_url, fetched_at) "
                "VALUES (?, ?, ?, ?)",
                (iso, n, source_url, now),
            )
            inserted += 1
        elif existing[0] != n:
            cur.execute(
                "UPDATE passenger_volumes SET passengers = ?, source_url = ?, fetched_at = ? "
                "WHERE date = ?",
                (n, source_url, now, iso),
            )
            updated += 1
        else:
            unchanged += 1
    conn.commit()
    return inserted, updated, unchanged


def cmd_update(args: argparse.Namespace) -> int:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    conn = init_db(args.db)
    try:
        html = fetch_page(session, CURRENT_URL)
        rows = parse_table(html)
        ins, upd, same = upsert(conn, rows, CURRENT_URL)
        print(
            f"{CURRENT_URL}: parsed {len(rows)} rows  "
            f"(inserted={ins}, updated={upd}, unchanged={same})"
        )
    finally:
        conn.close()
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    if args.start > args.end:
        print("error: --start must be <= --end", file=sys.stderr)
        return 2
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    conn = init_db(args.db)
    try:
        total_ins = total_upd = total_same = 0
        years = list(range(args.start, args.end + 1))
        for i, year in enumerate(years):
            url = YEAR_URL.format(year=year)
            html = fetch_page(session, url)
            rows = parse_table(html)
            ins, upd, same = upsert(conn, rows, url)
            total_ins += ins
            total_upd += upd
            total_same += same
            print(
                f"{year}: parsed {len(rows)} rows  "
                f"(inserted={ins}, updated={upd}, unchanged={same})"
            )
            if i < len(years) - 1:
                time.sleep(1.0)
        print(
            f"backfill done: inserted={total_ins}, updated={total_upd}, "
            f"unchanged={total_same}"
        )
    finally:
        conn.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("tsa.db"),
        help="Path to the SQLite database (default: tsa.db)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_update = sub.add_parser("update", help="Fetch current YTD page and upsert")
    p_update.set_defaults(func=cmd_update)

    p_back = sub.add_parser("backfill", help="Fetch per-year archive pages")
    p_back.add_argument("--start", type=int, default=2019)
    p_back.add_argument("--end", type=int, default=2025)
    p_back.set_defaults(func=cmd_backfill)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
