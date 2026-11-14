"""Register PhysioNet projects that distribute EEG, from cache/physionet/.

Usage: python3 tools/harvest/physionet_register.py [YYYY-MM-DD]

cache/physionet/projects.json holds the PhysioNet API records of the candidate projects
(https://physionet.org/api/v1/project/published/<slug>/<version>/) and <slug>.txt the text of
each project page. Which projects distribute EEG, and which signals each states, was read from
the pages (INCLUDE below, with the words that say so); the other values are taken from the
API record and the page by pattern. Projects whose pages do not state EEG signals in the files
are listed in EXCLUDE with the reason.
"""

import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/maintaining-eeg-dataset-db/scripts"))
from reglib import Batch  # noqa: E402

CACHE = ROOT / "cache" / "physionet"

# slug: (modalities, words on the page that state them)
INCLUDE = {
    "slpdb": ("psg;scalp_eeg;eog;emg;ecg", "Physiological measurements included electrocardiography (ECG), electroencephalography (EEG), electrooculography (EOG), chin electromyography (EMG)"),
    "sleep-edf": ("scalp_eeg;eog;emg", "they contain horizontal EOG, FpzCz and PzOz EEG, each sampled at 100 Hz. The sc* recordings also contain the submental-EMG envelope"),
    "sleep-edfx": ("psg;scalp_eeg;eog;emg", "PolySomnoGraphic sleep recordings, containing EEG, EOG, chin EMG, and event markers"),
    "shhpsgdb": ("psg;scalp_eeg;eog;emg;ecg", "The data include EEG, EOG, EMG, ECG, nasal airflow and respiratory effort signals"),
    "ucddb": ("scalp_eeg;eog;emg;ecg", "Signals recorded were: EEG (C3-A2), EEG (C4-A1), left EOG, right EOG, submental EMG, ECG"),
    "eegmmidb": ("scalp_eeg", "64-channel electroencephalography recordings collected with the BCI2000 system"),
    "chbmit": ("scalp_eeg", "consists of EEG recordings from pediatric subjects with intractable seizures"),
    "capslpdb": ("scalp_eeg;eog;emg", "include at least 3 EEG channels (F3 or F4, C3 or C4 and O1 or O2, referred to A1 or A2), EOG (2 channels)"),
    "motion-artifact": ("scalp_eeg;fnirs", "functional near-infrared spectroscopy (fNIRS) and electroencephalogram (EEG) recordings"),
    "mssvepdb": ("scalp_eeg", "the MSSVEP database contains EEG recordings of 11 subjects"),
    "ltrsvp": ("scalp_eeg", "This project contains EEG data from 11 healthy participants"),
    "eegmat": ("scalp_eeg", "The database contains EEG recordings of subjects before and during the performance of mental arithmetic tasks"),
    "siena-scalp-eeg": ("scalp_eeg", "The database consists of EEG recordings of 14 patients"),
    "eeg-power-anesthesia": ("scalp_eeg", "This database contains electroencephalography (EEG) multitaper spectra"),
    "auditory-eeg": ("scalp_eeg", "This data set consists of over 240 two-minute EEG recordings obtained from 20 volunteers"),
    "hmc-sleep-staging": ("psg;scalp_eeg;eog;emg;ecg", "The dataset contains electroencephalographic (EEG), electrooculographic (EOG), chin electromyographic (EMG), and electrocardiographic (ECG)"),
    "consumer-grade-wearables": ("scalp_eeg", "three wearable devices (Empatica E4 watch, Samsung Galaxy Watch4 and Muse S EEG headband)"),
    "eeg-eye-gaze-data": ("scalp_eeg;eye_tracking", "electroencephalogram (EEG) and eye-gaze data collected from 25 participants"),
    "eeg-gaba-anesthesia": ("scalp_eeg", "This dataset of electroencephalogram (EEG) activity was collected from subjects undergoing general anesthesia"),
    "eeg-eye-gaze-for-fls-tasks": ("scalp_eeg;eye_tracking", "electroencephalogram (EEG) and eye-gaze data collected from 25 participants"),
    "i-care": ("scalp_eeg;ecg", "continuous electroencephalogram (EEG) and electrocardiogram (ECG) recordings from comatose patients"),
    "brain-wearable-monitoring": ("scalp_eeg", "Using a muse headband, we also collected Electroencephalography (EEG) signals from four sensors"),
    "bigp3bci": ("scalp_eeg", "The data files, provided in open European Data Format"),
    "psg-ipa": ("psg;scalp_eeg;eog;emg", "recordings of common raw PSG signal activity, such as electroencephalography (EEG), electrooculography (EOG), electromyography (EMG)"),
    "neuro-stress-resilience-hci": ("scalp_eeg;fnirs;eda", "It comprises electroencephalography, functional near-infrared spectroscopy, electrodermal activity"),
    "multimodal-gait-dataset": ("scalp_eeg;emg", "synchronized recordings from scalp electroencephalography, surface electromyography of 12 lower-limb muscles"),
    "dreamt": ("psg;scalp_eeg;eog;emg;ecg", "These signals include EEG, EOG, EMG, ECG, respiratory effort, airflow, and blood oxygen saturation"),
    "jsmf-access": ("scalp_eeg", "This resource shares processed frontal electroencephalography (EEG) data"),
    "nch-sleep": ("psg;scalp_eeg", "Topics eeg ehr pediatrics polysomnography"),
    "cps-dataset-sleep": ("psg", "encompasses 113 diagnostic polysomnographic sleep recordings"),
}
# Subjects stated in the abstract (slug: (number, words))
SUBJECTS = {
    "auditory-eeg": ("20", "obtained from 20 volunteers"),
    "chbmit": ("22", "22 subjects"),
    "eeg-eye-gaze-data": ("25", "data collected from 25 participants"),
    "eeg-eye-gaze-for-fls-tasks": ("25", "data collected from 25 participants"),
    "ltrsvp": ("11", "EEG data from 11 healthy participants"),
    "mssvepdb": ("11", "EEG recordings of 11 subjects"),
    "multimodal-gait-dataset": ("59", "59 healthy adults"),
    "neuro-stress-resilience-hci": ("35", "35 participants"),
    "siena-scalp-eeg": ("14", "EEG recordings of 14 patients"),
}
EXCLUDE = {
    "santa-fe": "The page names EEG only as what a neurologist looked at for sleep staging, not as a signal in the files",
    "noneeg": "Non-EEG physiological signals",
    "sleepbrl": "Bioradiolocation; no EEG stated",
    "sleep-accel": "Wrist-worn motion and heart rate; no EEG stated",
    "wfdb-matlab": "Software package",
    "wfdb-python": "Software package",
    "calcium-imaging-sleep-state": "Wide-field calcium imaging; EEG/EMG were only used for scoring",
    "bidsleep-dataset": "Heart rate and accelerometry with labels derived from EEG; no EEG signals stated",
}
LICENSES = {
    "Open Data Commons Attribution License v1.0": "ODC-By-1.0",
    "Open Data Commons Open Database License v1.0": "ODbL-1.0",
    "Creative Commons Attribution 4.0 International Public License": "CC-BY-4.0",
    "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International Public License": "CC-BY-NC-SA-4.0",
    "PhysioNet Restricted Health Data License 1.5.0": "LicenseRef-physionet-restricted",
    "PhysioNet Credentialed Health Data License 1.5.0": "LicenseRef-physionet-credentialed",
    "PhysioNet Contributor Review Health Data License 1.5.0": "LicenseRef-physionet-contributor-review",
}
ACCESS = [  # (words of the Access Policy, access_method, human steps)
    ("users must have individual studies reviewed by the contributor", "request_form_or_email",
     "Become a credentialed PhysioNet user, sign the DUA, and have the individual study reviewed by the contributor"),
    ("Only credentialed users who sign the DUA can access the files", "credentialed_training",
     "Become a credentialed PhysioNet user (with the required training) and sign the DUA"),
    ("Only registered users who sign the specified data use agreement can access the files", "signed_agreement",
     "Register on PhysioNet and sign the data use agreement"),
    ("Anyone can access the files, as long as they conform to the terms of the specified license", "direct_download", "none"),
]


