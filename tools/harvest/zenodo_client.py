"""The one way the tools in this repository talk to zenodo.org, following https://developers.zenodo.org/.

- JSON API only (no HTML pages, no headless browser).
- An identifiable User-Agent, as the "User-Agent" section asks. A contact address, if any, comes from the
  environment variable ZENODO_CONTACT, so it is never written into the repository.
- At most one request every 3 s across all processes (guest limit: 60/min, 2000/h), and one every 4 s for
  search (30/min). X-RateLimit-Remaining is read; near zero, we wait for X-RateLimit-Reset.
- A 429 or 403 is not retried: every tool stops asking zenodo.org for an hour (cache/zenodo/.blocked_until)
  and callers fall back to their cached copies.
- ZENODO_TOKEN, if set, is sent as a bearer token (authenticated limit: 100/min, 5000/h). Not required.
"""
import fcntl
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "cache" / "zenodo"
UA = "eeg_dataset_db-harvester/1.0 (+https://github.com/itoten/eeg_dataset_db" + (f"; {os.environ['ZENODO_CONTACT']}" if os.environ.get("ZENODO_CONTACT") else "") + ")"
GAP, SEARCH_GAP, PAUSE = 3.0, 4.0, 3600


class Blocked(Exception):
    pass


def blocked_until():
    f = STATE / ".blocked_until"
    return float(f.read_text()) if f.exists() else 0.0


def get(url):
    """JSON from a zenodo.org API URL, or raises Blocked / urllib.error.HTTPError."""
    assert url.startswith("https://zenodo.org/api/") or url.startswith("https://zenodo.org/oai2d"), url
    STATE.mkdir(parents=True, exist_ok=True)
    if time.time() < blocked_until():
        raise Blocked(f"zenodo.org paused until {time.ctime(blocked_until())}")
    gap = SEARCH_GAP if "/api/records?" in url else GAP
    with open(STATE / ".lock", "a+") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)  # one request at a time across processes
        last = STATE / ".last_request"
        wait = (float(last.read_text()) if last.exists() else 0) + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        headers = {"User-Agent": UA, "Accept": "application/json"}
        if os.environ.get("ZENODO_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["ZENODO_TOKEN"]
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as r:
                body, h = r.read(), r.headers
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                (STATE / ".blocked_until").write_text(str(time.time() + PAUSE))
                raise Blocked(f"{e.code} from zenodo.org; paused for {PAUSE // 60} min") from e
            raise
        finally:
            last.write_text(str(time.time()))
        if h.get("X-RateLimit-Remaining", "9") in ("0", "1") and h.get("X-RateLimit-Reset"):
            reset = float(h["X-RateLimit-Reset"])  # the docs do not give its format: epoch or seconds left
            time.sleep(max(0, min(120, reset - time.time() if reset > 1e9 else reset)))
    return json.loads(body)


def record(rid, refresh=False):
    """A record from the API, cached in cache/zenodo/<id>.json; None if zenodo.org cannot be asked now."""
    f = STATE / f"{rid}.json"
    if f.exists() and not refresh:
        return json.loads(f.read_text())
    try:
        d = get(f"https://zenodo.org/api/records/{rid}")
    except (Blocked, urllib.error.URLError) as e:
        print("zenodo:", rid, e)
        return json.loads(f.read_text()) if f.exists() else None
    f.write_text(json.dumps(d))
    return d
