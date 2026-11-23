"""Share of arrangements in force each month, by how many arrangements the pharmacy holds.

  python3 -I concentration.py SNAPSHOT.json CONCENTRATION.json

Same in-force rule as backfill.py. For each month, each pharmacy's arrangements in force are
counted; the arrangements are then grouped by that count. Writes
{"months": [...], "bins": [labels], "arrangements": {label: [...]}, "pharmacies": {label: [...]}}.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from backfill import active, d, months  # noqa: E402

BINS = [(1, 1, "1"), (2, 9, "2 to 9"), (10, 49, "10 to 49"), (50, 199, "50 to 199"), (200, 10**9, "200 or more")]


def main(snapshot: Path, out: Path) -> None:
    snap = json.loads(snapshot.read_text(encoding="utf-8"))
    ms = months(date.fromisoformat(snap["taken_on"]))
    per = [Counter() for _ in ms]
    for e in snap["entities"]:
        ee = d(e.get("termination_date"))
        for p in e.get("contract_pharmacies") or []:
            pb, pe = d(p.get("begin_date")), d(p.get("termination_date"))
            if pb is None or pb > ms[-1]:
                continue
            end = min(x for x in (pe, ee) if x) if (pe or ee) else None
            pid = p.get("pharmacy_id")
            for i, m in enumerate(ms):
                if active(pb, end, m):
                    per[i][pid] += 1
    arr = {b[2]: [0] * len(ms) for b in BINS}
    ph = {b[2]: [0] * len(ms) for b in BINS}
    for i, c in enumerate(per):
        for k in c.values():
            for lo, hi, name in BINS:
                if lo <= k <= hi:
                    arr[name][i] += k
                    ph[name][i] += 1
                    break
    doc = {"months": [m.isoformat()[:7] for m in ms], "bins": [b[2] for b in BINS], "arrangements": arr, "pharmacies": ph}
    out.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    tot = sum(arr[b[2]][-1] for b in BINS)
    print(f"{out}: last month {tot:,} arrangements, {sum(ph[b[2]][-1] for b in BINS):,} pharmacies")
    for b in BINS:
        n = b[2]
        print(f"  {n:>12}: 2012-01 {arr[n][24]:>7,} ({ph[n][24]:,} ph)   now {arr[n][-1]:>7,} ({ph[n][-1]:,} ph)")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
