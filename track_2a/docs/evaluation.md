# Evaluation and submission checks

The CLI and the local evaluation runner use the same `claimlens.cli.predict_case`
function. The runner keeps unsuccessful cases in its diagnostic results and
exports only actual, validated predictions. A failed inference is never replaced
with a neutral answer.

Software compatibility, prediction quality, and quote provenance are checked
separately. Passing local checks does not establish a result on the organizers'
private benchmark or verify their inference endpoint.

## V0.5 development latency check

The default booklet pipeline now uses cached local BM25 passage search rather
than sending every page through model extraction. A short Apertus call expands
the claim/proposal into German, French and Italian search phrases (384 output
tokens maximum), then one final call assesses selected original passages within
a default 5,000-token planned input budget. Short inputs that fit use one full
source call. Task B always keeps full-reference/exhaustive processing.

The V0.5 latency experiment is restricted to **three development booklet cases**.
The script originally selected DE→FR entailment, FR→IT neutral and IT→DE
contradiction from previously exercised ballot dates, excluding exact requests
used before this experiment. It froze inputs and separate gold before inference
and did not read final Task A/B gold. These same cases were then repeatedly used
to diagnose citations and tune the response format. This is not a fresh quality
estimate or evidence of evaluation readiness.

The selected contextual-quotation version is recorded in
`output/v5-latency-context/`: **3/3 correct, accepted labels with no failures**,
**54.97 s mean**, **70.63 s p95**, and **12,819 input / 1,632 output tokens** total.
Every case used two model calls and complete provider usage. All three reused
lexical indexes while extracting their 32-, 72- and 40-page PDFs again.

Official gold-passage overlap remained **0.50 (1/2 non-neutral cases)**. A separate
audit verified all **three returned quotations** on their physical PDF pages,
with no output issues. Exact quotations can still differ from the benchmark's
intended evidence. See the selected [score](../output/v5-latency-context/summary.json)
and [audit](../output/v5-latency-context/evidence-audit.json). The full nine-case
Task A and 54-case Task B cohorts have not been rerun on this version.

Run from `track_2a/`, using a fresh output directory:

```sh
.venv/bin/python scripts/evaluate_fast.py prepare --directory output/my-v5-latency
.venv/bin/python scripts/evaluate_fast.py run --directory output/my-v5-latency
.venv/bin/python scripts/evaluate_fast.py score --directory output/my-v5-latency
.venv/bin/python scripts/audit_evidence.py \
  --input output/my-v5-latency/input/cases.jsonl \
  --predictions output/my-v5-latency/predictions.jsonl \
  --output output/my-v5-latency/evidence-audit.json
```

Without `--directory`, the script uses `output/v5-latency`. Preparation refuses
to overwrite a nonempty directory. The runner reads no gold, calls the production
CLI function, records failures and shares a maximum 120-second budget across
PDF preparation, planning, query expansion, local search, final inference and
transport retries. There are at most four transport attempts; a failed verdict
does not restart the pipeline or launch an exhaustive fallback. Unknown usage
remains unknown rather than becoming zero or an invented successful record.

Source preparation checks the deadline between PDF pages and limits OCR
subprocesses to the remaining budget. The in-process PDF parser cannot be
preempted during one page operation. A deadline is a bounded-processing policy,
not a claim that every possible blocking parser operation is interruptible.

Record selected source pages/units, query expansion, index-cache hits, observed
tokens, exact quotations and latency alongside labels. The local index is built
on first search and cached under the temporary directory in
`claimlens-retrieval-v1`, keyed by extracted text, provenance metadata and the
index version. It caches lexical statistics, never answers or gold. Browser
imports already cache PDF bytes and text separately. Cold import/extraction,
first index creation and warm-index queries are distinct costs; do not label a
measurement warm without inspecting its cache record.

The final model sees selected passages, so relevant qualifications,
counter-evidence or facts spread across the document can be missed. Original
quotes and physical pages remain verifiable. Neither a lexical score nor a
missing search hit proves neutrality. An empty or malformed retrieval result
fails explicitly. The UI exposes this coverage limitation.

### Development history

