"""Fetch the journal of every paper source from OpenAlex (journal name, ISSN, PubMed id), 50 DOIs per request.

Usage: python3 tools/harvest/journals_fetch.py

OpenAlex allows keyless casual use (10 requests/s; https://docs.openalex.org/); about 20 requests are needed.
Answers are kept in cache/journals/works.json ({doi: answer or null}); DOIs already there are not asked again.
"""
import csv
import json
import re
from pathlib import Path

import polite

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "cache" / "journals"
DOI = re.compile(r"10\.\d{4,9}/[^\s?#\"<>]+")
SELECT = "doi,ids,type,publication_year,primary_location"


def paper_dois():
    """{doi: [source_id, ...]} for the paper sources, DOI from the doi column or the URL."""
    found = {}
    for s in csv.DictReader(open(ROOT / "data/sources.csv")):
        if s["kind"] != "paper":
            continue
        m = DOI.search(s["doi"] or "") or DOI.search(s["url"])
        if m:
            found.setdefault(m.group(0).rstrip(".,;/").lower(), []).append(s["source_id"])
    return found


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "works.json"
    works = json.loads(f.read_text()) if f.exists() else {}
    todo = sorted(set(paper_dois()) - set(works))
    print(len(todo), "DOIs to ask", flush=True)
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        url = ("https://api.openalex.org/works?per-page=50&select=" + SELECT + "&filter=doi:" + "|".join("https://doi.org/" + d for d in batch))
        try:
            res = polite.get_json(url)["results"]
        except polite.Blocked as e:
            print("stopped:", e, flush=True)
            break
        got = {(r["doi"] or "").replace("https://doi.org/", "").lower(): r for r in res}
        for d in batch:
            works[d] = got.get(d)
        f.write_text(json.dumps(works))
    print("done", sum(1 for v in works.values() if v), "of", len(works), "found", flush=True)


if __name__ == "__main__":
    main()
