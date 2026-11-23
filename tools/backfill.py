"""Rebuild an approximate history of the 340B registry from the dates one snapshot carries.

Every contract pharmacy arrangement in today's registry keeps its begin date, and an ended one
keeps its termination date. Every covered entity keeps its participation start date and, once
ended, its termination date. So for any past day we can count what today's registry says was
active on that day.

That is today's record of the past, not a copy of the past. It misses anything removed from the
registry outright (ended records before about 2016-2017 are not listed), and it reflects later
corrections of dates.

An arrangement is counted active on day D when begin <= D, and D is before its own termination
date and before its entity's termination date (if any).

  python3 -I backfill.py SNAPSHOT.json OUTDIR

Writes, for the first day of each month from 2010-01 to the snapshot's month:
  national.csv        month, entities (all, parents, child sites), arrangements, distinct
                      pharmacies, out-of-state arrangements
  by_state.csv        month, state (entity's street address), entities, arrangements, pharmacies
  by_type.csv         month, entity type, entities, arrangements
  by_chain.csv        month, pharmacy group (by name), arrangements, distinct pharmacies
  flows.csv           January of each year and the snapshot's month: entity state, pharmacy
                      state, arrangements (pairs with at least one)
  ended_listed.csv    year, ended arrangements listed, ended entities listed (to show where the
                      record of endings starts)
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

# A pharmacy's group, from its name (and the "DBA" line, which often carries the chain name).
# Order matters: the first match wins. Names only; nothing is inferred from ownership records.
CHAINS = [
    ("CVS", r"\bCVS\b|LONGS DRUG|OMNICARE|CAREMARK"),
    ("Walgreens", r"WALGREEN|DUANE READE|ALLIANCE ?RX"),
    ("Walmart", r"WAL-?MART|WALMART|SAM'?S CLUB"),
    ("Rite Aid", r"RITE ?AID|THRIFTY PAYLESS|ELIXIR"),
    ("Kroger", r"KROGER|FRED MEYER|RALPHS|KING SOOPERS|SMITH'?S FOOD|FRY'?S FOOD|DILLON|HARRIS TEETER|MARIANO|QFC|BAKER'?S|PICK ?N ?SAVE|CITY MARKET|JAY C"),
    ("Albertsons", r"ALBERTSON|SAFEWAY|JEWEL|VONS|ACME MARKETS|SHAW'?S|PAVILIONS|RANDALLS|TOM THUMB|UNITED SUPERMARKETS|CARRS"),
    ("Express Scripts / Accredo", r"EXPRESS SCRIPTS|ACCREDO|CURASCRIPT|FREEDOM FERTILITY"),
    ("Optum", r"OPTUM|BRIOVA|DIPLOMAT"),
    ("Publix", r"PUBLIX"),
    ("H-E-B", r"\bH-?E-?B\b"),
    ("Costco", r"COSTCO"),
    ("Meijer", r"MEIJER"),
    ("Hy-Vee", r"HY-?VEE"),
    ("Giant Eagle", r"GIANT EAGLE"),
    ("Ahold Delhaize", r"GIANT FOOD|STOP ?& ?SHOP|HANNAFORD|FOOD LION|MARTIN'?S"),
    ("Centene / AcariaHealth", r"ACARIA"),
    ("Humana / CenterWell", r"CENTERWELL|HUMANA"),
]
CHAIN_RES = [(n, re.compile(p)) for n, p in CHAINS]


def chain_of(p: dict) -> str:
    a = p.get("address") or {}
    text = " ".join(str(x) for x in (p.get("name"), a.get("line1"), a.get("line2")) if x).upper()
    for name, rx in CHAIN_RES:
        if rx.search(text):
            return name
    return "Other"


def d(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def months(last: date) -> list[date]:
    out, y, m = [], 2010, 1
    while (y, m) <= (last.year, last.month):
        out.append(date(y, m, 1))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def active(begin: date | None, end: date | None, day: date) -> bool:
    return begin is not None and begin <= day and (end is None or day < end)


def main(snapshot: Path, outdir: Path) -> None:
    snap = json.loads(snapshot.read_text(encoding="utf-8"))
    taken = date.fromisoformat(snap["taken_on"])
    ms = months(taken)
    outdir.mkdir(parents=True, exist_ok=True)

    # Per month accumulators.
    nat = {m: Counter() for m in ms}
    st_e = defaultdict(Counter)   # (m) -> state -> entities
    st_a = defaultdict(Counter)   # arrangements
    st_p = defaultdict(lambda: defaultdict(set))  # m -> state -> pharmacy ids
    ty_e = defaultdict(Counter)
    ty_a = defaultdict(Counter)
    ch_a = defaultdict(Counter)
    ch_p = defaultdict(lambda: defaultdict(set))
    pharm = defaultdict(set)
    flow_months = sorted({m for m in ms if m.month == 1} | {ms[-1]})
    flows = defaultdict(Counter)
    ended_arr, ended_ent = Counter(), Counter()
    missing_begin = 0

    for e in snap["entities"]:
        es, ee = d(e.get("participating_start_date")), d(e.get("termination_date"))
        if ee:
            ended_ent[ee.year] += 1
        state = (e.get("street") or {}).get("state") or "??"
        etype = e.get("entity_type") or "??"
        child = bool(e.get("parent_340b_id"))
        for m in ms:
            if active(es, ee, m):
                nat[m]["entities"] += 1
                nat[m]["child_sites" if child else "parents"] += 1
                st_e[m][state] += 1
                ty_e[m][etype] += 1
        for p in e.get("contract_pharmacies") or []:
            pb, pe = d(p.get("begin_date")), d(p.get("termination_date"))
            if pe:
                ended_arr[pe.year] += 1
            if pb is None:
                missing_begin += 1
                continue
            end = min(x for x in (pe, ee) if x) if (pe or ee) else None
            pid = p.get("pharmacy_id")
            pstate = (p.get("address") or {}).get("state")
            ch = chain_of(p)
            for m in ms:
                if active(pb, end, m):
                    nat[m]["arrangements"] += 1
                    if pstate and pstate != state:
                        nat[m]["out_of_state"] += 1
                    pharm[m].add(pid)
                    st_a[m][state] += 1
                    st_p[m][state].add(pid)
                    ty_a[m][etype] += 1
                    ch_a[m][ch] += 1
                    ch_p[m][ch].add(pid)
            for m in flow_months:
                if active(pb, end, m):
                    flows[m][(state, pstate or "??")] += 1

    def w(name: str, header: list[str], rows: list[list[object]]) -> None:
        with open(outdir / name, "w", newline="", encoding="utf-8") as f:
            cw = csv.writer(f)
            cw.writerow(header)
            cw.writerows(rows)

    w("national.csv",
      ["month", "entities", "parents", "child_sites", "arrangements", "pharmacies", "out_of_state"],
      [[m.isoformat(), nat[m]["entities"], nat[m]["parents"], nat[m]["child_sites"],
        nat[m]["arrangements"], len(pharm[m]), nat[m]["out_of_state"]] for m in ms])
    states = sorted({s for m in ms for s in st_e[m]} | {s for m in ms for s in st_a[m]})
    w("by_state.csv", ["month", "state", "entities", "arrangements", "pharmacies"],
      [[m.isoformat(), s, st_e[m][s], st_a[m][s], len(st_p[m][s])] for m in ms for s in states])
    types = sorted({t for m in ms for t in ty_e[m]})
    w("by_type.csv", ["month", "entity_type", "entities", "arrangements"],
      [[m.isoformat(), t, ty_e[m][t], ty_a[m][t]] for m in ms for t in types])
    chains = [n for n, _ in CHAINS] + ["Other"]
    w("by_chain.csv", ["month", "group", "arrangements", "pharmacies"],
      [[m.isoformat(), c, ch_a[m][c], len(ch_p[m][c])] for m in ms for c in chains])
    w("flows.csv", ["month", "entity_state", "pharmacy_state", "arrangements"],
      [[m.isoformat(), a, b, n] for m in flow_months for (a, b), n in sorted(flows[m].items())])
    years = sorted(set(ended_arr) | set(ended_ent))
    w("ended_listed.csv", ["year", "ended_arrangements_listed", "ended_entities_listed"],
      [[y, ended_arr[y], ended_ent[y]] for y in years])
    print(f"{len(ms)} months; {missing_begin} arrangements without a begin date left out")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
