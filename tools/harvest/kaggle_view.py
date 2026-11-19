"""Save Kaggle's dataset metadata (title, subtitle, description, licenses) for every registered Kaggle dataset.

Usage: python3 tools/harvest/kaggle_view.py [GAP_SECONDS]   (default 8)

Uses the API the kaggle CLI uses, with an API token from $KAGGLE_API_TOKEN or the kaggle CLI's .kaggle/access_token in the home directory
(without a token Kaggle answers 403 after a few hundred requests). An empty description is a real answer:
many Kaggle datasets have none.

Writes cache/kaggle/view/<owner>__<slug>.json through polite.py, skipping ones already saved.
apply.py and the reviewers read these copies instead of the dataset page, which needs JavaScript.
"""
import csv
import json
import os
import re
import sys
import urllib.error
from pathlib import Path

import polite

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "cache" / "kaggle" / "view"


def path_for(ref):
    return OUT / (ref.replace("/", "__") + ".json")


def token():
    t = os.environ.get("KAGGLE_API_TOKEN")
    p = Path.home() / ".kaggle" / "access_token"
    return t or (p.read_text().strip() if p.exists() else None)


def main():
    polite.GAP = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    tok = token()
    if not tok:
        sys.exit("no Kaggle API token ($KAGGLE_API_TOKEN or .kaggle/access_token in the home directory)")
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
            d = polite.get_json("https://www.kaggle.com/api/v1/datasets/metadata/" + ref,
                                headers={"Authorization": "Bearer " + tok})
            d = d.get("info") or {"error": d.get("errorMessage")}
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