def words(s, n=25):
    return " ".join(s.split()[:n])


def main():
    today = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    projects = json.loads((CACHE / "projects.json").read_text())
    B = Batch(today)
    for slug, (mods, mod_words) in sorted(INCLUDE.items()):
        p = projects[slug]
        page = (CACHE / f"{slug}.txt").read_text()
        for w in (mod_words,) + ((SUBJECTS[slug][1],) if slug in SUBJECTS else ()):
            if w not in page:
                raise SystemExit(f"{slug}: the words {w!r} are not on the page")
        did = re.sub(r"[^a-z0-9]+", "_", slug.lower()).strip("_")
        R = B.dataset(did)
        url = f"https://physionet.org/content/{slug}/{p['version']}/"
        src = R.source(f"{did}_page", url, "repository_record", "authors", title=p["title"], doi=p.get("doi") or "",
                       describes_version=f"version {p['version']}", identity_basis=f"PhysioNet project {slug}",
                       note="Read from the project page and the PhysioNet API record of the same version")
        R.link(src, "distribution")
        R.alias(slug, "catalogue_id", src)
        R.ev("name", p["title"], src, "Project title", "script")
        lic = p["license"]["name"]
        if lic in LICENSES:
            R.ev("license_spdx", LICENSES[lic], src, f"License: {lic}", "script")
        R.ev("modalities", mods, src, words(mod_words))
        if slug in SUBJECTS:
            R.ev("n_subjects_reported", SUBJECTS[slug][0], src, f"Abstract: {SUBJECTS[slug][1]}")
        m = re.search(r"Total uncompressed size: ([\d.]+) GB", page)
        if m:
            R.ev("size_gb_reported", m.group(1), src, f"Total uncompressed size: {m.group(1)} GB", "script")
        R.child("access_routes", "physionet", route_kind="repository", url=url)
        for text, method, steps in ACCESS:
            if text in page:
                R.ev("access_routes:physionet.access_method", method, src, f"Access Policy: {words(text, 20)}", "script")
                R.ev("access_routes:physionet.human_steps", steps, src, f"Access Policy: {words(text, 20)}", "script")
                break
        if "wget -r -N -c -np" in page:
            R.ev("access_routes:physionet.automation_tool", "wget", src, "Files: Download the files using your terminal: wget -r -N -c -np", "script")
    B.save()
    print(f"{len(INCLUDE)} registered; {len(EXCLUDE)} excluded: {', '.join(sorted(EXCLUDE))}")


if __name__ == "__main__":
    main()
