# Instructions for a dataset reviewer (EEG dataset DB audit)

You review a batch of datasets that are already in a database of EEG datasets. The database is a
tertiary source: every value must be traceable to a public document where a reader can find the same
words. Your job is to read the primary sources thoroughly and report, with verbatim quotes, (1) whether
each row belongs in the DB and (2) the facts those sources state. **A person and a script will check
every quote against the page. A quote that is not found verbatim at its URL is discarded, and a
reviewer whose quotes fail is not trusted.** Be skeptical: report only what a source says in so many
words. Never infer, never fill from general knowledge, never round or convert units (except none at all:
copy numbers as written). "Not stated" is a good answer.

## What to read, for every dataset

1. The record (repository page / API): Zenodo — read the saved copy `cache/zenodo/<id>.json` (do not request zenodo.org yourself; cite `https://zenodo.org/records/<id>`; description is HTML),
   figshare `https://api.figshare.com/v2/articles/<id>` or `/collections/<id>`, Dataverse
   `https://<host>/api/datasets/:persistentId/?persistentId=doi:<doi>`, Hugging Face card
   `https://huggingface.co/datasets/<id>/raw/main/README.md`, OpenNeuro `https://openneuro.org/crn/graphql`
   (or the S3 file `https://s3.amazonaws.com/openneuro.org/<ds>/README` and `.../dataset_description.json`),
   NEMAR `https://api.nemar.org/datasets/<id>`, Dryad `https://datadryad.org/api/v2/datasets/<url-encoded doi:...>`
   (files: its `stash:version` link, then `/files`), Mendeley Data `https://data.mendeley.com/public-api/datasets/<id>`
   (the dataset page itself is JavaScript; cite the API URL), OSF `https://api.osf.io/v2/nodes/<id>/` (wiki:
   `/wikis/`, files: `/files/osfstorage/`), Kaggle: the dataset page needs JavaScript; the record values are in
   `cache/kaggle/search.json` of the repository (cite the dataset URL; read the description through
   `https://www.kaggle.com/api/v1/datasets/view/<owner>/<slug>` if it answers).
2. The README or description file in the release when the record links one you can open without logging in.
3. The paper that describes the dataset (data descriptor / article named by the record, e.g. a DOI in
   related identifiers or "please cite"). Read the full text when it is open access (publisher HTML,
   PubMed Central `https://www.ncbi.nlm.nih.gov/pmc/articles/PMC.../`, arXiv/bioRxiv/medRxiv, Frontiers,
   Scientific Data, PLOS, MDPI, eLife). Methods sections hold the participants, device, channels, rate,
   reference and task design. Use `curl -sL -A "Mozilla/5.0"` and Python to extract text; for PDFs use
   `pdftotext file.pdf -`. If a page cannot be opened, say so; do not guess its content.

Use Bash (curl/python/pdftotext) or WebFetch. Keep downloads to text documents (pages, JSON, PDFs of
papers); never download data files.

## Output

Write one JSON file to the path given in your task: a list with one object per dataset of the batch,
in this shape (omit keys you have nothing for; never invent):

```json
{
  "dataset_id": "zenodo_123",
  "verdict": "keep | remove | unclear",
  "verdict_reason": "eeg_recordings | not_eeg_recordings | no_data_files | code_or_results_only | animal | part_of_larger | duplicate_record | other",
  "verdict_evidence": {"url": "...", "quote": "verbatim words that show it"},
  "copy_of": {"name": "...", "url_or_doi": "...", "quote": "verbatim words saying it re-hosts/converts/copies that dataset"},
  "record_by_dataset_authors": {"answer": "yes | no | unknown", "quote": "...", "url": "..."},
  "paper": {"doi": "10....", "title": "...", "url": "...", "read": "full_text | abstract_only | not_open"},
  "facts": [
    {"field": "n_subjects_reported", "value": "24", "url": "...", "quote": "Twenty-four healthy adults (12 female) participated", "scope": "whole dataset"}
  ],
  "tasks": [
    {"task_name": "as written", "paradigms": ["motor_imagery"], "url": "...", "quote": "..."}
  ],
  "groups": [
    {"group_label": "as written", "n_subjects": "12", "condition": "healthy | patient | mixed", "diagnosis": "...",
     "age_min": "", "age_max": "", "age_mean": "", "age_sd": "", "n_female": "", "n_male": "", "handedness": "",
     "url": "...", "quote": "..."}
  ],
  "annotations": [{"item": "<annotation_item>", "name": "as written", "labels": "a;b;c", "url": "...", "quote": "..."}],
  "quality": [{"kind": "<quality_kind>", "description": "short, factual", "url": "...", "quote": "..."}],
  "notes": "anything a person should know (contradictions between sources, pages that would not open)"
}
```

