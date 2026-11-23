"""Keep the 340B registry's history small: one full copy a month, one delta a day.

A snapshot (from `opais snapshot`) is about 300 MB of JSON for the whole country.
Keeping one a day would grow by gigabytes a year. Most entities do not change from
one day to the next, so a day is kept as a delta: the full record of every entity
that is new or changed, and the 340B ID of every entity that is gone. Entities are
kept in 340B ID order, as `opais snapshot` writes them.

  make   OLD NEW OUT.json.gz     write the delta from snapshot OLD to snapshot NEW
  apply  BASE OUT DELTA...       rebuild a day: the base snapshot, then each delta in order
  check  OLD NEW                 make the delta, apply it to OLD, and confirm the result
                                 is NEW byte for byte (exit 1 if not)
  latest OUT                     rebuild the newest recorded day: download the newest full
                                 copy named in bases.json, check its fingerprint, then apply
                                 every later delta in days/
  record OLD NEW                 write days/YYYY/<day>.delta.json.gz, apply it back to OLD and
                                 confirm it gives NEW (stops if not)
  base   NEW OUT.json.gz         write NEW as a full copy, ready to attach to a release

Standard library only. Run with python3 -I.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

FORMAT = "clinx-registry-delta"
VERSION = 1


def load(path: Path) -> dict[str, Any]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def by_id(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for e in snapshot["entities"]:
        key = e["id_340b"]
        if key in out:
            raise SystemExit(f"two entities share the 340B ID {key}")
        out[key] = e
    return out


def make(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    a, b = by_id(old), by_id(new)
    upserts = [b[k] for k in sorted(b) if k not in a or canon(a[k]) != canon(b[k])]
    removed = sorted(set(a) - set(b))
    head = {k: v for k, v in new.items() if k != "entities"}
    return {
        "format": FORMAT,
        "format_version": VERSION,
        "from_date": old["taken_on"],
        "to_date": new["taken_on"],
        "from_sha256": old.get("source_sha256"),
        "head": head,
        "upserts": upserts,
        "removed": removed,
    }


def apply(base: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    if delta.get("format") != FORMAT:
        raise SystemExit("not a registry delta")
    if delta["from_date"] != base["taken_on"]:
        raise SystemExit(f"delta starts on {delta['from_date']}, base is {base['taken_on']}")
    cur = by_id(base)
    for k in delta["removed"]:
        cur.pop(k)
    for e in delta["upserts"]:
        cur[e["id_340b"]] = e
    if len(cur) != delta["head"].get("entity_count", len(cur)):
        raise SystemExit("the rebuilt day does not hold as many entities as the delta says")
    return {**delta["head"], "entities": [cur[k] for k in sorted(cur)]}


def write(obj: dict[str, Any], path: Path) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=None, sort_keys=True)
    if path.suffix == ".gz":
        with gzip.GzipFile(path, "wb", mtime=0, compresslevel=9) as f:
            f.write(text.encode("utf-8"))
    else:
        path.write_text(text, encoding="utf-8")


ROOT = Path(__file__).resolve().parent.parent
BASES = ROOT / "bases.json"
DAYS = ROOT / "days"


def delta_path(day: str) -> Path:
    return DAYS / day[:4] / f"{day}.delta.json.gz"


def bases() -> list[dict[str, str]]:
    found: list[dict[str, str]] = json.loads(BASES.read_text(encoding="utf-8"))["bases"]
    return sorted(found, key=lambda b: b["date"])


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def latest(out: Path) -> str:
    base = bases()[-1]
    local = out.with_name(Path(base["url"]).name)
    if not local.exists() or sha256(local) != base["sha256"]:
        urllib.request.urlretrieve(base["url"], local)  # noqa: S310 (a fixed https address)
    if sha256(local) != base["sha256"]:
        raise SystemExit(f"the full copy of {base['date']} does not match its fingerprint")
    day = load(local)
    later = sorted(p for p in DAYS.glob("*/*.delta.json.gz") if p.name[:10] > base["date"])
    for p in later:
        day = apply(day, load(p))
    write(day, out)
    return str(day["taken_on"])


def write_base(new: Path, out: Path) -> None:
    with open(new, "rb") as src, gzip.GzipFile(out, "wb", mtime=0, compresslevel=9) as f:
        for block in iter(lambda: src.read(1 << 20), b""):
            f.write(block)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, args = argv[1], [Path(a) for a in argv[2:]]
    if cmd == "make" and len(args) == 3:
        d = make(load(args[0]), load(args[1]))
        write(d, args[2])
        print(f"{d['from_date']} -> {d['to_date']}: {len(d['upserts'])} new or changed, "
              f"{len(d['removed'])} gone; {args[2].stat().st_size:,} bytes")
        return 0
    if cmd == "apply" and len(args) >= 3:
        day = load(args[0])
        for p in args[2:]:
            day = apply(day, load(p))
        write(day, args[1])
        print(f"rebuilt {day['taken_on']}: {len(day['entities'])} entities")
        return 0
    if cmd == "check" and len(args) == 2:
        old, new = load(args[0]), load(args[1])
        rebuilt = apply(old, json.loads(canon(make(old, new))))
        ok = canon(rebuilt) == canon(new)
        print("check: the rebuilt day matches" if ok else "check: MISMATCH")
        return 0 if ok else 1
    if cmd == "latest" and len(args) == 1:
        print(f"rebuilt {latest(args[0])} from the full copy and the deltas")
        return 0
    if cmd == "record" and len(args) == 2:
        old, new = load(args[0]), load(args[1])
        d = make(old, new)
        path = delta_path(str(d["to_date"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        write(d, path)
        if canon(apply(old, load(path))) != canon(new):
            path.unlink()
            raise SystemExit("the delta does not rebuild the new day; nothing kept")
        print(f"{d['from_date']} -> {d['to_date']}: {len(d['upserts'])} new or changed, "
              f"{len(d['removed'])} gone; {path.stat().st_size:,} bytes")
        return 0
    if cmd == "base" and len(args) == 2:
        write_base(args[0], args[1])
        print(f"{args[1].name}: {args[1].stat().st_size:,} bytes, sha256 {sha256(args[1])}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
