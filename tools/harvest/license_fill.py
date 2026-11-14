"""Record licenses that a repository record states but an earlier mapping did not recognise.

Usage: python3 tools/harvest/license_fill.py [YYYY-MM-DD]

For datasets whose license cell is empty although their Zenodo or NEMAR record has a license field:
a name that matches a listed SPDX identifier is mapped; any other stated license becomes
LicenseRef-other (or LicenseRef-custom-research-only for "non-commercial research use") with the
record's words in license_note. A record whose field says unknown, n/a or nothing is left empty.
"""
import datetime, glob, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
from reglib import Batch  # noqa: E402

MAP = {"mit-license": "MIT", "mit": "MIT", "odc-by": "ODC-By-1.0", "odc-by-1.0": "ODC-By-1.0", "open data commons attribution license v1.0": "ODC-By-1.0",
       "cc-by-3.0-us": "CC-BY-3.0-US", "cc-by-nd-2.5": "CC-BY-ND-2.5", "cc-by-nc-sa-3.0": "CC-BY-NC-SA-3.0", "cc-by-1.0": "CC-BY-1.0",
       "cdla-permissive-2.0": "CDLA-Permissive-2.0", "cdla-sharing-1.0": "CDLA-Sharing-1.0", "cern-ohl-s-2.0": "CERN-OHL-S-2.0"}
EMPTY = {"", "unknown", "n/a", "none", "null"}


def main():
    today = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    B = Batch(today)
    have = {d["dataset_id"]: d for d in B.db["datasets"][1]}
    items = []  # (dataset_id, source_id, raw license, label)
    best = {}
    for p in glob.glob(str(ROOT / "cache/zenodo/*.json")):
        if not Path(p).stem.isdigit():
            continue
        d = json.load(open(p))
        c = str(d.get("conceptrecid") or d["id"])
        if c not in best or d["metadata"].get("publication_date", "") > best[c]["metadata"].get("publication_date", ""):
            best[c] = d
    for c, d in best.items():
        items.append((f"zenodo_{c}", f"zenodo_{d['id']}", (d["metadata"].get("license") or {}).get("id", ""), "License field"))
    for x in json.load(open(ROOT / "cache/nemar/list.json")):
        if x["dataset_id"].startswith("nm"):
            items.append((x["dataset_id"], f"{x['dataset_id']}_nemar", x.get("license") or "", "License"))
    n = 0
    srcs = {s["source_id"] for s in B.db["sources"][1]}
    for did, sid, raw, label in items:
        if did not in have or have[did]["license_spdx"] or sid not in srcs or raw.strip().lower() in EMPTY:
            continue
        key = raw.strip().lower()
        R = B.dataset(did)
        if key in MAP:
            R.ev("license_spdx", MAP[key], sid, f"{label}: {raw}", "script")
        else:
            val = "LicenseRef-custom-research-only" if re.search(r"non-?commercial research", key) else "LicenseRef-other"
            R.ev("license_spdx", val, sid, f"{label}: {raw[:120]}", "script")
            R.set(license_note=(have[did]["license_note"] + " " if have[did]["license_note"] else "") + f"The record's license field begins '{' '.join(raw.split()).split('. ')[0].rstrip('.')[:200]}' [{sid}].")
        n += 1
    B.save()
    print(n, "licenses recorded")


if __name__ == "__main__":
    main()
