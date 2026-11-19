"""Polite HTTP for the APIs our harvest scripts read (zenodo.org has its own client, zenodo_client.py).

Rules (CLAUDE.md "do not burden data sites"; limits as published, 2026-11-18):
- An identifiable User-Agent, as DataCite and Crossref ask; a contact address comes only from the
  environment variable POLITE_CONTACT, never from the repository.
- At least GAP seconds between requests to the same host, across processes (figshare asks for at most
  one per second; Crossref's public pool allows 5/s, concurrency 1; OpenNeuro, Dryad, OSF and Kaggle
  publish nothing we could read, so the same cautious gap applies).
- A 403 or 429 is not retried: that host is left alone for an hour (cache/polite/<host>.blocked_until).
  Other failures are retried at most twice, slowly.
- Kaggle publishes no limit and blocked us after about 400 requests in a row, so it has a daily cap
  (DAILY) and a 24 h pause (PAUSES); the cap counts requests per host per day in cache/polite/<host>.count.
"""
import fcntl
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "cache" / "polite"
CONTACT = os.environ.get("POLITE_CONTACT", "")
UA = "eeg_dataset_db-harvester/1.0 (+https://github.com/itoten/eeg_dataset_db" + (f"; mailto:{CONTACT}" if CONTACT else "") + ")"
GAP, PAUSE = 2.0, 3600
DAILY = {"www.kaggle.com": 150}
PAUSES = {"www.kaggle.com": 86400}


class Blocked(Exception):
    pass


def request(url, data=None, headers=None, limit=None):
    """Bytes of the answer; raises Blocked, or urllib.error.HTTPError for other HTTP errors."""
    host = urllib.parse.urlsplit(url).hostname
    STATE.mkdir(parents=True, exist_ok=True)
    bf = STATE / f"{host}.blocked_until"
    if bf.exists() and time.time() < float(bf.read_text()):
        raise Blocked(f"{host} paused until {time.ctime(float(bf.read_text()))}")
    if host in DAILY:
        cf, today = STATE / f"{host}.count", time.strftime("%Y-%m-%d")
        day, n = (cf.read_text().split() + ["", "0"])[:2] if cf.exists() else ("", "0")
        n = int(n) if day == today else 0
        if n >= DAILY[host]:
            raise Blocked(f"{host}: daily cap of {DAILY[host]} requests reached")
        cf.write_text(f"{today} {n + 1}")
    h = {"User-Agent": UA, **(headers or {})}
    for i in range(3):
        with open(STATE / f"{host}.lock", "a+") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)  # one request at a time per host
            last = STATE / f"{host}.last"
            wait = (float(last.read_text()) if last.exists() else 0) + GAP - time.time()
            if wait > 0:
                time.sleep(wait)
            try:
                with urllib.request.urlopen(urllib.request.Request(url, data, h), timeout=120) as r:
                    return r.read(limit) if limit else r.read()
            except urllib.error.HTTPError as e:
                if e.code in (403, 429):
                    pause = PAUSES.get(host, PAUSE)
                    bf.write_text(str(time.time() + pause))
                    raise Blocked(f"{e.code} from {host}; paused for {pause // 60} min") from e
                if e.code < 500 or i == 2:
                    raise
            except (urllib.error.URLError, TimeoutError):
                if i == 2:
                    raise
            finally:
                last.write_text(str(time.time()))
        time.sleep(30 * (i + 1))


def get_json(url, data=None, headers=None):
    return json.loads(request(url, data, headers))
