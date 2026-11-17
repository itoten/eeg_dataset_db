"""Apply a pair reviewer's answers (tools/audit/PAIRS.md) as relations, after checking the quotes on their pages.

Usage: python3 tools/audit/pairs.py RESULT_JSON [--dry]

An answer other than "unclear" is applied when at least one of its quotes is found at its URL. The relation
is written from a to b (and contains/subset_of mirrored from b to a), with the source of the first checked
quote. The possibly_same_as rows of the pair are removed, except when the two share a name, ID or alias
(as the validator compares them): the validator then needs them, and they stay next to the new relation.
"""
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "audit"))
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
import apply as A  # noqa: E402
from reglib import Batch  # noqa: E402

ANSWERS = {"version_of", "subset_of", "contains", "derived_from", "shares_subjects_with", "distinct_from"}
MIRROR = {"subset_of": "contains", "contains": "subset_of"}


def norm(s):
    return re.sub(r"[\W_]", "", s.casefold())


def main():
    path, dry = Path(sys.argv[1]), "--dry" in sys.argv
    B = Batch(datetime.date.today().isoformat())
    names = {d["dataset_id"]: {norm(d["name"]), norm(d["dataset_id"])} for d in B.db["datasets"][1]}
    for r in B.db["aliases"][1]:
        if r["alias_type"] != "catalogue_id" and r["dataset_id"] in names:
            names[r["dataset_id"]].add(norm(r["alias"]))
    rels = B.db["relations"][1]
    applied, unclear, failed = [], [], []
    for it in json.loads(path.read_text()):
        a, b, ans = it.get("a"), it.get("b"), it.get("answer")
        if a not in names or b not in names or ans not in ANSWERS:
            unclear.append((a, b, ans))
            continue
        ok = next((e for e in it.get("evidence") or [] if A.quote_ok(e.get("url"), e.get("quote"))[0]), None)
        if not ok:
            failed.append((a, b, ans))
            continue
        R = B.dataset(a)
        sid = A.src_for(R, B, ok["url"], False)
        note = "Pair review (audit, quote checked): " + " ".join(str(ok["quote"]).split()[:30])
        R.relation(ans, b, sid, note)
        if ans in MIRROR:
            B.dataset(b).relation(MIRROR[ans], a, sid, note)
        if not names[a] & names[b]:
            rels[:] = [r for r in rels if not (r["relation"] == "possibly_same_as" and {r["dataset_id"], r["other_dataset_id"]} == {a, b})]
        applied.append((a, b, ans))
    print(f"{path.stem}: {len(applied)} relations applied, {len(failed)} with no checked quote, {len(unclear)} unclear")
    for x in applied:
        print("  applied", *x)
    for x in failed:
        print("  no quote found", *x)
    if not dry:
        B.save()


if __name__ == "__main__":
    main()
