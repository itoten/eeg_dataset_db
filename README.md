# eeg_dataset_db

A database of EEG datasets, kept as CSV files under git. It is a tertiary source: it does not offer the truth about a dataset, but the way to the primary sources (papers, repository records, BIDS metadata, license files) where the truth can be checked.

The design follows `ser_dataset_db` (a database of speech emotion recognition datasets by the same maintainer). Where this README is silent, its rules apply.

## Mission and principles

**Mission**: to collect every EEG dataset that has information on the web, as material for training a large EEG foundation model, in a database where anyone can check the primary source of every value.

**Principles** (none ranks above the others):

- **Verifiability**: every value can be checked against a primary source. Information without a source is not recorded.
- **Coverage**: collect as many datasets and as much information about them as possible.
- **Currency**: every value records when it was checked.
- **Transparency**: show who checked what and when, and whether a person or only AI checked it. State what is unknown.
- **Neutrality**: record facts only. The DB does not say whether a dataset should be used, and does not choose between disagreeing sources.

**Emphasis: how the data can be obtained.** Whether a dataset can be downloaded without any human step, needs one human step per site, or needs a request approved by its provider decides how it can enter training. Every dataset records its access routes (`access_routes.csv`) and the derived `access_tier`; `views/access_summary.csv` sums datasets, subjects and hours per tier.

**Current position**: private, used by one project; written so that it can be made public later (see Conventions).

- **`data/*.csv` is authoritative.** Everything in `views/` is generated from it.
- Scope: recordings that are EEG in a broad sense: scalp EEG of any channel count (including consumer and ear devices), the EEG of polysomnography, and intracranial EEG (ECoG, sEEG). MEG-only datasets are out of scope; MEG recorded together with EEG is in.
- What a project decides to use, and why, is not here (see `local/`).

## Where to look first

| You want | Look at |
|---|---|
| All datasets at a glance | `views/datasets_wide.csv` (one row per dataset, with source URLs, access tier and stage of checking) |
| What can be obtained without a human | `views/access_summary.csv`, `data/access_routes.csv` |
| Disagreements between sources | `views/discrepancies.csv` |
| Where a value comes from | `data/evidence.csv` (filter by `dataset_id` and `field`), then `data/sources.csv` by `source_id` |
| Meaning, type and allowed nulls of a column | `schema/columns.csv`; allowed values in `schema/enums.csv`; table keys in `schema/tables.csv` |
| How the DB was designed | `docs/README.md` (index of discussions and plans, in Japanese) |

## Tables

| File | One row is |
|---|---|
| `data/datasets.csv` | one dataset |
| `data/evidence.csv` | the source of one value of a column with `evidence=yes` |
| `data/sources.csv` | one source document |
| `data/dataset_sources.csv` | a source that introduces a dataset (paper, distribution, mirror, catalogue) |
| `data/aliases.csv`, `data/relations.csv` | another name of a dataset; a relation between datasets (subset, version, derived, ...) |
| `data/providers.csv` | an institution that recorded or distributes data |
| `data/access_routes.csv` | one way to obtain the data and what a person must do on it |
| `data/acquisition_setups.csv` | one recording setup in a dataset (device, electrodes, montage, reference, sampling rate) |
| `data/channels.csv` | one channel of a setup, named as the source writes it |
| `data/channel_normalization.csv` | a channel name that differs only in case, or that the dataset's own documentation maps to an electrode |
| `data/tasks.csv` | one experimental task (paradigm) |
| `data/task_steps.csv` | one step of a task's sequence (fixation, cue, imagery, rest, ...) |
| `data/annotations.csv`, `data/label_counts.csv` | a label set or annotation; units per label |
| `data/participant_groups.csv` | a group of participants with the summary values a source gives (age, sex, handedness, prior experience) |
| `data/participant_fields.csv` | a per-participant variable in the release (age, weight, BCI experience, ...) and how many have it |
| `data/quality_info.csv` | quality information from the data collectors (impedances, bad channels, artifact marks, ratings) |
| `data/distributed_versions.csv` | a form of the distributed data (raw, preprocessed, epoched) and the provider's processing |
| `data/benchmarks.csv` | a machine-learning task a paper defined on the dataset |
| `data/issues.csv` | a problem of the release as distributed |

"Task" means two things in EEG work. An experimental task (what participants did) is a row of `tasks`; a machine-learning task (what a model predicts, with a metric) is a row of `benchmarks`.

## Conventions

