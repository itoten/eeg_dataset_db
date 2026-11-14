#!/bin/sh
# Check one reviewer result against the sources, apply what holds, and commit with a message built from the reports.
# Usage: sh tools/audit/process.sh BATCH
set -e
cd "$(dirname "$0")/../.."
b="$1"
python3 tools/audit/apply.py "cache/audit/results/$b.json" > "cache/audit/reports/$b.apply.txt"
python3 tools/audit/decide.py "$b" > "cache/audit/reports/$b.decide.txt"
python3 tools/views.py > /dev/null
python3 tools/validate.py | tail -1
python3 - "$b" > "cache/audit/reports/$b.msg" <<'PY'
import json, sys
b = sys.argv[1]
rep = json.load(open(f"cache/audit/reports/{b}.json"))
na, nr = len(rep["accepted"]), len(rep["rejected"])
dec = open(f"cache/audit/reports/{b}.decide.txt").read().strip().splitlines()
rem = [l for l in dec if l.startswith("remove")]
der = [l for l in dec if l.startswith("derived_from")]
print(f"Audit {b}: {na} quoted claims checked on their pages, {len(rem)} rows removed\n")
print(f"A reviewer read the records, READMEs and papers of this batch and quoted every claim.")
print(f"tools/audit/apply.py fetched each cited page and kept a claim only when the quote is on the")
print(f"page and contains the value: {na} held, {nr} were kept out. Rows are removed only where the")
print(f"reviewer's quoted evidence (no EEG data, animals, part of a larger set, duplicate) was found on the page.\n")
for l in rem + der:
    print(l)
print("\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
PY
git add data views
git commit -q -F "cache/audit/reports/$b.msg"
git log --oneline | head -1
