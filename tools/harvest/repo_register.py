"""Register datasets deposited in figshare, Harvard-type Dataverse, OSF, Mendeley Data or Synapse.

Usage: python3 tools/harvest/repo_register.py ENTRIES_JSON [YYYY-MM-DD]

ENTRIES_JSON is a list of {"dataset_id", "repo", "id"} where repo is figshare_article,
figshare_collection, dataverse (id = "<host>|<doi>"), osf, mendeley or synapse. Metadata is
read through each repository's public API into cache/repos/. Values: name (the record title),
license, publication year, modality when the title or description says EEG, and the access
route. Synapse downloads go through a login (Synapse's download documentation).
"""

import datetime
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
from reglib import Batch  # noqa: E402

CACHE = ROOT / "cache" / "repos"
LIC = [(r"^cc[- ]?by[- ]?4\.0|creativecommons\.org/licenses/by/4\.0|^cc-by-4\.0", "CC-BY-4.0"),
       (r"^cc0|publicdomain/zero|^cc0-1\.0", "CC0-1.0"), (r"^cc[- ]?by[- ]?nc[- ]?4\.0|by-nc/4\.0", "CC-BY-NC-4.0"),
       (r"^cc[- ]?by[- ]?nc[- ]?sa[- ]?4\.0|by-nc-sa/4\.0", "CC-BY-NC-SA-4.0"), (r"^cc[- ]?by[- ]?nc[- ]?nd[- ]?4\.0|by-nc-nd/4\.0", "CC-BY-NC-ND-4.0"),
       (r"^cc[- ]?by[- ]?sa[- ]?4\.0|by-sa/4\.0", "CC-BY-SA-4.0"), (r"^mit$", "MIT"), (r"^apache[- ]2\.0", "Apache-2.0")]
EEG = re.compile(r"[^.]{0,80}\b(EEG|electroencephalogra\w*)\b[^.]{0,80}", re.I)
IEEG = re.compile(r"\b(intracranial|ECoG|electrocorticogra\w*|sEEG|stereo-?EEG)", re.I)
SYNAPSE_DOC = "https://help.synapse.org/docs/Downloading-Data-Programmatically.2003796248.html"


def curl(url, data=None):
    cmd = ["curl", "-sL", "-m", "60", "-A", "Mozilla/5.0", url]
    if data:
        cmd += ["-H", "content-type: application/json", "-d", data]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    return json.loads(out)


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def lic_value(s):
    s = (s or "").strip().lower()
    return next((v for p, v in LIC if re.search(p, s)), "")


def read(e):
    f = CACHE / f"{e['repo']}_{re.sub(r'[^A-Za-z0-9]+', '_', e['id'])}.json"
    if f.exists():
        return json.loads(f.read_text())
    r, i = e["repo"], e["id"]
    if r == "figshare_article":
        d = curl(f"https://api.figshare.com/v2/articles/{i}")
        m = dict(title=d["title"], desc=text(d.get("description")), license=(d.get("license") or {}).get("name", ""),
                 date=d.get("published_date", ""), url=d.get("url_public_html") or f"https://doi.org/{d.get('doi')}", doi=d.get("doi", ""),
                 public=d.get("is_public") and not d.get("is_embargoed") and not d.get("is_confidential"))
    elif r == "figshare_collection":
        d = curl(f"https://api.figshare.com/v2/collections/{i}")
        arts = curl(f"https://api.figshare.com/v2/collections/{i}/articles?page_size=1")
        a = curl(f"https://api.figshare.com/v2/articles/{arts[0]['id']}") if arts else {}
        m = dict(title=d["title"], desc=text(d.get("description")), license=(a.get("license") or {}).get("name", ""),
                 license_from="the license of the collection's first item", date=d.get("published_date", ""),
                 url=d.get("url_public_html") or f"https://doi.org/{d.get('doi')}", doi=d.get("doi", ""), public=bool(arts))
    elif r == "dataverse":
        host, doi = i.split("|")
        d = curl(f"https://{host}/api/datasets/:persistentId/?persistentId=doi:{doi}")["data"]
        v = d["latestVersion"]
        cit = {x["typeName"]: x["value"] for x in v["metadataBlocks"]["citation"]["fields"]}
        desc = " ".join(text(x["dsDescriptionValue"]["value"]) for x in cit.get("dsDescription", []))
        lic = v.get("license") or {}
        m = dict(title=cit.get("title", ""), desc=desc, license=lic.get("rightsIdentifier") or lic.get("name", "") if isinstance(lic, dict) else str(lic),
                 date=d.get("publicationDate", ""), url=f"https://doi.org/{doi}", doi=doi,
                 public=not any(f.get("restricted") for f in v.get("files", [])),
                 terms_of_access=text(v.get("termsOfAccess")))
    elif r == "osf":
        d = curl(f"https://api.osf.io/v2/nodes/{i}/")["data"]
        a = d["attributes"]
        lic = ""
        lr = d["relationships"].get("license", {}).get("links", {}).get("related", {}).get("href")
        if lr:
            lic = curl(lr)["data"]["attributes"]["name"]
        m = dict(title=a["title"], desc=text(a.get("description")), license=lic, date=a.get("date_created", ""),
                 url=f"https://osf.io/{i}/", doi="", public=a.get("public"))
    elif r == "mendeley":
        d = curl(f"https://data.mendeley.com/public-api/datasets/{i}")
        m = dict(title=d["name"], desc=text(d.get("description")), license=(d.get("data_licence") or {}).get("short_name", ""),
                 date=d.get("publish_date", ""), url=f"https://data.mendeley.com/datasets/{i}", doi=(d.get("doi") or {}).get("id", ""), public=True)
    elif r == "synapse":
        d = curl(f"https://repo-prod.prod.sagebase.org/repo/v1/entity/{i}")
        ar = curl(f"https://repo-prod.prod.sagebase.org/repo/v1/entity/{i}/accessRequirement")
        m = dict(title=d["name"], desc="", license="", date=d.get("createdOn", ""), url=f"https://www.synapse.org/Synapse:{i}", doi="",
                 public=None, access_requirements=ar.get("totalNumberOfResults", 0))
    else:
        raise SystemExit(f"unknown repo {r}")
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(m))
    return m


