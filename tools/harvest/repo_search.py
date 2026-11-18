"""Search Dryad, Mendeley Data, OSF and Kaggle for EEG records and save the hits to cache/<repo>/search.json.

Usage: python3 tools/harvest/repo_search.py [dryad|mendeley|osf|kaggle ...]

Each hit keeps the title, description, DOI or URL and date the search API returns. Mendeley Data is
searched through DataCite (prefix 10.17632), which lists every version; versions are merged by their
dataset id. Kaggle's list API needs no login. Selection happens later (select_candidates in this file).
"""

import json
import re
import sys
import urllib.parse
from pathlib import Path

import polite

ROOT = Path(__file__).resolve().parents[2]
TERMS = ["EEG", "electroencephalography", "electroencephalogram", "polysomnography", "ECoG", "intracranial EEG", "iEEG"]
TITLE = re.compile(r"\b(EEG|iEEG|sEEG|ECoG|electroencephalo\w*|electrocorticogra\w*|polysomnogra\w*|PSG)\b", re.I)


def get(url):
    return polite.get_json(url)  # spacing, User-Agent and stopping on 403/429 live there


def dryad():
    hits = {}
    for q in TERMS:
        page = 1
        while True:
            d = get(f"https://datadryad.org/api/v2/search?q={urllib.parse.quote(q)}&per_page=100&page={page}")
            items = d.get("_embedded", {}).get("stash:datasets", [])
            for it in items:
                hits[it["identifier"]] = dict(title=it.get("title", ""), desc=it.get("abstract", ""), doi=it["identifier"].replace("doi:", ""),
                                              url="https://doi.org/" + it["identifier"].replace("doi:", ""), date=it.get("publicationDate", ""),
                                              license=it.get("license", ""))
            if len(items) < 100:
                break
            page += 1
    return hits


def mendeley():
    hits = {}
    for q in TERMS:
        url = f"https://api.datacite.org/dois?query={urllib.parse.quote(q)}&prefix=10.17632&page%5Bsize%5D=1000&page%5Bcursor%5D=1"
        while url:
            d = get(url)
            for it in d["data"]:
                a = it["attributes"]
                m = re.match(r"10\.17632/([a-z0-9]+)(?:\.(\d+))?$", a["doi"].lower())
                if not m:
                    continue
                ver = int(m.group(2) or 0)
                if m.group(1) in hits and hits[m.group(1)]["version"] >= ver:
                    continue
                hits[m.group(1)] = dict(title=(a.get("titles") or [{}])[0].get("title", ""),
                                        desc=" ".join(x.get("description", "") for x in a.get("descriptions") or []),
                                        doi=a["doi"], url=f"https://data.mendeley.com/datasets/{m.group(1)}/{ver}" if ver else f"https://doi.org/{a['doi']}",
                                        date=str(a.get("publicationYear", "")), version=ver,
                                        license=";".join(r.get("rightsIdentifier") or r.get("rights", "") for r in a.get("rightsList") or []))
            url = d.get("links", {}).get("next")
    return hits


def osf():
    hits = {}
    for q in TERMS:
        url = f"https://api.osf.io/v2/nodes/?filter%5Btitle%5D={urllib.parse.quote(q)}&filter%5Bparent%5D=null&page%5Bsize%5D=100"
        while url:
            d = get(url)
            for it in d["data"]:
                a = it["attributes"]
                hits[it["id"]] = dict(title=a.get("title", ""), desc=a.get("description") or "", url=f"https://osf.io/{it['id']}/",
                                      date=(a.get("date_created") or "")[:10], category=a.get("category", ""))
            url = d["links"].get("next")
    return hits


def kaggle():
    hits = {}
    for q in ["eeg", "electroencephalography", "polysomnography", "ecog"]:
        for page in range(1, 200):
            items = get(f"https://www.kaggle.com/api/v1/datasets/list?search={urllib.parse.quote(q)}&page={page}")
            for it in items:
                hits[it["ref"]] = dict(title=it.get("title", ""), desc=it.get("subtitle") or "", url=it.get("url", ""),
                                       date=str(it.get("lastUpdated") or "")[:10], license=it.get("licenseName", ""), bytes=it.get("totalBytes"))
            if len(items) < 20:
                break
    return hits


def main():
    for repo in sys.argv[1:] or ["dryad", "mendeley", "osf", "kaggle"]:
        hits = globals()[repo]()
        out = ROOT / "cache" / repo / "search.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(hits, ensure_ascii=False, indent=0))
        sel = {k: v for k, v in hits.items() if TITLE.search(v["title"])}
        print(repo, len(hits), "hits,", len(sel), "with an EEG term in the title", flush=True)


if __name__ == "__main__":
    main()
