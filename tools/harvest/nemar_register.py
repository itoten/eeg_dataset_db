"""Register NEMAR-native datasets (ids nm...) that hold EEG or iEEG, and add NEMAR routes to
OpenNeuro datasets that NEMAR mirrors (ids on...).

Usage: python3 tools/harvest/nemar_register.py [YYYY-MM-DD]

Reads cache/nemar/list.json (https://api.nemar.org/datasets, paged) and cache/nemar/detail/<id>.json
(https://api.nemar.org/datasets/<id>). NEMAR is a repository run by third parties: its records are
`secondary` sources (a hosting repository's own record, not the dataset authors'). Values are NEMAR's
record values (subjects, recordings, size, hours, rate, channel counts when all recordings agree).
A NEMAR dataset that says it is a version of another dataset by DOI is linked to it with derived_from
when that DOI is a source in the DB. Nothing is counted or inferred here.
"""

import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
from reglib import Batch  # noqa: E402

CACHE = ROOT / "cache" / "nemar"
BY = "script"
GUIDE = "https://docs.nemar.org/cli/guides/downloading/"
LIC = [(r"^cc0|zero", "CC0-1.0"), (r"^cc[- ]?by[- ]?nc[- ]?sa[- ]?4", "CC-BY-NC-SA-4.0"), (r"^cc[- ]?by[- ]?nc[- ]?nd[- ]?4", "CC-BY-NC-ND-4.0"),
       (r"^cc[- ]?by[- ]?nc[- ]?4", "CC-BY-NC-4.0"), (r"^cc[- ]?by[- ]?sa[- ]?4", "CC-BY-SA-4.0"), (r"^cc[- ]?by[- ]?nd[- ]?4", "CC-BY-ND-4.0"),
       (r"^cc[- ]?by[- ]?4", "CC-BY-4.0"), (r"^cc[- ]?by[- ]?3", "CC-BY-3.0"), (r"^odc[- ]?by", "ODC-By-1.0"), (r"^odbl", "ODbL-1.0"),
       (r"^pddl", "PDDL-1.0"), (r"^mit$", "MIT"), (r"^apache", "Apache-2.0")]
MODS = {"eeg": "scalp_eeg", "ieeg": "ieeg", "meg": "meg", "emg": "emg", "nirs": "fnirs", "fmri": "fmri", "func": "fmri"}
SYSTEMS = {"10-10": "10_10", "10-20": "10_20", "10-5": "10_05", "10-05": "10_05"}
HIDDEN = re.compile(r"[^\w]")


def num(v):
    try:
        f = float(v)
        return f if f >= 0 else None
    except (TypeError, ValueError):
        return None


def fmt(f):
    return f"{f:g}"


def slug_task(s, taken):
    b = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "task"
    if not b[0].isalpha():
        b = "t_" + b
    out, i = b, 2
    while out in taken:
        out, i = f"{b}_{i}", i + 1
    taken.add(out)
    return out


