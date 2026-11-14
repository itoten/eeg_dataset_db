"""Read more of the BIDS metadata already cached for OpenNeuro datasets.

Usage: python3 tools/harvest/bids_more.py [YYYY-MM-DD]

From the one sidecar and one channels file read per dataset (cache/openneuro):
- InstitutionName -> providers.csv and datasets.provider_ids (single institution only)
- TaskDescription -> tasks.description of the task whose name equals the sidecar's TaskName
- SubjectArtefactDescription -> quality_info (recording_notes)
- a `status` column in channels.tsv -> quality_info (bad_channel_marks): the release marks channels good or bad
Nothing is counted; only what the files say is recorded, cited to the file.
"""
import datetime, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
from reglib import Batch  # noqa: E402

BY = "script"


def slug(s):
    b = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:50].strip("_") or "x"
    return b if b[0].isalpha() else "i_" + b


def clean(s):
    return " ".join(str(s).split())


def main():
    today = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    B = Batch(today)
    db = B.db
    have = {d["dataset_id"]: d for d in db["datasets"][1]}
    srcs = {s["source_id"] for s in db["sources"][1]}
    tasks = {}
    for t in db["tasks"][1]:
        tasks.setdefault(t["dataset_id"], []).append(t)
    prov = {p["provider_id"]: p for p in db["providers"][1]}
    n = {"provider": 0, "task": 0, "artefact": 0, "status": 0}
    for path in sorted((ROOT / "cache" / "openneuro").glob("ds*.json")):
        c = json.loads(path.read_text())
        ds = c["dataset"]["id"].lower()
        if ds not in have:
            continue
        side = next(((k, v) for k, v in c["texts"].items() if k.startswith("sidecar:")), None)
        chan = next(((k, v) for k, v in c["texts"].items() if k.startswith("channels:")), None)
        R = None
        if side and f"{ds}_sidecar" in srcs:
            sid = f"{ds}_sidecar"
            try:
                j = json.loads(side[1]["text"])
            except ValueError:
                j = None
            if isinstance(j, dict):
                R = B.dataset(ds)
                inst = clean(j.get("InstitutionName") or "")
                if inst and inst.lower() not in ("n/a", "na", "unknown", "none") and not have[ds]["provider_ids"]:
                    pid = slug(inst)
                    if pid not in prov or prov[pid]["name"] != inst:
                        pid = pid if pid not in prov else f"{pid}_{len(prov)}"
                        B.provider(pid, inst, sid, locator="InstitutionName", by=BY)
                        prov[pid] = {"name": inst}
                    R.ev("provider_ids", pid, sid, "InstitutionName", BY)
                    n["provider"] += 1
                tn, td = clean(j.get("TaskName") or ""), clean(j.get("TaskDescription") or "")
                if tn and td and td.lower() not in ("n/a", "na"):
                    for t in tasks.get(ds, []):
                        if t["task_name"].casefold() == tn.casefold() and not t["description"]:
                            t["description"] = f"{td[:600]} [{sid}]" if td.endswith(".") or td.endswith("]") else f"{td[:600]}. [{sid}]"
                            n["task"] += 1
                art = clean(j.get("SubjectArtefactDescription") or "")
                if art and art.lower() not in ("n/a", "na", "none", "unknown"):
                    R.add_row("quality_info", BY, kind="recording_notes", description=art[:400], form="sidecar field SubjectArtefactDescription",
                              source_id=sid, locator="SubjectArtefactDescription")
                    n["artefact"] += 1
        if chan and f"{ds}_channels" in srcs:
            head = chan[1]["text"].split("\n", 1)[0].rstrip("\r").split("\t")
            if "status" in [h.lstrip("﻿") for h in head]:
                R = R or B.dataset(ds)
                extra = " and a status_description column" if "status_description" in head else ""
                R.add_row("quality_info", BY, kind="bad_channel_marks",
                          description=f"The channels file has a status column (BIDS: good or bad per channel){extra}.", form="status column of channels.tsv",
                          source_id=f"{ds}_channels", locator="header row")
                n["status"] += 1
    B.save()
    print(n)


if __name__ == "__main__":
    main()
