"""Check a reviewer's audit output against the sources and register only what checks out.

Usage: python3 tools/audit/apply.py RESULT_JSON [--dry] [YYYY-MM-DD]

For every quote the reviewer gives, this script fetches the URL itself (cache/audit/pages/), turns it into
text (JSON is flattened, HTML stripped, PDF through pdftotext, script-built pages through headless Chrome)
and accepts the quote only if its letters and digits appear in that order in the page. For numbers, the
value must also appear in the quote. Nothing a reviewer says is registered without that check.

Applied when checked: facts (datasets columns and the recording setup), tasks with paradigms, participant
groups, annotations, quality information, the paper as a source, and whether the record is the dataset
authors' own (source_type). Removal verdicts and copies are not applied here: they are written to
cache/audit/decisions/<batch>.json for a person (or a second check) to decide.
A report of accepted and rejected items goes to cache/audit/reports/<batch>.json.
"""
import datetime, hashlib, html, json, re, subprocess, sys, unicodedata, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
from reglib import Batch  # noqa: E402

PAGES = ROOT / "cache/audit/pages"
DATASET_FIELDS = {"n_subjects_reported": "int", "hours_reported": "num", "modalities": "enum", "domains": "enum", "year_published": "int", "license_spdx": "enum"}
SETUP_FIELDS = {"device_manufacturer": "text", "device_model": "text", "electrode_type": "enum", "n_channels_eeg": "int", "montage_system": "enum",
                "reference": "text", "ground": "text", "sampling_rate_hz": "num", "line_freq_hz": "int", "hardware_filter": "text"}
GROUP_FIELDS = {"n_subjects": "int", "condition": "enum", "diagnosis": "text", "age_min": "num", "age_max": "num", "age_mean": "num", "age_sd": "num",
                "n_female": "int", "n_male": "int", "handedness": "text"}
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
           "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
           "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100}


def alnum(s):
    s = unicodedata.normalize("NFKC", html.unescape(s or "")).casefold()
    return re.sub(r"[^0-9a-z぀-ヿ一-鿿]+", "", s)


def flatten(o):
    if isinstance(o, dict):  # keys too: reviewers quote sidecar lines such as "SamplingFrequency": 512
        return " ".join(f"{k} {flatten(v)}" for k, v in o.items())
    if isinstance(o, list):
        return " ".join(flatten(v) for v in o)
    return str(o) if o is not None else ""


def strip_html(t):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S | re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", t))


def curl(url, out):
    r = subprocess.run(["curl", "-sL", "-m", "90", "-A", "Mozilla/5.0", "-o", str(out), "-w", "%{http_code} %{content_type}", url], capture_output=True, text=True)
    return r.stdout


def fetch(url):
    """Text of a page as this script sees it (cached)."""
    PAGES.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    f = PAGES / f"{key}.txt"
    if f.exists():
        return f.read_text()
    raw = PAGES / f"{key}.raw"
    info = curl(url, raw)
    if not info.startswith("2"):  # some hosts (figshare downloads) refuse a browser user agent
        r = subprocess.run(["curl", "-sL", "-m", "90", "-o", str(raw), "-w", "%{http_code} %{content_type}", url], capture_output=True, text=True)
        info = r.stdout
    data = raw.read_bytes() if raw.exists() else b""
    m = re.match(r"https?://zenodo\.org/(?:api/)?records?/(\d+)", url)
    zc = ROOT / "cache" / "zenodo" / f"{m.group(1)}.json" if m else None
    if not info.startswith("2") and zc and zc.exists():
        # zenodo.org refuses this network at times; use the copy of the same API record fetched at registration
        data, info = zc.read_bytes(), "200 application/json"
    text = ""
    if data[:5] == b"%PDF-" or "pdf" in info:
        text = subprocess.run(["pdftotext", "-q", str(raw), "-"], capture_output=True, text=True).stdout
    else:
        s = data.decode("utf-8", "replace")
        try:
            text = flatten(json.loads(s))
            text = strip_html(text)
        except ValueError:
            text = strip_html(s)
        if len(text.split()) < 300 and not url.startswith("https://api."):
            r = subprocess.run(["timeout", "120", "google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=25000", "--dump-dom", url],
                               capture_output=True, text=True)
            if len(r.stdout) > len(s):
                text = text + " " + strip_html(r.stdout)
    raw.unlink(missing_ok=True)
    f.write_text(" ".join(text.split()))
    (PAGES / f"{key}.url").write_text(url)
    return f.read_text()


