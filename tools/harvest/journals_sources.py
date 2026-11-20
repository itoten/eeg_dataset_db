"""Fetch each journal's record from OpenAlex (name, ISSNs, open-access flag, subject fields), 50 per request.

Usage: python3 tools/harvest/journals_sources.py   (after journals_fetch.py)

Answers go to cache/journals/sources.json ({openalex source id: answer}); ones already there are not asked again.
"""
import json
from pathlib import Path

import polite

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "cache" / "journals"
SELECT = "id,display_name,issn_l,issn,type,is_in_doaj,topics"


def main():
    works = json.loads((OUT / "works.json").read_text())
    f = OUT / "sources.json"
    have = json.loads(f.read_text()) if f.exists() else {}
    ids = sorted({((w.get("primary_location") or {}).get("source") or {}).get("id") for w in works.values() if w} - {None} - set(have))
    print(len(ids), "journals to ask", flush=True)
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        url = ("https://api.openalex.org/sources?per-page=50&select=" + SELECT + "&filter=openalex:" + "|".join(b.rsplit("/", 1)[-1] for b in batch))
        try:
            res = polite.get_json(url)["results"]
        except polite.Blocked as e:
            print("stopped:", e, flush=True)
            break
        got = {r["id"]: r for r in res}
        for b in batch:
            have[b] = got.get(b)
        f.write_text(json.dumps(have))
    print("done", sum(1 for v in have.values() if v), "of", len(have), flush=True)


if __name__ == "__main__":
    main()
