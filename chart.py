#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["matplotlib"]
# ///
"""Plot TSA monthly passenger totals, one line per year."""

import calendar
import sqlite3
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

DB = Path(__file__).parent / "tsa.db"
OUT = Path(__file__).parent / "chart.png"

conn = sqlite3.connect(DB)
rows = conn.execute(
    """
    SELECT
      CAST(substr(date, 1, 4) AS INTEGER) AS y,
      CAST(substr(date, 6, 2) AS INTEGER) AS m,
      SUM(passengers) AS total,
      COUNT(*)        AS days_present
    FROM passenger_volumes
    GROUP BY y, m
    ORDER BY y, m
    """
).fetchall()

# Only keep months that are complete (days_present == days_in_month).
series = defaultdict(dict)  # year -> {month: total_millions}
for y, m, total, days_present in rows:
    days_in_month = calendar.monthrange(y, m)[1]
    if days_present == days_in_month:
        series[y][m] = total / 1_000_000

fig, ax = plt.subplots(figsize=(11, 6.5))
months = list(range(1, 13))
labels = [calendar.month_abbr[m] for m in months]

cmap = plt.get_cmap("viridis")
years = sorted(series.keys())
for i, year in enumerate(years):
    color = cmap(i / max(1, len(years) - 1))
    ys = [series[year].get(m) for m in months]
    ax.plot(
        months, ys,
        marker="o", linewidth=2, color=color, label=str(year),
    )

ax.set_xticks(months)
ax.set_xticklabels(labels)
ax.set_ylabel("Passengers per month (millions)")
ax.set_xlabel("Month")
ax.set_title("TSA checkpoint passenger volumes by month, 2019–2026")
ax.grid(True, alpha=0.3)
ax.legend(title="Year", loc="lower right", ncols=2)
ax.set_ylim(bottom=0)

fig.tight_layout()
fig.savefig(OUT, dpi=140)
print(f"wrote {OUT}")
