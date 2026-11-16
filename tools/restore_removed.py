"""One-off: put back datasets that earlier audit passes deleted from the tables (see docs/discussions/0003).

Usage: python3 tools/restore_removed.py IDS_JSON
IDS_JSON is a list of [dataset_id, commit] where the commit is the last one that still held the dataset.
Every row of the dataset (all tables), the relations that point at it and the sources it uses come back from that commit.
"""
import csv, io, json, subprocess, sys, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import csvio  # noqa: E402

def git_show(rev, path):
    r = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True, cwd=ROOT)
    return list(csv.DictReader(io.StringIO(r.stdout))) if r.returncode == 0 else []

ids = json.load(open(sys.argv[1]))
by_rev = collections.defaultdict(set)
for i, c in ids:
    by_rev[c].add(i)
tables = csvio.tables()
db = {t: csvio.read_rows(info["path"]) for t, info in tables.items()}
keyset = {t: {tuple(r.get(c, "") for c in db[t][0]) for r in db[t][1]} for t in tables}
have_src = {r["source_id"] for r in db["sources"][1]}
n = collections.Counter()
for rev, want in by_rev.items():
    for t, info in tables.items():
        path = str(info["path"].relative_to(ROOT))
        old = git_show(rev, path)
        if not old or "dataset_id" not in old[0]:
            continue
        h = db[t][0]
        for r in old:
            mine = r["dataset_id"] in want or (t == "relations" and r.get("other_dataset_id") in want)
            if not mine:
                continue
            row = {c: r.get(c, "") for c in h}
            k = tuple(row[c] for c in h)
            if k not in keyset[t]:
                db[t][1].append(row); keyset[t].add(k); n[t] += 1
    # sources the restored rows use
    need = {r["source_id"] for t in ("dataset_sources", "evidence") for r in db[t][1] if r.get("source_id") and r["dataset_id"] in want}
    need |= {r["source_id"] for r in db["relations"][1] if r.get("source_id") and (r["dataset_id"] in want or r["other_dataset_id"] in want)}
    for r in git_show(rev, "data/sources.csv"):
        if r["source_id"] in need and r["source_id"] not in have_src:
            db["sources"][1].append({c: r.get(c, "") for c in db["sources"][0]}); have_src.add(r["source_id"]); n["sources"] += 1
for t, info in tables.items():
    csvio.write_rows(info["path"], *db[t], info["keys"])
print(dict(n))
