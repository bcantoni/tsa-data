# tsa-data

Scrapes daily TSA checkpoint passenger volumes from
`https://www.tsa.gov/travel/passenger-volumes` (current YTD) and
`https://www.tsa.gov/travel/passenger-volumes/{YYYY}` (per-year archives)
into a local SQLite DB.

## Run

```bash
# One-time seed of 2019–2025:
uv run tsa.py backfill --start 2019 --end 2025

# Pull the current YTD page (safe to re-run; uses upsert):
uv run tsa.py update

# Re-export tsa.csv from the DB without fetching:
uv run tsa.py export

# Validate tsa.csv (exits non-zero on any problem):
uv run validate.py

# Custom DB / CSV paths:
uv run tsa.py --db /tmp/foo.db --csv /tmp/foo.csv update
```

`tsa.py` is a PEP 723 single-file script — `uv run` resolves
`requests` + `beautifulsoup4` automatically, no venv setup needed.

## Schema

`tsa.db`, single table:

```sql
passenger_volumes(
    date        TEXT PRIMARY KEY,  -- ISO 'YYYY-MM-DD'
    passengers  INTEGER NOT NULL,
    source_url  TEXT NOT NULL,     -- which page this row came from
    fetched_at  TEXT NOT NULL      -- ISO 8601 UTC of the fetch
)
```

`update` and `backfill` both upsert: rows whose `passengers` value changed
are overwritten; identical rows are left alone. Counts (inserted / updated /
unchanged) are printed per page.

## CSV export

`update` and `backfill` rewrite `tsa.csv` (default path; override with
`--csv`) after upserting, and the standalone `export` subcommand does the
same without fetching. The file is fully overwritten each run — all rows,
`date ASC`, two columns only: `date,passengers`. CSV uses stdlib `csv`, so
no new dependency was added.

## CSV validation

`validate.py` (stdlib-only PEP 723 script) is a quality gate over
`tsa.csv`. Defaults to `./tsa.csv`; pass a path to override. Exits `0` when
clean, `1` (with per-line problems on stderr) otherwise. Checks: parses as
CSV, header is exactly `date,passengers`, every row is exactly two columns
(strict ISO `YYYY-MM-DD` date + non-negative integer via `str.isdigit`,
i.e. no commas/signs/decimals), and dates are unique and strictly
ascending. Run `uv run tsa.py update && uv run validate.py` to export then
verify.

## Automation

`.github/workflows/daily.yml` runs daily (12:00 UTC) + on manual dispatch:
`update` → `validate.py` → commit `tsa.db` + `tsa.csv` back to the repo. Both
data files are **committed** (not gitignored) — the committed `tsa.db` is the
source of truth the incremental `update` builds on. The commit step is gated
on `tsa.csv` changing, so no-op days don't churn the binary DB. If
`validate.py` fails, the job stops before committing.

## Gotchas

- **The TSA site 403s any non-browser User-Agent.** `tsa.py` sets a desktop
  Chrome UA on the `requests.Session`. If fetches start failing, check
  whether the site is now blocking that UA string.
- Page structure assumed: a `<table>` whose `<th>` headers include
  `Date` and `Numbers`, with `<tbody>` rows of `M/D/YYYY` + comma-separated
  integer. If TSA changes this, `parse_table` will raise.
