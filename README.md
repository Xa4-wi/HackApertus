# ClaimLens

ClaimLens checks claims against Swiss voting booklets with **Apertus v1.5** for **Hack Apertus Track 2A — OST**. German, French and Italian source documents and claims can be combined independently. Results contain a source-relative label—**0 entailment, 1 neutral, 2 contradiction**—with exact quotations, PDF pages, observed token usage and elapsed time.

## Repository map

| Location | Purpose | Use |
| --- | --- | --- |
| [`track_2a/`](track_2a/README.md) | Active application, tests, scripts, documentation and both final reports | Develop, run and review ClaimLens here |
| [`track_2a/technical_report.md`](track_2a/technical_report.md) | Final technical report source in the template's location | Edit the submission report here |
| [`track_2a/technical_report.pdf`](track_2a/technical_report.pdf) | Final technical report PDF beside its source | Read the submission report here |
| [`VERSION_HISTORY.md`](VERSION_HISTORY.md) | Release history, earlier approaches and recorded comparisons | Read development history here |
| [`archive/`](archive/README.md) | Preserved experiment outputs, earlier reports, template reference and former submission export | Historical evidence; excluded from runtime and final delivery |
| `track_2a/output/` | Fresh predictions and evaluation runs | Ignored working artifacts; preserve completed evidence in the archive |
| `.cache/`, `track_2a/data/local/`, `track_2a/.venv/`, `track_2a/.env` | Local weights, documents, dataset, dependencies and configuration | Ignored machine-specific resources; excluded from final delivery |

The template's `track_2a/` layout remains intact, with `archive/` alongside it and no separate `submission/` directory. The root Makefile forwards development commands into `track_2a/`. The prediction image contains application code and PDF/OCR tools; the local dataset, gold labels, model weights, previous outputs and credentials remain outside it.

## Start locally

On the configured Mac, run these in separate terminals from the repository root:

```bash
make model-serve
```

```bash
make dev
```

Open **http://localhost:8000**. Select a booklet and proposal, enter a claim, and choose **Check claim**. The library contains 60 cached official PDFs across the three source languages and accepts official PDF links or uploads. Every check calls the local model; the button is disabled while it is offline. Stop both terminals with `Ctrl+C` when finished.

The configured runtime is llama.cpp with Apple Metal and a pinned 5.06 GB Q4_K_M text conversion of Apertus v1.5 8B. It serves `http://127.0.0.1:8081/v1` without an API key. See [first-time setup and CLI usage](track_2a/README.md), [local model setup](track_2a/docs/local-model.md), the [presentation walkthrough](track_2a/docs/presentation-walkthrough.md) and the [120-second video script](track_2a/docs/video-script.md).

## How it works

Small sources use one complete-source Apertus assessment. For a longer booklet, Apertus generates search phrases in German, French and Italian, a cached local BM25 index selects original passages, and a final model call classifies the unchanged claim. The default final input budget is 5,000 tokens and the retrieval deadline is 120 seconds. Reference-only Task B inputs always use their full supplied reference.

Python independently validates quotations and physical PDF pages. The UI shows selected-page coverage because retrieval can miss relevant evidence; a matching quotation does not prove that the interpretation is correct. Failed checks remain failures. Usage and time include all model passes and retries. See the [API contract](track_2a/docs/solution-api.md) for exact input, output and resource limits.

## Commands

| Command | Purpose |
| --- | --- |
| `make model-serve` / `make dev` | Start the local model / browser application |
| `make dataset` / `make booklets` | Prepare the pinned dataset / official booklet cache |
| `make ocr-setup` | Prepare German, French and Italian OCR language files |
| `make check-endpoint` | Make one real synthetic CLI prediction through the configured endpoint |
| `make test` / `make test-ui` | Check Python behavior / frontend interactions |
| `make evaluate-prepare` / `make evaluate` / `make evaluate-score` | Prepare / run / score the three-case development check |
| `make run` | Build and start the interactive Docker application |
| `make submission` / `make verify-submission` | Build / check the separate prediction image |
| `make report` | Render `track_2a/technical_report.pdf` beside its Markdown source |

Evaluation and endpoint checks consume real inference calls. Run them separately from a presentation on the single local model slot. Use a fresh evaluation directory when code, model or inputs change; see [evaluation instructions](track_2a/docs/evaluation.md).

## Validation and delivery

The delivered configuration retains multilingual queries, a 5,000-token input budget and full contextual quotations. Short exact quotation prefixes remain experimental: matching tuning classifications did not prevent weaker supporting evidence. Source-language-only queries also remain experimental. These experiments add no default latency improvement. Current software checks, paired measurements, evidence reviews and limitations are recorded in [validation.md](track_2a/docs/validation.md); small public-data checks do not establish private-benchmark performance or organizer access.

The [technical report source](track_2a/technical_report.md) and [PDF](track_2a/technical_report.pdf) sit directly in `track_2a/`. Follow the [report instructions](track_2a/docs/evaluation.md#report-and-final-delivery) to rebuild and review them. Build manifests and page-review artifacts belong in ignored `track_2a/output/report/`. Release-by-release changes belong in [VERSION_HISTORY.md](VERSION_HISTORY.md).

For final delivery, use the root `README.md`, `LICENSE` and `Makefile`, plus the application source, configuration examples, supporting documentation and both reports in `track_2a/`. Exclude `archive/`, `.env`, downloaded data and gold, model weights, virtual environments, caches and working `output/` files. The previous export is preserved in `archive/legacy-submission/`; it is historical. `make submission` and `make verify-submission` still build and test the prediction Docker image; their names do not refer to a directory.

Based on the [official template](https://github.com/HackApertus/project-template/tree/7f2382275461baf3fa6c8855d157d86abffe9f0e). Source code: Apache-2.0; project documentation: CC-BY-4.0. Imported data retains its original attribution and license; see [data provenance](track_2a/data/README.md).
