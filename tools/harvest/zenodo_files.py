"""Read the file lists of Zenodo records: signal file formats, and the access right of records first read through DataCite.

Usage: python3 tools/harvest/zenodo_files.py [YYYY-MM-DD]

Records registered through DataCite (zenodo_datacite.py) are fetched again from the Zenodo API when
zenodo.org answers; their source then points to the Zenodo record and the access method is filled.
file_formats is set from file names whose extension belongs to one EEG format (.edf, .bdf, .vhdr,
.set, .fif, .gdf, .cnt, .mefd); the locator quotes one such file name. Archives are not opened, and
.mat, .npy, .csv and the like are left out because the name does not say they hold signals.
"""
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
from reglib import Batch  # noqa: E402
import zenodo_client  # noqa: E402

CACHE = ROOT / "cache" / "zenodo"
EXT = {".edf": "edf", ".bdf": "bdf", ".vhdr": "brainvision", ".set": "eeglab_set", ".fif": "fif", ".gdf": "gdf", ".cnt": "cnt", ".mefd": "mef"}
ACCESS = {"open": ("direct_download", "none"), "restricted": ("request_form_or_email", "Request access on the Zenodo record page; the uploader approves requests")}


def refetch(rid):
    try:
        d = zenodo_client.get(f"https://zenodo.org/api/records/{rid}")
    except Exception as e:
        print("zenodo:", rid, e)
        return None
    return d if "metadata" in d else None


def main():
    B = Batch(sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat())
    src = {s["source_id"]: s for s in B.db["sources"][1]}
    routes = {(r["dataset_id"], r["route_id"]): r for r in B.db["access_routes"][1]}
    n_ref = n_fmt = 0
    for ln in list(B.db["dataset_sources"][1]):
        did, sid = ln["dataset_id"], ln["source_id"]
        if not (did.startswith("zenodo_") and ln["role"] == "distribution" and sid.startswith("zenodo_")):
            continue
        rid = sid.split("_")[1]
        f = CACHE / f"{rid}.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text())
        R = B.dataset(did)
        if d.get("_datacite"):
            new = refetch(rid)
            if not new:
                continue
            f.write_text(json.dumps(new))
            d = new
            n_ref += 1
            url = f"https://zenodo.org/records/{rid}"
            src[sid].update(url=url, note="Read through the Zenodo API (first found through DataCite); the record creators were not compared with the authors of a paper")
            acc = d["metadata"].get("access_right")
            if acc in ACCESS and (did, "zenodo") in routes and not routes[(did, "zenodo")]["access_method"]:
                R.ev("access_routes:zenodo.access_method", ACCESS[acc][0], sid, f"access_right: {acc}", "script")
                R.ev("access_routes:zenodo.human_steps", ACCESS[acc][1], sid, f"access_right: {acc}", "script")
                if acc == "open":
                    R.ev("access_routes:zenodo.automation_tool", "zenodo-api", sid, "Files listed in the record API with download links", "script")
        found = {}
        for x in d.get("files") or []:
            fmt = EXT.get(os.path.splitext(x["key"])[1].lower())
            if fmt:
                found.setdefault(fmt, x["key"])
        if found and not R.row["file_formats"]:
            fmts = sorted(found)
            R.ev("file_formats", ";".join(fmts), sid, "files: " + ", ".join(found[k] for k in fmts)[:200], "script",
                 note="From file names in the record's file list; archives were not opened")
            n_fmt += 1
    B.save()
    print(n_ref, "records fetched again;", n_fmt, "datasets with file_formats")


if __name__ == "__main__":
    main()
