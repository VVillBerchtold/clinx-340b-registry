"""Pack the rebuilt history (backfill.py's tables) into one compact file for the site.

  python3 -I site_data.py OUTDIR LAWS.csv [LAW-DATES.csv] SITE.json

OUTDIR holds backfill.py's tables. LAWS.csv is clinx-340b's data/state-laws.csv. LAW-DATES.csv
(optional) gives effective dates the laws table does not print, with their source. Every number
in SITE.json is copied from the tables; nothing is estimated here.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

MAIL = {"Express Scripts / Accredo", "Optum", "Centene / AcariaHealth", "Humana / CenterWell"}
CHAIN_GROUPS = ["CVS", "Walgreens", "Walmart", "Mail-order and specialty", "Other"]
HOSPITALS = {"DSH", "CAH", "PED", "CAN", "RRC", "SCH"}
HEALTH_CENTERS = {"CH", "FQHCLA", "FQHC638"}
TYPE_GROUPS = ["Health centers", "Hospitals", "Other federal grantees"]


def chain_group(g: str) -> str:
    if g in MAIL:
        return "Mail-order and specialty"
    return g if g in ("CVS", "Walgreens", "Walmart") else "Other"


def type_group(t: str) -> str:
    if t in HOSPITALS:
        return "Hospitals"
    if t in HEALTH_CENTERS:
        return "Health centers"
    return "Other federal grantees"


def rows(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main(outdir: Path, laws_csv: Path, dates_csv: Path | None, site: Path) -> None:
    nat = rows(outdir / "national.csv")
    months = [r["month"][:7] for r in nat]
    idx = {m: i for i, m in enumerate(months)}
    n = len(months)

    def series() -> list[int]:
        return [0] * n

    national = {k: [int(r[k]) for r in nat] for k in
                ("entities", "parents", "child_sites", "arrangements", "pharmacies", "out_of_state")}

    ch_a = defaultdict(series)
    ch_p = defaultdict(series)  # pharmacies summed over groups (a pharmacy sits in one group)
    for r in rows(outdir / "by_chain.csv"):
        g, i = chain_group(r["group"]), idx[r["month"][:7]]
        ch_a[g][i] += int(r["arrangements"])
        ch_p[g][i] += int(r["pharmacies"])
    mail_detail = defaultdict(dict)
    last = months[-1]
    for r in rows(outdir / "by_chain.csv"):
        if r["month"][:7] == last and r["group"] in MAIL:
            mail_detail[r["group"]] = {"arrangements": int(r["arrangements"]),
                                       "pharmacies": int(r["pharmacies"])}

    ty_e = defaultdict(series)
    ty_a = defaultdict(series)
    ty_detail: dict[str, dict[str, int]] = {}
    for r in rows(outdir / "by_type.csv"):
        g, i = type_group(r["entity_type"]), idx[r["month"][:7]]
        ty_e[g][i] += int(r["entities"])
        ty_a[g][i] += int(r["arrangements"])
        if r["month"][:7] == last:
            ty_detail[r["entity_type"]] = {"entities": int(r["entities"]),
                                           "arrangements": int(r["arrangements"])}

    st = defaultdict(lambda: {"entities": series(), "arrangements": series(), "pharmacies": series()})
    for r in rows(outdir / "by_state.csv"):
        i = idx[r["month"][:7]]
        for k in ("entities", "arrangements", "pharmacies"):
            st[r["state"]][k][i] = int(r[k])

    flows: dict[str, list[list[object]]] = defaultdict(list)
    out_of_state: dict[str, dict[str, list[int]]] = defaultdict(dict)
    for r in rows(outdir / "flows.csv"):
        m, a, b, k = r["month"][:7], r["entity_state"], r["pharmacy_state"], int(r["arrangements"])
        tot = out_of_state[m].setdefault(a, [0, 0])
        tot[0] += k
        if a != b:
            tot[1] += k
            flows[m].append([a, b, k])
    for m in flows:
        flows[m].sort(key=lambda x: (-int(x[2]), x[0], x[1]))

    dates = {}
    if dates_csv and dates_csv.exists():
        for r in rows(dates_csv):
            if r.get("effective_date"):
                dates.setdefault(r["law_id"], {"date": r["effective_date"], "basis": r.get("basis", ""),
                                               "url": r.get("source_url", ""),
                                               "confidence": r.get("confidence", "")})
    laws = []
    for r in rows(laws_csv):
        if "contract-pharmacy" not in r["kinds"].split("|"):
            continue
        eff, basis = r["effective_date"], "printed in the law"
        if not eff and r["law_id"] in dates:
            eff, basis = dates[r["law_id"]]["date"], dates[r["law_id"]]["basis"]
        laws.append({"law_id": r["law_id"], "state": r["state"], "title": r["title"], "bill": r["bill"],
                     "act": r["act"], "signed": r["signed_date"], "effective": eff,
                     "effective_basis": basis if eff else "", "kinds": r["kinds"].split("|")})
    laws.sort(key=lambda x: (x["effective"] or "9999", x["state"]))

    doc = {
        "months": months,
        "national": national,
        "chains": {"groups": CHAIN_GROUPS, "arrangements": {g: ch_a[g] for g in CHAIN_GROUPS},
                   "pharmacies": {g: ch_p[g] for g in CHAIN_GROUPS}, "mail_detail": mail_detail},
        "types": {"groups": TYPE_GROUPS, "entities": {g: ty_e[g] for g in TYPE_GROUPS},
                  "arrangements": {g: ty_a[g] for g in TYPE_GROUPS}, "detail": ty_detail},
        "states": {s: st[s] for s in sorted(st) if s != "??"},
        "flows": dict(flows),
        "out_of_state": dict(out_of_state),
        "ended_listed": [{k: int(v) for k, v in r.items()} for r in rows(outdir / "ended_listed.csv")],
        "laws": laws,
    }
    site.parent.mkdir(parents=True, exist_ok=True)
    site.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"{site}: {site.stat().st_size:,} bytes; {len(laws)} contract pharmacy laws, "
          f"{sum(1 for x in laws if x['effective'])} with an effective date")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(Path(a[0]), Path(a[1]), Path(a[2]) if len(a) == 4 else None, Path(a[-1]))
