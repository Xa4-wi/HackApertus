# Evaluation and submission checks

The CLI and the local evaluation runner use the same `claimlens.cli.predict_case`
function. The runner keeps unsuccessful cases in its diagnostic results and
exports only actual, validated predictions. A failed inference is never replaced
with a neutral answer.

Software compatibility, prediction quality, and quote provenance are checked
separately. Passing local checks does not establish a result on the organizers'
private benchmark or verify their inference endpoint.

## Frozen public-data cohorts

The current preparation is in `output/v4-readiness/`, generated from
`OSTswiss/MNLIoverSwissVotingBooklets` revision
`fc2b27600310778da6bbf445651ddbca22d86269` with seed
`claimlens-v4-readiness-20261008`.

| Directory | Cases | Purpose |
| --- | ---: | --- |
| `development` | 27 | One case per source language, claim language, and label; development and tuning only |
| `final-b` | 27 | Predetermined reference-text holdout; one case per language pair and label |
| `final-b-extension` | 27 | Additional predetermined reference cases; may extend the final sample without replacing poor results |
| `final-a` | 9 | Full-PDF holdout; one case per language pair, three cases per label overall |

The split groups every translation and proposal from the same ballot date.
All 13 dates represented in the previously tuned 27-case sample are excluded from
the final cohorts. The March 3, 2024 booklet used in the earlier full-document
smoke test is also excluded. The six final dates are November 29, 2020; March 7,
2021; November 28, 2021; May 15, 2022; February 9, 2025; and November 30, 2025.

Identical requests are deduplicated before selection. Final A excludes normalized
same-language claims appearing in either final B cohort. An independent split
audit found no repeated normalized claims between development and final cohorts,
between the two B cohorts, or between final A and B. It also found no
development/final same-language claim pair above 90% character similarity.
Character similarity does not establish that all semantic paraphrases have been
removed. Final cohorts can share ballot dates and related or translated claims;
they are not separate independent datasets.

The split was frozen before final inference. `split.json`, each cohort's
`selection.json`, and `split-audit.json` record its provenance. Input JSONL, gold
JSONL, original PDFs, the cached Arrow dataset, and the official evaluator have
content hashes. Gold labels and reference passages live under `gold/`; only the
`input/` directory belongs in an inference container mount.

## Run and score

Run these commands from `track_2a/`. Configure the local model as described in
[local-model.md](local-model.md), and use the project virtual environment:

```sh
.venv/bin/python -m pip install -r requirements-evaluation.txt
.venv/bin/python scripts/evaluate_readiness.py run --directory output/v4-readiness/final-b
.venv/bin/python scripts/evaluate_readiness.py score --directory output/v4-readiness/final-b
```

Use `final-a` for the full-booklet run. Its predetermined PDFs contain 16–56 pages;
these cases can take several minutes each. Run the model serially on a small local
machine. `final-b-extension` is optional additional evidence; report its result
alongside the original cohort, including any failures.

Freeze the inference implementation before running a final cohort. If code,
endpoint, model, limits, or inputs change, use a new run and retain the previous
artifacts. `--resume` is only accepted when the recorded run identity matches. It
skips all already recorded cases, including failures. The runner checks source
identity between cases and stops if the implementation changes during a run.

The `run` command never reads `gold/`. It writes:

- `results.jsonl`: each accepted or failed case, actual elapsed time, available
  usage, and diagnostic processing information.
- `predictions.jsonl`: only accepted official-format responses; updated after
  each case so earlier results survive a later failure.
- `results.run.json`: code and input hashes, configured model, endpoint hash,
  context/call/time limits, and intended local model provenance. A model alias
  alone does not attest which weights the server loaded.

