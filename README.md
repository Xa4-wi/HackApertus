# ClaimLens

Check multilingual claims against Swiss voting booklets and follow the evidence back to the original PDF. **Version 0.4** is a local Python application for **Hack Apertus Track 2A — OST: Multilingual Natural Language Inference over Swiss Official Voting Booklets**.

The browser now offers a library of **60 official booklet PDFs**: 20 in each of German, French and Italian. Select a booklet and proposal, write a claim in any of those languages, and run **Apertus v1.5 8B** locally. You can also import a direct Federal Chancellery PDF link or upload a booklet. The result shows the NLI class, exact source quotations, original PDF pages, token usage, elapsed time and document coverage.

## Start the presentation

Run these in separate terminals from the repository root:

```bash
# Terminal 1: local Apertus with a 16,384-token context
make model-serve
```

```bash
# Terminal 2: ClaimLens
make dev
```

Open **http://localhost:8000**. Search the booklet library by date/title and filter its language. Choose a booklet, name the proposal, write a claim and select **Check claim**. Every check uses the local Apertus model. The button stays disabled while the model is offline; the status panel shows how to start it. There is no stored-answer mode.

The interface uses a compact library and claim workspace, with the resulting assessment and source evidence side by side. Original PDF links, measured usage, extraction notes and JSON export remain available.

This Mac uses llama.cpp with Apple Metal and a downloaded **5.06 GB Q4_K_M text conversion** of Apertus v1.5 8B. The API is `http://127.0.0.1:8081/v1`; no key is needed. Local configuration is in the ignored `track_2a/.env`. See [local model setup](track_2a/docs/local-model.md) and the [three-minute presentation walkthrough](track_2a/docs/presentation-walkthrough.md).

## Current capabilities

- **Booklet library:** Downloads the official PDFs referenced by the OST snapshot, caches their original bytes and extracted pages, and keeps source URL, language, content hash and proposal names. Imports do not call the model.
- **Long documents:** Reads every supplied source segment and selects exact excerpts. If those excerpts are too large, Apertus ranks the original source units in up to eight reduction rounds before the joint assessment. Original page references remain intact; selecting fewer excerpts can miss relevant facts. Smaller inputs use one model call.
- **Scanned pages:** Uses local Poppler and Tesseract for bounded OCR when a PDF has little extractable text. OCR and unreadable-page warnings remain visible.
- **Evaluation:** The readiness harness freezes separate development and public-data evaluation cohorts by ballot date, covers all nine language pairs, retains failed cases, and runs the official scorer. See [evaluation instructions](track_2a/docs/evaluation.md).
- **Submission path:** Accepts both the presentation's minimal JSONL inputs and the annotated API examples. Bounded retries preserve known usage; a failed batch keeps successful cases in a separate partial file. The separate `linux/amd64` prediction image contains application code and PDF/OCR tools; models, the downloaded dataset and gold labels stay outside it.

Version 0.4 also simplifies the model response to an explanation, a source relation (`supported`, `not_enough_information`, or `refuted`) and evidence. Python preserves the submitted claim, maps that relation to the official labels 0/1/2 and independently validates quotations. This targets observed responses whose explanations described missing information while their labels said contradiction; effectiveness must still be measured. Quote matching does not prove semantic correctness.

The 1,488-row OST dataset is also saved locally, with prediction inputs and gold labels separated. Downloading this dataset did **not** train the model. See [data setup](track_2a/data/README.md).

## Useful commands

| Command | Purpose |
| --- | --- |
| `make dev` | Start the browser application on port 8000 |
| `make model-serve` | Start the downloaded local model |
| `make check-endpoint` | Make one real synthetic prediction through the CLI and report endpoint/format results |
| `make booklets` | Import/cache the official PDFs from the local OST snapshot |
| `make ocr-setup` | Download and verify the three OCR language files |
| `make evaluate-prepare` | Legacy development sampler; defaults to the preserved V2 output location |
| `make evaluate` | Legacy development runner; refuses to resume V2 results with changed code |
| `make test` | Run unit and integration checks |
| `make test-ui` | Check frontend interactions and API contracts |
| `make run` | Build and start the interactive Docker image |
| `make submission` | Build the separate official prediction image |
| `make verify-submission` | Build and test Task A/B in the isolated submission container |
| `make report` | Build the current V0.4 PDF from `technical_report.md`; final metrics and visual review are still required |
| `make report-v2` | Regenerate the historical V2 PDF from its preserved measurements |

The library and dataset are already populated on this Mac. First-time setup and OCR prerequisites are described in [the Track 2A guide](track_2a/README.md). Use the [V0.4 readiness harness](track_2a/docs/evaluation.md) for current measurements; its frozen cohorts are separate from the legacy V2 evaluation. Evaluation and endpoint checks make real model calls; run them separately from a live presentation. Existing evaluation files are preserved, and resuming after code/model/input changes requires a new evaluation directory.

