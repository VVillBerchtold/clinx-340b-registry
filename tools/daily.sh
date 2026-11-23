#!/usr/bin/env bash
# One day of the registry's history.
#
#   1. pull today's export from HRSA's public 340B reports page (opais pull)
#   2. make a snapshot of it, without people (opais snapshot), and delete the raw file
#   3. rebuild the last recorded day from the newest full copy and the deltas
#   4. compare the two (opais changes): a plain report, and the tripwire
#   5. keep the day as a delta, checked by rebuilding the new day from it
#   6. on the first run of a month, also write a new full copy for a release
#
# Needs: OPAIS_DIR (a checkout of clinx-radar), uv, python3, curl.
# Optional: BROWSER (path of a browser for the pull), ACCEPT=true (keep a day the tripwire
# stopped, after a person has looked), OUT (where the run's notes go; default _out).
# Exit 0: a day was kept, or there was nothing new. Exit 3: the tripwire stopped it.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"
out="${OUT:-_out}"
mkdir -p "$out"
: > "$out/line.txt"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
chmod 700 "$work"
mkdir "$work/raw"

opais() { uv run --quiet --project "$OPAIS_DIR" --extra pull opais "$@"; }

echo "Pulling today's export"
pull_args=(pull --out "$work/raw" --timeout 600)
[[ -n "${BROWSER:-}" ]] && pull_args+=(--browser "$BROWSER")
info="$(opais "${pull_args[@]}")"
echo "$info"
day="$(python3 -I -c 'import json,sys; print(json.loads(sys.argv[1])["export_date"])' "$info")"

if [[ -e "days/${day:0:4}/$day.delta.json.gz" ]]; then
  echo "The export of $day is already kept. Nothing to do."
  echo "export of $day already kept" > "$out/line.txt"
  exit 0
fi

(cd "$work/raw" && unzip -q ./*.zip && rm -f ./*.zip)
opais snapshot "$work/raw/OPA_CE_DAILY_PUBLIC.JSON" --date "$day" --out "$work/new.json"
rm -rf "$work/raw"

echo "Rebuilding the last recorded day"
python3 -I tools/history.py latest "$work/old.json"

same="$(python3 -I - "$work/old.json" "$work/new.json" <<'PY'
import json, sys
a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))
print("yes" if a["source_sha256"] == b["source_sha256"] or a["taken_on"] >= b["taken_on"] else "no")
PY
)"
if [[ "$same" == "yes" ]]; then
  echo "HRSA has not posted a newer export than the last one kept. Nothing to do."
  echo "no newer export than the last one kept" > "$out/line.txt"
  exit 0
fi

mkdir -p "days/${day:0:4}"
set +e
opais changes "$work/old.json" "$work/new.json" --format md --out "days/${day:0:4}/$day.md"
code=$?
opais changes "$work/old.json" "$work/new.json" --format json --out "$work/changes.json"
set -e
if [[ $code -eq 3 && "${ACCEPT:-false}" != "true" ]]; then
  cp "days/${day:0:4}/$day.md" "$out/report.md"
  rm "days/${day:0:4}/$day.md"
  echo "The tripwire stopped the day; nothing kept. The report is in $out/report.md."
  exit 3
elif [[ $code -ne 0 && $code -ne 3 ]]; then
  echo "opais changes failed with code $code"
  exit 1
fi
if [[ $code -eq 3 ]]; then
  printf '\n> Kept after a person looked: the tripwire gave a reason this day (see above).\n' \
    >> "days/${day:0:4}/$day.md"
fi
cp "days/${day:0:4}/$day.md" "$out/report.md"

python3 -I tools/history.py record "$work/old.json" "$work/new.json"

python3 -I - "$work/changes.json" "$day" > "$out/line.txt" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))["summary"]["counts"]
words = {
    "entities_added": "entities added", "entities_removed": "entities removed",
    "terminations": "terminations", "reinstatements": "reinstatements",
    "field_changes": "field changes", "pharmacies_added": "contract pharmacies added",
    "pharmacies_removed": "contract pharmacies removed",
    "pharmacies_terminated": "contract pharmacies newly terminated",
}
parts = [f"{c[k]} {w}" for k, w in words.items() if c.get(k)]
print(f"Registry of {sys.argv[2]}: " + (", ".join(parts) if parts else "no changes"))
PY

last_base="$(python3 -I -c 'import json; print(sorted(b["date"] for b in json.load(open("bases.json"))["bases"])[-1])')"
if [[ "${last_base:0:7}" < "${day:0:7}" ]]; then
  echo "First day kept this month: writing a full copy"
  python3 -I tools/history.py base "$work/new.json" "$out/base-$day.json.gz"
  echo "$day" > "$out/base-day.txt"
fi

cat "$out/line.txt"
