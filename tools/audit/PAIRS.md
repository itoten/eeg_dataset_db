# Instructions for a pair reviewer (EEG dataset DB)

Each item of your batch is a pair of datasets that the DB marks `possibly_same_as`, usually because
both print the same name or share a paper. Decide from their public sources how the two relate.
A script checks every quote on its page; a quote not found verbatim at its URL is discarded.
Report only what a source says in so many words; never infer from names or counts alone.

Read, for both datasets: the record or page in `sources` (repository API where one exists: Zenodo
— read only the saved copy `cache/zenodo/<id>.json` (never request zenodo.org) and cite
`https://zenodo.org/records/<id>`; figshare `https://api.figshare.com/v2/articles/<id>`;
Mendeley `https://data.mendeley.com/public-api/datasets/<id>`; OSF `https://api.osf.io/v2/nodes/<id>/`;
OpenNeuro `https://s3.amazonaws.com/openneuro.org/<ds>/README`; NEMAR `https://api.nemar.org/datasets/<id>`),
and the paper either one names. One request at a time; wait 2 seconds between requests to one host.

Answer with one of (a is the item's `a`, b is its `b`):

- `version_of`: a is another version of b (a source says new version, updated release, v2 of ...).
- `subset_of`: a is part of b. `contains`: a contains b.
- `derived_from`: a re-hosts, mirrors, converts (e.g. to BIDS) or re-processes b's data, as a source says.
- `shares_subjects_with`: different releases that a source says share participants.
- `distinct_from`: a source shows they are different data (different participants, experiments or tasks).
- `unclear`: the sources do not settle it. This is a good answer when true.

Output: one JSON list, one object per item, written to the path given in your task:

```json
{"a": "...", "b": "...", "answer": "derived_from",
 "evidence": [{"url": "...", "quote": "verbatim words, 8-40 words"}],
 "note": "one sentence"}
```

Every answer other than `unclear` needs at least one quote that says it. Do not modify anything else
in the repository, and leave no background jobs running.
