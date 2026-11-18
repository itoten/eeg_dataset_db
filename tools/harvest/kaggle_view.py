"""Save Kaggle's dataset view API answer for every registered Kaggle dataset (no login needed).

Usage: python3 tools/harvest/kaggle_view.py

Writes cache/kaggle/view/<owner>__<slug>.json through polite.py, skipping ones already saved.
apply.py and the reviewers read these copies instead of the dataset page, which needs JavaScript.
"""
import csv
import json
import re
import urllib.error
from pathlib import Path

import polite

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "cache" / "kaggle" / "view"


def path_for(ref):
    return OUT / (ref.replace("/", "__") + ".json")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    refs = set()
    for s in csv.DictReader(open(ROOT / "data/sources.csv")):
        m = re.match(r"https://www\.kaggle\.com/datasets/([^/?#]+/[^/?#]+)", s["url"])
        if m:
            refs.add(m.group(1))
    for ref in sorted(refs):
        if path_for(ref).exists():
            continue
        try:
            d = polite.get_json("https://www.kaggle.com/api/v1/datasets/view/" + ref)
        except polite.Blocked as e:
            print("stopped:", e, flush=True)
            return
        except urllib.error.HTTPError as e:
            d = {"error": e.code}
            print(ref, e.code, flush=True)
        path_for(ref).write_text(json.dumps(d))
    print("done", len(refs), flush=True)


if __name__ == "__main__":
    main()
