"""Link the papers that dataset records point to, and read participant counts from their abstracts.

Usage: python3 tools/harvest/papers_link.py fetch    (Crossref lookups into cache/crossref/, slow)
       python3 tools/harvest/papers_link.py register [YYYY-MM-DD]

DOIs come from OpenNeuro ReferencesAndLinks and from Zenodo related identifiers of type isSupplementTo,
isDescribedBy and isDocumentedBy. A paper is a `paper` source of the dataset. For OpenNeuro the record only
lists the reference, so the paper is a secondary source with a note that it may not be the dataset's own
paper; Zenodo's isSupplementTo/isDescribedBy says the record belongs to the paper (primary source).
A participant count is read from the abstract with the strict phrase of text_facts.py when the cell is empty.
"""
import datetime, glob, html, json, re, sys, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from reglib import Batch  # noqa: E402
import text_facts  # noqa: E402
import polite  # noqa: E402

CACHE = ROOT / "cache" / "crossref"
SKIP_PREFIX = ("10.18112/", "10.5281/", "10.6084/", "10.13026/", "10.7303/", "10.17605/", "10.5524/", "10.82901/")


def wanted():
    out = {}  # dataset_id -> [(doi, basis)]
    for p in glob.glob(str(ROOT / "cache/openneuro/ds*.json")):
        d = json.load(open(p))["dataset"]
        for r in ((d["latestSnapshot"] or {}).get("description") or {}).get("ReferencesAndLinks") or []:
            for m in re.finditer(r"10\.\d{4,9}/[^\s,;\"<>)]+", r or ""):
                doi = m.group(0).rstrip(".")
                if not doi.startswith(SKIP_PREFIX):
                    out.setdefault(d["id"].lower(), []).append((doi, "openneuro_reference"))
    best = {}
    for p in glob.glob(str(ROOT / "cache/zenodo/*.json")):
        if not Path(p).stem.isdigit():
            continue
        d = json.load(open(p))
        c = str(d.get("conceptrecid") or d["id"])
        if c not in best or d["metadata"].get("publication_date", "") > best[c]["metadata"].get("publication_date", ""):
            best[c] = d
    for c, d in best.items():
        for r in d["metadata"].get("related_identifiers", []):
            if r.get("relation") in ("isSupplementTo", "isDescribedBy", "isDocumentedBy") and r.get("scheme") == "doi" and not r["identifier"].startswith(SKIP_PREFIX):
                out.setdefault(f"zenodo_{c}", []).append((r["identifier"], "zenodo_" + r["relation"]))
    return out


def fetch():
    CACHE.mkdir(parents=True, exist_ok=True)
    dois = sorted({doi for v in wanted().values() for doi, _ in v})
    for i, doi in enumerate(dois):
        f = CACHE / (urllib.parse.quote(doi, safe="") + ".json")
        if f.exists():
            continue
        try:
            f.write_text(polite.request("https://api.crossref.org/works/" + urllib.parse.quote(doi)).decode())
        except Exception as e:
            f.write_text(json.dumps({"error": str(e)[:80]}))
        if i % 50 == 0:
            print(i, len(dois), flush=True)


def register(today):
    B = Batch(today)
    have = {d["dataset_id"]: d for d in B.db["datasets"][1]}
    n = n_subj = 0
    for did, lst in wanted().items():
        if did not in have:
            continue
        seen = set()
        for doi, basis in lst:
            if doi.lower() in seen or len(seen) >= 2:
                continue
            f = CACHE / (urllib.parse.quote(doi, safe="") + ".json")
            if not f.exists():
                continue
            m = json.loads(f.read_text()).get("message")
            if not m or m.get("type") in ("dataset", "component") or not (m.get("title") or [""])[0]:
                continue
            seen.add(doi.lower())
            primary = basis.startswith("zenodo_")
            sid = f"{did}_paper" if len(seen) == 1 else f"{did}_paper_{len(seen)}"
            R = B.dataset(did)
            title = " ".join(html.unescape(m["title"][0]).split())
            note = ("The Zenodo record says it supplements or is described by this paper" if primary else
                    "Listed in the dataset record's ReferencesAndLinks; whether it is the dataset's own paper is not established")
            ex = next((x for x in B.db["sources"][1] if x["doi"].lower() == doi.lower()), None)
            if ex:  # the DOI is already a source (a paper cited twice, or the record itself): reuse it
                R.link(ex["source_id"], "paper" if primary and ex["kind"] == "paper" else "other")
                continue
            sid = R.source(sid, "https://doi.org/" + doi, "paper", "authors" if primary else "third_party", title=title, doi=doi,
                     identity_basis=note, note="Title read from Crossref")
            R.link(sid, "paper" if primary else "other")
            n += 1
            ab = text_facts.clean(m.get("abstract") or "")
            if ab and not have[did]["n_subjects_reported"] and not re.search(r"\b(synthetic|simulated)\b", ab, re.I):
                s = text_facts.facts(ab).get("n_subjects_reported")
                if s:
                    R.ev("n_subjects_reported", s[0], sid, f"Abstract: {s[1]}", "script", "Abstract as given by Crossref")
                    have[did]["n_subjects_reported"] = s[0]
                    n_subj += 1
    B.save()
    print(n, "paper sources linked;", n_subj, "participant counts from abstracts")


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        fetch()
    else:
        register(sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat())
