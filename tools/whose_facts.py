"""The figures quoted in the essay "Whose pharmacies?" (clinx.org/writing/whose-pharmacies/).

  python3 -I whose_facts.py SNAPSHOT.json FACTS.json

Every number the essay prints is computed here from one registry snapshot, with the in-force rule
of backfill.py (in force on day D when begin <= D < min(own end, entity end)) and the owner names
of insurer.py. "Now" is the first of the snapshot's month, as on the registry page; rows still
open at closed Rite Aid stores are counted on the snapshot day itself.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from backfill import active, chain_of, d  # noqa: E402
from insurer import owner_of  # noqa: E402

HC = {"CH", "FQHCLA", "FQHC638"}
GROUPS = {"hc": HC, "cah": {"CAH"}, "dsh": {"DSH"}}


def main(snapshot: Path, out: Path) -> None:
    snap = json.loads(snapshot.read_text(encoding="utf-8"))
    taken = date.fromisoformat(snap["taken_on"])
    now = taken.replace(day=1)
    rows = []
    for e in snap["entities"]:
        ee = d(e.get("termination_date"))
        state = (e.get("street") or {}).get("state") or "??"
        for p in e.get("contract_pharmacies") or []:
            pb, pe = d(p.get("begin_date")), d(p.get("termination_date"))
            if pb is None:
                continue
            end = min(x for x in (pe, ee) if x) if (pe or ee) else None
            pstate = (p.get("address") or {}).get("state")
            who = owner_of(p)
            rows.append(dict(eid=e.get("id_340b"), etype=e.get("entity_type"), begin=pb, end=end,
                             own_end=pe, away=bool(pstate and pstate != state), who=who,
                             chain="insurer-owned" if who else chain_of(p), pid=p.get("pharmacy_id")))

    def on(day: date) -> list[dict]:
        return [r for r in rows if active(r["begin"], r["end"], day)]

    def share(xs: list[dict], test) -> float:
        return sum(1 for r in xs if test(r)) / max(len(xs), 1)

    f: dict = {"snapshot": taken.isoformat(), "now": now.isoformat()[:7]}
    N, J16, J17 = on(now), on(date(2016, 1, 1)), on(date(2017, 1, 1))
    f["arrangements"] = len(N)
    f["insurer"] = sum(1 for r in N if r["who"])
    f["insurer_share"] = f["insurer"] / len(N)
    f["insurer_share_2016"] = share(J16, lambda r: r["who"])
    ent = {r["eid"] for r in N}
    ent_i = {r["eid"] for r in N if r["who"]}
    f["entities"], f["entities_insurer"] = len(ent), len(ent_i)
    e16 = {r["eid"] for r in J16}
    f["entities_insurer_share_2016"] = len({r["eid"] for r in J16 if r["who"]}) / len(e16)
    f["owners"] = dict(Counter(r["who"] for r in N if r["who"]).most_common())
    f["groups"] = {}
    for g, types in GROUPS.items():
        a17 = [r for r in J17 if r["etype"] in types]
        an = [r for r in N if r["etype"] in types]
        f["groups"][g] = {"insurer_2017": share(a17, lambda r: r["who"]), "insurer_now": share(an, lambda r: r["who"]),
                          "away_now": share(an, lambda r: r["away"]),
                          "insurer_of_away_now": share([r for r in an if r["away"]], lambda r: r["who"])}

    # Out of state.
    def away(day: date) -> dict:
        xs = on(day)
        aw = [r for r in xs if r["away"]]
        oth = [r for r in xs if not r["who"]]
        ins = [r for r in xs if r["who"]]
        return {"share": len(aw) / len(xs), "insurer_part": share(aw, lambda r: r["who"]),
                "other_rate": share(oth, lambda r: r["away"]), "insurer_rate": share(ins, lambda r: r["away"])}
    f["away"] = {"2017-01": away(date(2017, 1, 1)), "2019-01": away(date(2019, 1, 1)),
                 "2023-01": away(date(2023, 1, 1)), "now": away(now)}

    # New arrangements by quarter start, 2022 to now, and those registered to start after the snapshot.
    q = defaultdict(lambda: [0, 0])
    for r in rows:
        b = r["begin"]
        if r["end"] is not None and r["end"] <= b:
            continue
        if date(2022, 1, 1) <= b <= now and b.day == 1 and b.month in (1, 4, 7, 10):
            q[b][0] += 1
            q[b][1] += bool(r["who"])
    parts = [i / n for n, i in q.values() if n]
    f["new_insurer_min"], f["new_insurer_max"] = min(parts), max(parts)
    later = [r for r in rows if r["begin"] > taken and (r["end"] is None or r["end"] > r["begin"])]
    f["pending_day"] = min(r["begin"] for r in later).isoformat() if later else None
    f["pending"] = len(later)
    f["pending_insurer"] = sum(1 for r in later if r["who"])

    # Hospitals and health centers, first of each month from 2017.
    months = [date(y, m, 1) for y in range(2017, now.year + 1) for m in range(1, 13) if date(y, m, 1) <= now]
    dsh, hc = [], []
    for m in months:
        xs = on(m)
        dsh.append(sum(1 for r in xs if r["etype"] == "DSH"))
        hc.append(sum(1 for r in xs if r["etype"] in HC))
    pk = max(range(len(dsh)), key=lambda i: dsh[i])
    f["dsh_peak_month"], f["dsh_peak"], f["dsh_now"] = months[pk].isoformat()[:7], dsh[pk], dsh[-1]
    f["hc_at_dsh_peak"], f["hc_now"] = hc[pk], hc[-1]
    f["hc_share_now"], f["dsh_share_now"] = hc[-1] / len(N), dsh[-1] / len(N)

    # Yearly ending rate: arrangements in force on 1 January that ended within the year.
    f["ending_rate"] = {}
    for y in range(2017, now.year + 1):
        xs = on(date(y, 1, 1))
        stop = min(date(y + 1, 1, 1), taken)
        f["ending_rate"][str(y)] = sum(1 for r in xs if r["end"] is not None and r["end"] <= stop) / len(xs)

    # Pharmacies: distinct ids in force, October 2023 against now, by group.
    def ids(day: date) -> dict[str, set]:
        out: dict[str, set] = defaultdict(set)
        for r in on(day):
            out[r["chain"]].add(r["pid"])
            out["all"].add(r["pid"])
        return out
    a, b = ids(date(2023, 10, 1)), ids(now)
    f["pharmacies"] = {g: [len(a[g]), len(b[g])] for g in ("all", "Rite Aid", "Walgreens", "CVS", "insurer-owned")}
    f["pharmacy_peak"] = None
    best = (0, None)
    for m in months:
        n = len({r["pid"] for r in on(m)})
        if n > best[0]:
            best = (n, m)
    f["pharmacy_peak"] = [best[1].isoformat()[:7], best[0]]
    f["insurer_left"] = len(a["insurer-owned"] - b["insurer-owned"])
    f["insurer_joined"] = len(b["insurer-owned"] - a["insurer-owned"])

    # Rows still open at Rite Aid on the snapshot day.
    ra = [r for r in rows if r["chain"] == "Rite Aid" and active(r["begin"], r["end"], taken)]
    f["rite_aid_open"] = {"arrangements": len(ra), "pharmacies": len({r["pid"] for r in ra}),
                          "entities": len({r["eid"] for r in ra}),
                          "health_center_share": share(ra, lambda r: r["etype"] in HC)}

    out.write_text(json.dumps(f, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps(f, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
