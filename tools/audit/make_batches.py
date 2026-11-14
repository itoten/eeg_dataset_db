"""Write audit batches (cache/audit/batches/<name>_<n>.json) for reviewers who read the sources.

Usage: python3 tools/audit/make_batches.py GROUP SIZE
GROUP: a dataset_id prefix (zenodo_, figshare_, dv_, hf_, ds, nm) or "other" (everything else).
Each item carries the dataset's current values and its linked sources, so a reviewer can check them.
"""
import csv, json, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIXES = ("zenodo_", "figshare_", "dv_", "hf_", "ds", "nm")


def group_of(i):
    for p in PREFIXES:
        if i.startswith(p) and (p not in ("ds", "nm") or i[2:].isdigit()):
            return p
    return "other"


def main():
    group, size = sys.argv[1], int(sys.argv[2])
    wide = list(csv.DictReader(open(ROOT / "views/datasets_wide.csv", encoding="utf-8")))
    src = {r["source_id"]: r for r in csv.DictReader(open(ROOT / "data/sources.csv", encoding="utf-8"))}
    links = defaultdict(list)
    for r in csv.DictReader(open(ROOT / "data/dataset_sources.csv", encoding="utf-8")):
        s = src.get(r["source_id"])
        if s and s["url"]:
            links[r["dataset_id"]].append({"url": s["url"], "title": s["title"], "kind": s["kind"], "source_type": s["source_type"], "role": r["role"]})
    rel = defaultdict(list)
    for r in csv.DictReader(open(ROOT / "data/relations.csv", encoding="utf-8")):
        rel[r["dataset_id"]].append(f"{r['relation']} {r['other_dataset_id']}")
    keys = ["name", "modalities", "domains", "license_spdx", "n_subjects_reported", "n_channels_eeg", "sampling_rates_hz", "devices",
            "montage_systems", "paradigms", "hours_reported", "size_gb_reported", "best_access_method"]
    items = [{"dataset_id": r["dataset_id"], **{k: r[k] for k in keys}, "relations": rel[r["dataset_id"]], "sources": links[r["dataset_id"]]}
             for r in wide if group_of(r["dataset_id"]) == group]
    out = ROOT / "cache/audit/batches"
    out.mkdir(parents=True, exist_ok=True)
    tag = group.rstrip("_")
    for n in range(0, len(items), size):
        (out / f"{tag}_{n // size:03d}.json").write_text(json.dumps(items[n:n + size], ensure_ascii=False, indent=1))
    print(len(items), "items in", (len(items) + size - 1) // size, "batches")


if __name__ == "__main__":
    main()
