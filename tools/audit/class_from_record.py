"""Give content_class eeg_signals to datasets a reviewer kept without quoting a sentence that names EEG.

Usage: python3 tools/audit/class_from_record.py [--dry]

apply.py needs a checked quote that names EEG before it writes eeg_signals; some "keep" verdicts quoted
only other facts. For those, this script reads the pages the reviewer cited and the dataset's own
distribution record (repository records and distribution pages only, not papers), and takes the first
sentence that names EEG together with a word for recorded data (data, dataset, recorded, recordings,
signals). Page furniture and reference lists are skipped. The verdict stays the reviewer's; only the quote is
picked here. Datasets with no such sentence stay undecided.
"""
import datetime
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "audit"))
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
import apply as A  # noqa: E402
from reglib import Batch  # noqa: E402

DATAWORD = re.compile(r"\b(data ?sets?|data|recorded|recordings?|signals?|acquired|collected)\b", re.I)
NOISE = re.compile(r"AI-generated|Files Download|Bookmark|View on NEMAR|Signal viewer|Search models|scripts?\b|[├│`#*=]|_behav|monopolar|Large, synchronized|"
                   r"resampled|subtract|comfortably|We refer|data id |methods_description|evidence from|extending the Brain Imaging|double-blind|A model was designed|cannot be executed|converts the DANDI|Video-EEG was recorded|Published |Version v?\d|\bdoi\b|Open Source Software|pip install|Authors/Creators|Show affiliation|dataset_id|not mirrored|not repackaged|"
                   r"\bet al\b|removed from analysis|challenges? of|tutorial|protocol|\(\d{4}\)|\b(19|20)\d\d[a-z]?\)|\bwas used to\b|were used to", re.I)
RECORD = re.compile(r"zenodo|datacite|figshare|dataverse|openneuro|nemar\.org|huggingface|osf\.io|physionet|mendeley|datadryad|synapse|isip\.piconepress|bnci|kaggle|github", re.I)


def sentence(text):
    for s in re.split(r"(?<=[.!?])\s+|\s[-•*]\s", text):
        w = s.split()
        if 6 <= len(w) <= 45 and A.EEGWORD.search(s) and DATAWORD.search(s) and "http" not in s and not NOISE.search(s):
            return " ".join(w)
    return ""


def main():
    dry = "--dry" in sys.argv
    B = Batch(datetime.date.today().isoformat())
    items = {}
    for f in sorted(glob.glob(str(ROOT / "cache/audit/results/*.json"))):
        for x in json.loads(Path(f).read_text()):
            if isinstance(x, dict) and x.get("dataset_id"):
                items[x["dataset_id"]] = x
    src = {s["source_id"]: s for s in B.db["sources"][1]}
    dist = {}
    for ln in B.db["dataset_sources"][1]:
        if ln["role"] == "distribution":
            dist.setdefault(ln["dataset_id"], []).append(src[ln["source_id"]]["url"])
    n = 0
    for d in B.db["datasets"][1]:
        did, it = d["dataset_id"], items.get(d["dataset_id"])
        if d["content_class"] or not it:
            continue
        if not (it.get("verdict") == "keep" or (it.get("verdict") == "remove" and it.get("verdict_reason") == "part_of_larger")):
            continue
        urls = [(it.get("verdict_evidence") or {}).get("url")] + [f.get("url") for f in it.get("facts") or []] + dist.get(did, [])
        for url in dict.fromkeys(u for u in urls if u and RECORD.search(u)):
            q = sentence(A.fetch(url))
            if q and A.quote_ok(url, q)[0]:
                n += 1
                print(did, "|", url, "|", q[:110])
                if not dry:
                    R = B.dataset(did)
                    R.ev("content_class", "eeg_signals", A.src_for(R, B, url, False), " ".join(q.split()[:25]), "script",
                         note="Audit reviewer's verdict: keep; the quote was picked by tools/audit/class_from_record.py")
                break
    print(n, "datasets")
    if not dry:
        B.save()


if __name__ == "__main__":
    main()
