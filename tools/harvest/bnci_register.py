"""Register the data sets of the BNCI Horizon 2020 database from its data-set page.

Usage: python3 tools/harvest/bnci_register.py [YYYY-MM-DD]

Reads cache/bnci/data-sets.html (https://bnci-horizon-2020.eu/database/data-sets). Each card
gives the title, participants, signals, license, licensor and data files; the page says that
all data sets are open access and can be freely downloaded.
"""

import datetime
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
from reglib import Batch  # noqa: E402

PAGE = ROOT / "cache" / "bnci" / "data-sets.html"
URL = "https://bnci-horizon-2020.eu/database/data-sets"
OPEN = "All data sets in this database are open access. This means that you can freely download and use the data according to their licenses."
LICENSES = [(r"\(CC BY-ND 4\.0\)|by-nd/4\.0", "CC-BY-ND-4.0"), (r"\(CC BY-NC-ND 4\.0\)|by-nc-nd/4\.0", "CC-BY-NC-ND-4.0"),
            (r"\(CC BY-NC-SA 4\.0\)|by-nc-sa/4\.0", "CC-BY-NC-SA-4.0"), (r"\(CC BY-NC 4\.0\)|by-nc/4\.0", "CC-BY-NC-4.0"),
            (r"\(CC BY-SA 4\.0\)|by-sa/4\.0", "CC-BY-SA-4.0"), (r"\(CC BY 4\.0\)|licenses/by/4\.0", "CC-BY-4.0"),
            (r"CC0|publicdomain/zero", "CC0-1.0")]
OTHER = {"EOG": "eog", "EMG": "emg", "ECG": "ecg", "EKG": "ecg", "EDA": "eda", "GSR": "eda"}


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def cards(page):
    for m in re.finditer(r'<h3 class="card-title">(.*?)</h3>(.*?)</dl>', page, re.S):
        title = text(m.group(1))
        body = m.group(2)
        fields = {text(k): (v, text(v)) for k, v in re.findall(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", body, re.S)}
        intro = text(body.split("<dl", 1)[0])
        yield title, intro, fields


def main():
    today = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    page = PAGE.read_text(errors="replace")
    if OPEN not in text(page):
        raise SystemExit("the open-access statement is not on the page")
    B = Batch(today)
    n = 0
    for title, intro, f in cards(page):
        m = re.match(r"^(\d+)\.\s+(.*?)\s*\((\d{3}-\d{4})\)$", title)
        if not m:
            print("skipped card:", title)
            continue
        _, name, code = m.groups()
        sig = f.get("Signals", ("", ""))[1]
        has_eeg, has_ecog = bool(re.search(r"\bEEG\b", sig)), bool(re.search(r"\bECoG\b", sig))
        if not (has_eeg or has_ecog):
            print(f"out of scope (Signals: {sig}):", title)
            continue
        did = "bnci_" + code.replace("-", "_")
        R = B.dataset(did)
        src = R.source("bnci_data_sets", URL, "repository_record", "authors", title="Data sets - BNCI Horizon 2020",
                       identity_basis="Database of BNCI Horizon 2020; each card names the licensor of the data",
                       note="One page lists every data set; the locator names the card")
        R.link(src, "distribution")
        R.alias(code, "catalogue_id", src)
        loc = f"Card {code}"
        R.ev("name", f"{name} ({code})", src, f"{loc}: title", "script")
        if "Participants" in f and re.fullmatch(r"\d+", f["Participants"][1]):
            R.ev("n_subjects_reported", f["Participants"][1], src, f"{loc}: Participants", "script")
        words = [w.upper() for w in re.findall(r"[A-Za-z]+", sig)]
        others = sorted({OTHER[w] for w in words if w in OTHER})
        mods = (["scalp_eeg"] if has_eeg else []) + (["ieeg_ecog"] if has_ecog else []) + others
        sloc = f"{loc}: Signals {sig}"[:120]
        R.ev("modalities", ";".join(sorted(mods)), src, sloc, "script")
        R.child("acquisition_setups", "main", description="As stated in the Signals field of the BNCI card")
        n_eeg = re.findall(r"(\d+)\s+(?:subdural\s+)?(?:EEG|ECoG)\b", sig)
        if len(n_eeg) == 1 and not re.search(r"\d+-\d+", sig):
            R.ev("acquisition_setups:main.n_channels_eeg", n_eeg[0], src, sloc, "script")
        if others:
            R.ev("acquisition_setups:main.other_channel_types", ";".join(others), src, sloc, "script")
        if "License" in f:
            lic = f["License"][0] + " " + f["License"][1]
            v = next((val for pat, val in LICENSES if re.search(pat, lic)), "")
            if v:
                R.ev("license_spdx", v, src, f"{loc}: License {f['License'][1]}"[:150], "script")
        R.child("access_routes", "bnci", route_kind="repository", url=URL)
        R.ev("access_routes:bnci.access_method", "direct_download", src, "All data sets in this database are open access ... freely download", "script")
        R.ev("access_routes:bnci.human_steps", "none", src, "All data sets in this database are open access", "script")
        if "Data" in f and "href=" in f["Data"][0]:
            R.ev("access_routes:bnci.automation_tool", "http", src, f"{loc}: Data (direct file links)", "script")
        if intro:
            R.set(notes=f"{intro} [bnci_data_sets]" if intro.endswith(".") else f"{intro}. [bnci_data_sets]")
        n += 1
    B.save()
    print(n, "BNCI data sets registered")


if __name__ == "__main__":
    main()