def quote_ok(url, quote):
    if not url or not quote:
        return False, "missing"
    q = alnum(quote)
    if len(q) < 14:
        return False, "too short"
    t = alnum(fetch(url))
    if not t:
        return False, "page could not be read"
    return (q in t), ("" if q in t else "quote not found on the page")


def numbers_in(quote):
    out = set(re.findall(r"\d+(?:[.,]\d+)?", quote.replace(",", "")))
    for k in re.findall(r"(\d+(?:\.\d+)?)\s*kHz\b", quote.replace(",", "")):  # "1 kHz" states 1000 Hz
        out.add(f"{float(k) * 1000:g}")
    for w, n in WORDNUM.items():
        if re.search(rf"\b{w}\b", quote, re.I):
            out.add(str(n))
    m = re.findall(r"\b(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[- ](one|two|three|four|five|six|seven|eight|nine)\b", quote, re.I)
    for a, b in m:
        out.add(str(WORDNUM[a.lower()] + WORDNUM[b.lower()]))
    return out


def value_ok(kind, value, quote):
    v = str(value).strip()
    if not v:
        return False
    if kind in ("int", "num"):
        try:
            x = float(v)
        except ValueError:
            return False
        if not any(abs(float(n) - x) < 1e-9 for n in numbers_in(quote) if re.fullmatch(r"\d+(?:\.\d+)?", n)):
            return False
        # a bound ("over 22 hours", "≥ 1000 Hz") is not the value itself
        num = re.escape(v[:-2] if v.endswith(".0") else v)
        return not re.search(r"(?:[≥≤><~≈]|\b(?:over|about|approximately|approx\.?|around|nearly|almost|more than|less than|up to|at least|at most)\s*)\s*" + num + r"(?![\d.])", quote.replace(",", ""), re.I)
    if kind == "text":
        return alnum(v) in alnum(quote)
    return True  # other enums: the mapping is the reviewer's reading; the quote is checked


# enum values that must be visible in the quote itself (a reviewer's inference is not enough)
ENUM_WORDS = {"montage_system": {"10_20": r"(?<!extended )(?<!extended international )10\s*[-–/]\s*20", "10_10": r"10\s*[-–/]\s*10|10\s*%", "10_05": r"10\s*[-–/]\s*0?5\b",
                                 "egi_hydrocel": r"hydro\s*cel", "biosemi_abc": r"\bABC\b", "ear": r"\bear", "intracranial": r"intracranial|ECoG|depth|SEEG|subdural"},
              "electrode_type": {"dry": r"\bdry\b", "wet_gel": r"\bgel|paste", "saline": r"saline|sponge", "intracranial": r"intracranial|ECoG|depth|SEEG|subdural"},
              # a notch filter at 50 Hz does not say the line frequency is 50 Hz
              "line_freq_hz": {v: r"\bline|mains|power[- ]?(?:line|grid|supply)|utility|\bAC\b" for v in ("50", "60")}}


# a group's condition is taken only when the quote says it in words
_H = r"healthy|neurotypical|typically developing|no (?:history|known)|without (?:any )?(?:history|neurolog|psychiatr)"
_P = r"patient|diagnos|disorder|disease|epilep|syndrome|injur|stroke|tumou?r|lesion|impair|autis|ADHD|schizophren|dementia|alzheimer|parkinson|depress"
COND_WORDS = {"healthy": _H, "patient": _P, "mixed": rf"(?=.*(?:{_H}|control))(?=.*(?:{_P}))"}


def _enums():
    import csv
    out = {}
    for r in csv.DictReader(open(ROOT / "schema/enums.csv", encoding="utf-8")):
        out.setdefault(r["enum"], set()).add(r["value"])
    return out


ENUMS = _enums()
ENUMS.setdefault("quality_kind", set()); ENUMS.setdefault("annotation_item", set())
ENUM_OF = {"modalities": "modality", "domains": "domain", "license_spdx": "license_spdx", "electrode_type": "electrode_type",
           "montage_system": "montage_system", "condition": "group_condition", "paradigms": "paradigm"}


def in_vocab(fld, v):
    """Every ;-item of an enum value must be in the schema's vocabulary."""
    e = ENUM_OF.get(fld)
    return True if not e else all(x in ENUMS[e] for x in str(v).split(";") if x)


