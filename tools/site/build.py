"""Build a browsable, read-only HTML page of the DB (cache/site/index.html).

Usage: python3 tools/site/build.py

The page embeds the data of data/*.csv (datasets, their child rows, evidence and sources) as
JSON in tools/site/template.html. Nothing from local/ is included.
"""

import csv
import datetime
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "cache" / "site" / "index.html"


def rows(name):
    with open(ROOT / "data" / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def by_ds(name):
    out = defaultdict(list)
    for r in rows(name):
        out[r["dataset_id"]].append(r)
    return out


def repo_of(url):
    host = urlparse(url).netloc.lower()
    for key, label in (("openneuro", "OpenNeuro"), ("physionet", "PhysioNet"), ("bnci-horizon", "BNCI Horizon"),
                       ("zenodo", "Zenodo"), ("figshare", "figshare"), ("osf.io", "OSF"), ("synapse", "Synapse"),
                       ("dataverse", "Dataverse"), ("rdr.kuleuven", "Dataverse"), ("gigadb", "GigaDB"), ("doi.org/10.5524", "GigaDB"),
                       ("mendeley", "Mendeley Data"), ("isip.piconepress", "TUH (NEDC)"), ("bcmi.sjtu", "SEED (BCMI)"),
                       ("github", "GitHub"), ("g-node", "GIN"), ("kaggle", "Kaggle"), ("nitrc", "INDI / NITRC"), ("tu-berlin", "TU Berlin")):
        if key in host or key in url:
            return label
    return "Other"


def main():
    wide = {r["dataset_id"]: r for r in rows("datasets")}
    view = {r["dataset_id"]: r for r in csv.DictReader(open(ROOT / "views" / "datasets_wide.csv", encoding="utf-8"))}
    srcs = rows("sources")
    sidx = {s["source_id"]: i for i, s in enumerate(srcs)}
    S = [[s["source_id"], s["url"], s["title"], s["kind"], s["source_type"], s["doi"]] for s in srcs]
    ev, links = by_ds("evidence"), by_ds("dataset_sources")
    routes, setups, tasks = by_ds("access_routes"), by_ds("acquisition_setups"), by_ds("tasks")
    groups, pfields, anns = by_ds("participant_groups"), by_ds("participant_fields"), by_ds("annotations")
    issues, rels, aliases, chans = by_ds("issues"), by_ds("relations"), by_ds("aliases"), by_ds("channels")
    quality = by_ds("quality_info")
    D = []
    for i, d in wide.items():
        v = view[i]
        dist = [l for l in links[i] if l["role"] == "distribution"]
        repo = repo_of(srcs[sidx[dist[0]["source_id"]]]["url"]) if dist else "Other"
        ch = defaultdict(list)
        for c in sorted(chans[i], key=lambda c: int(c["order"] or 0)):
            ch[c["setup_id"]].append([c["channel_name"], c["channel_type"]])
        D.append({
            "id": i, "name": d["name"], "full": d["full_title"], "mod": d["modalities"], "dom": d["domains"],
            "lic": d["license_spdx"], "licn": d["license_note"], "terms": [d["ml_training_terms"], d["commercial_use_terms"], d["derivative_terms"]],
            "termsn": d["terms_note"], "bids": d["is_bids"], "year": d["year_published"],
            "subj": d["n_subjects_reported"], "sess": d["n_sessions_reported"], "rec": d["n_recordings_reported"],
            "hours": d["hours_reported"], "gb": d["size_gb_reported"],
            "rel_counts": [d["n_subjects_release"], d["n_recordings_release"], d["hours_release"]],
            "best": d["best_access_method"], "tier": d["access_tier"], "nch": d["n_channels_eeg"], "fs": d["sampling_rates_hz"],
            "mont": d["montage_systems"], "dev": d["devices"], "par": d["paradigms"], "notes": d["notes"], "upd": d["last_updated_on"],
            "doc": v["documents_checked"] == "true", "impl": v["implementation_checked"] == "true", "repo": repo,
            "links": [[l["role"], sidx[l["source_id"]]] for l in links[i] if l["source_id"] in sidx],
            "ev": [[e["field"], e["value"], sidx.get(e["source_id"], -1), e["locator"], e["checked_on"], e["checked_by"], e["status"]]
                   for e in ev[i] if e["status"] in ("current", "conflicting")],
            "routes": [[r["route_id"], r["route_kind"], r["url"], r["access_method"], r["human_steps"], r["automation_tool"], r["access_observed"]] for r in routes[i]],
            "setups": [{k: r[k] for k in r if k != "dataset_id" and r[k]} for r in setups[i]],
            "tasks": [[r["task_id"], r["task_name"], r["paradigms"], r["description"]] for r in tasks[i]],
            "groups": [{k: r[k] for k in r if k != "dataset_id" and r[k]} for r in groups[i]],
            "pf": [[r["field_name"], r["category"], r["description"], r["unit"]] for r in pfields[i]],
            "ann": [[r["item"], r["name"], r["labels"], sidx.get(r["source_id"], -1), r["locator"]] for r in anns[i]],
            "iss": [[r["type"], r["description"], sidx.get(r["source_id"], -1)] for r in issues[i]],
            "qual": [[r["kind"], r["description"], r["form"], sidx.get(r["source_id"], -1)] for r in quality[i]],
            "rel": [[r["relation"], r["other_dataset_id"], r["note"]] for r in rels[i]],
            "alias": [[r["alias"], r["alias_type"]] for r in aliases[i]],
            "ch": ch,
        })
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True).stdout.strip()
    data = {"meta": {"commit": commit, "built": datetime.date.today().isoformat()}, "S": S, "D": D}
    page = (ROOT / "tools" / "site" / "template.html").read_text(encoding="utf-8")
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("\ufffd", "\\ufffd")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page.replace("__DATA__", blob), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.1f} MB, {len(D)} datasets)")


if __name__ == "__main__":
    main()
