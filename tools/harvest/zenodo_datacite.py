"""Find Zenodo dataset records about EEG through DataCite and save them to cache/zenodo/<id>.json.

Usage: python3 tools/harvest/zenodo_datacite.py

zenodo.org refuses this network at times. Every Zenodo DOI is registered at DataCite with its
title, description, rights, dates and version relations, and DataCite's public API is meant for
reading them. Records are written in the shape of the Zenodo API (metadata.title, description,
license, access_right, publication_date, conceptrecid) with "_datacite": true, so
zenodo_register.py cites the DataCite record instead of zenodo.org. File lists are not in DataCite, and newer records carry no access right there (access_right is then empty).
Records already cached are kept.
"""
import json
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

CACHE = Path(__file__).resolve().parents[2] / "cache" / "zenodo"
QUERIES = ["EEG", "electroencephalography", "electroencephalogram", "polysomnography", "ECoG", "intracranial EEG",
           "brain-computer interface", "motor imagery", "SSVEP", "P300", "event-related potential", "sleep EEG", "epilepsy EEG"]
CC = [(r"publicdomain/zero", "cc0-1.0"), (r"licenses/by/4", "cc-by-4.0"), (r"licenses/by-sa/4", "cc-by-sa-4.0"), (r"licenses/by-nc/4", "cc-by-nc-4.0"),
      (r"licenses/by-nc-sa/4", "cc-by-nc-sa-4.0"), (r"licenses/by-nc-nd/4", "cc-by-nc-nd-4.0"), (r"licenses/by-nd/4", "cc-by-nd-4.0")]


def get(url):
    for i in range(5):
        out = subprocess.run(["curl", "-s", "-m", "90", url], capture_output=True, text=True).stdout
        try:
            return json.loads(out)
        except ValueError:
            time.sleep(10 * (i + 1))
    raise RuntimeError(url)


def convert(a):
    m = re.match(r"10\.5281/zenodo\.(\d+)$", a["doi"].lower())
    rel = a.get("relatedIdentifiers") or []
    if not m or any(r.get("relationType") == "HasVersion" for r in rel):  # a concept DOI stands for all versions
        return None
    concept = next((r["relatedIdentifier"].rsplit(".", 1)[-1] for r in rel if r.get("relationType") == "IsVersionOf"
                    and "zenodo." in r.get("relatedIdentifier", "")), m.group(1))
    uris = " ".join((r.get("rightsUri") or "") for r in a.get("rightsList") or [])
    acc = "open" if "openAccess" in uris else "restricted" if "restrictedAccess" in uris else "closed" if "closedAccess" in uris else "embargoed" if "embargoedAccess" in uris else ""
    date = next((d["date"] for d in a.get("dates") or [] if d.get("dateType") == "Issued"), str(a.get("publicationYear") or ""))
    return {"id": int(m.group(1)), "conceptrecid": concept, "doi": a["doi"], "_datacite": True,
            "metadata": {"title": (a.get("titles") or [{}])[0].get("title", ""),
                         "description": " ".join(d.get("description", "") for d in a.get("descriptions") or []),
                         "resource_type": {"type": "dataset"}, "access_right": acc, "publication_date": date, "version": a.get("version") or "",
                         "license": {"id": next((r["rightsIdentifier"].lower() for r in a.get("rightsList") or [] if r.get("rightsIdentifierScheme") == "SPDX"),
                                                 next((v for p, v in CC if re.search(p, uris)), ""))}}}


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    for q in QUERIES:
        n, seen = 0, 0
        url = ("https://api.datacite.org/dois?client-id=cern.zenodo&resource-type-id=dataset&page%5Bsize%5D=500&page%5Bcursor%5D=1&query="
               + urllib.parse.quote(f'titles.title:"{q}" OR descriptions.description:"{q}"'))
        while url:
            d = get(url)
            for it in d["data"]:
                seen += 1
                r = convert(it["attributes"])
                if r and not (CACHE / f"{r['id']}.json").exists():
                    (CACHE / f"{r['id']}.json").write_text(json.dumps(r))
                    n += 1
            url = d.get("links", {}).get("next") if d["data"] else None
            time.sleep(1)
        print(q, seen, "records,", n, "new", flush=True)


if __name__ == "__main__":
    main()
