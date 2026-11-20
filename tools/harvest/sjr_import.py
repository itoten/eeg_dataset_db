"""Import SCImago Journal Rank for the journals named in paper_journals, from a file a person downloaded.

Usage: python3 tools/harvest/sjr_import.py cache/journals/scimagojr_<year>.csv

scimagojr.com refuses scripts (403 on the first request), so the file is saved by hand: on
https://www.scimagojr.com/journalrank.php choose the year and use "Download data". The file is
semicolon-separated with the columns Sourceid, Title, Issn, SJR, SJR Best Quartile and Categories.
Journals are matched by ISSN through the ISSNs OpenAlex lists (cache/journals/sources.json).
Writes data/journal_rankings.csv.
"""
import csv
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import csvio  # noqa: E402

HEADER = ["issn_l", "sjr_title", "sjr_year", "sjr", "best_quartile", "categories", "record_url", "checked_on", "checked_by"]


def main():
    path = Path(sys.argv[1])
    year = int(re.search(r"(20\d\d)", path.name).group(1))
    by_issn = {}
    for r in csv.DictReader(open(path, encoding="utf-8-sig"), delimiter=";"):
        for i in re.split(r"[,\s]+", r["Issn"] or ""):
            if i:
                by_issn[i.replace("-", "")] = r
    sources = json.loads((ROOT / "cache" / "journals" / "sources.json").read_text())
    wanted = {}
    for s in sources.values():
        if s and s.get("issn_l"):
            wanted[s["issn_l"]] = [x.replace("-", "") for x in (s.get("issn") or []) + [s["issn_l"]]]
    today = datetime.date.today().isoformat()
    rows = []
    for issn_l, issns in sorted(wanted.items()):
        r = next((by_issn[i] for i in issns if i in by_issn), None)
        if r:
            sjr = (r["SJR"] or "").replace(",", ".")
            rows.append({"issn_l": issn_l, "sjr_title": r["Title"], "sjr_year": year, "sjr": sjr, "best_quartile": r["SJR Best Quartile"] if r["SJR Best Quartile"] != "-" else "",
                         "categories": r["Categories"], "record_url": "https://www.scimagojr.com/journalsearch.php?q=" + r["Sourceid"] + "&tip=sid",
                         "checked_on": today, "checked_by": "script"})
    csvio.write_rows(ROOT / "data" / "journal_rankings.csv", HEADER, rows, ["issn_l"])
    print(len(rows), "of", len(wanted), "journals found in the file;", sum(1 for r in rows if r["best_quartile"] == "Q1"), "have best quartile Q1")


if __name__ == "__main__":
    main()
