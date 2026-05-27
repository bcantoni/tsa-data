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

# Custom DB path:
uv run tsa.py --db /tmp/foo.db update
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

## Gotchas

- **The TSA site 403s any non-browser User-Agent.** `tsa.py` sets a desktop
  Chrome UA on the `requests.Session`. If fetches start failing, check
  whether the site is now blocking that UA string.
- Page structure assumed: a `<table>` whose `<th>` headers include
  `Date` and `Numbers`, with `<tbody>` rows of `M/D/YYYY` + comma-separated
  integer. If TSA changes this, `parse_table` will raise.
