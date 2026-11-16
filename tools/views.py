"""Generate views/ from data/.

Usage: python3 tools/views.py      (rewrite every view)
validate.py regenerates them in memory and fails if the files on disk differ.

- views/datasets_wide.csv   one row per dataset, with source URLs and the stage of checking
- views/discrepancies.csv   conflicting evidence and reported-vs-release differences
- views/access_summary.csv  datasets, subjects and hours per access tier and method (EEG signals and undecided only)
"""

import csvio
import db as dbmod
import derive

EXTRA_COLS = ["documents_checked", "implementation_checked", "access_observed", "paper_url", "distribution_url",
              "mirror_url", "catalogue_url", "readme_url", "other_url", "annotation_items", "license_checked_on",
              "license_checked_by", "oldest_checked_on", "latest_checked_on"]
DISC_COLS = ["dataset_id", "field", "kind", "value", "source_type", "source_ref", "note"]
DISC_KEYS = ("dataset_id", "field", "kind", "value", "source_ref")
ACC_COLS = ["access_tier", "access_method", "n_datasets", "n_subjects_reported", "hours_reported",
            "n_datasets_without_subjects", "n_datasets_without_hours"]
PAIRS = [("n_subjects_reported", "n_subjects_release"), ("n_sessions_reported", "n_sessions_release"),
         ("n_recordings_reported", "n_recordings_release")]


def src_url(sources, sid):
    r = sources.get(sid)
    return (r["url"] or r["source_id"]) if r else ""


def wide(db):
    sources = {r["source_id"]: r for r in db["sources"][1]}
    urls = {}
    for r in db["dataset_sources"][1]:
        urls.setdefault((r["dataset_id"], r["role"]), []).append(src_url(sources, r["source_id"]))
    stage, dates, lic = {}, {}, {}
    for e in db["evidence"][1]:
        if e["status"] not in ("current", "conflicting"):
            continue
        s = sources.get(e["source_id"], {})
        st = stage.setdefault(e["dataset_id"], set())
        if s.get("source_type") == "primary":
            st.add("documents")
        if s.get("source_type") == "implementation":
            st.add("implementation")
        dates.setdefault(e["dataset_id"], []).append(e["checked_on"])
        if e["field"] == "license_spdx":
            lic.setdefault(e["dataset_id"], []).append(e)
    observed = {}
    for r in db["access_routes"][1]:
        if r["access_observed"]:
            observed.setdefault(r["dataset_id"], []).append(f"{r['route_id']}:{r['access_observed']}")
    items = {}
    for a in db["annotations"][1]:
        items.setdefault(a["dataset_id"], set()).add(a["item"])
    out = []
    for d in db["datasets"][1]:
        i = d["dataset_id"]
        dd = sorted(dates.get(i, []))
        le = lic.get(i, [])
        row = dict(d)
        row.update({
            "documents_checked": "true" if "documents" in stage.get(i, ()) else "false",
            "implementation_checked": "true" if "implementation" in stage.get(i, ()) else "false",
            "access_observed": ";".join(sorted(observed.get(i, []))),
            **{f"{role}_url": ";".join(urls.get((i, role), []))
               for role in ("paper", "distribution", "mirror", "catalogue", "readme", "other")},
            "annotation_items": ";".join(sorted(items.get(i, ()))),
            "license_checked_on": max((e["checked_on"] for e in le), default=""),
            "license_checked_by": ";".join(sorted({e["checked_by"] for e in le})),
            "oldest_checked_on": dd[0] if dd else "",
            "latest_checked_on": dd[-1] if dd else "",
        })
        out.append(row)
    return out


def discrepancies(db):
    sources = {r["source_id"]: r for r in db["sources"][1]}
    out = []
    for e in db["evidence"][1]:
        if e["status"] == "conflicting":
            out.append({"dataset_id": e["dataset_id"], "field": e["field"], "kind": "conflicting",
                        "value": e["value"], "source_type": sources.get(e["source_id"], {}).get("source_type", ""),
                        "source_ref": src_url(sources, e["source_id"]), "note": e["note"]})
    for d in db["datasets"][1]:
        for a, b in PAIRS:
            if d[a].isdigit() and d[b].isdigit() and d[a] != d[b]:
                out.append({"dataset_id": d["dataset_id"], "field": f"{a} vs {b}", "kind": "reported_vs_release",
                            "value": f"{d[a]} vs {d[b]}", "source_type": "", "source_ref": "", "note": ""})
    return out


def _num(v):
    try:
        return float(v)
    except ValueError:
        return None


def access_summary(db):
    groups = {}
    for d in db["datasets"][1]:
        if d["content_class"] not in ("", "eeg_signals"):
            continue  # only releases that hold, or may hold, human EEG signals
        groups.setdefault((d["access_tier"], d["best_access_method"]), []).append(d)
    tier_order = list(dict.fromkeys(derive.TIER.values())) + [""]
    out = []
    for (tier, method), ds in groups.items():
        subj = [_num(d["n_subjects_reported"]) for d in ds]
        hrs = [_num(d["hours_reported"]) for d in ds]
        out.append({"access_tier": tier, "access_method": method, "n_datasets": str(len(ds)),
                    "n_subjects_reported": str(int(sum(x for x in subj if x is not None))),
                    "hours_reported": f"{sum(x for x in hrs if x is not None):g}",
                    "n_datasets_without_subjects": str(sum(x is None for x in subj)),
                    "n_datasets_without_hours": str(sum(x is None for x in hrs))})
    order = derive.ACCESS_ORDER + [""]
    out.sort(key=lambda r: (tier_order.index(r["access_tier"]), order.index(r["access_method"])))
    return out


def build(db):
    """Return {relative path: canonical file text}."""
    return {
        "views/datasets_wide.csv": csvio.format_rows(db["datasets"][0] + EXTRA_COLS, wide(db), ("dataset_id",)),
        "views/discrepancies.csv": csvio.format_rows(DISC_COLS, discrepancies(db), DISC_KEYS),
        "views/access_summary.csv": csvio.format_rows(ACC_COLS, access_summary(db)),
    }


def main():
    for path, text in build(dbmod.load()).items():
        (csvio.ROOT / path).write_bytes(text.encode("utf-8"))
        print("wrote", path, text.count("\n") - 1, "rows")


if __name__ == "__main__":
    main()
