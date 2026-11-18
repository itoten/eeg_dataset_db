"""Ask figshare, OSF, Dryad and OpenNeuro, slowly, whether each registered record still exists.

Usage: python3 tools/harvest/repo_recheck.py [GAP_SECONDS]   (default 5)

Only each repository's API is asked (through polite.py). Answers other than 200 are saved with their body
to cache/recheck/<dataset_id>.json for a person or a later script to read; nothing in the DB is changed.
Progress goes to cache/recheck/done.tsv, so a stopped run continues where it left off.
Zenodo has its own script (zenodo_recheck.py). Mendeley Data's API needs a login, so it is not asked.
"""
import csv
import json
import re
import sys
import urllib.error
import urllib.parse
from pathlib import Path

import polite

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "cache" / "recheck"


def api_for(url):
    """(api_url, post_data) for a distribution URL, or None."""
    m = re.search(r"openneuro\.org/datasets/(ds\d+)", url)
    if m:
        q = json.dumps({"query": f'{{ dataset(id: "{m.group(1)}") {{ id }} }}'}).encode()
        return "https://openneuro.org/crn/graphql", q
    m = re.search(r"osf\.io/([a-z0-9]{5})(?:/|$)", url)
    if m:
        return f"https://api.osf.io/v2/nodes/{m.group(1)}/", None
    m = re.search(r"figshare\.com/articles/(?:[^/]+/)*(\d+)|10\.6084/m9\.figshare\.(\d+)", url)
    if m:
        return f"https://api.figshare.com/v2/articles/{m.group(1) or m.group(2)}", None
    m = re.search(r"figshare\.com/collections/(?:[^/]+/)*(\d+)|10\.6084/m9\.figshare\.c\.(\d+)", url)
    if m:
        return f"https://api.figshare.com/v2/collections/{m.group(1) or m.group(2)}", None
    m = re.search(r"(10\.5061/dryad\.[a-z0-9]+)", url)
    if m:
        return "https://datadryad.org/api/v2/datasets/" + urllib.parse.quote("doi:" + m.group(1), safe=""), None
    return None


def main():
    polite.GAP = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    OUT.mkdir(parents=True, exist_ok=True)
    src = {s["source_id"]: s["url"] for s in csv.DictReader(open(ROOT / "data/sources.csv"))}
    todo = {}
    for ln in csv.DictReader(open(ROOT / "data/dataset_sources.csv")):
        a = ln["role"] == "distribution" and api_for(src[ln["source_id"]])
        if a:
            todo.setdefault(ln["dataset_id"], a)
    log = OUT / "done.tsv"
    done = {ln.split("\t")[0] for ln in log.read_text().splitlines()} if log.exists() else set()
    for did in sorted(set(todo) - done):
        url, data = todo[did]
        hdr = {"content-type": "application/json"} if data else None
        try:
            body = polite.request(url, data, hdr)
            status = "200"
            if data and json.loads(body).get("data", {}).get("dataset") is None:
                status = "not_found"  # OpenNeuro answers 200 with an empty dataset
        except polite.Blocked as e:
            print("stopped:", e, flush=True)
            return
        except urllib.error.HTTPError as e:
            status, body = str(e.code), e.read()
        except Exception as e:  # network trouble: try again on the next run
            print(did, "error", e, flush=True)
            continue
        if status != "200":
            (OUT / f"{did}.json").write_text(json.dumps({"url": url, "status": status, "body": body.decode("utf-8", "replace")[:3000]}))
            print(did, status, url, flush=True)
        with open(log, "a") as f:
            f.write(f"{did}\t{status}\n")
    print("done", len(todo), "records", flush=True)


if __name__ == "__main__":
    main()