The initial run in `output/v5-latency/` returned three correct labels in 39.15 s
mean (40.80 s p95), using two calls per case and newly built indexes. Its exact
quotations were inadequate: an attribution-only footer and a broken hyphenated
line, even though substantive supporting text was present among retrieved units.
The exact-page audit did not detect that semantic weakness. Those results remain
preserved and must not be presented as the selected version's measurements.

The chosen repair keeps verbatim contextual quotation candidates of about 900
characters, merging a tiny trailing fragment with preceding context up to 1,200
characters. The model returns the full quotation text. With ordinary JSON-only
providers, Python may expand an unambiguous exact anchor within the cited
passage to the containing original context. The label and original quoted words
stay unchanged; the expansion count is disclosed, and no quote crosses omitted
text. Task B/exhaustive quotation behavior is unchanged.

The selected contextual run is `output/v5-latency-context/`. A later experiment
that replaced quotation text generation with citation IDs regressed to two
correct labels out of three and was discarded. Its artifacts are preserved under
`output/v5-fast-final/`; despite that directory name, it is not the selected
implementation. These repeated cases were used for development decisions, so
none of the reruns is an independent holdout result.

## Historical V0.4 public-data cohorts

The preserved preparation is in `output/v4-readiness/`, generated from
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

## Prepare broader validation

The commands below describe the larger readiness harness. Use a fresh directory
for changed code; the completed V0.4 artifacts cannot resume as V0.5.

Run these commands from `track_2a/`. Configure the local model as described in
[local-model.md](local-model.md), and use the project virtual environment:

```sh
.venv/bin/python -m pip install -r requirements-evaluation.txt
.venv/bin/python scripts/evaluate_readiness.py prepare \
  --directory output/another-readiness-run \
  --evaluator /path/to/hackapertus-starter/evaluate.py
.venv/bin/python scripts/evaluate_readiness.py run --directory output/another-readiness-run/final-b
.venv/bin/python scripts/evaluate_readiness.py score --directory output/another-readiness-run/final-b
```

Use `final-a` for a full-booklet quality run only after reviewing the small latency
experiment. Its predetermined PDFs contain 16–56 pages. Set the booklet strategy
explicitly when comparing retrieval and exhaustive runs; keep their artifacts
separate. Run the model serially on a small local machine. `final-b-extension` is
optional additional evidence; report its result alongside the original cohort,
including any failures.

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