def enum_ok(fld, v, quote):
    if not in_vocab(fld, v):
        return False
    pat = ENUM_WORDS.get(fld, {}).get(v)
    return True if fld not in ENUM_WORDS else bool(pat and re.search(pat, quote, re.I))


def fmt(kind, v):
    v = str(v).strip()
    if kind == "int":
        return str(int(float(v)))
    if kind == "num":
        f = float(v)
        return f"{f:g}"
    return " ".join(v.split())


def src_for(R, B, url, record_primary, title=""):
    host = urllib.parse.urlparse(url).netloc.lower()
    paperish = any(h in host for h in ("doi.org", "ncbi.nlm.nih.gov", "arxiv.org", "biorxiv", "medrxiv", "frontiersin", "nature.com", "plos", "mdpi",
                                       "elifesciences", "sciencedirect", "springer", "wiley", "ieee", "acm.org", "oup.com", "tandfonline", "sagepub", "cell.com",
                                       "jneurosci", "physiology.org", "biomedcentral", "hindawi", "iop.org", "mitpressjournals", "direct.mit.edu", "openreview", "aclanthology"))
    repo = any(h in host for h in ("zenodo", "figshare", "dataverse", "rdr.kuleuven", "openneuro", "nemar", "huggingface", "osf.io", "physionet", "mendeley", "dryad", "synapse"))
    for s in B.db["sources"][1]:
        if s["url"] == url:
            R.link(s["source_id"], "paper" if s["kind"] == "paper" else "other")
            return s["source_id"]
    kind = "paper" if paperish else "repository_record" if repo else "distribution_page"
    pub = "authors" if paperish or (repo and record_primary) else "third_party"
    sid = f"{R.D}_doc{hashlib.sha1(url.encode()).hexdigest()[:6]}"
    sid = R.source(sid, url, kind, pub, title=title, identity_basis="Read by an audit reviewer for this dataset; the quote was checked on the page by script",
                   note="Added during the 2026-11 audit")
    R.link(sid, "paper" if kind == "paper" else "other")
    return sid


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    path = Path(args[0])
    today = args[1] if len(args) > 1 else datetime.date.today().isoformat()
    items = json.loads(path.read_text())
    B = Batch(today)
    have = {d["dataset_id"]: d for d in B.db["datasets"][1]}
    rep = {"accepted": [], "rejected": []}
    decisions = []

    def check(did, what, url, quote):
        ok, why = quote_ok(url, quote)
        (rep["accepted"] if ok else rep["rejected"]).append({"dataset_id": did, "what": what, "url": url, "quote": quote, "why": why})
        return ok

    for it in items:
        did = it.get("dataset_id")
        if did not in have:
            rep["rejected"].append({"dataset_id": did, "what": "unknown dataset_id"})
            continue
        R = B.dataset(did)
        ve = it.get("verdict_evidence") or {}
        if it.get("verdict") in ("remove", "unclear") or it.get("copy_of"):
            vok = bool(ve) and check(did, "verdict", ve.get("url"), ve.get("quote"))
            cp = it.get("copy_of") or {}
            cok = bool(cp) and check(did, "copy_of", cp.get("url_or_doi") if str(cp.get("url_or_doi", "")).startswith("http") else (ve.get("url") or ""), cp.get("quote"))
            decisions.append({"dataset_id": did, "name": have[did]["name"], "verdict": it.get("verdict"), "reason": it.get("verdict_reason"),
                              "evidence": ve, "evidence_checked": vok, "copy_of": cp, "copy_checked": cok, "notes": it.get("notes", "")})
        rb = it.get("record_by_dataset_authors") or {}
        record_primary = False
        if rb.get("answer") == "yes" and rb.get("url"):
            # a creator list: every surname-like word (3+ letters) must be on the record page
            words = [w for w in re.findall(r"[A-Za-z\u00C0-\u024F'-]{3,}", rb.get("quote", "")) if w.lower() not in ("and", "the")]
            page = alnum(fetch(rb["url"]))
            ok = bool(words) and all(alnum(w) in page for w in words)
            (rep["accepted"] if ok else rep["rejected"]).append({"dataset_id": did, "what": "record_by_authors", "url": rb.get("url"), "quote": rb.get("quote"),
                                                                "why": "" if ok else "a name is not on the record page"})
            record_primary = ok
        # the record source(s) of this dataset: primary only when checked
        for ln in B.db["dataset_sources"][1]:
            if ln["dataset_id"] == did and ln["role"] == "distribution":
                s = next(x for x in B.db["sources"][1] if x["source_id"] == ln["source_id"])
                if s["kind"] == "repository_record" and s["source_id"].startswith(did.split("_")[0]):
                    s.update(publisher="authors" if record_primary else "third_party", source_type="primary" if record_primary else "secondary")
        p = it.get("paper") or {}
        if p.get("doi") and p.get("read") in ("full_text", "abstract_only"):
            doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", p["doi"]).strip()
            url = "https://doi.org/" + doi
            ex = next((x for x in B.db["sources"][1] if x["doi"].lower() == doi.lower()), None)
            if ex:
                R.link(ex["source_id"], "paper" if ex["kind"] == "paper" else "other")
            else:
                sid = R.source(f"{did}_paper_a", url, "paper", "authors", doi=doi, title=" ".join(str(p.get("title", "")).split()),
                               identity_basis="Named by the dataset's record or README as the dataset's paper (audit reviewer)", note="Added during the 2026-11 audit")
                R.link(sid, "paper")
        setup_rows = {r["setup_id"]: r for r in B.db["acquisition_setups"][1] if r["dataset_id"] == did}
        for fct in it.get("facts", []):
            fld, val, url, q = fct.get("field"), fct.get("value"), fct.get("url"), fct.get("quote")
            scope = (fct.get("scope") or "").lower()
            if fld == "year_published":  # reviewers quoted submission or paper years; the release year comes from the record itself
                rep["rejected"].append({"dataset_id": did, "what": fld, "why": "year_published is taken from repository records only"})
                continue
            if fld in DATASET_FIELDS:
                kind, key = DATASET_FIELDS[fld], fld
            elif fld in SETUP_FIELDS:
                kind, key = SETUP_FIELDS[fld], f"acquisition_setups:main.{fld}"
            else:
                rep["rejected"].append({"dataset_id": did, "what": f"unknown field {fld}"})
                continue
            if fld in ("n_subjects_reported", "hours_reported") and scope and not re.search(r"whole|all|entire|dataset|total", scope):
                rep["rejected"].append({"dataset_id": did, "what": fld, "why": f"scope '{scope}' is not the whole dataset"})
                continue
            if not check(did, fld, url, q):
                continue
            if not value_ok(kind, val, q) or not enum_ok(fld, str(val).strip(), q):
                rep["rejected"].append({"dataset_id": did, "what": fld, "why": "value not in quote", "value": val, "quote": q})
                rep["accepted"].pop()
                continue
            try:
                v = fmt(kind, val)
            except ValueError:
                continue
            if fld in SETUP_FIELDS and "main" not in setup_rows:
                setup_rows["main"] = R.child("acquisition_setups", "main", description="As stated in the documents cited for each value")
            sid = src_for(R, B, url, record_primary)
            loc = " ".join(q.split()[:25])
            cur = have[did].get(fld, "") if fld in DATASET_FIELDS else setup_rows["main"].get(fld, "")
            try:
                # modalities from the harvest scripts were coarse ("the name says EEG"); a checked, specific statement replaces them
                if fld == "modalities" and cur and cur != v:
                    R.ev(key, v, sid, loc, "claude", f"Audit reviewer; replaces a value read from a name or a generic modality field")
                elif cur and cur != v and cur not in ("unknown", "NA", "conflicting"):
                    R.conflicting(key, v, sid, loc, "claude", f"Audit reviewer; scope: {scope or 'not given'}")
                else:
                    R.ev(key, v, sid, loc, "claude", f"Audit reviewer; scope: {scope or 'not given'}")
            except SystemExit as e:
                rep["rejected"].append({"dataset_id": did, "what": fld, "why": str(e)})
        tasks = {t["task_id"]: t for t in B.db["tasks"][1] if t["dataset_id"] == did}
        for t in it.get("tasks", []):
            if not check(did, "task", t.get("url"), t.get("quote")):
                continue
            name = " ".join(str(t.get("task_name", "")).split())
            tid = next((k for k, r in tasks.items() if r["task_name"].casefold() == name.casefold()), None)
            if not tid:
                tid = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40].strip("_") or "task"
                tid = tid if tid[0].isalpha() else "t_" + tid
                while tid in tasks and tasks[tid]["task_name"].casefold() != name.casefold():
                    tid += "_x"
                tasks[tid] = R.child("tasks", tid)
            sid = src_for(R, B, t["url"], record_primary)
            loc = " ".join(t["quote"].split()[:25])
            if name and not tasks[tid]["task_name"]:
                R.ev(f"tasks:{tid}.task_name", name, sid, loc, "claude")
            pars = ";".join(sorted({p for p in t.get("paradigms", []) if p and p in ENUMS["paradigm"]}))
            if pars and not tasks[tid]["paradigms"]:
                R.ev(f"tasks:{tid}.paradigms", pars, sid, loc, "claude")
        groups = {g["group_id"]: g for g in B.db["participant_groups"][1] if g["dataset_id"] == did}
        for g in it.get("groups", []):
            if not check(did, "group", g.get("url"), g.get("quote")):
                continue
            label = " ".join(str(g.get("group_label") or "all participants").split())
            gid = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:30].strip("_") or "all"
            gid = gid if gid[0].isalpha() else "g_" + gid
            if gid not in groups:
                groups[gid] = R.child("participant_groups", gid, group_label=label)
            sid = src_for(R, B, g["url"], record_primary)
            loc = " ".join(g["quote"].split()[:25])
            for fld, kind in GROUP_FIELDS.items():
                val = g.get(fld)
                if val in (None, "") or groups[gid].get(fld):
                    continue
                if kind != "enum" and not value_ok(kind, val, g["quote"]):
                    rep["rejected"].append({"dataset_id": did, "what": f"group.{fld}", "why": "value not in quote", "value": val})
                    continue
                if kind == "enum" and not re.search(COND_WORDS.get(val, r"(?!)"), g["quote"], re.I):
                    rep["rejected"].append({"dataset_id": did, "what": f"group.{fld}", "why": "condition not stated in quote", "value": val})
                    continue
                try:
                    R.ev(f"participant_groups:{gid}.{fld}", fmt(kind, val) if kind in ("int", "num") else " ".join(str(val).split()), sid, loc, "claude")
                except (SystemExit, ValueError) as e:
                    rep["rejected"].append({"dataset_id": did, "what": f"group.{fld}", "why": str(e)})
        anns = {(a["item"], a["name"]) for a in B.db["annotations"][1] if a["dataset_id"] == did}
        for a in it.get("annotations", []):
            if (a.get("item"), a.get("name")) in anns or a.get("item") not in ENUMS["annotation_item"] or not check(did, "annotation", a.get("url"), a.get("quote")):
                continue
            sid = src_for(R, B, a["url"], record_primary)
            R.add_row("annotations", "claude", item=a["item"], name=" ".join(str(a["name"]).split()), labels=";".join(x.strip() for x in str(a.get("labels", "")).split(";") if x.strip()),
                      source_id=sid, locator=" ".join(a["quote"].split()[:25]))
            anns.add((a["item"], a["name"]))
        quals = {(q["kind"], q["description"]) for q in B.db["quality_info"][1] if q["dataset_id"] == did}
        for qi in it.get("quality", []):
            if (qi.get("kind"), " ".join(str(qi.get("description", "")).split())[:400]) in quals:
                continue
            if qi.get("kind") not in ENUMS["quality_kind"] or not check(did, "quality", qi.get("url"), qi.get("quote")):
                continue
            sid = src_for(R, B, qi["url"], record_primary)
            R.add_row("quality_info", "claude", kind=qi["kind"], description=" ".join(str(qi.get("description", "")).split())[:400], form="stated in the document",
                      source_id=sid, locator=" ".join(qi["quote"].split()[:25]))
    tag = path.stem
    for sub in ("reports", "decisions"):
        (ROOT / "cache/audit" / sub).mkdir(parents=True, exist_ok=True)
    (ROOT / f"cache/audit/reports/{tag}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    (ROOT / f"cache/audit/decisions/{tag}.json").write_text(json.dumps(decisions, ensure_ascii=False, indent=1))
    na, nr = len(rep["accepted"]), len(rep["rejected"])
    print(f"{tag}: {na} quotes accepted, {nr} rejected ({nr / max(1, na + nr):.0%}); {len(decisions)} removal/copy decisions queued")
    if not dry:
        B.save()


if __name__ == "__main__":
    main()
