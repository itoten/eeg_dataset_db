"""Register Hugging Face dataset repositories (not EEGDash pointers) whose card states EEG recordings.

Usage: python3 tools/harvest/hf_register.py [YYYY-MM-DD]

Reads cache/candidates/huggingface.json (https://huggingface.co/api/datasets?search=eeg&full=true).
A repository is registered when its name or card text says EEG data/recordings and nothing in the name
points to a derived form (images, features, preprocessed, splits). The uploader is not the dataset's
author as far as the card says, so the source is secondary. Skips are listed in cache/hf_skipped.tsv.
"""
import datetime, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
from reglib import Batch  # noqa: E402

LIC = {"cc0-1.0": "CC0-1.0", "cc-by-4.0": "CC-BY-4.0", "cc-by-sa-4.0": "CC-BY-SA-4.0", "cc-by-nc-4.0": "CC-BY-NC-4.0", "cc-by-nc-sa-4.0": "CC-BY-NC-SA-4.0",
       "cc-by-nc-nd-4.0": "CC-BY-NC-ND-4.0", "cc-by-nd-4.0": "CC-BY-ND-4.0", "mit": "MIT", "apache-2.0": "Apache-2.0", "odc-by": "ODC-By-1.0", "odbl": "ODbL-1.0",
       "cc-by-3.0": "CC-BY-3.0", "cc-by-nc-3.0": "CC-BY-NC-3.0", "gpl-3.0": "GPL-3.0-only"}
STATES = re.compile(r"\b(EEG|electroencephalogra\w*)\s+(data|datasets?|database|recordings?|signals?|corpus|files)\b|\b(recorded|collected|acquired|recordings? of)\b[^.]{0,60}\b(EEG|electroencephalogra\w*)\b", re.I)
DERIVED = re.compile(r"prepro|synthetic|image|greyscale|grayscale|spectrogram|feature|preprocess|process|denois|embedding|split|train|eval|dev|test|subset|mini|caption|pointer|checkpoint|model|clip|text", re.I)
DERIVED_TEXT = re.compile(r"preprocess|pre-process|filtered|tokeni[sz]ed|windowed|spectrogram|embedding|re-?upload|copy of|mirror|converted|derived from|extracted from|based on the|synthetic|simulated", re.I)
IEEG = re.compile(r"intracranial|ECoG|electrocortico|sEEG", re.I)


def txt(s):
    return " ".join(re.sub(r"<[^>]+>", " ", s or "").split())


def main():
    today = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    H = [x for x in json.loads((ROOT / "cache/candidates/huggingface.json").read_text()) if x["author"] != "EEGDash"]
    B = Batch(today)
    skipped, n = [], 0
    for x in H:
        rid = x["id"]
        card = x.get("cardData") or {}
        name = card.get("pretty_name") or rid.split("/", 1)[1]
        text = txt(x.get("description")) + " " + " ".join(card.get("tags") or [])
        why = None
        if DERIVED.search(rid.split("/", 1)[1]):
            why = "repository name points to a derived or split form"
        elif not STATES.search(txt(x.get("description"))):
            why = "the card text does not state EEG recordings"
        elif DERIVED_TEXT.search(txt(x.get("description"))):
            why = "the card text points to a processed or derived form"
        if why:
            skipped.append((rid, why))
            continue
        did = "hf_" + re.sub(r"[^a-z0-9]+", "_", rid.lower()).strip("_")
        R = B.dataset(did)
        url = f"https://huggingface.co/datasets/{rid}"
        src = R.source(f"{did}_card", url, "repository_record", "third_party", title=name, identity_basis=f"Hugging Face dataset repository {rid}",
                       note="Read through the Hugging Face API. The card does not make the uploader the dataset's author; no original publication was checked")
        R.link(src, "distribution")
        R.alias(rid, "catalogue_id", src)
        R.ev("name", " ".join(str(name).split()), src, "Card pretty_name or repository name", "script")
        if not IEEG.search(text):
            R.ev("modalities", "scalp_eeg", src, "Repository name or card: EEG")
        lic = LIC.get(str(card.get("license") or "").lower())
        if lic:
            R.ev("license_spdx", lic, src, f"Card license: {card['license']}", "script")
        if (x.get("createdAt") or "")[:4].isdigit():
            R.ev("year_published", x["createdAt"][:4], src, "createdAt of the repository", "script")
        g = x.get("gated")
        R.child("access_routes", "huggingface", route_kind="repository", url=url)
        method = "direct_download" if not g else "gated_click_through" if g == "auto" else "request_form_or_email"
        steps = "none" if not g else "Accept the repository's access conditions" if g == "auto" else "Request access; the repository owner approves"
        R.ev("access_routes:huggingface.access_method", method, src, f"API field gated: {g}", "script")
        R.ev("access_routes:huggingface.human_steps", steps, src, f"API field gated: {g}", "script")
        R.ev("access_routes:huggingface.automation_tool", "huggingface-hub;datasets", src, "Hugging Face repository", "script")
        n += 1
    import collections
    norm = collections.defaultdict(list)
    for d in B.db["datasets"][1]:
        norm[re.sub(r"\W", "", d["name"].casefold())].append(d["dataset_id"])
        norm[re.sub(r"\W", "", d["dataset_id"].casefold())].append(d["dataset_id"])
    for r in B.db["aliases"][1]:
        if r["alias_type"] != "catalogue_id":
            norm[re.sub(r"\W", "", r["alias"].casefold())].append(r["dataset_id"])
    for ids in norm.values():
        ids = sorted(set(ids))
        hf = [i for i in ids if i.startswith("hf_")]
        for a in hf:
            for b in ids:
                if b != a:
                    B.dataset(a).relation("possibly_same_as", b, f"{a}_card", "Both print the same name; whether they are the same data is not checked")
    (ROOT / "cache" / "hf_skipped.tsv").write_text("\n".join(f"{a}\t{b}" for a, b in skipped) + "\n")
    B.save()
    print(n, "registered;", len(skipped), "skipped")


if __name__ == "__main__":
    main()