### Verdict
- `keep / eeg_recordings`: the files contain EEG (scalp, ear, PSG with EEG, ECoG, sEEG) recordings of
  humans, raw or processed signals.
- `remove` (the dataset is NOT deleted; it is registered and labelled so readers can tell it apart; see
  docs/discussions/0003): the release has no EEG signals (only code, statistics, features, connectivity
  matrices, figures, behavioural data, fNIRS/MEG/EMG only), or its signals are not from living humans
  (animals, phantom heads, simulations), or the record is one part of a larger dataset
  (`part_of_larger`; give the larger one in `copy_of`; this one is still usable). Quote the words that show it.
- `unclear`: the sources do not say enough; explain in `notes`.
- `copy_of`: only when the record itself says it re-hosts, mirrors, converts or derives from another
  dataset; quote those words.
- `record_by_dataset_authors`: "yes" only if the record's creators/authors include the paper's authors
  or the record says it is the authors' release; quote the creator list or statement.

### Facts (field names and allowed values)
Each fact needs `url` and a verbatim `quote` (at most 40 words) that contains the value as written.
If sources disagree, report each with its own quote and say so in `notes`. If the value applies to
part of the data only (one group, one session), give `scope`.

| field | value |
|---|---|
| n_subjects_reported | integer, participants in the whole dataset |
| hours_reported | number of hours as stated (only if hours are stated) |
| modalities | ;-list from: scalp_eeg, ear_eeg, ieeg, ieeg_ecog, ieeg_seeg, psg, meg, eog, ecg, emg, eye_tracking, fnirs, fmri, eda, respiration, video, audio, other_physiological |
| domains | ;-list from: clinical, epilepsy, sleep, bci, emotion, cognitive, perception, motor, resting_state, development, psychiatry, neurology, other |
| device_manufacturer | as written (e.g. "BioSemi") |
| device_model | as written (e.g. "ActiveTwo") |
| electrode_type | wet_gel, saline, dry, intracranial, mixed |
| n_channels_eeg | integer, EEG (or iEEG) channels only |
| montage_system | 10_20, 10_10, 10_05, egi_hydrocel, biosemi_abc, easycap_custom, device_fixed, ear, intracranial, custom |
| reference | as written |
| ground | as written |
| sampling_rate_hz | number of the recorded (or distributed, say which in scope) signals |
| line_freq_hz | 50 or 60 |
| hardware_filter | as written |
| license_spdx | only if the record has no license and a document states one: give the words |
| year_published | year of first public release of the data |

Task paradigms: resting_eyes_open, resting_eyes_closed, resting_unspecified, motor_imagery, motor_execution,
p300_erp, ssvep, auditory_erp, visual_erp, emotion_induction, imagined_speech, overt_speech, language,
cognitive_task, passive_viewing, sleep, clinical_routine, long_term_monitoring, anesthesia, neurofeedback, other.

Annotation items: event_markers, class_labels, self_report_ratings, clinical_diagnosis, clinical_report,
normal_abnormal, seizure_annotations, event_annotations, sleep_stages, artifact_annotations,
behavioral_responses, questionnaires, other.

Quality kinds (information the data collectors provide about quality): impedance_values,
impedance_threshold, bad_channel_marks, bad_segment_marks, artifact_annotations, quality_rating,
rejected_trials, recording_notes, signal_check_procedure, other.

## Rules that matter most
- Verbatim quotes only. Copy the characters as they appear in the text you fetched (keep the
  original language). Do not paraphrase inside `quote`.
- One dataset at a time; read the record AND the paper/README before answering. If you cannot open the
  paper, say `"read": "not_open"` and use the record only.
- Never report counts you computed (adding groups, counting files). Only stated numbers.
- Do not modify anything in the repository. Write only your output file.
- Finish with a one-paragraph summary of what you could not open or decide.

## Practical notes
- Never send requests to zenodo.org (Zenodo limits traffic from this network; tools/harvest/zenodo_client.py is the
  only client). Read `cache/zenodo/<id>.json` (read-only); if it is missing, read
  `https://api.datacite.org/dois/10.5281/zenodo.<id>` and cite it.
- Leave out inferred values: montage from channel names, `healthy` the quote does not say, device_fixed or
  custom montages, line frequency from notch filters, gel from "wet".
- Rates written in kHz are fine (give Hz). Give no year_published.
- `duplicate_record` only when the record itself says it is a copy. A volume or part of a larger dataset is
  `remove`/`part_of_larger` with `copy_of` naming the larger one: it is kept and linked, not deleted.
- Be economical: read each paper's Methods and data sections, not whole PDFs page by page; stop once
  the fields are settled. Check quotes with one script at the end.
