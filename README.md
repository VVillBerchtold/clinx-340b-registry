<p>
  <a href="https://clinx.org">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/WillBerchtold/clinx-org/main/public/brand/clinx-wordmark-on-dark.svg">
      <img src="https://raw.githubusercontent.com/WillBerchtold/clinx-org/main/public/brand/clinx-wordmark-on-light.svg" alt="ClinX" height="28">
    </picture>
  </a>
</p>

# 340B registry history

A daily record of the federal 340B registry, kept from 23 November 2026.

The registry (HRSA's Office of Pharmacy Affairs Information System, OPAIS) lists every hospital
and clinic in the 340B drug pricing program, with its status, its addresses and its contract
pharmacies. HRSA posts a fresh export of it every day. Each export shows the registry as it is
that day. When a record is edited or deleted, the earlier version is not kept anywhere public.

This repository keeps every day. Any day since the start can be rebuilt exactly, as it was.

## What is kept

For each covered entity: its 340B ID, name, type, participation and dates, addresses, grant
number, Medicare, Medicaid and NPI numbers, and each contract pharmacy with its name, address and
dates.

People are not kept. The export names an authorizing official and a primary contact for each
entity. Those, pharmacy phone numbers and free-text comments are dropped when the file is read,
by [clinx-radar](https://github.com/WillBerchtold/clinx-radar), and never stored. The raw
export is deleted inside the run that read it.

## How it is laid out

| Where | What |
|---|---|
| `bases.json` | Each full copy: its day, size, SHA-256 and address |
| Releases `base-YYYY-MM-DD` | A full copy of the registry, one a month (about 23 MB, gzipped JSON) |
| `days/YYYY/YYYY-MM-DD.delta.json.gz` | One day: the full record of every entity that is new or changed since the day before, and the 340B ID of every entity that is gone |
| `days/YYYY/YYYY-MM-DD.md` | The same day as a plain report: what was added, removed, terminated, reinstated or changed |
| `tools/history.py` | Makes, applies and checks deltas; rebuilds a day |
| `tools/daily.sh` | The daily run |
| `tools/backfill.py` | Rebuilds the monthly history since 2010 from the dates one full copy carries |
| `tools/site_data.py` | Packs backfill.py's tables into the file the [registry history page](https://clinx.org/registry/) draws |
| `tools/cohorts.py`, `tools/concentration.py`, `tools/insurer.py` | The page's charts by start year, by pharmacy size and by pharmacy owner |
| `tools/whose_facts.py` | Every figure in the analysis [Whose pharmacies?](https://clinx.org/writing/whose-pharmacies/) |

A full copy for the whole country is about 300 MB of JSON. Keeping one a day would grow by
gigabytes a year, and most entities do not change from one day to the next. So a day is kept as
a delta, and a full copy is kept once a month.

## Rebuild a day

You need Python 3.12 or later. Nothing else is installed.

The newest day:

```bash
python3 -I tools/history.py latest newest.json
```

Any day: take the newest full copy on or before it, then apply each delta after the copy up to
that day, in order.

```bash
python3 -I tools/history.py apply base-2026-11-23.json.gz day.json days/2026/2026-11-24.delta.json.gz days/2026/2026-11-25.delta.json.gz
```

`apply` stops if a delta does not follow on from the day before it. Every delta is checked when
it is made: the new day is rebuilt from it and compared with the export's snapshot.

## The history before the daily record

The daily record starts on 23 November 2026. The monthly history back to 2010 on
[clinx.org/registry](https://clinx.org/registry/) is rebuilt from one full copy: every arrangement
keeps its begin date and, once ended, its termination date, and every entity keeps its own. An
arrangement is counted in force on a day D when it began on or before D and D is before its own
termination date and its entity's. That is today's record of the past, not a copy of the past:
records removed outright are missing, so the rebuild counts 2 to 7% fewer arrangements than were
published in each year since 2017, and later corrections of dates show. "Out of state" compares
the pharmacy's address with the entity's street address. Chains and insurer-owned pharmacies are
matched by name, because the registry records no owner.

```bash
python3 -I tools/backfill.py base.json out/
python3 -I tools/whose_facts.py base.json whose.json
```

## Each day's run

A scheduled job ([daily.yml](.github/workflows/daily.yml)) runs every morning:

1. `opais pull` opens HRSA's public 340B reports page and presses its daily export button, once.
2. `opais snapshot` reads the export and drops people. The raw file is deleted.
3. The last day kept is rebuilt and compared with the new one.
4. If the change looks unusual (the registry much shorter, or far more changed than on an
   ordinary day), the run stops, keeps nothing and opens an issue. A person looks before that
   day is kept.
5. Otherwise the day's delta and report are committed.

If HRSA has not posted a newer export, nothing is kept that day.

## What it does not show

- Why anything changed. A report says what differs between two days, never why.
- Anything before 23 November 2026. The export does carry its own dates: each contract pharmacy
  arrangement keeps its start date, and ended arrangements stay listed with the day they ended.
  Those dates say something about earlier years, but they are HRSA's record as it stands now,
  not a copy of how it stood then.
- Days HRSA did not post, or days the run could not reach the page.

## Source

U.S. Health Resources and Services Administration, Office of Pharmacy Affairs, 340B OPAIS,
Covered Entity Daily Export. Where this record and HRSA's own registry differ, HRSA's registry
governs.

## Licence

The code in `tools/` is under the MIT licence ([LICENSE](LICENSE)). The data (`days/`,
`bases.json` and the release files) is under CC BY 4.0 ([LICENSE-DATA](LICENSE-DATA)). Suggested
credit: "340B registry history, ClinX, CC BY 4.0."

The rest of ClinX: [clinx.org](https://clinx.org), the state filings in
[clinx-340b](https://github.com/WillBerchtold/clinx-340b), bills and the calendar in
[clinx-340b-bills](https://github.com/WillBerchtold/clinx-340b-bills).
