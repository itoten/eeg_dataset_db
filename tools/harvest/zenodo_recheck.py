"""Ask Zenodo, slowly, whether each registered Zenodo record still exists; save deletion notices.

Usage: python3 tools/harvest/zenodo_recheck.py [GAP_SECONDS]   (default 10)

Only the status is checked: saved copies in cache/zenodo/ are not replaced (evidence was quoted from them).
A 410 answer is saved to cache/zenodo/tombstones/<id>.json; then run zenodo_tombstones.py.
Progress goes to cache/zenodo/recheck.tsv, so a stopped run continues where it left off.
"""
import csv
import re
import sys
import urllib.error
from pathlib import Path

import zenodo_client

ROOT = Path(__file__).resolve().parents[2]


def main():
    zenodo_client.GAP = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    src = {s["source_id"]: s["url"] for s in csv.DictReader(open(ROOT / "data/sources.csv"))}
    ids = set()
    for ln in csv.DictReader(open(ROOT / "data/dataset_sources.csv")):
        m = ln["role"] == "distribution" and re.search(r"zenodo\.org/(?:api/)?records?/(\d+)|10\.5281/zenodo\.(\d+)", src[ln["source_id"]])
        if m:
            ids.add(m.group(1) or m.group(2))
    log = ROOT / "cache/zenodo/recheck.tsv"
    done = {ln.split("\t")[0] for ln in log.read_text().splitlines()} if log.exists() else set()
    tomb = ROOT / "cache/zenodo/tombstones"
    tomb.mkdir(parents=True, exist_ok=True)
    for rid in sorted(ids - done):
        try:
            zenodo_client.get(f"https://zenodo.org/api/records/{rid}")
            status = "200"
        except urllib.error.HTTPError as e:
            status, body = str(e.code), e.read()
            if e.code == 410:
                (tomb / f"{rid}.json").write_bytes(body)
        except zenodo_client.Blocked as e:
            print("stopped:", e, flush=True)
            return
        if status in ("200", "410"):  # other answers (500 ...) are tried again on the next run
            with open(log, "a") as f:
                f.write(f"{rid}\t{status}\n")
        if status != "200":
            print(rid, status, flush=True)
    print("done", len(ids), "records", flush=True)


if __name__ == "__main__":
    main()
