"""Apply the relations from cache/audit/decisions/<batch>.json. Nothing is deleted.

Usage: python3 tools/audit/decide.py BATCH [--dry]

A dataset that holds nothing usable (no EEG signals, animals, not released) stays in the database: apply.py
gives it a content_class so that readers can tell it apart (docs/discussions/0003). This script only adds
relations: a checked copy_of whose target is a dataset in the database becomes derived_from, or subset_of
when the verdict is part_of_larger or the quote says "subset of" / "part of" / "portion of". A duplicate_record
verdict with a checked copy_of becomes derived_from as well; the record stays.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import db as dbmod  # noqa: E402

NOTES = {"derived_from": "The record says its data come from the other dataset (audit, quote checked)",
         "subset_of": "The record says it is part of the other dataset (audit, quote checked)"}


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
    rel = []
    for d in dec:
        if not d.get("copy_checked") or d["verdict"] == "unclear":
            continue
        t = str(d["copy_of"].get("url_or_doi", "")).rstrip("/").lower()
        t = re.sub(r"^https?://(dx\.)?doi\.org/", "", t)
        other = by_key.get(t) or by_key.get("https://doi.org/" + t)
        if other and other != d["dataset_id"]:
            sub = d["reason"] == "part_of_larger" or re.search(r"\b(subset of|part of|portion of)\b", str(d["copy_of"].get("quote", "")), re.I)
            rel.append((d["dataset_id"], other, "subset_of" if sub else "derived_from"))
    for a, b, k in rel:
        print(f"{k} {a} -> {b}")
    if dry:
        return
    for a, b, k in rel:
        if not any(r["dataset_id"] == a and r["relation"] == k and r["other_dataset_id"] == b for r in db["relations"][1]):
            sid = next((l["source_id"] for l in db["dataset_sources"][1] if l["dataset_id"] == a), "")
            db["relations"][1].append({"dataset_id": a, "relation": k, "other_dataset_id": b, "source_id": sid, "note": NOTES[k]})
    dbmod.save(db)


if __name__ == "__main__":
    main()
