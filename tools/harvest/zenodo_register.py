"""Register Zenodo records that distribute EEG, from their record metadata.

Usage: python3 tools/harvest/zenodo_register.py IDS_FILE|all [YYYY-MM-DD]

IDS_FILE is a JSON object whose keys are Zenodo record ids (the values are ignored; a candidate
list keeps where each id came from). Records are fetched into cache/zenodo/<id>.json. Versions
of one concept are one dataset (dataset_id zenodo_<concept record id>), described by the latest
version found. A record is registered only if its title or description states EEG recordings in
words this script quotes; otherwise it is listed as skipped. Records that say they re-host or copy
data published elsewhere are skipped too: the original belongs in the DB, the copy is a mirror.
"""

import datetime
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
from reglib import Batch  # noqa: E402
import zenodo_client  # noqa: E402

CACHE = ROOT / "cache" / "zenodo"
LICENSES = {"cc-by-4.0": "CC-BY-4.0", "cc-by-3.0": "CC-BY-3.0", "cc-zero": "CC0-1.0", "cc0-1.0": "CC0-1.0",
            "cc-by-sa-4.0": "CC-BY-SA-4.0", "cc-by-nc-4.0": "CC-BY-NC-4.0", "cc-by-nc-sa-4.0": "CC-BY-NC-SA-4.0",
            "cc-by-nc-nd-4.0": "CC-BY-NC-ND-4.0", "cc-by-nd-4.0": "CC-BY-ND-4.0", "odc-by-1.0": "ODC-By-1.0",
            "odbl-1.0": "ODbL-1.0", "pddl-1.0": "PDDL-1.0", "mit": "MIT", "apache-2.0": "Apache-2.0", "gpl-3.0-only": "GPL-3.0-only"}
ACCESS = {"open": ("direct_download", "none"),
          "restricted": ("request_form_or_email", "Request access through the record's form; the record owners decide")}
EEG = re.compile(r"[^.]{0,80}\b(EEG|electroencephalogra\w*)\b[^.]{0,80}", re.I)
# What counts as stating recordings: EEG in the title, or a phrase that says signals were recorded or are provided.
REC = re.compile(r"\b(EEG|electroencephalogra\w*)\s+(data|datasets?|database|recordings?|signals?|corpus|measurements?|files)\b"
                 r"|\b(recorded|collected|acquired|measured|recordings? of|data of)\b[^.]{0,60}\b(EEG|electroencephalogra\w*)\b", re.I)
# Titles and descriptions that point to something other than the recordings themselves (checked by hand later).
OTHER = re.compile(r"\b(code|scripts?|toolbox|software|pipeline|model weights|checkpoints?|simulat\w+|synthetic|supplementary|figures?|poster|slides|"
                   r"features?|derivatives?|preprocessed|pre-processed|annotations? only|results of|re-?analysis|replication|used to generate|"
                   r"fig(?:ure)?s?|accuracy|neural networks?|spiking|systematic analysis|sample files|"
                   r"mice|mouse|rats?|dogs?|monkeys?|macaques?|rodents?|zebrafish|pigs?|sheep|animals?|in vivo)\b|\b(?:zip|part) \d+ of \d+\b", re.I)
IEEG = re.compile(r"\b(intracranial|ECoG|electrocorticogra\w*|sEEG|stereo-?EEG|depth electrode)", re.I)


def fetch(rid):
    return zenodo_client.record(rid)