- **Missing values**: empty = not checked. `unknown` = the whole source was read and does not say; `NA` = does not apply; `none` = checked, there is none; `conflicting` = sources disagree. Allowed per column: `nulls` in `schema/columns.csv`.
- **Multiple values** are `;`-separated.
- **IDs** match `^[a-z][a-z0-9]*(_[a-z0-9]+)*$` and never change once committed.
- **CSV format**: UTF-8, no BOM, LF, rows in key order. After editing by hand, run `python3 tools/db.py fmt`.
- **Language**: all text in the data and in this README is English (names and quotations keep their language). Discussions and plans in `docs/` are Japanese.
- **Ready for a public release**: write no personal names, e-mail addresses, internal links or machine-specific paths, in files or commit messages. Refer to people by role ("the project maintainer"). `tools/validate.py` rejects absolute home paths.

## Evidence rules

- Columns with `evidence=yes` in `schema/columns.csv` need a row in `evidence.csv` for every value. In `datasets` the `field` is the column name; in a child table it is `<table>:<row id>.<column>` (for example `acquisition_setups:main.sampling_rate_hz`).
- Rows of the other child tables (channels, task steps, annotations, participant fields, quality information, distributed versions, benchmarks) carry their own `source_id`, `locator`, `checked_on` and `checked_by`.
- **The DB creates no facts of its own.** It does not count, measure or inspect the data. What only obtaining and opening a release shows (counts of the release, problems in it, whether it could be obtained) comes from the `## The data` section of an ESPnet recipe readme.
- **Sources** have a `source_type`: `primary` (published by the dataset's authors or their organisation, including a repository record of their deposit and the metadata documents inside the release such as BIDS `participants.tsv`), `secondary` (a third party: mirror, catalogue, survey; only when no primary source says it), or `implementation` (the `## The data` section of a recipe readme, cited at a commit on the public fork `itoten/espnet`; written by the recipe author, a practical reference and not a research result). A recipe readme is cited only for what the documentation does not state.
- `*_reported` columns are what the documentation (including a repository record) states; `*_release` columns and `access_observed` take only `implementation` sources. The two may differ; the DB does not choose.
- All `current` rows of a field agree; if sources disagree the rows and the cell are `conflicting`. A newer fact marks the older row `superseded`; history is never deleted. There are no `provisional` rows.
- `checked_by` is `claude` (AI investigation), `script` (a tool read a machine-readable source) or `user` (the maintainer opened the source). `user` is set only through a merged pull request named `verify/...`, and its note names the pull request.
- Free-text columns (`notes`, `license_note`, `terms_note`, `other_traits`) name a source in every sentence, for example `[tuab_paper]`.
- Write nothing the sources do not say. Never guess URLs or titles.

## Validation and updates

```bash
python3 tools/validate.py     # format, types, keys, evidence, sources, derived columns, views
python3 tools/derive.py       # recompute the derived columns of datasets.csv
python3 tools/views.py        # regenerate views/
python3 tools/db.py get|set|add|fmt   # view or edit one row
```

Run with the system Python 3; no third-party packages. `git config core.hooksPath tools/hooks` makes `tools/validate.py` run before every commit.

## Channel names

Channel names are recorded as the sources write them. Mapping old to new 10-10 names (T3 to T7), taking the electrode out of a referenced name (`EEG FP1-REF`) or interpreting bipolar derivations is a project's decision and belongs in `local/`, as label mappings do in `ser_dataset_db`. `channel_normalization.csv` holds only case differences and mappings that the dataset's own documentation states.

## How datasets are checked

1. **Documents check**: values from primary sources (papers, distribution pages, repository records, metadata documents of the release). `documents_checked` in `views/datasets_wide.csv`.
2. A recipe is made in ESPnet for datasets that look usable; its readme's `## The data` section reports the whole release as distributed.
3. **Implementation check**: values from that section. `implementation_checked`.

Harvest scripts for machine-readable repositories are in `tools/harvest/` (their cache is the git-ignored `cache/`); their evidence rows have `checked_by=script`.

## What counts as one row

- One row per original dataset. Plain re-uploads are not rows; they are access routes (`route_kind=mirror`) and aliases. Datasets whose content differs (subsets such as the TUH sub-corpora, new labels, re-splits) are separate rows linked with `relations`.
- A repository record (an OpenNeuro accession, a PhysioNet project) is one dataset unless its authors present several datasets in it. OpenNeuro datasets use the accession as `dataset_id` (`ds003478`); a dataset with a recipe uses the egs3 recipe name.

## License

Not decided while the repository is private. The datasets described here keep their own terms, recorded in `license_spdx`, `license_note` and the `*_terms` columns.
