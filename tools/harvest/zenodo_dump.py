"""Download Zenodo's monthly bulk metadata dump (records-json.tar.gz, about 14 GB) and check its checksum.

Usage: python3 tools/harvest/zenodo_dump.py

Zenodo recommends the dumps (/api/exporter, made at the start of each month) over fetching records one by
one. One request lists the dumps, one request downloads the file (a stopped download continues where it left
off). The file goes to cache/zenodo/dump/; nothing in the DB is changed.
"""
import hashlib
import json
import sys
from pathlib import Path

import zenodo_client as z

NAME = "records-json.tar.gz"
OUT = z.STATE / "dump"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    head = next(v for v in z.get("https://zenodo.org/api/exporter")[NAME] if v.get("is_head"))
    dest = OUT / NAME
    (OUT / "head.json").write_text(json.dumps(head))
    print("head", head["created"], head["size"], flush=True)
    z.download(head["links"]["self"], dest)
    algo, _, want = head["checksum"].partition(":")
    h = hashlib.new(algo)
    with open(dest, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    ok = h.hexdigest() == want
    print("checksum", "ok" if ok else f"MISMATCH {h.hexdigest()} != {want}", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