RIGHTS = {"open": "info:eu-repo/semantics/openAccess", "restricted": "info:eu-repo/semantics/restrictedAccess"}


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def main():
    arg = sys.argv[1]
    ids = [p.stem for p in CACHE.glob("*.json") if p.stem.isdigit()] if arg == "all" else [k for k in json.loads(Path(arg).read_text()) if k.isdigit() and int(k) >= 10000]
    today = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat()
    CACHE.mkdir(parents=True, exist_ok=True)
    concepts = {}
    for rid in ids:
        d = fetch(rid)
        if not d or "metadata" not in d:
            continue
        c = str(d.get("conceptrecid") or d["id"])
        if c not in concepts or d["metadata"].get("publication_date", "") > concepts[c]["metadata"].get("publication_date", ""):
            concepts[c] = d
    B = Batch(today)
    have = {d["dataset_id"] for d in B.db["datasets"][1]}
    concepts = {c: d for c, d in concepts.items() if f"zenodo_{c}" not in have}
    skipped = []
    for c, d in sorted(concepts.items()):
        m = d["metadata"]
        title, desc = text(m.get("title")), text(m.get("description"))
        if m.get("resource_type", {}).get("type") != "dataset":
            skipped.append((d["id"], "not a dataset record"))
            continue
        if m.get("access_right") not in ("open", "restricted") and not (d.get("_datacite") and not m.get("access_right")):
            skipped.append((d["id"], "not open or restricted"))
            continue
        if re.search(r"re-?host|re-?upload|mirror of|copy of|converted (?:from|to)|BIDS (?:version|conversion|format) of", title + " " + desc, re.I):
            skipped.append((d["id"], "says it is a re-host, copy or conversion of data published elsewhere (check by hand)"))
            continue
        if OTHER.search(title):
            skipped.append((d["id"], "title points to code, features or derivatives (check by hand)"))
            continue
        hit = EEG.search(title) or (REC.search(desc) and EEG.search(desc))
        if not hit:
            skipped.append((d["id"], "no EEG recordings stated in the title or description"))
            continue
        R = B.dataset(f"zenodo_{c}")
        url = f"https://zenodo.org/records/{d['id']}"
        dc = d.get("_datacite")  # read from DataCite (zenodo_datacite.py): cite the record a reader can open there
        src = R.source(f"zenodo_{d['id']}", f"https://api.datacite.org/dois/{d['doi']}" if dc else url, "repository_record", "authors", title=title, doi=d.get("doi") or "",
                       describes_version=f"version {m.get('version') or d['id']}",
                       identity_basis=f"Zenodo record {d['id']} (concept {c})", note=("Read through the DataCite API (the DOI record of the Zenodo deposit)" if dc else "Read through the Zenodo API")
                       + "; the record creators were not compared with the authors of a paper")
        R.link(src, "distribution")
        R.alias(f"zenodo:{c}", "catalogue_id", src)
        R.ev("name", title, src, "Record title", "script")
        if not IEEG.search(title + " " + desc):
            R.ev("modalities", "scalp_eeg", src, " ".join(hit.group(0).split()[:25]))
        lic = (m.get("license") or {}).get("id", "").lower()
        if lic in LICENSES:
            R.ev("license_spdx", LICENSES[lic], src, f"License: {lic}", "script")
        if (m.get("publication_date") or "")[:4].isdigit():
            R.ev("year_published", m["publication_date"][:4], src, f"Published {m['publication_date']}", "script")
        acc = m.get("access_right")
        if dc and not acc:  # DataCite does not say whether the files are open
            R.child("access_routes", "zenodo", route_kind="repository", url=url)
        if acc in ACCESS:
            R.child("access_routes", "zenodo", route_kind="repository", url=url)
            R.ev("access_routes:zenodo.access_method", ACCESS[acc][0], src, f"{RIGHTS[acc] if dc else 'access_right: ' + acc}", "script")
            R.ev("access_routes:zenodo.human_steps", ACCESS[acc][1], src, f"{RIGHTS[acc] if dc else 'access_right: ' + acc}", "script")
            if acc == "open" and not dc:
                R.ev("access_routes:zenodo.automation_tool", "zenodo-api", src, "Files listed in the record API with download links", "script")
    import collections
    norm = collections.defaultdict(list)
    for d in B.db["datasets"][1]:
        norm[re.sub(r"\W", "", d["name"].casefold())].append(d["dataset_id"])
        norm[re.sub(r"\W", "", d["dataset_id"].casefold())].append(d["dataset_id"])
    for r in B.db["aliases"][1]:
        if r["alias_type"] != "catalogue_id":
            norm[re.sub(r"\W", "", r["alias"].casefold())].append(r["dataset_id"])
    for ids in norm.values():
        ids = sorted(set(ids))
        for a in [i for i in ids if i.startswith("zenodo_")]:
            for b in ids:
                if b != a:
                    R = B.dataset(a)
                    rid = next((x["source_id"] for x in B.db["dataset_sources"][1] if x["dataset_id"] == a), "")
                    R.relation("possibly_same_as", b, rid, "Both print the same name; whether they are the same data is not checked")
    B.save()
    from collections import Counter
    (ROOT / "cache" / "zenodo_skipped.tsv").write_text("\n".join(f"{rid}\t{why}" for rid, why in skipped) + "\n")
    print(Counter(w for _, w in skipped))
    print(len(concepts) - len(skipped), "registered,", len(skipped), "skipped")


if __name__ == "__main__":
    main()
