"""Fill the datasets columns derived from access_routes, acquisition_setups and tasks.

Usage: python3 tools/derive.py      (rewrite data/datasets.csv)
validate.py computes the same values and fails if the file differs.
"""

import csvio
import db as dbmod

# Ordered from the least to the most human work; the best route is the first one found.
ACCESS_ORDER = ["direct_download", "free_account_required", "site_terms_agreement", "gated_click_through", "request_form_or_email",
                "credentialed_training", "signed_agreement", "paid_or_membership", "unavailable"]
TIER = {"direct_download": "open", "free_account_required": "one_time_human", "site_terms_agreement": "one_time_human",
        "gated_click_through": "per_dataset_human", "request_form_or_email": "approval",
        "credentialed_training": "approval", "signed_agreement": "approval",
        "paid_or_membership": "approval", "unavailable": "unavailable"}
DERIVED = ["best_access_method", "access_tier", "n_channels_eeg", "sampling_rates_hz",
           "montage_systems", "devices", "paradigms"]
NOT_VALUES = ("", "unknown", "NA", "none", "conflicting")


def _num_key(v):
    return float(v)


def _join(values, numeric=False):
    vals = {v for v in values if v not in NOT_VALUES}
    return ";".join(sorted(vals, key=_num_key if numeric else None))


def _fmt_num(v):
    return v[:-2] if v.endswith(".0") else v


def expected(db):
    """{dataset_id: {derived column: value}}."""
    by = {}
    for table in ("access_routes", "acquisition_setups", "tasks"):
        for r in db[table][1]:
            by.setdefault((table, r["dataset_id"]), []).append(r)
    out = {}
    for d in db["datasets"][1]:
        i = d["dataset_id"]
        routes = by.get(("access_routes", i), [])
        setups = by.get(("acquisition_setups", i), [])
        tasks = by.get(("tasks", i), [])
        methods = {r["access_method"] for r in routes}
        best = next((m for m in ACCESS_ORDER if m in methods), "")
        out[i] = {
            "best_access_method": best,
            "access_tier": TIER.get(best, ""),
            "n_channels_eeg": _join((s["n_channels_eeg"] for s in setups), numeric=True),
            "sampling_rates_hz": _join((_fmt_num(s["sampling_rate_hz"]) for s in setups), numeric=True),
            "montage_systems": _join(s["montage_system"] for s in setups),
            "devices": _join(" ".join(x for x in (s["device_manufacturer"], s["device_model"]) if x not in NOT_VALUES)
                             for s in setups),
            "paradigms": _join(p for t in tasks for p in t["paradigms"].split(";")),
        }
    return out


def apply(db):
    exp = expected(db)
    for d in db["datasets"][1]:
        d.update(exp[d["dataset_id"]])


def main():
    db = dbmod.load()
    apply(db)
    dbmod.save(db)
    print("derived columns written")


if __name__ == "__main__":
    main()
