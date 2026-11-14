"""Fetch OpenNeuro metadata for EEG/iEEG datasets into cache/openneuro/<id>.json (git-ignored).

Reads: the snapshot record (description, summary, root files), participants.json/tsv header,
and one *_eeg.json / *_ieeg.json sidecar and *_channels.tsv (root level if present, else the
first subject's first recording). Re-running skips datasets already cached.
"""
import json, sys, time, urllib.request, re
from pathlib import Path

API = "https://openneuro.org/crn/graphql"
CACHE = Path(__file__).resolve().parents[2] / "cache" / "openneuro"


def gql(q, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(API, json.dumps({"query": q}).encode(), {"content-type": "application/json"})
            d = json.load(urllib.request.urlopen(req, timeout=120))
            if "errors" in d:
                raise RuntimeError(d["errors"][0]["message"])
            return d["data"]
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def get(url, limit=200000):
    for i in range(4):
        try:
            return urllib.request.urlopen(url, timeout=120).read(limit).decode("utf-8", "replace")
        except Exception:
            if i == 3:
                return None
            time.sleep(3 * (i + 1))


def list_ids():
    ids = {}
    for mod in ("EEG", "iEEG", "MEG"):
        after = None
        while True:
            a = f', after:"{after}"' if after else ""
            d = gql(f'{{ datasets(first:100, modality:"{mod}"{a}){{ edges{{ node{{ id }} }} pageInfo{{ hasNextPage endCursor }} }} }}')
            for e in d["datasets"]["edges"]:
                if e and e["node"]:
                    ids.setdefault(e["node"]["id"], set()).add(mod)
            pi = d["datasets"]["pageInfo"]
            if not pi["hasNextPage"]:
                break
            after = pi["endCursor"]
    return ids


FILES = "files{ id filename directory size urls }"


def tree(ds, tag, tid):
    q = f'{{ snapshot(datasetId:"{ds}", tag:"{tag}"){{ files(tree:"{tid}"){{ id filename directory size urls }} }} }}'
    return gql(q)["snapshot"]["files"]


def fetch(ds):
    q = f'''{{ dataset(id:"{ds}"){{ id created publishDate latestSnapshot{{ tag created
      description{{ Name License Authors DatasetDOI ReferencesAndLinks HowToAcknowledge BIDSVersion DatasetType }}
      summary{{ subjects sessions tasks modalities secondaryModalities totalFiles size }} readme {FILES} }} }} }}'''
    d = gql(q)["dataset"]
    snap = d["latestSnapshot"]
    tag = snap["tag"]
    root = snap.pop("files")
    out = {"dataset": d, "root_files": [f["filename"] for f in root], "texts": {}, "sidecar_scope": None}
    byname = {f["filename"]: f for f in root}

    def text(f, key, limit=200000):
        t = get(f["urls"][0], limit) if f.get("urls") else None
        if t is not None:
            out["texts"][key] = {"filename": f["filename"], "url": f["urls"][0], "text": t}

    for n in ("participants.json", "participants.tsv"):
        if n in byname:
            text(byname[n], n, 20000 if n.endswith("tsv") else 200000)
    if "participants.tsv" in out["texts"]:  # keep the header line only
        t = out["texts"]["participants.tsv"]["text"]
        out["texts"]["participants.tsv"]["text"] = t.split("\n", 1)[0]
    side = [f for f in root if re.search(r"_(eeg|ieeg)\.json$", f["filename"])]
    chan = [f for f in root if f["filename"].endswith("_channels.tsv")]
    scope = "root"
    if not side:
        subs = sorted([f for f in root if f["directory"] and f["filename"].startswith("sub-")], key=lambda f: f["filename"])
        if subs:
            files = tree(ds, tag, subs[0]["id"])
            path = [subs[0]["filename"]]
            ses = sorted([f for f in files if f["directory"] and f["filename"].startswith("ses-")], key=lambda f: f["filename"])
            if ses:
                files = tree(ds, tag, ses[0]["id"]); path.append(ses[0]["filename"])
            mod = [f for f in files if f["directory"] and f["filename"] in ("eeg", "ieeg")]
            if mod:
                files = tree(ds, tag, mod[0]["id"]); path.append(mod[0]["filename"])
                side = sorted([f for f in files if re.search(r"_(eeg|ieeg)\.json$", f["filename"])], key=lambda f: f["filename"])[:1]
                chan = sorted([f for f in files if f["filename"].endswith("_channels.tsv")], key=lambda f: f["filename"])
                if side:
                    stem = side[0]["filename"].rsplit("_", 1)[0]
                    chan = [f for f in chan if f["filename"].startswith(stem)] or chan[:1]
                chan = chan[:1]
            scope = "/".join(path)
    else:
        side = sorted(side, key=lambda f: f["filename"])
    out["sidecar_scope"] = scope
    for f in side:
        text(f, "sidecar:" + f["filename"])
    for f in chan[:1]:
        text(f, "channels:" + f["filename"], 50000)
    return out


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    idf = CACHE / "_ids.json"
    if idf.exists():
        ids = json.loads(idf.read_text())
    else:
        ids = {k: sorted(v) for k, v in list_ids().items()}
        idf.write_text(json.dumps(ids, indent=0))
    print(len(ids), "datasets listed", flush=True)
    for i, ds in enumerate(sorted(ids)):
        f = CACHE / f"{ds}.json"
        if f.exists():
            continue
        try:
            f.write_text(json.dumps(fetch(ds)))
        except Exception as e:
            print("FAIL", ds, e, flush=True)
        if i % 25 == 0:
            print(i, ds, flush=True)
        time.sleep(0.3)
    print("done", flush=True)


if __name__ == "__main__":
    main()
