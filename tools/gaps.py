"""Count what is still unchecked: empty cells of the main datasets columns, by source group.

Usage: python3 tools/gaps.py
"""
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLS = ["modalities", "domains", "license_spdx", "year_published", "n_subjects_reported", "hours_reported", "size_gb_reported",
        "n_channels_eeg", "sampling_rates_hz", "montage_systems", "devices", "paradigms", "best_access_method"]


def group(i):
    for p, g in (("ds", "OpenNeuro"), ("nm", "NEMAR"), ("zenodo_", "Zenodo"), ("figshare_", "figshare"), ("hf_", "HuggingFace"), ("bnci_", "BNCI")):
        if i.startswith(p) and (p != "ds" or i[2:].isdigit()) and (p != "nm" or i[2:].isdigit()):
            return g
    return "other"


def main():
    rows = list(csv.DictReader(open(ROOT / "views" / "datasets_wide.csv", encoding="utf-8")))
    ev = defaultdict(set)
    for r in csv.DictReader(open(ROOT / "data" / "evidence.csv", encoding="utf-8")):
        if r["status"] in ("current", "conflicting"):
            ev[r["dataset_id"]].add(r["field"].split(":")[0] if ":" in r["field"] else r["field"])
    g = defaultdict(list)
    for r in rows:
        g[group(r["dataset_id"])].append(r)
    print(f"{'group':12s} {'n':>5s} " + " ".join(f"{c[:11]:>11s}" for c in COLS) + "  paper_linked")
    for k, rs in sorted(g.items(), key=lambda x: -len(x[1])):
        line = " ".join(f"{sum(1 for r in rs if not r[c]):>11d}" for c in COLS)
        print(f"{k:12s} {len(rs):>5d} {line}  {sum(1 for r in rs if r['paper_url']):>5d}")
    print("(numbers are datasets with an EMPTY cell; the last column counts datasets with a paper source linked)")


if __name__ == "__main__":
    main()
