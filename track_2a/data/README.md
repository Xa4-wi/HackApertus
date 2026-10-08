# ClaimLens data

The downloaded dataset lives in the ignored `local/ost/` directory, and official
booklets are cached under `local/library/`. Neither is included in the prediction
image. `ost-sample.jsonl` retains a small attributed source sample for inspection.

The former stored walkthrough is removed from the application. Its source and
quotation examples are retained only in `tests/fixtures/reference-examples.json`
for regression testing. The browser and CLI cannot replay them as predictions.

## Download the full dataset

Run from `track_2a/` after creating the project virtual environment:

```sh
.venv/bin/python -m pip install -r requirements-data.txt
.venv/bin/python scripts/prepare_dataset.py
```

The script calls `datasets.load_dataset("OSTswiss/MNLIoverSwissVotingBooklets",
revision=...)` at the pinned revision below and saves the returned DatasetDict.
It downloads public dataset files only: no model inference or booklet PDF
downloads occur. Caches stay in the repository's ignored `.cache/huggingface/`.
An existing nonempty output directory is preserved; supply `--output` with a
new path for another snapshot. A different revision must be an exact commit SHA.

```text
data/local/ost/
├── dataset/                         # load_from_disk-compatible; contains labels
├── input/reference-train.jsonl      # official Task B input; no gold labels
├── gold/reference-train.gold.jsonl  # expected labels, kept outside input/
└── manifest.json                    # revision, counts, versions and file hashes
```

Load the saved snapshot without downloading again:

```python
from datasets import load_from_disk

ds = load_from_disk("data/local/ost/dataset")
```

For prediction runs, mount only `data/local/ost/input/` as the container's `/data`.
Keep `gold/` and `dataset/` outside that mount. Exported inputs whitelist exactly
`id`, `vote`, `claim` and `reference`; `entailment_label` and `baseline_score`
never appear as input fields. Expected labels are a separate JSONL file joined
by the stable `ost-train-000000`-style case IDs.

## Verified snapshot

Downloaded 8 October 2026 from
[OSTswiss/MNLIoverSwissVotingBooklets](https://huggingface.co/datasets/OSTswiss/MNLIoverSwissVotingBooklets/tree/fc2b27600310778da6bbf445651ddbca22d86269).
Revision: `fc2b27600310778da6bbf445651ddbca22d86269`; upstream license: MIT.

The upstream dataset contains one `train` split with **1,488 rows**. Its split
name is preserved; this is not a newly constructed held-out test set.

| Label | Code | Rows |
| --- | ---: | ---: |
| Entailment | 0 | 495 |
| Neutral | 1 | 498 |
| Contradiction | 2 | 495 |

All nine claim/reference language combinations are present:

| Claim language | German reference | French reference | Italian reference | Total |
| --- | ---: | ---: | ---: | ---: |
| German | 159 | 184 | 152 | 495 |
| French | 149 | 196 | 152 | 497 |
| Italian | 147 | 189 | 160 | 496 |
| Total | 455 | 569 | 464 | 1,488 |

There are 1,153 distinct exported requests and 335 repeated rows, with no
conflicting labels among identical requests. All upstream rows are preserved.
Any future train/test split must account for duplicate requests and shared
booklets to avoid leakage. There are 177 distinct vote-title strings and 60
distinct booklet URLs; vote-title strings may describe translations of the same
proposal. Maximum claim length is 461 characters and maximum reference length
is 25,425 characters, both within the prototype's limits.

Validation loaded the saved DatasetDict, checked all 1,488 exported inputs with
the production request parser, verified matching input/gold IDs, and confirmed
the absence of supervision fields in every input. No accuracy result is claimed.
