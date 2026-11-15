"""Apply checked removal and copy decisions from cache/audit/decisions/<batch>.json.

Usage: python3 tools/audit/decide.py BATCH [--dry]

remove (with its evidence quote found on the page) -> the dataset's rows are deleted from every table,
with the reason printed for the commit message. A duplicate verdict deletes only when the record itself
says so in a checked copy_of quote; a shared title is not enough. A part of a larger dataset holds data
of its own, so it is never deleted: a checked copy_of gives a subset_of relation instead. copy_of (checked) -> a derived_from relation to the DB
dataset whose source URL or DOI matches, else nothing. unclear and unchecked decisions are left alone.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import db as dbmod  # noqa: E402


def main():
    tag = sys.argv[1]
    dry = "--dry" in sys.argv
    dec = json.loads((ROOT / f"cache/audit/decisions/{tag}.json").read_text())
    db = dbmod.load()
    srcs = {s["source_id"]: s for s in db["sources"][1]}
    by_key = {}
    for l in db["dataset_sources"][1]:
        s = srcs.get(l["source_id"])
        if s:
            for k in (s["url"].rstrip("/").lower(), s["doi"].lower()):
                if k:
                    by_key.setdefault(k, l["dataset_id"])
    remove, rel = {}, []
    for d in dec:
        part = d["reason"] == "part_of_larger"
        if d["verdict"] == "remove" and d["evidence_checked"] and not part:
            if d["reason"] == "duplicate_record" and not d.get("copy_checked"):
                print(f"kept {d['dataset_id']}: duplicate_record is not stated by the record itself")
                continue
            remove[d["dataset_id"]] = d["reason"]
        elif d.get("copy_checked") and (d["verdict"] == "keep" or part):
            t = str(d["copy_of"].get("url_or_doi", "")).rstrip("/").lower()
            t = re.sub(r"^https?://(dx\.)?doi\.org/", "", t)
            other = by_key.get(t) or by_key.get("https://doi.org/" + t)
            if other and other != d["dataset_id"]:
                rel.append((d["dataset_id"], other, "subset_of" if part else "derived_from"))
    for did, why in sorted(remove.items()):
        print(f"remove {did}: {why}")
    for a, b, k in rel:
        print(f"{k} {a} -> {b}")
    if dry:
        return
    for t, (h, rows) in db.items():
        if "dataset_id" in h:
            rows[:] = [r for r in rows if r["dataset_id"] not in remove and not (t == "relations" and r.get("other_dataset_id") in remove)]
    used = {r["source_id"] for r in db["dataset_sources"][1]} | {r["source_id"] for r in db["evidence"][1]}
    db["sources"][1][:] = [s for s in db["sources"][1] if s["source_id"] in used]
    notes = {"derived_from": "The record says its data come from the other dataset (audit, quote checked)",
             "subset_of": "The record says it is part of the other dataset (audit, quote checked)"}
    for a, b, k in rel:
        if not any(r["dataset_id"] == a and r["relation"] == k and r["other_dataset_id"] == b for r in db["relations"][1]):
            sid = next((l["source_id"] for l in db["dataset_sources"][1] if l["dataset_id"] == a), "")
            db["relations"][1].append({"dataset_id": a, "relation": k, "other_dataset_id": b, "source_id": sid, "note": notes[k]})
    dbmod.save(db)


if __name__ == "__main__":
    main()
