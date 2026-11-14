"""Register Zenodo records that distribute EEG, from their record metadata.

Usage: python3 tools/harvest/zenodo_register.py IDS_FILE [YYYY-MM-DD]

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
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
from reglib import Batch  # noqa: E402

CACHE = ROOT / "cache" / "zenodo"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
LICENSES = {"cc-by-4.0": "CC-BY-4.0", "cc-by-3.0": "CC-BY-3.0", "cc-zero": "CC0-1.0", "cc0-1.0": "CC0-1.0",
            "cc-by-sa-4.0": "CC-BY-SA-4.0", "cc-by-nc-4.0": "CC-BY-NC-4.0", "cc-by-nc-sa-4.0": "CC-BY-NC-SA-4.0",
            "cc-by-nc-nd-4.0": "CC-BY-NC-ND-4.0", "cc-by-nd-4.0": "CC-BY-ND-4.0", "odc-by-1.0": "ODC-By-1.0",
            "odbl-1.0": "ODbL-1.0", "pddl-1.0": "PDDL-1.0", "mit": "MIT", "apache-2.0": "Apache-2.0", "gpl-3.0-only": "GPL-3.0-only"}
ACCESS = {"open": ("direct_download", "none"),
          "restricted": ("request_form_or_email", "Request access through the record's form; the record owners decide")}
EEG = re.compile(r"[^.]{0,80}\b(EEG|electroencephalogra\w*)\b[^.]{0,80}", re.I)
IEEG = re.compile(r"\b(intracranial|ECoG|electrocorticogra\w*|sEEG|stereo-?EEG|depth electrode)", re.I)


def fetch(rid):
    f = CACHE / f"{rid}.json"
    if f.exists():
        return json.loads(f.read_text())
    for i in range(5):
        try:
            d = json.load(urllib.request.urlopen(urllib.request.Request(f"https://zenodo.org/api/records/{rid}", headers=UA), timeout=90))
            f.write_text(json.dumps(d))
            time.sleep(1)
            return d
        except Exception as e:
            err = e
            time.sleep(5 * (i + 1))
    print("FAIL", rid, err)
    return None


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def main():
    ids = [k for k in json.loads(Path(sys.argv[1]).read_text()) if k.isdigit() and int(k) >= 10000]
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
    skipped = []
    for c, d in sorted(concepts.items()):
        m = d["metadata"]
        title, desc = text(m.get("title")), text(m.get("description"))
        if m.get("resource_type", {}).get("type") != "dataset":
            skipped.append((d["id"], "not a dataset record"))
            continue
        if re.search(r"re-?host|re-?upload|mirror of|copy of", title + " " + desc, re.I):
            skipped.append((d["id"], "says it is a re-host or copy of data published elsewhere (check by hand)"))
            continue
        hit = EEG.search(title) or EEG.search(desc)
        if not hit:
            skipped.append((d["id"], "no EEG in title or description"))
            continue
        R = B.dataset(f"zenodo_{c}")
        url = f"https://zenodo.org/records/{d['id']}"
        src = R.source(f"zenodo_{d['id']}", url, "repository_record", "authors", title=title, doi=d.get("doi") or "",
                       describes_version=f"version {m.get('version') or d['id']}",
                       identity_basis=f"Zenodo record {d['id']} (concept {c})", note="Read through the Zenodo API; the record creators were not compared with the authors of a paper")
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
        if acc in ACCESS:
            R.child("access_routes", "zenodo", route_kind="repository", url=url)
            R.ev("access_routes:zenodo.access_method", ACCESS[acc][0], src, f"access_right: {acc}", "script")
            R.ev("access_routes:zenodo.human_steps", ACCESS[acc][1], src, f"access_right: {acc}", "script")
            if acc == "open":
                R.ev("access_routes:zenodo.automation_tool", "zenodo-api", src, "Files listed in the record API with download links", "script")
    B.save()
    for rid, why in skipped:
        print("skipped", rid, why)
    print(len(concepts) - len(skipped), "registered,", len(skipped), "skipped")


if __name__ == "__main__":
    main()