The `score` command checks frozen input and gold hashes, then executes the copied,
unmodified [official starter evaluator](https://gitlab.com/ifsoftware/hackapertus-starter/-/blob/main/evaluate.py).
It writes `official-score.json`, `official-score.log`, and `summary.json`. These
report macro-F1, accuracy, class scores, source-to-claim language pairs, Task A
evidence overlap, missing responses, token completeness, and mean/p95 case time.
The p95 uses the nearest-rank method. Unknown token usage is not counted as zero.

Long inputs first examine every original source segment. If selected excerpts
exceed the final context, Apertus ranks the original candidate units in bounded
windows for at most eight reduction rounds. Every candidate is examined in each
round; IDs, physical pages and verbatim text remain attached. Selecting fewer
units can omit relevant evidence. Results record reduction rounds/windows and
candidate counts, and usage/latency include extraction, reduction, final calls
and retries. Fixed capacity failures do not cause another full analysis.

The official macro-F1 thresholds are **0.70 for Task B** and **0.60 for Task A**.
Missing predictions count as wrong. The official script reports invalid usage
metrics but does not reduce F1 for them; they are still a submission-contract
problem. A single Task A case per language pair cannot support a reliable
per-language quality estimate. Token/time rankings require the official run and
other teams' results.

## Independent citation and output audit

The official evaluator checks fuzzy overlap with the gold passage. It does not
check whether the quotation actually appears on the claimed physical PDF page.
Run the separate auditor after scoring:

```sh
.venv/bin/python scripts/audit_evidence.py \
  --input output/v4-readiness/final-a/input/cases.jsonl \
  --predictions output/v4-readiness/final-a/predictions.jsonl \
  --output output/v4-readiness/final-a/evidence-audit.json
```

The auditor makes no model calls and never reads gold. It freshly extracts PDF
text with pypdf, preserves blank pages in physical page numbering, checks exact
quotes, and records PDF and per-page extracted-text hashes. It also checks
prediction IDs, labels/names, finite nonnegative required metrics, quote length,
and required Task A evidence. Task B citations are checked against the supplied
reference and must have `page: null`.

Exit status is `0` when every check verifies, `1` for audit findings, and `2` for
an audit execution error. OCR-only text may be absent from pypdf's text layer; such
quotes remain explicitly unverified until the original page is inspected. A quote
found only on another physical page is reported as a page mismatch. A verified
quote establishes its text and location, not its relevance, attribution, or the
correctness of the predicted label.

## Reproduce preparation

Keep an inspected copy of the official starter's `evaluate.py`; the preparation
command copies it unchanged and records its SHA-256. With the pinned dataset and
booklet cache already downloaded:

```sh
.venv/bin/python scripts/evaluate_readiness.py prepare \
  --directory output/another-readiness-run \
  --evaluator /path/to/hackapertus-starter/evaluate.py
```

Preparation needs `requirements-data.txt`; scoring needs
`requirements-evaluation.txt`. Neither dependency set is required in the
submission image. Preparation refuses to overwrite an existing evaluation
directory. The inference runner never downloads data or model weights.

## Build and review the report

After completing the measurements, update `technical_report.md` from the saved
score and audit artifacts and retain failures. The report identifies
**OneLegedCoder - Xavier**.
From `track_2a/`:

```sh
.venv/bin/python -m pip install -r requirements-report.txt
make report
pdftoppm -png -r 110 output/pdf/claimlens-v4-report.pdf output/pdf/claimlens-v4-page
```

`make report` invokes `scripts/build_submission_report.py`, renders the current
Markdown report and writes `output/pdf/claimlens-v4-report.pdf` plus its build
manifest. The manifest records source, builder and PDF hashes. The builder
rejects more than six pages; inspect every rendered page after the last content
change before delivering the report. A successful build is not a visual review
or a completed submission. The existing PDF is an earlier draft. It has not been
regenerated after the user's intentional evaluation stop; final measurements,
image checks and PDF regeneration remain pending.

`make report-v2` explicitly invokes the older `scripts/build_report.py` and
recreates `output/pdf/claimlens-v2-report.pdf` from its historical measurement
artifacts. Keep it separate from the current report. Neither report command runs
inference or modifies evaluation results. Both commands also work from the
repository root through its forwarding Makefile.

## Recorded results and limits

The prior, tuned 27-case development sample scored **0.5556 macro-F1** and
**18/27 correct** using the unmodified official evaluator. All nine neutral cases
were misclassified as contradiction. Its reproduction is preserved in
`output/v4-readiness/baseline-v2/official-score.json`; it is not a holdout result.

The two predetermined Task B cohorts are complete: **50/54 correct**, **macro-F1
0.9247219356**, **54 accepted predictions, zero failed/missing cases**. The combined
[official score](../output/v4-readiness/final-b-combined/summary.json) recomputes
F1 over all 54 original predictions instead of averaging cohort F1 scores. All
18 neutral cases were correct. Mean case time was **15.85 seconds**, p95
**27.74 seconds**; recorded usage was **119,486 input / 7,069 output tokens**.
Independent [primary](../output/v4-readiness/final-b/evidence-audit.json) and
[extension](../output/v4-readiness/final-b-extension/evidence-audit.json) audits
verified all **34 returned exact reference quotations**, with no output issues.
Exact quote provenance does not establish semantic correctness.

The Task A rerun was intentionally stopped at the user's request to redesign
latency after **one of nine cases produced an accepted output**. That case took
**458,532.384 ms (458.53 seconds)**, with **62,050 input / 661 output tokens**,
**six model calls** and **one evidence-reduction round**. It has not been scored
for correctness. The following in-flight case was interrupted with incomplete
usage. The nine-case cohort is incomplete; no Task A F1 or overall readiness is
claimed. Original results remain preserved.

The earlier unsuccessful attempt and source remain under
`final-a/interrupted-context-overflow/`. Its capacity repair adds bounded evidence
reduction and prevents repeated full analysis of fixed capacity constraints.
Task B retains its pre-repair run identity and source snapshot; its short-source
inference branch is unchanged. Do not combine these records as though all
measurements used one source hash. The completed **181 software tests**, frontend
checks and **54-case Task B results** remain valid recorded observations.

Testing and evaluation are stopped. The local model and UI are stopped, ports
8081 and 8000 have no listener, and the Colima VM is stopped. The final image
rebuild and PDF regeneration remain pending while latency improvements are
considered. No result on the organizers' endpoint or private benchmark has been
recorded.

These are small samples from a public training dataset. Date separation reduces
development leakage but cannot rule out model pretraining exposure. Full-booklet
cases retain the dataset's reference-based labels, matching the official case
construction; a full document can contain additional context. PDFs and dataset
caches are local artifacts and are not bundled into the submission image.

## Latency diagnosis and proposed next iteration

The user stopped the full-booklet run to prioritize response time. No faster
inference path has been implemented or measured yet. The completed case took
458.53 seconds and six model calls. Native server timings attribute 380.37
seconds (83%) to reading prompts, 44.09 seconds to generation and 34.07 seconds
to other case overhead. The final classification call alone took 30.75 seconds;
the preceding three extraction and two reduction calls took 393.71 seconds of
model time. See the preserved [timing profile](../output/v4-readiness/latency-analysis/profile.json).

The proposed first experiment is a cached local passage index followed by a
small, live Apertus assessment:

1. Extract/OCR each PDF once and cache paragraph-sized source spans with original
   page numbers. Key the index by extracted-text hash and indexing version so an
   OCR refresh invalidates it. Keep index creation separate from warm-query
   latency; report cold-import costs too. Evaluation must build any missing
   index from the supplied PDF, without labels or network downloads.
2. Use one short Apertus call to translate the claim and proposal into search
   terms in the source language; if metadata is absent, generate German, French
   and Italian queries together. Preserve names, negation and quantities.
3. Rank original paragraphs locally with [BM25](https://www.elastic.co/docs/reference/elasticsearch/index-settings/similarity)
   and normalized text matching. Boost the intended proposal rather than
   excluding other sections solely by a heading. Include neighboring context
   and diverse matches; do not require the claimed number to appear, because a
   different number may be the decisive contradiction. This can run in Python
   without Elasticsearch or another inference model.
4. Give Apertus the original claim and roughly 8–12 selected passages, within a
   measured 4,000–6,000-token prompt budget, for one joint verdict. Preserve the
   existing exact-quote and physical-page validation. Translated search terms
   never count as source evidence. Record selected coverage;
   do not describe retrieval as the model reading the whole booklet.

The initial warm-query target is **30–60 seconds**, not a measured result or
guarantee. Cross-language and distributed evidence can be missed, particularly
for neutral decisions. A weak retrieval score is not proof of neutrality or a
calibrated confidence estimate. Use an explicit bounded expansion or report
insufficient coverage rather than silently reverting to many minutes of work.
Retain the exhaustive path as a comparison until quality is established.

Lower-risk supporting experiments are removing repeated title/language metadata
from every source unit and reducing llama.cpp prompt-cache memory. Reconstructed
extraction requests for this case shrink by 24.05% in UTF-8 bytes when metadata
is sent once; token savings are unmeasured. Large prompt-cache evictions suggest
memory pressure may contribute to overhead, but do not prove swapping. GPU
offload, Q4 weights and disabled reasoning are already configured. Shorter
answers alone cannot address the measured input-processing bottleneck.

Next validation should begin with a small development-only set and a fixed
per-case deadline, recording retrieval coverage, labels, exact citations, tokens
and cold/warm latency. Expand to all nine language pairs and the frozen quality
cohorts only after the latency experiment is acceptable. Task A evaluation
readiness remains unestablished.