## Project guide

The template's `track_2a/` directory remains the project root. The top-level Makefile forwards commands into it.

```text
HackApertus/
├── Makefile                        Convenience commands
├── LICENSE                         Apache-2.0 license
└── track_2a/
    ├── README.md                   Setup, configuration and official CLI
    ├── technical_report.md         Method, validation and limitations
    ├── Makefile / Dockerfile       Development and submission commands
    ├── requirements*.txt           Runtime and optional dataset dependencies
    ├── src/claimlens/
    │   ├── cli.py                  Official JSONL input/output
    │   ├── booklets.py / ocr.py     PDF extraction and bounded local OCR
    │   ├── library.py              Cached booklet imports and provenance
    │   ├── engine.py               Assessment and independent quote checks
    │   ├── context.py              Full-source context planning and extraction
    │   ├── llm.py                  Apertus transport, prompts and JSON schema
    │   ├── config.py / runtime.py  Configuration and model availability
    │   ├── models.py               Shared labels and limits
    │   ├── server.py               Browser API
    │   └── static/                 HTML, CSS and JavaScript interface
    ├── scripts/                    Model/data/import/OCR/evaluation commands
    ├── data/                       Source metadata and ignored local dataset/library
    ├── output/                     Ignored predictions and evaluation records
    ├── tests/                      Unit and integration checks
    └── docs/                       Setup, presentation and event requirements
```

## What the results mean

The labels are **0 entailment**, **1 neutral**, and **2 contradiction**, relative to the supplied source. Exact quotations establish provenance; they do not independently prove the model's interpretation. Reading every segment does not guarantee that evidence selection or reduction retains every relevant fact. OCR may introduce transcription errors. Context, time and call limits fail explicitly when bounded reduction cannot produce a fitting assessment; fixed capacity failures do not trigger another full analysis. Usage and latency include all selection, reduction, final and retry calls.

Software tests verify behavior, not model accuracy. The latest completed software suite passed **181 tests**, and the frontend interaction checks passed. The completed V0.4 development run achieved **25/27 correct, macro-F1 0.927**, with all nine neutral cases correct and no failed predictions. Mean case time was **17.8 seconds**, with p95 **30.7 seconds**. These are development results used while tuning, not final validation. See the [recorded development summary](track_2a/output/v4-readiness/development/summary.json).

The two predetermined Task B reference cohorts produced **50/54 correct**, **macro-F1 0.924722**, and **54 valid predictions with no failures**. Independent audits verified all **34 returned exact quotations** against their supplied references. These cohorts come from the public training dataset, with previously exercised ballot dates reserved for development; they are not the organizers' private benchmark. See the [combined Task B result](track_2a/output/v4-readiness/final-b-combined/summary.json).

The Task A full-booklet rerun was intentionally stopped at the user's request to redesign latency after **one of nine cases produced an accepted output**. That case took **458.53 seconds**, with **62,050 input / 661 output tokens**, **six model calls** and **one evidence-reduction round**. It has not been scored for correctness. The following in-flight case was interrupted with incomplete usage. Original records and earlier source snapshots are preserved. The nine-case cohort is incomplete; no Task A F1 or overall readiness is claimed. Task B measurements retain their earlier source identity and remain unchanged. See [the current technical report](track_2a/technical_report.md).

Testing and evaluation are stopped. The local model and UI are stopped, ports **8081** and **8000** have no listener, and the Colima VM is stopped. The final container rebuild and final PDF regeneration remain pending while latency improvements are considered.

The historical V2 evaluation achieved 18/27 correct and macro-F1 0.556, misclassifying all nine neutral cases; a recorded full-booklet number-change case was also wrong despite an exact quote. Those failures remain in the evaluation artifacts and historical V2 PDF. The organizer's authenticated inference proxy and final acceptance remain unverified; `make check-endpoint` provides a real smoke check once credentials are supplied.

A real local API smoke check using the canonical model ID and ordinary JSON-object response mode passed with **514 input tokens, 60 output tokens and 3.152 seconds**. That verifies the generic protocol against the local Apertus server; it is not a test of the organizer's proxy. [Recorded smoke result](track_2a/output/v4-readiness/local-api-protocol-smoke.json).

The official submission deadline is **16 October 2026 at 12:00 CEST**, with an OST report of at most six PDF pages. Sources: [OST API guide](https://hackapertus.notion.site/solution-api-guide-ef5b4fec112a834da43101ede56300f5), [event](https://hackapertus.ch/online-hack), and [submission page](https://hackapertus.ch/online-hack/submissions).

Based on the [official template](https://github.com/HackApertus/project-template/tree/7f2382275461baf3fa6c8855d157d86abffe9f0e). Source code: Apache-2.0; project documentation: CC-BY-4.0. Imported data retains its original attribution and license; see [data provenance](track_2a/data/README.md).
