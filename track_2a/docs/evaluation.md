# Evaluation and submission checks

The CLI and live evaluation runners use the same `claimlens.cli.predict_case` function. A failed inference remains a failure, and only validated predictions enter official output. Software behavior, model accuracy and quotation provenance are separate checks. See [validation.md](validation.md) for current recorded measurements; release comparisons belong in the workspace's root `VERSION_HISTORY.md`.

## Software checks

From `track_2a/`:

```sh
make test
make test-ui
make verify-submission
```

The submission check builds the `linux/amd64` prediction image and checks Task A/B with no network, a read-only filesystem and writable `/tmp`. Test model responses are stubbed. These checks do not run Apertus or establish accuracy. A Docker runtime is required; on the configured Mac use `DOCKER='docker --context colima-claimlens'` after starting that profile.

## Three-case development check

Install the development dependencies, which include the runtime, data preparation, scoring and report tools, and start the configured model in a separate terminal:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
make evaluate-prepare
make evaluate
make evaluate-score
```

The shortcuts use `output/evaluations/latency`. Preparation freezes exactly three development booklet cases with DE→FR, FR→IT and IT→DE language pairs, one per label. It relies on the pinned local dataset, cached booklets and preserved split/prior-input/evaluator records under the workspace's `archive/track_2a/output/`. These archive dependencies are for reproducing development selection only; the application and prediction image do not use them. Final delivery excludes the archive, so restore those records or supply the original `--previous` and `--prior-inputs` paths to run preparation from a delivered copy.

Use a fresh directory for a changed implementation, model or inputs:

```sh
make evaluate-prepare RUN_DIR=output/evaluations/latency-next
make evaluate RUN_DIR=output/evaluations/latency-next
make evaluate-score RUN_DIR=output/evaluations/latency-next
```

The equivalent explicit commands are:

```sh
.venv/bin/python scripts/evaluate_fast.py prepare --directory output/evaluations/latency-next
.venv/bin/python scripts/evaluate_fast.py run --directory output/evaluations/latency-next
.venv/bin/python scripts/evaluate_fast.py score --directory output/evaluations/latency-next
```

Preparation refuses to overwrite existing records. Run inference serially, separately from browser checks on the single local model slot. The runner reads no gold and allows at most four transport attempts within a shared 120-second case budget, including source preparation and both model passes. There is no whole-pipeline retry or automatic exhaustive fallback. Unknown token usage remains unknown. PDF deadline checks run between pages; an in-process parser cannot be interrupted during one page operation.

These cases have already been used for tuning. Repeating them measures behavior and latency on known development cases; it is not a fresh quality estimate. Do not infer general performance from three cases or relabel them as the private benchmark.

## Paired token and latency experiment

`scripts/benchmark_efficiency.py` freezes nine additional full-booklet requests before inference: one per source-to-claim language pair and three per label. Six tuning cases include all three same-language pairs and three cross-language pairs, with two examples per label. The remaining three cross-language cases form a separate confirmation cohort, one per label. These are small public development samples, not the private benchmark.

The current comparison fixes one candidate before selecting cases. Both variants retain multilingual query generation and a 5,000-token assessment input budget. The baseline generates full contextual quotations; `body-prefix-5000` uses the existing substantial-body quotation filter and emits short, registered quotation prefixes that Python expands back into exact complete passages. The assessment messages and source text are unchanged by this citation mode. This is a fixed two-variant comparison, with no adaptive search over further configurations. See [validation.md](validation.md) for the measured outcome and released configuration; the commands below specify an experiment, not a performance claim or production recommendation.

Preparation requires the workspace's pinned OST dataset, cached PDF library and preserved prior-input, date-split and official-evaluator records in `archive/track_2a/output/`. Those assets are excluded from final delivery. Selection excludes previously exercised exact reference/booklet requests, including both earlier tuning and confirmation cohorts, and all reserved final ballot dates. Gold is used for balanced selection and explicit scoring only; inference reads input cases and PDFs, never gold. Frozen input, PDF, dataset and evaluator hashes preserve provenance.

Before preparation, preserve two identical copies of the current source package and record their file hashes together with the fixed experiment protocol. Each `--source-root` must contain a `claimlens/` package. The copies must include the candidate's quotation-prefix/body filter implementation; explicit flags select which mode each run uses. Keep both snapshots and the runner unchanged throughout the comparison. From `track_2a/`, use a fresh working directory:

```sh
.venv/bin/python scripts/benchmark_efficiency.py prepare --directory output/evaluations/full-context-next --seed claimlens-v7-full-context-20261008
RETRIEVAL_PROMPT_TOKENS=5000 .venv/bin/python scripts/benchmark_efficiency.py run --directory output/evaluations/full-context-next --cohort tuning --variant baseline --source-root /path/to/baseline-src --query-mode multilingual --citation-mode full --trace-prompts
RETRIEVAL_PROMPT_TOKENS=5000 .venv/bin/python scripts/benchmark_efficiency.py run --directory output/evaluations/full-context-next --cohort tuning --variant body-prefix-5000 --source-root /path/to/candidate-src --query-mode multilingual --citation-mode prefix --trace-prompts
.venv/bin/python scripts/benchmark_efficiency.py score --directory output/evaluations/full-context-next --cohort tuning --variant baseline
.venv/bin/python scripts/benchmark_efficiency.py score --directory output/evaluations/full-context-next --cohort tuning --variant body-prefix-5000
```

Explicit `--query-mode multilingual --citation-mode full` baseline flags are essential: a future default change must not silently alter the reference configuration. Unsupported flags are rejected. Review all six paired outcomes before proceeding. Faster averages or equal overall accuracy are insufficient if a baseline-correct case becomes incorrect, an accepted case fails, or supporting evidence becomes weaker for an individual claim. Check substantive evidence, amounts, qualifications and attribution as well as exact quotation/page provenance. Retain the baseline if this gate fails; preserve the candidate's measurements and limitations.

Lock the predeclared candidate's source, configuration and tuning results before either confirmation run:

```sh
.venv/bin/python scripts/benchmark_efficiency.py lock --directory output/evaluations/full-context-next --variant body-prefix-5000
```

Repeat each variant's `run` command with `--cohort confirmation`, preserving its source path, 5,000-token limit and every flag, including `--trace-prompts`. **Both variants must finish confirmation inference before either confirmation score command is run or confirmation gold is inspected.** Only then repeat both `score` commands with `--cohort confirmation`. Confirmation permits only `baseline` and the locked candidate and rejects changed tuning source/settings or altered locked candidate results. Apply the same per-case label, acceptance and evidence gate to confirmation without selecting another candidate from those outcomes.

Run variants serially on the same model/runtime configuration. Snapshot runs explicitly load the active project's `.env` and use its OCR/library asset paths. Recorded identities hash the imported snapshot, settings, endpoint, inputs, runner and diagnostic configuration without storing transport credentials or the endpoint URL. Results live under `runs/<variant>/<cohort>/`. The runner verifies input/PDF hashes and source/configuration identity between cases, flags source changes during a case, and permits `--resume` only for an unchanged identity.

`--trace-prompts` saves local diagnostics for each case and transport stage: exact message content, supplied source passages and the raw model JSON, including generated search queries and quotation prefixes before local expansion. Only public development text is used in this comparison. The trace allowlist excludes settings, endpoint URLs, transport headers and API keys; it does not redact claim or booklet text. Diagnostic files stay in the local experiment output and are excluded from final delivery. Their hashes are recorded in each result, and resume rejects missing or changed traces. Compare exact assessment messages and passages across the pair, and inspect generated-query differences; the intentional response-grammar change is separate from input equality.

Every case uses the production CLI pipeline with a maximum 120-second budget and four transport attempts. The PDF parser's cooperative deadline limitation described above still applies. `results.jsonl` adds per-stage provider input/output tokens, request duration and attempts for query generation and assessment, plus time outside model transport for extraction, retrieval, token planning and other local work. `summary.json` includes stage totals, official label/evidence scores, failures and usage completeness; `evidence-audit.json` independently checks exact quotations and physical pages. Unknown usage is not counted as zero. All failures or missing responses remain in the score denominator.

Compare paired cases and stage totals as well as averages, accounting for index-cache state and any prompt differences shown by the traces. One run per case does not isolate cache/order effects or measure timing variance. New exact requests may still share proposals, translated claim families and previously exercised ballot dates with earlier development work. Report the three locked confirmation cases separately; combined nine-case results are descriptive rather than a general accuracy estimate, even though the candidate was fixed before selection.

A delivered source copy can consume a separately prepared experiment directory through `--directory /path/to/prepared-experiment` without the selection archives. Supply matching source snapshots and configure the model locally; keep gold outside the inference input mount and invoke `score` separately. Preserve both variants, including failures and rejected optimizations, instead of replacing cases or rerunning until a favorable result appears.

The measured-source records for this comparison belong in the workspace's `archive/track_2a/output/v7-final/`: the predeclared plan, source snapshots and hashes, frozen selections, runtime identity, raw results/traces, official scores and per-case reviews. The commands above use a fresh working directory. Archived identities retain their original absolute source paths: copy the prepared inputs and source snapshots into a new comparison and record a new identity rather than resuming archived runs or editing their manifests. The seed alone does not reproduce selection when the set of previously exercised requests has changed. Reusing the archived selection remains a comparison on known development cases, even in a new directory.

## Broader validation

The readiness harness creates date-separated development and evaluation cohorts from the public dataset. It reserves previously exercised ballot dates for development and deduplicates normalized requests. Its cohort names are selection roles, not a claim that a submission is ready:

| Cohort | Cases | Purpose |
| --- | ---: | --- |
| `development` | 27 | One case per language pair and label; tuning only |
| `final-b` | 27 | Predetermined reference-text evaluation sample |
| `final-b-extension` | 27 | Additional predetermined reference cases |
| `final-a` | 9 | Full-PDF evaluation, one per language pair |

Prepare from the pinned dataset/booklet cache and an inspected copy of the official starter evaluator:

```sh
.venv/bin/python scripts/evaluate_readiness.py prepare --directory output/evaluations/readiness --evaluator /path/to/hackapertus-starter/evaluate.py
.venv/bin/python scripts/evaluate_readiness.py run --directory output/evaluations/readiness/final-b
.venv/bin/python scripts/evaluate_readiness.py score --directory output/evaluations/readiness/final-b
```

Preparation also needs preserved prior development inputs to keep the date split consistent. Its default is in the local archive; pass `--prior-inputs /path/to/original/input.jsonl` when restoring those records elsewhere. Do not substitute an empty file or a different cohort to bypass this safeguard.

Use the corresponding cohort path for `final-a` or `final-b-extension`. Freeze code and settings before evaluation. If code, endpoint, model, limits or inputs change, use a new directory and retain the original results. `--resume` accepts only the same recorded run identity and skips every recorded case, including failures. The runner checks source identity between cases.

Only the cohort's `input/` directory belongs in the prediction container mount. Keep `gold/` outside it. The run command reads no gold and writes:

| File | Contents |
| --- | --- |
| `results.jsonl` | Accepted and failed cases, observed usage, timing and processing details |
| `predictions.jsonl` | Valid official-format responses, updated after each accepted case |
| `results.run.json` | Source/input hashes, model/endpoint identity and limits |

Scoring verifies the frozen inputs and gold, then calls the copied unmodified official evaluator. `official-score.json`, `official-score.log` and `summary.json` report class/language scores, Task A evidence overlap, missing responses, usage completeness and mean/p95 time. P95 uses nearest rank. Unknown usage is not treated as zero. Official macro-F1 targets are 0.60 for Task A and 0.70 for Task B; small local samples do not establish private-benchmark performance.

For strategy comparisons, explicitly set `DOCUMENT_STRATEGY=retrieval` or `exhaustive` and keep separate directories. Retrieval records selected coverage and cache use; exhaustive processing records source segments and reduction rounds. Both include all model calls and retries in usage/time. Distinguish cold PDF import/extraction, first index creation and warm-index queries. The index stores lexical statistics, not predictions.

## Independent evidence audit

The official overlap metric does not verify physical PDF pages. Audit accepted outputs independently:

```sh
.venv/bin/python scripts/audit_evidence.py --input output/evaluations/latency/input/cases.jsonl --predictions output/evaluations/latency/predictions.jsonl --output output/evaluations/latency/evidence-audit.json
```

The auditor makes no model calls and reads no gold. It freshly extracts PDFs, preserves physical page numbering, checks exact quotes and records document/text hashes. It also checks IDs, labels, required metrics, quote limits and required Task A evidence. Reference-only citations must match the supplied reference and use `page: null`.

Exit `0` means all checks verified, `1` indicates findings, and `2` indicates an execution error. OCR-only text can remain unverified against a PDF's text layer and requires visual inspection. A verified quote establishes its wording and location, not its relevance, attribution or the correctness of the label. Review substantive evidence separately from exact matching and official fuzzy overlap.

## Report and final delivery

The template-located `technical_report.md` is the final report source. Keep it focused on the delivered method, actual measurements and limitations. Maintain release history separately in the workspace's `VERSION_HISTORY.md`.

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
make report
```

The builder writes `technical_report.pdf` directly beside `technical_report.md` in `track_2a/` and puts its build manifest in `output/report/`. The manifest records source, builder and PDF hashes. The builder enforces the six-page limit. Render and inspect every PDF page after the last content change, and keep the page images and matching completed visual-review manifest in `output/report/`. The report command runs no inference and does not submit the project remotely.

The root [README](../../README.md#validation-and-delivery) lists final delivery contents. Use the active `track_2a/` project and its two reports; no separate `submission/` directory or export step is needed. `make submission` and `make verify-submission` still build and check the prediction Docker image.

Completed measurements and older reports are preserved under the workspace's `archive/`; new evaluation work belongs in ignored `output/evaluations/`. Do not edit archived predictions or silently resume them with current source. Final delivery excludes archived records, development history, downloaded data/gold, model weights, credentials and working outputs. The former generated export is retained in `archive/legacy-submission/` as a historical record.
