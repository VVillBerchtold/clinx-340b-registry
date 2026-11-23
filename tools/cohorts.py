"""Arrangements in force on the first day of each month, by the year each one began.

  python3 -I cohorts.py SNAPSHOT.json COHORTS.json

Same rule as backfill.py: an arrangement is in force on day D when begin <= D and D is before
its own termination date and its entity's. Arrangements that began in 2010 or before are one
layer. Writes {"months": [...], "years": [...], "layers": {year: [count per month]}}.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from backfill import active, d, months  # noqa: E402

FIRST = 2010


def main(snapshot: Path, out: Path) -> None:
    snap = json.loads(snapshot.read_text(encoding="utf-8"))
    ms = months(date.fromisoformat(snap["taken_on"]))
    years = list(range(FIRST, ms[-1].year + 1))
    layers = {y: [0] * len(ms) for y in years}
    for e in snap["entities"]:
        ee = d(e.get("termination_date"))
        for p in e.get("contract_pharmacies") or []:
            pb, pe = d(p.get("begin_date")), d(p.get("termination_date"))
            if pb is None or pb > ms[-1]:
                continue  # no date, or not begun by the snapshot's month
            end = min(x for x in (pe, ee) if x) if (pe or ee) else None
            y = max(pb.year, FIRST)
            row = layers[y]
            for i, m in enumerate(ms):
                if active(pb, end, m):
                    row[i] += 1
    doc = {"months": [m.isoformat()[:7] for m in ms], "years": years, "layers": {str(y): layers[y] for y in years}}
    out.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    total = [sum(layers[y][i] for y in years) for i in range(len(ms))]
    print(f"{out}: {len(ms)} months, {len(years)} layers; last month {total[-1]:,} in all")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
