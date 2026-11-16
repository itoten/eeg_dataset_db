"""Register OpenNeuro EEG/iEEG datasets from the cache written by openneuro_fetch.py.

Usage: python3 tools/harvest/openneuro_register.py [YYYY-MM-DD] [dsXXXXXX ...]

With accession numbers, only those datasets are registered (rows are added, not merged, so
register each dataset once).

Reads cache/openneuro/*.json (git-ignored). Every value comes from the snapshot record (shown on the
dataset page) or from a metadata file of the release (dataset_description, participants.json/tsv,
one *_eeg.json sidecar, one *_channels.tsv). Nothing is counted or inferred; values that cannot be
mapped to the schema's vocabulary are left empty and listed in cache/openneuro_unmapped.tsv.
Evidence rows are checked_by=script.
"""

import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
from reglib import Batch  # noqa: E402

CACHE = ROOT / "cache" / "openneuro"
UNMAPPED = ROOT / "cache" / "openneuro_unmapped.tsv"
BY = "script"

LICENSES = [
    (r"^(cc0|cc0[ -]?1\.0|cc-0|cc 0|cc0 license|creative commons zero.*|public domain.*cc0.*)$", "CC0-1.0"),
    (r"^(pddl|odc[- ]pddl.*)$", "PDDL-1.0"),
    (r"^cc[- ]?by[- ]?4\.0$|^cc[- ]by[- ]4\.0 international$|^creative commons attribution 4\.0.*$", "CC-BY-4.0"),
    (r"^cc[- ]?by[- ]?3\.0$", "CC-BY-3.0"),
    (r"^cc[- ]?by[- ]?sa[- ]?4\.0$", "CC-BY-SA-4.0"),
    (r"^cc[- ]?by[- ]?nc[- ]?4\.0$", "CC-BY-NC-4.0"),
    (r"^cc[- ]?by[- ]?nc[- ]?sa[- ]?4\.0$", "CC-BY-NC-SA-4.0"),
    (r"^cc[- ]?by[- ]?nc[- ]?nd[- ]?4\.0$", "CC-BY-NC-ND-4.0"),
    (r"^odbl([- ]1\.0)?$", "ODbL-1.0"),
]
CHANNEL_TYPES = {"EEG": "eeg", "EOG": "eog", "HEOG": "eog", "VEOG": "eog", "ECG": "ecg", "EKG": "ecg",
                 "EMG": "emg", "TRIG": "trigger", "TRIGGER": "trigger", "STIM": "trigger", "MISC": "misc",
                 "REF": "ref", "RESP": "resp", "GSR": "eda", "EDA": "eda", "AUDIO": "audio",
                 "SEEG": "ieeg", "ECOG": "ieeg", "DBS": "ieeg"}
FIELD_CATEGORIES = [
    (r"^age", "age"), (r"^(sex|gender)$", "sex_gender"), (r"^(hand|handedness)$", "handedness"),
    (r"^(weight|body_?weight)", "weight"), (r"^height", "height"), (r"^(diagnosis|dx)$", "diagnosis"),
    (r"^(medication|meds)$", "medication"), (r"^(education|edu|years_of_education)$", "education"),
]
unmapped = []


def clean(v):
    return re.sub(r"\s+", " ", str(v)).strip()


def num(v, integer=False):
    if isinstance(v, bool) or v in (None, "", "n/a", "N/A"):
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    if f < 0:
        return ""
    if integer:
        return str(int(f)) if f == int(f) else ""
    return f"{f:g}" if f == int(f) else f"{f}"


def slug(s, taken):
    b = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "task"
    if not b[0].isalpha():
        b = "t_" + b
    out, i = b, 2
    while out in taken:
        out, i = f"{b}_{i}", i + 1
    taken.add(out)
    return out


def license_value(text):
    t = clean(text).lower().rstrip(".")
    for pat, val in LICENSES:
        if re.match(pat, t):
            return val
    return ""