`DOCUMENT_STRATEGY=exhaustive` retains the V0.4 long-document method: every
original source segment is examined, and oversized selected excerpts are reduced
in at most eight ranking rounds. Every candidate is examined in each round;
IDs, physical pages and verbatim text remain attached. Selecting fewer units can
still omit relevant evidence. These runs record reduction rounds/windows and
candidate counts. Default `retrieval` runs record selected coverage and cache
use instead. Both strategies aggregate actual usage and latency across all model
passes and retries, and fixed capacity failures do not restart full analysis.

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
pdftoppm -png -r 110 output/pdf/claimlens-v5-report.pdf output/pdf/claimlens-v5-page
```

`make report` invokes `scripts/build_submission_report.py`, renders the current
Markdown report and writes `output/pdf/claimlens-v5-report.pdf` plus its build
manifest. The manifest records source, builder and PDF hashes. The builder
rejects more than six pages; inspect every rendered page after the last content
change before delivering the report. A successful build is not a visual review
or a completed submission. Earlier V0.4/V2 PDFs remain historical artifacts;
regenerate the V0.5 report from the selected run and inspect its rendered pages
before submission.

`make report-v2` explicitly invokes the older `scripts/build_report.py` and
recreates `output/pdf/claimlens-v2-report.pdf` from its historical measurement
artifacts. Keep it separate from the current report. Neither report command runs
inference or modifies evaluation results. Both commands also work from the
repository root through its forwarding Makefile.

## Historical results and limits

The prior, tuned 27-case development sample scored **0.5556 macro-F1** and
**18/27 correct** using the unmodified official evaluator. All nine neutral cases
were misclassified as contradiction. Its reproduction is preserved in
`output/v4-readiness/baseline-v2/official-score.json`; it is not a holdout result.

The two V0.4 Task B cohorts are complete: **50/54 correct**, **macro-F1
0.9247219356**, **54 accepted predictions, zero failed/missing cases**. The combined
[official score](../output/v4-readiness/final-b-combined/summary.json) recomputes
F1 over all 54 original predictions instead of averaging cohort F1 scores. All
18 neutral cases were correct. Mean case time was **15.85 seconds**, p95
**27.74 seconds**; recorded usage was **119,486 input / 7,069 output tokens**.
Independent [primary](../output/v4-readiness/final-b/evidence-audit.json) and
[extension](../output/v4-readiness/final-b-extension/evidence-audit.json) audits
verified all **34 returned exact reference quotations**, with no output issues.
Exact quote provenance does not establish semantic correctness.

The V0.4 exhaustive Task A rerun was intentionally stopped at the user's request to redesign
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
measurements used one source hash. The historical software/frontend checks and
54-case Task B results remain recorded observations, not current-version reruns.
The selected V0.5 source passed **233 Python tests locally and 233 inside the
`linux/amd64` submission image**, with no network, a read-only filesystem and
writable temporary storage. The frontend smoke check also passed. Model calls
in software tests are stubbed; the repeated three-case live measurements are
recorded above.

Reviewed PDF regeneration and an authenticated organizer-endpoint test remain
separate checks. No result on the organizers' endpoint or private benchmark has been
recorded.

These are small samples from a public training dataset. Date separation reduces
development leakage but cannot rule out model pretraining exposure. Full-booklet
cases retain the dataset's reference-based labels, matching the official case
construction; a full document can contain additional context. PDFs and dataset
caches are local artifacts and are not bundled into the submission image.

## Measured motivation for the retrieval path

The user stopped the V0.4 full-booklet run to prioritize response time. Its one
completed case took 458.53 seconds and six model calls. Native server timings
attribute 380.37 seconds (83%) to prompt processing, 44.09 seconds to generation
and 34.07 seconds to other case overhead. The final classification call alone
took 30.75 seconds; the preceding three extraction and two reduction calls took
393.71 seconds of model time. See the preserved
[timing profile](../output/v4-readiness/latency-analysis/profile.json).

V0.5 implements local retrieval to reduce text repeatedly sent through Apertus.
The selected contextual-quotation version averaged **54.97 seconds** on the
three repeated development cases, with cached lexical indexes. These are
different cases from the 458.53-second V0.4 observation; those figures do not
establish a paired speedup or isolate caching. The earlier 30–60-second target
was not a guarantee, and the slowest selected-version case took 70.63 seconds.
Review the evidence-overlap limitation before broader quality evaluation;
three repeatedly tuned cases cannot establish all-nine-language-pair quality.

A separate timing-only run of that same slow booklet, using the selected
contextual-quotation version, is recorded in
[`v5-latency-context/same-case-comparison/results.jsonl`](../output/v5-latency-context/same-case-comparison/results.jsonl):

| Same unscored case | V0.4 exhaustive | Selected V0.5 retrieval |
| --- | ---: | ---: |
| Case wall time | 458,532.384 ms | 56,112.593 ms |
| Input tokens | 62,050 | 4,363 |
| Output tokens | 661 | 526 |
| Model calls | 6 | 2 |

The observed change is **8.17× faster** with **92.97% fewer input tokens**. The
model and hardware were the same; the final run selected 12 units with a warm
lexical index and the runtime cache setting also changed. This is one unscored
case, not a quality result or an isolated causal test of retrieval. It measures
the combined operational setup and cannot predict every booklet's latency.

The launcher now sets `LOCAL_MODEL_CACHE_MB=1024`, replacing the observed
runtime's implicit 8,192 MiB prompt-cache limit. No isolated cache-specific speed
benefit has been measured. Earlier large cache evictions suggested memory
pressure might contribute to overhead, but did not prove swapping. GPU offload,
Q4 weights and disabled reasoning were already configured.

The earlier request reconstruction found a 24.05% reduction in UTF-8 bytes by
sending repeated metadata once. That was a byte estimate, not a measurement of
token savings or runtime, and is not a V0.5 benchmark result. Faster answers
must still preserve sufficient evidence for a correct source-relative decision;
Task A evaluation readiness remains unestablished.