def main():
    today = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    L = {x["dataset_id"]: x for x in json.loads((CACHE / "list.json").read_text())}
    B = Batch(today)
    db = B.db
    doi_to_ds = {}
    srcdoi = {r["source_id"]: r["doi"].lower() for r in db["sources"][1] if r["doi"]}
    for r in db["dataset_sources"][1]:
        if r["source_id"] in srcdoi:
            doi_to_ds.setdefault(srcdoi[r["source_id"]], r["dataset_id"])
    skipped, n_new, n_routes = [], 0, 0
    guide = B.source("nemar_download_guide", GUIDE, "distribution_page", "third_party", title="Downloading Data - NEMAR documentation",
                     identity_basis="Documentation of the repository that hosts the datasets", note="Repository-wide documentation")
    have = {d["dataset_id"] for d in db["datasets"][1]}
    for did, x in sorted(L.items()):
        mods = [m for m in (x.get("modalities") or "").split(",") if m]
        if did.startswith("on"):
            ds = x.get("source_id") or ""
            if ds in have and ("eeg" in mods or "ieeg" in mods):
                R = B.dataset(ds)
                url = f"https://nemar.org/dataset/{did}"
                src = R.source(f"{ds}_nemar", url, "repository_record", "third_party", title=x["name"], doi=x.get("concept_doi") or "",
                               identity_basis=f"NEMAR record {did}, whose source is OpenNeuro {ds}", note="Read through the NEMAR API")
                R.link(src, "mirror")
                R.alias(did, "catalogue_id", src)
                R.child("access_routes", "nemar", route_kind="mirror", url=url)
                R.ev("access_routes:nemar.access_method", "direct_download", guide,
                     "datalad get resolves annexed files from NEMAR's public S3 special remote, so no NEMAR account is needed for published datasets", BY)
                R.ev("access_routes:nemar.human_steps", "none", guide, "no NEMAR account is needed for published datasets", BY)
                R.ev("access_routes:nemar.automation_tool", "nemar-cli;datalad;git-annex;wget", guide, "NEMAR CLI; datalad clone; git-annex; direct files (wget / curl / rclone)", BY)
                n_routes += 1
            continue
        if not ("eeg" in mods or "ieeg" in mods):
            skipped.append((did, x.get("modalities")))
            continue
        f = CACHE / "detail" / f"{did}.json"
        if not f.exists():
            print("no detail yet:", did)
            continue
        d = json.loads(f.read_text())["dataset"]
        enr = json.loads(d.get("enrichment_json") or "{}")
        R = B.dataset(did)
        url = f"https://nemar.org/dataset/{did}"
        src = R.source(f"{did}_nemar", url, "repository_record", "third_party", title=d["name"], doi=d.get("concept_doi") or "",
                       identity_basis=f"NEMAR record {did}",
                       note="Read through the NEMAR API. NEMAR is a hosting repository; the record's author list was not compared with the authors of the original publication")
        R.link(src, "distribution")
        R.ev("name", d["name"], src, "Record name", BY)
        mapped = sorted({MODS[m] for m in mods if m in MODS})
        R.ev("modalities", ";".join(mapped), src, "recording modalities: " + ", ".join(mods), BY)
        lic = (d.get("license") or "").strip().lower()
        v = next((val for p, val in LIC if re.search(p, lic)), "")
        if v:
            R.ev("license_spdx", v, src, f"License: {d['license']}", BY)
        if num(d.get("subject_count")) is not None:
            R.ev("n_subjects_reported", str(int(num(d["subject_count"]))), src, "subject_count", BY)
        if num(d.get("recording_count")):
            R.ev("n_recordings_reported", str(int(num(d["recording_count"]))), src, "recording_count (NEMAR's own measurement)", BY)
        if num(d.get("total_recording_duration")):
            R.ev("hours_reported", fmt(round(num(d["total_recording_duration"]) / 3600, 2)), src, "total_recording_duration in seconds, shown as hours (NEMAR's own measurement)", BY)
        if num(d.get("file_size")):
            R.ev("size_gb_reported", fmt(round(num(d["file_size"]) / 2**30, 2)), src, "file_size in bytes, shown as GB", BY)
        if d.get("bids_version"):
            R.ev("is_bids", "true", src, f"bids_version {d['bids_version']}", BY)
        if (d.get("first_published_at") or "")[:4].isdigit():
            R.ev("year_published", d["first_published_at"][:4], src, "first_published_at", BY)
        # recording setup: only values that agree across the recordings
        cmin, cmax = num(d.get("channel_count_min")), num(d.get("channel_count_max"))
        fs, pl, ref = num(d.get("sampling_frequency")), num(d.get("power_line_frequency")), (d.get("eeg_reference") or "").strip()
        sysm = SYSTEMS.get((d.get("electrode_system") or "").strip())
        if any((fs, pl, sysm, ref, cmin and cmin == cmax)):
            R.child("acquisition_setups", "main", description="As stated in the NEMAR record, which aggregates its recordings")
            s = "acquisition_setups:main."
            if cmin and cmin == cmax:
                R.ev(s + "n_channels_eeg", str(int(cmin)), src, "channel_count_min = channel_count_max (all channels, not only EEG)", BY)
            if fs:
                R.ev(s + "sampling_rate_hz", fmt(fs), src, "sampling_frequency", BY)
            if pl:
                R.ev(s + "line_freq_hz", str(int(pl)), src, "power_line_frequency", BY)
            if sysm:
                R.ev(s + "montage_system", sysm, src, f"electrode_system: {d['electrode_system']}", BY)
            if ref and ref.lower() not in ("n/a", "none", "unknown"):
                R.ev(s + "reference", ref[:200], src, "eeg_reference", BY)
        taken = set()
        for t in [t.strip() for t in (d.get("tasks") or "").split(",") if t.strip()]:
            tid = slug_task(t, taken)
            R.child("tasks", tid)
            R.ev(f"tasks:{tid}.task_name", t, src, "tasks", BY)
        R.child("access_routes", "nemar", route_kind="repository", url=url)
        R.ev("access_routes:nemar.access_method", "direct_download", guide,
             "datalad get resolves annexed files from NEMAR's public S3 special remote, so no NEMAR account is needed for published datasets", BY)
        R.ev("access_routes:nemar.human_steps", "none", guide, "no NEMAR account is needed for published datasets", BY)
        R.ev("access_routes:nemar.automation_tool", "nemar-cli;datalad;git-annex;wget", guide, "NEMAR CLI; datalad clone; git-annex; direct files (wget / curl / rclone)", BY)
        for ri in enr.get("related_identifiers", []):
            if ri.get("identifier_type") == "DOI" and ri.get("relation_type") in ("IsVersionOf", "IsDerivedFrom", "IsVariantFormOf"):
                o = doi_to_ds.get(ri["identifier"].lower())
                if o and o != did:
                    R.relation("derived_from", o, src, f"NEMAR lists {ri['identifier']} as {ri['relation_type']} this record")
        n_new += 1
    # same printed name as another dataset: record the suspicion (as for OpenNeuro)
    names = {}
    for d in db["datasets"][1]:
        if d["name"]:
            names.setdefault(HIDDEN.sub("", d["name"].casefold()), []).append(d["dataset_id"])
    for d in db["datasets"][1]:
        names.setdefault(HIDDEN.sub("", d["dataset_id"].casefold()), []).append(d["dataset_id"])
    for r in db["aliases"][1]:
        if r["alias_type"] != "catalogue_id":
            names.setdefault(HIDDEN.sub("", r["alias"].casefold()), []).append(r["dataset_id"])
    names = {k: sorted(set(v)) for k, v in names.items()}
    for ids in names.values():
        nm = [i for i in ids if i.startswith("nm")]
        for a in nm:  # the relation is recorded on the NEMAR row, whose own source is linked to it
            for b in ids:
                if b == a or any({r["dataset_id"], r["other_dataset_id"]} == {a, b} and r["relation"] == "possibly_same_as" for r in db["relations"][1]):
                    continue
                B.dataset(a).relation("possibly_same_as", b, f"{a}_nemar",
                                      "Both print the same name; whether they are the same data is not checked")
    B.save()
    print(f"{n_new} NEMAR-native datasets registered, {n_routes} NEMAR routes added to OpenNeuro datasets, {len(skipped)} skipped (no EEG/iEEG): {skipped[:5]}")


if __name__ == "__main__":
    main()
