"""Write data/paper_journals.csv from the OpenAlex answers saved by journals_fetch.py and journals_sources.py.

Usage: python3 tools/harvest/journals_build.py

One row per paper source that has a DOI. The venue's fields and subfields are the three most frequent
among the topics OpenAlex lists for the venue.
"""
import datetime
import json
import sys
from collections import Counter
from pathlib import Path

import journals_fetch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import csvio  # noqa: E402

HEADER = ["source_id", "doi", "journal", "issn_l", "venue_type", "pmid", "fields", "subfields", "record_url", "checked_on", "checked_by", "note"]


def top(src, key, n=3):
    c = Counter()
    for t in src.get("topics") or []:
        name = (t.get(key) or {}).get("display_name")
        if name:
            c[name] += t.get("count", 0)
    return ";".join(k for k, _ in c.most_common(n))


def main():
    cache = ROOT / "cache" / "journals"
    works = json.loads((cache / "works.json").read_text())
    sources = json.loads((cache / "sources.json").read_text())
    today = datetime.date.today().isoformat()
    rows = []
    for doi, sids in sorted(journals_fetch.paper_dois().items()):
        w = works.get(doi)
        src = ((w or {}).get("primary_location") or {}).get("source") or {}
        full = sources.get(src.get("id")) or {}
        for sid in sorted(sids):
            rows.append({
                "source_id": sid, "doi": doi, "journal": src.get("display_name", "") or "", "issn_l": src.get("issn_l") or "",
                "venue_type": src.get("type") or "", "pmid": ((w or {}).get("ids") or {}).get("pmid", "").rsplit("/", 1)[-1],
                "fields": top(full, "field"), "subfields": top(full, "subfield"),
                "record_url": "https://api.openalex.org/works/https://doi.org/" + doi, "checked_on": today, "checked_by": "script",
                "note": "" if w else "OpenAlex has no record of this DOI",
            })
    csvio.write_rows(ROOT / "data" / "paper_journals.csv", HEADER, rows, ["source_id"])
    print(len(rows), "rows;", sum(1 for r in rows if r["pmid"]), "with a PubMed id;", sum(1 for r in rows if r["journal"]), "with a journal")


if __name__ == "__main__":
    main()
