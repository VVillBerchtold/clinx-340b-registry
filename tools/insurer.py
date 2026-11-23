"""Arrangements in force each month at pharmacies owned by a company that also owns a health
insurer or a pharmacy benefit manager, split by whether the pharmacy is in another state.

  python3 -I insurer.py SNAPSHOT.json INSURER.json

Same in-force rule and the same out-of-state test as backfill.py (the pharmacy's address state
differs from the entity's street-address state). A pharmacy counts as insurer-owned when its name
or address lines match one of the brands in OWNERS. Names only, as in backfill.CHAINS: the
registry records no owner. Writes
{"months": [...], "arrangements": [...], "out_of_state": [...], "insurer": [...],
 "insurer_out": [...], "owners": {owner: arrangements in the last month}}.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from backfill import active, d, months  # noqa: E402

# Specialty, mail, infusion and long-term-care pharmacies, by the insurer or PBM group that owns them.
OWNERS = [
    ("CVS Health (Aetna, Caremark)", r"CVS ?SPECIALTY|CAREMARK|CVS/?SPECIALTY|PROCARE PHARMACY|CORAM|NOVOLOGIX|AETNA SPECIALTY"),
    ("Cigna (Express Scripts, Accredo)", r"EXPRESS SCRIPTS|ACCREDO|CURASCRIPT|FREEDOM FERTILITY"),
    ("UnitedHealth (Optum)", r"OPTUM|BRIOVA|DIPLOMAT|AVELLA|GENOA HEALTHCARE"),
    ("Elevance (CarelonRx, BioPlus)", r"CARELON|INGENIORX|BIOPLUS"),
    ("Humana (CenterWell)", r"CENTERWELL|HUMANA"),
    ("Centene (AcariaHealth)", r"ACARIA"),
    ("Blue plans (Prime Therapeutics)", r"PRIME THERAPEUTICS"),
]
OWNER_RES = [(n, re.compile(p)) for n, p in OWNERS]


def owner_of(p: dict) -> str | None:
    a = p.get("address") or {}
    text = " ".join(str(x) for x in (p.get("name"), a.get("line1"), a.get("line2")) if x).upper()
    for name, rx in OWNER_RES:
        if rx.search(text):
            return name
    return None


def main(snapshot: Path, out: Path) -> None:
    snap = json.loads(snapshot.read_text(encoding="utf-8"))
    ms = months(date.fromisoformat(snap["taken_on"]))
    n = len(ms)
    arr, oos, ins, ins_out = ([0] * n for _ in range(4))
    owners: Counter[str] = Counter()
    for e in snap["entities"]:
        ee = d(e.get("termination_date"))
        state = (e.get("street") or {}).get("state") or "??"
        for p in e.get("contract_pharmacies") or []:
            pb, pe = d(p.get("begin_date")), d(p.get("termination_date"))
            if pb is None or pb > ms[-1]:
                continue
            end = min(x for x in (pe, ee) if x) if (pe or ee) else None
            pstate = (p.get("address") or {}).get("state")
            away = bool(pstate and pstate != state)
            who = owner_of(p)
            for i, m in enumerate(ms):
                if active(pb, end, m):
                    arr[i] += 1
                    oos[i] += away
                    if who:
                        ins[i] += 1
                        ins_out[i] += away
                        if i == n - 1:
                            owners[who] += 1
    doc = {"months": [m.isoformat()[:7] for m in ms], "arrangements": arr, "out_of_state": oos,
           "insurer": ins, "insurer_out": ins_out, "owners": dict(owners.most_common())}
    out.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"{out}: last month {arr[-1]:,} arrangements, {oos[-1]:,} out of state, "
          f"{ins[-1]:,} insurer-owned ({ins_out[-1]:,} of them out of state)")
    for i in (84, 108, 132, n - 1):
        print(f"  {ms[i]:%Y-%m}: out of state {oos[i] / arr[i]:.1%}, insurer-owned part {ins_out[i] / max(oos[i], 1):.0%}, "
              f"other arrangements out of state {(oos[i] - ins_out[i]) / max(arr[i] - ins[i], 1):.1%}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
