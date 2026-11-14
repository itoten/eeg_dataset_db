"""Record paradigms that a task name or a dataset name states in so many words.

Usage: python3 tools/harvest/paradigms_from_names.py [YYYY-MM-DD]

For each task row without paradigms, its task name is matched against the phrases below. A
dataset with no task rows gets a row "main" without a task name when its name states a task in a
phrase that cannot be just the study's topic (NAME_RULES: not "sleep", "rest", "anesthesia"). Evidence cites the source of the name
or task name, with the matched words as the locator. Only explicit phrases count: an
abbreviation such as "MI" alone, or a task name like "task1", gives nothing.
"""

import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
from reglib import Batch  # noqa: E402

RULES = [
    ("motor_imagery", r"motor[ -]imagery|imagined (?:hand |foot |limb )?movements?|kinesthetic imagery"),
    ("motor_execution", r"motor execution|executed movements?|movement execution"),
    ("imagined_speech", r"imagined speech|inner speech|covert speech"),
    ("ssvep", r"\bSSVEPs?\b|steady[- ]state visual(?:ly)? evoked"),
    ("p300_erp", r"\bP300\b|\boddball\b"),
    ("resting_eyes_closed", r"\beyes[- ]closed\b"),
    ("resting_eyes_open", r"\beyes[- ]open\b"),
    ("resting_unspecified", r"\bresting[- ]state\b|\brest(?:ing)?\b(?! of)"),
    ("sleep", r"\bsleep\b(?![- ]deprivation)|polysomnograph"),
    ("emotion_induction", r"emotion (?:induction|elicitation)|affect(?:ive)? elicitation"),
    ("neurofeedback", r"neurofeedback"),
    ("anesthesia", r"an(?:a)?esthesia|an(?:a)?esthetic"),
]


NAME_RULES = [r for r in RULES if r[0] not in ("sleep", "anesthesia", "neurofeedback", "emotion_induction")]
NAME_RULES = [(p, r"\bresting[- ]state\b") if p == "resting_unspecified" else (p, x) for p, x in NAME_RULES]


def match(text, rules=RULES):
    hits = []
    for par, pat in rules:
        m = re.search(pat, text or "", re.I)
        if m:
            hits.append((par, m.group(0)))
    pars = [h[0] for h in hits]
    if "resting_unspecified" in pars and ({"resting_eyes_closed", "resting_eyes_open"} & set(pars)):
        hits = [h for h in hits if h[0] != "resting_unspecified"]
    return hits


def main():
    today = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    B = Batch(today)
    db = B.db
    ev = {}
    for e in db["evidence"][1]:
        if e["status"] == "current":
            ev[(e["dataset_id"], e["field"])] = e
    tasks = {}
    for t in db["tasks"][1]:
        tasks.setdefault(t["dataset_id"], []).append(t)
    n = 0
    for d in list(db["datasets"][1]):
        did = d["dataset_id"]
        rows = tasks.get(did, [])
        done = False
        for t in rows:
            if t["paradigms"]:
                done = True
                continue
            src = ev.get((did, f"tasks:{t['task_id']}.task_name"))
            hits = match(t["task_name"]) if src else []
            if hits:
                R = B.dataset(did)
                R.ev(f"tasks:{t['task_id']}.paradigms", ";".join(sorted({h[0] for h in hits})), src["source_id"],
                     "Task name: " + "; ".join(h[1] for h in hits), "script")
                n += 1
                done = True
        if rows:
            continue
        src = ev.get((did, "name"))
        hits = match(d["name"], NAME_RULES) if src else []
        if not hits:
            continue
        R = B.dataset(did)
        tid = "main"
        R.child("tasks", "main", description="Paradigm stated by the dataset name")
        R.ev(f"tasks:{tid}.paradigms", ";".join(sorted({h[0] for h in hits})), src["source_id"],
             "Dataset name: " + "; ".join(h[1] for h in hits), "script")
        n += 1
    B.save()
    print(n, "paradigm values recorded")


if __name__ == "__main__":
    main()
