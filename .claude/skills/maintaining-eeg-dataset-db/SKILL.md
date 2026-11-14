---
name: maintaining-eeg-dataset-db
description: Maintains the EEG dataset database, a git repository of CSV tables in which every value carries an evidence row pointing to a source document. Registers datasets from primary sources (documents check), harvests machine-readable repositories (OpenNeuro, PhysioNet, BNCI), later reads ESPnet recipe readmes (implementation check), validates and commits. Use when asked to add or check an EEG dataset, to continue the survey of EEG datasets, to register a recipe, or when asked about an EEG dataset's license, access, size, channels, tasks or participants.
---

# Maintaining the EEG dataset DB

The DB follows `ser_dataset_db` (same maintainer): same mission, five principles
(verifiability, coverage, currency, transparency, neutrality) and rules. Read `README.md` first,
then `docs/discussions/0002-align-with-ser-principles.md` (what was carried over and why).
Run `python3 tools/validate.py`; it must end with `0 error(s)`.

## Rules (from ser_dataset_db)

1. **The DB creates no facts of its own.** Never count, measure or inspect data (no file counts,
   no summing of channel counts, no reading of signal files). Values that need counting stay empty
   until a recipe readme's `## The data` section states them.
2. **Every value has a source** in `sources.csv`; free-text columns name their source in every
   sentence (`[seed_license]`).
3. **Source types**: `primary` (dataset authors or their organisation; a repository record of
   their deposit; metadata documents inside the release such as BIDS `participants.json`),
   `implementation` (recipe readme `## The data`, at a commit on the public fork `itoten/espnet`;
   only source for `*_release` and `access_observed`), `secondary` (only when no primary source
   says it; say why in `note`).
4. **Do not judge.** Disagreeing sources → `conflicting`. Record wording as written. No advice.
5. **Empty / unknown / none / NA** differ: `unknown` only after reading a whole source.
6. **Write only what a source supports.** Quote the words in `locator` (25 words at most). Assert
   the quoted words are in the cached page text in your registration script.
7. **Never delete history**; superseded rows stay.
8. **Channel names stay as written.** No 10-10 renaming, no reference stripping; only case and
   mappings the dataset's own documentation states go in `channel_normalization.csv`.
9. **Scope**: EEG in a broad sense (scalp of any channel count, ear, PSG with EEG, ECoG, sEEG).
   A dataset whose sources do not state EEG signals in the files is not registered; note why in
   the commit message.
10. **Public-ready**: no personal names (say "the project maintainer"), e-mail addresses or
    machine-specific paths in files or commits. BIDS `Authors` fields hold e-mails: never copy them.
11. **Stay within the request.** Design changes only when the maintainer asks.

## Workflows

- **Machine-readable repositories**: `tools/harvest/` (fetch into the git-ignored `cache/`, then
  register; evidence `checked_by=script`). OpenNeuro: `openneuro_fetch.py` then
  `openneuro_register.py`; PhysioNet: `physionet_register.py` (the EEG inclusion list is in the
  script, with the words of each page); BNCI: `bnci_register.py`.
- **One dataset or a family from pages**: save the page text under `cache/pages/`, write a short
  script in the scratch directory with `scripts/reglib.py` (`Batch`, `dataset`, `source`, `link`,
  `ev`, `child`, `add_row`, `relation`, `set`), assert every quoted phrase is in the page, run once,
  then `tools/views.py` and `tools/validate.py`.
- **Recipes (implementation check)**: only after the documents check of that dataset. Read the
  recipe readme's `## The data` from the recipe branch at a commit that is on the public fork, as
  in ser_dataset_db.

Evidence fields of child rows are `<table>:<row id>.<column>`, e.g.
`acquisition_setups:main.sampling_rate_hz`; create the row with `R.child(table, row_id)` first.

## Finish

`python3 tools/views.py`, `python3 tools/validate.py`, then commit one dataset, family or harvest
per commit, staging files by name. Commit messages in English: what was uncertain, what the
evidence was, what was left out and why. Never bypass the hook.
