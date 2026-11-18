"""Search Zenodo for dataset records about EEG and save the full records to cache/zenodo/<id>.json.

Usage: python3 tools/harvest/zenodo_search.py

The search API returns each record in full (title, description, license, access right, files), so one
request covers 25 records. Records already cached are kept.
"""
import json, urllib.parse
import zenodo_client
from pathlib import Path

CACHE = Path(__file__).resolve().parents[2] / "cache" / "zenodo"
QUERIES = ["EEG", "electroencephalography", "electroencephalogram", "polysomnography", "ECoG", "intracranial EEG",
           "brain-computer interface", "motor imagery", "SSVEP", "P300", "event-related potential", "sleep EEG", "epilepsy EEG"]


def get(u):
    return zenodo_client.get(u)  # spacing, User-Agent and stopping on 403/429 live there


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    for q in QUERIES:
        page, n = 1, 0
        while True:
            d = get(f"https://zenodo.org/api/records?q={urllib.parse.quote(q)}&type=dataset&size=25&page={page}&sort=mostrecent")
            hits = d["hits"]["hits"]
            for h in hits:
                f = CACHE / f"{h['id']}.json"
                if not f.exists():
                    f.write_text(json.dumps(h))
                    n += 1
            if len(hits) < 25 or page * 25 >= d["hits"]["total"] or page >= 400:
                break
            page += 1
        print(q, n, d["hits"]["total"], flush=True)


if __name__ == "__main__":
    main()