def montage(text):
    t = clean(text).lower()
    if re.search(r"10[-/ ]?(05|5)\b|10-5", t):
        return "10_05"
    if re.search(r"10[-/ ]?10|10 ?%|10 percent", t):
        return "10_10"
    if re.search(r"10[-/ ]?20", t):
        return "10_20"
    return ""


def register(B, c):
    d = c["dataset"]
    ds = d["id"]
    snap = d["latestSnapshot"]
    tag, desc, summ = snap["tag"], snap["description"] or {}, snap["summary"] or {}
    mods = {m.lower() for m in (summ.get("modalities") or []) + (summ.get("secondaryModalities") or [])}
    name_eeg = re.search(r"(?<![A-Za-z])(EEG|iEEG|ECoG|electroenceph\w*)", desc.get("Name") or "", re.I)
    if not mods & {"eeg", "ieeg"} and not (not mods and name_eeg):
        return False  # MEG-only and other datasets without EEG are out of scope
    R = B.dataset(ds.lower())
    rec_url = f"https://openneuro.org/datasets/{ds}/versions/{tag}"
    doi = desc.get("DatasetDOI") or ""
    if doi and ds.lower() not in doi.lower():
        unmapped.append((ds, "DatasetDOI (not this accession)", doi))
        doi = ""
    rec = R.source(f"{ds.lower()}_record", rec_url, "repository_record", "authors", title=clean(desc.get("Name") or ""),
                   doi=doi, describes_version=f"snapshot {tag}",
                   identity_basis=f"OpenNeuro accession {ds}",
                   note="Read through the OpenNeuro GraphQL API; the dataset page shows the same values")
    R.link(rec, "distribution")
    R.alias(ds, "catalogue_id", rec)

    name = clean(desc.get("Name") or "")
    if name:
        R.ev("name", name, rec, "dataset_description.json Name (page title)", BY)
    lic = clean(desc.get("License") or "")
    if lic:
        v = license_value(lic)
        if v:
            R.ev("license_spdx", v, rec, f"License: {lic[:80]}", BY)
        else:
            unmapped.append((ds, "license", lic))
    if desc.get("BIDSVersion"):
        R.ev("is_bids", "true", rec, f"dataset_description.json BIDSVersion {clean(desc['BIDSVersion'])}", BY)
    mapped = sorted({"eeg": "scalp_eeg", "ieeg": "ieeg"}[m] for m in mods if m in ("eeg", "ieeg"))
    if mapped:
        if "meg" in mods:
            mapped.append("meg")
        R.ev("modalities", ";".join(sorted(mapped)), rec, "Available Modalities: " + ", ".join(sorted(mods)), BY)
    elif not mods and name_eeg:  # the record shows no modalities; the Name says EEG
        kind = "ieeg" if re.match(r"(?i)ieeg|ecog", name_eeg.group(1)) else "scalp_eeg"
        R.ev("modalities", kind, rec, f"Name: {clean(desc['Name'])[:100]}", BY,
             "The record lists no modalities; the dataset name states the recording")
    subs = summ.get("subjects") or []
    if subs:
        R.ev("n_subjects_reported", str(len(subs)), rec, f"Participants {len(subs)}", BY)
    if summ.get("size"):
        gb = round(summ["size"] / 2**30, 2)
        R.ev("size_gb_reported", f"{gb:g}", rec, f"Size: {gb:g}GB", BY)

    # access route: the site-wide agreement banner and the S3 instructions of the download page
    R.child("access_routes", "openneuro", route_kind="repository", url=rec_url)
    R.ev("access_routes:openneuro.access_method", "site_terms_agreement", rec,
         "Floating agreement: By clicking I Agree, I affirm ... institutional permissions", BY,
         "The agreement is shown once per browser (OpenNeuro app, components/agreement.tsx)")
    R.ev("access_routes:openneuro.human_steps",
         "Click I Agree on the site's data use agreement (institutional permission to receive de-identified data; no re-identification)",
         rec, "Floating agreement text (common/content/download-agreement.ts)", BY)
    R.ev("access_routes:openneuro.automation_tool", "aws-s3;openneuro-cli;datalad", rec,
         "Download page: aws s3 sync --no-sign-request; openneuro download; datalad install", BY)

    taken = set()
    for t in summ.get("tasks") or []:
        tid = slug(t, taken)
        R.child("tasks", tid)
        R.ev(f"tasks:{tid}.task_name", clean(t), rec, f"Tasks: {clean(t)[:60]}", BY)

    texts = c.get("texts", {})
    side = next(((k, v) for k, v in texts.items() if k.startswith("sidecar:")), None)
    scope = c.get("sidecar_scope")
    if side:
        _, s = side
        try:
            j = json.loads(s["text"])
        except ValueError:
            j = None
        if isinstance(j, dict):
            sid = R.source(f"{ds.lower()}_sidecar", s["url"], "release_files", "authors", title=s["filename"],
                           describes_version=f"snapshot {tag}", identity_basis=f"File of OpenNeuro {ds}",
                           note=("Root-level sidecar" if scope == "root" else f"Sidecar of one recording in {scope}; other recordings not read"))
            where = s["filename"]
            R.child("acquisition_setups", "main",
                    description=("As stated in the root-level sidecar " + where if scope == "root"
                                 else f"As stated in the sidecar of one recording ({scope}/{where}); other recordings not read"))
            f = "acquisition_setups:main."
            for col, key, conv in (("sampling_rate_hz", "SamplingFrequency", num), ("line_freq_hz", "PowerLineFrequency", lambda v: num(v, True))):
                v = conv(j.get(key))
                if v:
                    R.ev(f + col, v, sid, f"{key}", BY)
            for col, key in (("device_manufacturer", "Manufacturer"), ("device_model", "ManufacturersModelName"),
                             ("reference", "EEGReference"), ("ground", "EEGGround")):
                v = clean(j.get(key) or "")
                if key == "EEGReference" and not v:
                    key, v = "iEEGReference", clean(j.get("iEEGReference") or "")
                if key == "EEGGround" and not v:
                    key, v = "iEEGGround", clean(j.get("iEEGGround") or "")
                if v and v.lower() not in ("n/a", "na", "unknown"):
                    R.ev(f + col, v[:200], sid, key, BY)
            n = num(j.get("EEGChannelCount"), True)
            if n and n != "0":  # 0 in an iEEG sidecar means no scalp channels
                R.ev(f + "n_channels_eeg", n, sid, "EEGChannelCount", BY)
            else:
                ec, se = num(j.get("ECOGChannelCount"), True), num(j.get("SEEGChannelCount"), True)
                if ec and ec != "0" and se in ("", "0"):
                    R.ev(f + "n_channels_eeg", ec, sid, "ECOGChannelCount", BY)
                elif se and se != "0" and ec in ("", "0"):
                    R.ev(f + "n_channels_eeg", se, sid, "SEEGChannelCount", BY)
            hw = j.get("HardwareFilters")
            if hw not in (None, "", "n/a", "N/A"):
                R.ev(f + "hardware_filter", clean(json.dumps(hw) if not isinstance(hw, str) else hw)[:300], sid, "HardwareFilters", BY)
            ps = clean(j.get("EEGPlacementScheme") or "")
            if ps:
                m = montage(ps)
                if m:
                    R.ev(f + "montage_system", m, sid, f"EEGPlacementScheme: {ps[:80]}", BY)
                else:
                    unmapped.append((ds, "EEGPlacementScheme", ps))

    ch = next(((k, v) for k, v in texts.items() if k.startswith("channels:")), None)
    if ch and side:
        _, s = ch
        lines = [ln.rstrip("\r") for ln in s["text"].split("\n") if ln.strip()]
        if lines and lines[0].split("\t")[:2] == ["name", "type"]:
            csid = R.source(f"{ds.lower()}_channels", s["url"], "release_files", "authors", title=s["filename"],
                            describes_version=f"snapshot {tag}", identity_basis=f"File of OpenNeuro {ds}",
                            note=("Root-level channels file" if scope == "root" else f"Channels file of one recording in {scope}"))
            seen = set()
            for i, ln in enumerate(lines[1:], 1):
                parts = ln.split("\t")
                if len(parts) < 2 or not parts[0].strip() or parts[0] in seen:
                    continue
                seen.add(parts[0])
                raw = parts[1].strip().upper()
                ctype = CHANNEL_TYPES.get(raw, "misc")
                R.add_row("channels", BY, setup_id="main", channel_name=clean(parts[0]), channel_type=ctype, order=str(i),
                      source_id=csid, locator=f"row {i}",
                      note="" if raw in CHANNEL_TYPES else f"type in the file: {clean(parts[1])[:40]}")

    ptsv = texts.get("participants.tsv")
    if ptsv:
        cols = [clean(x) for x in ptsv["text"].rstrip("\r").split("\t") if clean(x)]
        tsid = R.source(f"{ds.lower()}_participants_tsv", ptsv["url"], "release_files", "authors",
                        title="participants.tsv", describes_version=f"snapshot {tag}", identity_basis=f"File of OpenNeuro {ds}")
        pj = {}
        pjs = texts.get("participants.json")
        jsid = ""
        if pjs:
            try:
                pj = json.loads(pjs["text"])
            except ValueError:
                pj = {}
            if isinstance(pj, dict) and pj:
                jsid = R.source(f"{ds.lower()}_participants_json", pjs["url"], "release_files", "authors",
                                title="participants.json", describes_version=f"snapshot {tag}", identity_basis=f"File of OpenNeuro {ds}")
            else:
                pj = {}
        done = set()
        for col in cols:
            if col == "participant_id" or col in done:
                continue
            done.add(col)
            meta = pj.get(col) if isinstance(pj.get(col), dict) else {}
            cat = next((c for p, c in FIELD_CATEGORIES if re.match(p, col.lower())), "other")
            descr = clean(meta.get("Description") or meta.get("LongName") or "")[:300]
            unit = clean(meta.get("Units") or "")[:40]
            R.add_row("participant_fields", BY, field_name=col, category=cat, level="subject", description=descr, unit=unit,
                  source_id=jsid if (meta and jsid) else tsid,
                  locator=f"{'participants.json key' if (meta and jsid) else 'participants.tsv header'} {col}"[:120])
    return True