def main():
    entries = json.loads(Path(sys.argv[1]).read_text())
    today = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat()
    B = Batch(today)
    seen_urls, kept = set(), []
    for e in entries:
        m = read(e)
        keys = {k for k in (m["url"], (m.get("doi") or "").lower()) if k}
        if keys & seen_urls:
            print("skipped (same URL or DOI as an earlier entry):", e["dataset_id"])
            continue
        seen_urls |= keys
        kept.append(e)
    entries = kept
    for e in entries:
        m = read(e)
        did, repo = e["dataset_id"], e["repo"]
        R = B.dataset(did)
        kind = repo.split("_")[0]
        src = R.source(f"{did}_{kind}", m["url"], "repository_record", e.get("publisher", "authors"), title=m["title"], doi=m.get("doi", ""),
                       identity_basis=e.get("identity", "Repository record cited as the data location by the dataset's paper"),
                       note=f"Read through the {kind} API" + (f"; license is {m['license_from']}" if m.get("license_from") else ""))
        R.link(src, "distribution")
        if e.get("paper_doi"):
            ps = R.source(f"{did}_paper", "https://doi.org/" + e["paper_doi"], "paper", "authors", doi=e["paper_doi"],
                          title=e.get("paper_title", ""), identity_basis="The data descriptor of the dataset")
            R.link(ps, "paper")
        if e.get("name_from_paper"):
            R.ev("name", e["paper_title"], ps, "Article title", note="The repository record's title is generic")
        else:
            R.ev("name", text(m["title"]), src, "Record title", "script")
        hit = EEG.search(m["title"]) or EEG.search(m["desc"])
        if hit and not IEEG.search(m["title"] + " " + m["desc"]):
            R.ev("modalities", "scalp_eeg", src, " ".join(hit.group(0).split()[:25]))
        v = lic_value(m["license"])
        if v:
            R.ev("license_spdx", v, src, f"License: {m['license']}", "script")
        if m["date"][:4].isdigit():
            R.ev("year_published", m["date"][:4], src, f"Published {m['date'][:10]}", "script")
        R.child("access_routes", kind, route_kind="repository", url=m["url"])
        if repo == "synapse":
            doc = R.source("synapse_download_doc", SYNAPSE_DOC, "distribution_page", "authors",
                           title="Downloading Data Programmatically - Synapse", identity_basis="Documentation of the repository that holds the data",
                           note="Repository-wide documentation")
            R.ev(f"access_routes:{kind}.access_method", "free_account_required", doc, "syn = synapseclient.login() ... syn.get(...)",
                 note="The documented download examples log in first")
            R.ev(f"access_routes:{kind}.human_steps", "Create a Synapse account and log in", doc, "synLogin(email=..., password=...)")
            R.ev(f"access_routes:{kind}.automation_tool", "synapseclient", doc, "synapse get -r syn2390898")
        elif m.get("terms_of_access"):  # some files restricted; the terms say how to ask
            R.ev(f"access_routes:{kind}.access_method", "request_form_or_email", src, "Terms of Access: " + " ".join(m["terms_of_access"].split()[:18]), "script")
            R.ev(f"access_routes:{kind}.human_steps", m["terms_of_access"][:300], src, "Terms of Access", "script")
        elif m["public"]:
            R.ev(f"access_routes:{kind}.access_method", "direct_download", src, "Public record with files (API)", "script")
            R.ev(f"access_routes:{kind}.human_steps", "none", src, "Public record with files (API)", "script")
            R.ev(f"access_routes:{kind}.automation_tool", f"{kind}-api", src, "Files listed in the record API", "script")
    import collections
    norm = collections.defaultdict(list)
    for d in B.db["datasets"][1]:
        norm[re.sub(r"\W", "", d["name"].casefold())].append(d["dataset_id"])
        norm[re.sub(r"\W", "", d["dataset_id"].casefold())].append(d["dataset_id"])
    for r in B.db["aliases"][1]:
        if r["alias_type"] != "catalogue_id":
            norm[re.sub(r"\W", "", r["alias"].casefold())].append(r["dataset_id"])
    mine = {e["dataset_id"] for e in entries}
    for ids in norm.values():
        ids = sorted(set(ids))
        for a in [i for i in ids if i in mine]:
            for b in ids:
                if b != a:
                    kind = next(e["repo"].split("_")[0] for e in entries if e["dataset_id"] == a)
                    B.dataset(a).relation("possibly_same_as", b, f"{a}_{kind}", "Both print the same name; whether they are the same data is not checked")
    B.save()
    print(len(entries), "entries registered")


if __name__ == "__main__":
    main()
