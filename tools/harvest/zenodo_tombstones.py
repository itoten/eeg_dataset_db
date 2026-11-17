"""Mark datasets whose Zenodo record was deleted, from the saved deletion notices (cache/zenodo/tombstones/<id>.json).

Usage: python3 tools/harvest/zenodo_tombstones.py

A notice is the 410 answer of https://zenodo.org/api/records/<id>, saved by zenodo_client. Each deleted
record gets an issue removed_by_provider, citing that API URL, and its Zenodo route becomes unavailable.
The dataset and what was known before stay as they are.
"""
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
from reglib import Batch  # noqa: E402


def main():
    B = Batch(datetime.date.today().isoformat())
    ids = {d["dataset_id"] for d in B.db["datasets"][1]}
    for f in sorted((ROOT / "cache/zenodo/tombstones").glob("*.json")):
        rid, b = f.stem, json.loads(f.read_text())
        t, did = b.get("tombstone") or {}, f"zenodo_{f.stem}"
        if b.get("status") != 410 or did not in ids:
            continue
        if any(r["dataset_id"] == did and r["type"] == "removed_by_provider" for r in B.db["issues"][1]):
            continue
        R = B.dataset(did)
        url = f"https://zenodo.org/api/records/{rid}"
        sid = R.source(f"zenodo_{rid}_tombstone", url, "repository_record", "third_party", title=f"Zenodo deletion notice for record {rid}",
                       note="The 410 answer of the Zenodo API for a deleted record")
        R.link(sid, "other")
        why, when = (t.get("removal_reason") or {}).get("id", ""), (t.get("removal_date") or "")[:10]
        loc = f'"message": "{b.get("message", "")}", removal_reason: {why}, removal_date: {when}'
        R.add_row("issues", type="removed_by_provider", description=f"Zenodo deleted the record (reason given: {why}; date: {when}).",
                  source_id=sid, locator=loc)
        R.ev("access_routes:zenodo.access_method", "unavailable", sid, loc, "script")
        print(did, why, when)
    B.save()


if __name__ == "__main__":
    main()