def main():
    today = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    B = Batch(today)
    only = set(sys.argv[2:])
    files = sorted(p for p in CACHE.glob("ds*.json") if not only or p.stem in only)
    n = sum(bool(register(B, json.loads(p.read_text()))) for p in files)
    # Different accessions whose dataset_description.json prints the same Name
    # (also against datasets from other sources with the same name)
    names = {}
    for d in B.db["datasets"][1]:
        if d["name"]:
            names.setdefault(re.sub(r"\W", "", d["name"].casefold()), []).append(d["dataset_id"])
    names = {k: v for k, v in names.items() if any(re.fullmatch(r"ds\d{6}", x) for x in v)}
    for name, ids in names.items():
        for i, a in enumerate(sorted(ids)):
            for b in sorted(ids)[i + 1:]:
                if not any(r["dataset_id"] == a and r["other_dataset_id"] == b for r in B.db["relations"][1]):
                    on = a if re.fullmatch(r"ds\d{6}", a) else b
                    B.dataset(a).relation("possibly_same_as", b, f"{on}_record",
                                          "Both print the same name; whether they are the same data is not checked")
    B.save()
    with open(UNMAPPED, "w", encoding="utf-8") as f:
        f.write("dataset\tfield\tvalue\n")
        for r in unmapped:
            f.write("\t".join(clean(x) for x in r) + "\n")
    print(f"{n} of {len(files)} cached datasets registered (the rest have no EEG); {len(unmapped)} unmapped values in {UNMAPPED.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
