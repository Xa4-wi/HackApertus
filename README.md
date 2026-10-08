# ClaimLens

Check multilingual claims against Swiss voting booklets and follow the evidence back to the original PDF. **Version 2** is a local Python application for **Hack Apertus Track 2A — OST: Multilingual Natural Language Inference over Swiss Official Voting Booklets**.

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

Open **http://localhost:8000**. The model status shows whether the selected runtime is reachable. Choose **Voting booklets**, select the document and proposal, then choose **Live Apertus** and examine a claim. For an immediate offline explanation, select **Guided walkthrough** and **Demo**; those four answers are clearly labeled as prewritten examples.

This Mac uses llama.cpp with Apple Metal and a downloaded **5.06 GB Q4_K_M text conversion** of Apertus v1.5 8B. The API is `http://127.0.0.1:8081/v1`; no key is needed. Local configuration is in the ignored `track_2a/.env`. See [local model setup](track_2a/docs/local-model.md) and the [three-minute presentation walkthrough](track_2a/docs/presentation-walkthrough.md).

## What changed in V2

- **Booklet library:** Downloads the official PDFs referenced by the OST snapshot, caches their original bytes and extracted pages, and keeps source URL, language, content hash and proposal names. Imports do not call the model.
- **Long documents:** Reads every supplied source segment, selects relevant exact excerpts and jointly assesses the claim across those excerpts. Smaller inputs use one model call. The UI explains which strategy ran.
- **Scanned pages:** Uses local Poppler and Tesseract for bounded OCR when a PDF has little extractable text. OCR and unreadable-page warnings remain visible.
- **Evaluation:** A repeatable development evaluation covers all nine language pairs and three labels, records failures, and reports accuracy, macro F1, usage and speed.
- **Submission path:** Retains the official JSONL CLI and separate `linux/amd64` prediction image. The image contains application code and PDF/OCR tools; models, the downloaded dataset and gold labels stay outside it.

The 1,488-row OST dataset is also saved locally, with prediction inputs and gold labels separated. Downloading this dataset did **not** train the model. See [data setup](track_2a/data/README.md).

## Useful commands

| Command | Purpose |
| --- | --- |
| `make dev` | Start the browser application on port 8000 |
| `make model-serve` | Start the downloaded local model |
| `make booklets` | Import/cache the official PDFs from the local OST snapshot |
| `make ocr-setup` | Download and verify the three OCR language files |
| `make demo` | Produce stored walkthrough predictions without inference |
| `make evaluate-prepare` | Prepare 27 distinct development cases, one per language-pair/label combination |
| `make evaluate` | Run/resume local inference and write `track_2a/output/v2-evaluation/summary.json` |
| `make test` | Run unit and integration checks |
| `make test-ui` | Check frontend interactions and API contracts |
| `make run` | Build and start the interactive Docker image |
| `make submission` | Build the separate official prediction image |
| `make verify-submission` | Build and test Task A/B in the isolated submission container |
| `make report` | Regenerate the PDF from recorded evaluation and verification artifacts |

The library and dataset are already populated on this Mac. First-time setup and OCR prerequisites are described in [the Track 2A guide](track_2a/README.md). Evaluation makes real model calls; run it separately from a live presentation. Existing evaluation files are preserved, and resuming after code/model/input changes requires a new evaluation directory.

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
    │   ├── models.py / corpus.py   Shared labels and walkthrough data
    │   ├── server.py               Browser API
    │   └── static/                 HTML, CSS and JavaScript interface
    ├── scripts/                    Model/data/import/OCR/evaluation commands
    ├── data/                       Walkthrough plus ignored local dataset/library
    ├── output/                     Ignored predictions and evaluation records
    ├── tests/                      Unit and integration checks
    └── docs/                       Setup, presentation and event requirements
```

## What the results mean

The labels are **0 entailment**, **1 neutral**, and **2 contradiction**, relative to the supplied source. Exact quotations establish provenance; they do not independently prove the model's interpretation. Reading every segment does not guarantee that evidence selection finds every relevant fact. OCR may introduce transcription errors. Context, time and call limits fail explicitly rather than silently dropping source text.

Software tests verify behavior, not model accuracy. The development evaluation uses a small stratified sample of the published training split; it is not a held-out or official benchmark. The organizer's remote inference proxy still needs validation with organizer credentials. For current measured results and container checks, see [the technical report](track_2a/technical_report.md).

The official submission deadline is **16 October 2026 at 12:00 CEST**, with an OST report of at most six PDF pages. Sources: [OST API guide](https://hackapertus.notion.site/solution-api-guide-ef5b4fec112a834da43101ede56300f5), [event](https://hackapertus.ch/online-hack), and [submission page](https://hackapertus.ch/online-hack/submissions).

Based on the [official template](https://github.com/HackApertus/project-template/tree/7f2382275461baf3fa6c8855d157d86abffe9f0e). Source code: Apache-2.0; project documentation: CC-BY-4.0. Imported data retains its original attribution and license; see [data provenance](track_2a/data/README.md).
