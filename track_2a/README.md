# ClaimLens — Track 2A / OST, v0.4

ClaimLens checks a claim against a Swiss voting booklet and returns **0 entailment, 1 neutral, or 2 contradiction**, with exact source quotations and original PDF page references. German, French and Italian claims and booklets can be combined independently. The browser supports booklet selection/import; the CLI accepts the presentation's minimal inputs and the fuller task A/PDF and task B/reference API examples.

The current local model is a Q4_K_M text conversion of **`swiss-ai/Apertus-v1.5-8B`**. A remote endpoint can also offer `swiss-ai/Apertus-v1.5-70B`. The browser uses the configured local model only; the official CLI retains remote organizer-endpoint support. See the preserved [template instructions](docs/upstream-track-2a.md), [challenge requirements](docs/event-requirements.md) and [solution API contract](docs/solution-api.md).

## Start locally

The dataset, model and booklet library are already downloaded on this Mac. Start these in separate terminals from this directory or the repository root:

```bash
make model-serve
```

```bash
make dev
```

Open **http://localhost:8000**. Search the library by date or title and filter by booklet language. Select a booklet, enter its proposal name, choose the claim language and write the claim. **Check claim** makes a real local Apertus call. Results link quoted evidence to cached PDF pages and show actual time/token usage.

The browser checks model availability first. When Apertus is offline or its status is unknown, claim checking is disabled; importing and browsing booklets remain available. Start `make model-serve` and select **Refresh model status**. No demo mode, bundled example selector or prewritten result is available. The browser API also rejects legacy demo requests and nonlocal model configuration. The CLI continues to support the organizer's remote endpoint for official evaluation.

The library contains 60 official PDFs, 20 per source language. **Add a booklet** accepts a direct HTTPS PDF URL on `bk.admin.ch`/`www.bk.admin.ch` or an uploaded PDF. Imports cache original documents and page text without running inference. Scans can use bounded local OCR. The [presentation guide](docs/presentation-walkthrough.md) describes the current live-only interface.

`PORT=8001 make dev` changes the UI port. The model runtime and UI are separate processes; changing configuration requires restarting the relevant process.

## First-time data and OCR setup

Python 3.9+ is supported. From `track_2a/`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-data.txt
make dataset
make booklets
```

`make dataset` downloads the pinned 1,488-row OST snapshot and exports unlabeled prediction inputs separately from gold labels. It preserves an existing snapshot. `make booklets` imports the unique official URL/language pairs from that snapshot into `data/local/library/`; re-running it resumes using cached PDFs. The import manifest records successful and failed imports. This requires internet access only while fetching uncached sources. See [data/README.md](data/README.md) for snapshot provenance and paths.

Install optional OCR tools on macOS:

```bash
brew install poppler tesseract
make ocr-setup
```

The setup script downloads checksum-pinned German, French and Italian language files into the repository's `.cache/tessdata/`; OCR detects them automatically. To re-extract existing cached PDFs after enabling OCR:

```bash
.venv/bin/python scripts/import_booklets.py --refresh
```

PDF pages with little extractable text receive a bounded OCR attempt: at most 20 pages and 180 seconds per extraction. When CLI language metadata is omitted, OCR uses German, French and Italian together. Unreadable pages, missing language data and OCR usage remain visible as warnings. Page references always use physical, 1-based PDF page positions, including blank pages. OCR transcription is approximate; open the original PDF to inspect the evidence. The Docker images already install Poppler, Tesseract and the three language packs.

## Model configuration

The local `.env` uses:

```dotenv
LLM_NAME=swiss-ai/Apertus-v1.5-8B
BASE_URL=http://127.0.0.1:8081/v1
API_KEY=
LOCAL_MODEL_ID=claimlens-apertus-v1.5-8b-q4
LLM_TIMEOUT_SECONDS=300
CONTEXT_TOKENS=16384
DOCUMENT_TIMEOUT_SECONDS=1800
MAX_DOCUMENT_MODEL_CALLS=48
```

No inference key or Hugging Face login is needed for the downloaded public GGUF. llama.cpp runs on this Mac with Apple Metal; the 5.06 GB artifact is a community text conversion and quantization of Apertus 1.5 8B. See [local-model.md](docs/local-model.md) for pinned provenance and installation.

For a fresh remote setup, copy `.env.example` to `.env`; on this configured Mac, edit the existing file. Set the supplied endpoint/key, remove `LOCAL_MODEL_ID`, and set the context limit to the provider's supported window. The organizer documents `https://api.inference.cscs.ch/v1` for CSCS development access. The official evaluator injects its proxy through `BASE_URL` and `API_KEY`. Remote access remains unverified without organizer credentials.

Run `make check-endpoint` after configuring or starting an endpoint. It sends one temporary German-reference/French-claim request through the production CLI and reports the canonical model, classification, provider token counts and elapsed time. Exit `0` establishes a valid response; `matches_synthetic_example` reports whether its simple classification was correct. This real request consumes inference tokens and is not an accuracy benchmark. See [organizer endpoint instructions](docs/solution-api.md#check-an-organizer-endpoint).

| Setting | Purpose |
| --- | --- |
| `LLM_NAME` | Official Apertus v1.5 8B or 70B model ID |
| `BASE_URL`, `API_KEY` | Official runtime endpoint/key; evaluator values take precedence |
| `LLM_BASE_URL`, `LLM_API_KEY` | Generic template-compatible aliases |
| `LOCAL_MODEL_ID` | Optional served alias, enabled only on recognized local hostnames |
| `LLM_TIMEOUT_SECONDS` | Shared timeout for one request and its bounded transport retries; default 120, allowed 1–600 seconds; local file uses 300 |
| `CONTEXT_TOKENS` | Total prompt/output context; default 8,192, allowed 4,096–262,144; local file uses 16,384 |
| `DOCUMENT_TIMEOUT_SECONDS` | Total case-analysis/recovery budget, including context planning; default 1,800, maximum 3,600 seconds |
| `MAX_DOCUMENT_MODEL_CALLS` | Extraction, evidence reduction, final inference and transport-retry call limit; default 48, allowed 2–128 |

`CONTEXT_TOKENS` must match the actual serving runtime. The local launcher now defaults to 16,384; when changing it, update both the launcher's `LOCAL_MODEL_CONTEXT` and the application's `CONTEXT_TOKENS`.

Runtime environment overrides `.env`, including across endpoint/key aliases. An explicitly empty runtime endpoint does not fall back to a local file or another provider. Remote evaluator URLs ignore the local model alias and receive the official model ID. Keys stay in Python and are never sent to the browser. Transient transport/JSON failures receive bounded retries against the same endpoint. The CLI can retry a rejected model verdict once when usage is known; all attempts share the case budget. Unknown billed usage prevents an official prediction instead of being replaced by an estimate. There is no provider fallback.

The V0.4 prompt distinguishes missing information from an explicit contradiction about the same entity, time and condition. The model returns only `explanation`, `relation` and `evidence`, explaining its decision before selecting `supported`, `not_enough_information` or `refuted`. Python maps those relations to the official labels 0/1/2, preserves the original claim and creates one whole-claim assessment for the UI. The model need not copy the claim or generate diagnostic dimensions/subchecks. Local decoding constrains the relation and exact quotations; independent Python validation still requires valid evidence for entailment and contradiction. This design addresses observed explanation/label disagreements and is assessed through real inference, not presumed to improve accuracy because formatting tests pass.

For ordinary JSON-object endpoints, an evidence string can be converted into a citation only when it appears verbatim in exactly one supplied passage. Ambiguous text, paraphrases and an explicitly supplied incorrect passage ID are not repaired into valid evidence. A local canonical-ID/JSON-object protocol smoke passed with 514 input tokens, 60 output tokens and 3,152.339 ms; see [the recorded result](output/v4-readiness/local-api-protocol-smoke.json). This used the local Apertus server, not the organizer's proxy.

## How long documents are handled

1. Extract and retain every supplied source page with its original page number. Reference-only cases use only the supplied reference.
2. If the complete source and reserved output fit the context, assess the claim in one model call.
3. Otherwise partition the entire source into contiguous units. Every segment is examined by Apertus for supporting, opposing, conditional and partial evidence. The model selects unit IDs; Python reconstructs exact excerpts from the original pages.
4. If the selected excerpts exceed the final context, Apertus ranks the original selected units in bounded windows. Every candidate is examined in each round; at most eight rounds retain fewer units until the evidence fits. IDs, page numbers and verbatim text are preserved. Reduction can omit relevant evidence, and its coverage warning remains visible.
5. Assess the full claim against all retained excerpts together. Labels from individual chunks are never voted or aggregated.
6. Map the model's source relation to the official label, retain the submitted claim unchanged and independently validate every cited quotation against the original source. One whole-claim assessment supplies the final classification and UI finding.

For the configured local runtime, planning can render the actual chat template and tokenize it through llama.cpp. A conservative UTF-8 byte estimate is used when a tokenizer is unavailable, and for requests that clearly fit. Remote evaluation uses only the configured inference endpoint's chat-completions API. Planning estimates are never reported as actual usage.

The final inference pass reserves up to 3,000 output tokens; extraction and reduction passes reserve 1,600. Total provider-reported input/output tokens and elapsed time include all extraction, reduction, final and retry calls. The UI reports full-source/hierarchical strategy, source coverage, segment count, model-call count and elapsed analysis time. Detailed processing records include reduction rounds and candidate counts. Context-only tokens remain `null` because the provider does not report them separately.

Examining every segment is not a guarantee of retaining every relevant fact. Missing evidence during selection/reduction, OCR errors or mistaken interpretation can still affect classification. Invalid/incomplete extraction, too many required calls, a timeout or evidence that still cannot fit after bounded reduction produces an explicit error. Fixed capacity failures are not retried as a full analysis. The original source is examined before reduction, and the loss of candidate evidence is disclosed.

## Evaluation and readiness

Use the [readiness evaluation guide](docs/evaluation.md) for V0.4. `scripts/evaluate_readiness.py` freezes a development cohort and separate final Task A/B cohorts by ballot publication date, keeps inputs apart from gold labels, records source/model/run identities and scores predictions with the official evaluator. These are small, public-data local holdouts, not the organizers' private benchmark. All nine language pairs are represented. Task B is complete. The Task A rerun was intentionally stopped at the user's request for latency redesign after **one of nine cases produced an accepted output**, without scoring that output. The cohort is incomplete, so no Task A F1 or overall readiness is claimed. See [technical_report.md](technical_report.md).

The completed booklet case took **458,532.384 ms (458.53 seconds)**, with **62,050 input / 661 output tokens**, **six model calls** and **one reduction round**. The following in-flight case was interrupted with incomplete usage; all original records are preserved. Testing and evaluation are stopped. The local model, UI and Colima VM are stopped, with no listener on ports 8081 or 8000. The final image rebuild and PDF regeneration remain pending.

The two predetermined Task B cohorts together achieved **50/54 correct**, **macro-F1 0.924722**, **54 accepted predictions and no failures**. An independent audit verified all **34 returned exact quotations** against their supplied references. Mean case time was **15.85 seconds**, p95 **27.74 seconds**. The [combined score](output/v4-readiness/final-b-combined/summary.json) recomputes metrics across all original predictions rather than averaging cohort F1 scores. Task B retains its recorded source identity from before the long-document fix; its short-source inference path is unchanged. This does not establish current Task A or private-benchmark performance.

The completed [V0.4 development run](output/v4-readiness/development/summary.json) produced 27 valid predictions with no failures: **25/27 correct**, **macro-F1 0.927451**, and all **9/9 neutral cases correct**. Mean case time was **17.8 seconds** and p95 **30.7 seconds**. The official scorer reported no format issues. This development cohort was available for tuning, so its score does not establish final-cohort or private-benchmark performance.

From `track_2a/`, after the frozen cohorts have been prepared:

```bash
.venv/bin/python scripts/evaluate_readiness.py run --directory output/v4-readiness/development --resume
.venv/bin/python scripts/evaluate_readiness.py score --directory output/v4-readiness/development
```

Follow the guide to prepare a fresh run, freeze the implementation before final-cohort inference, and score Task A/B separately. A changed source/model/input identity cannot silently resume an older run. Run evaluation separately from browser checks on the single local model.

### Historical development workflow

The following legacy shortcuts default to `output/v2-evaluation/`; that directory contains preserved V2 measurements and should not be overwritten:

```bash
make evaluate-prepare
make evaluate
```

Preparation deterministically selects 27 distinct task B requests: one per source/claim-language combination and label. Gold labels are used for stratified selection and scoring, never sent to the model. This is a development sample of the published training split, not a held-out or official benchmark. Run evaluation separately from live UI inference on the single local model.

Files are written to `output/v2-evaluation/`:

| File | Contents |
| --- | --- |
| `input.jsonl`, `gold.jsonl` | Separate selected requests and targets |
| `selection.json` | Fixed selection seed, size and sampling method |
| `results.jsonl` | Per-case accepted predictions or explicit failures |
| `results.run.json` | Code/model/input identity used to prevent mixed runs |
| `summary.json` | Accuracy, macro F1, per-language-pair counts, confusion matrix, speed and recorded token usage |

Failures count against accuracy/F1 and are not replaced with neutral predictions. Exact quote presence is checked, but citation relevance and the official task A evidence-overlap score are not measured. Token totals cover calls whose usage was successfully returned.

`make evaluate` resumes the same unchanged run. To evaluate changed code or a larger sample, choose a fresh directory:

```bash
.venv/bin/python scripts/evaluate_local.py prepare --directory output/next-evaluation --per-stratum 2
.venv/bin/python scripts/evaluate_local.py run --directory output/next-evaluation --resume
```

The historical V2 run achieved 18/27 correct and macro-F1 0.556, with all nine neutral examples misclassified. Its recorded full-booklet number-change check also produced an incorrect verdict despite a verified exact quote. Current observations belong in [technical_report.md](technical_report.md); test counts alone are not evidence of model accuracy.

### Build the reports

The current Markdown report is [technical_report.md](technical_report.md). Build its V0.4 PDF with:

```bash
.venv/bin/python -m pip install -r requirements-report.txt
make report
```

`make report` uses `scripts/build_submission_report.py` and writes `output/pdf/claimlens-v4-report.pdf`, with a source/PDF hash manifest. The builder enforces the six-page limit. The report identifies **OneLegedCoder - Xavier**. Its existing PDF is an earlier draft and has not been rebuilt after the intentional evaluation stop; final measurements, image checks and PDF regeneration remain pending. Rebuild it after those results are recorded and inspect every rendered page before submission. See [report reproduction](docs/evaluation.md#build-and-review-the-report). Report generation makes no model calls.

The historical V2 presentation PDF remains at `output/pdf/claimlens-v2-report.pdf`. It describes the earlier interface and its recorded model-quality failures; the current application has no walkthrough mode. Regenerate it explicitly with `make report-v2`, which uses `scripts/build_report.py` and requires the preserved V2 evaluation, baseline and smoke-test artifacts. This historical report must not be relabeled as a current result.

## Official CLI and Docker

The CLI accepts UTF-8 JSONL with both task types in one file:

```json
{"id":"case-B","vote":"Example proposal","claim":{"text":"Die Regel gilt ab 2028.","language":"de"},"reference":{"text":"La règle s’applique à partir de 2028.","language":"fr"}}
{"id":"case-A","vote":"Exact proposal name","claim":{"text":"La règle s’applique en 2028.","language":"fr"},"booklet":{"path":"booklets/example.pdf","language":"it"}}
```

These illustrate the schema; they are not official voting material. Each case needs exactly one source. The CLI never imports unrelated online material. PDF paths stay inside the input directory, or an explicitly supplied `--data-root` (`/data` in evaluation).

Language fields may be omitted independently; Apertus reads the original text without guessing language from filenames. Task B also accepts an omitted `vote`. A supplied language must still be `de`, `fr`, or `it`, and Task A still requires its proposal name. These minimal forms are accepted too:

```json
{"id":"minimal-B","claim":{"text":"Die Regel gilt ab 2028."},"reference":{"text":"La règle s’applique à partir de 2028."}}
{"id":"minimal-A","vote":"Exact proposal name","claim":{"text":"La règle s’applique en 2028."},"booklet":{"path":"booklets/example.pdf"}}
```

```bash
PYTHONPATH=src .venv/bin/python -m claimlens \
  --input /path/to/cases.jsonl --output output/predictions.jsonl
```

The template's Docker workflow is:

```bash
make run         # Local browser image, persistent local booklet-library mount
make submission  # Separate claimlens:submission prediction image
```

Both use `linux/amd64`. On this Mac Docker runs through the separate Colima `claimlens` profile; the initial image build has been verified. Consult the technical report for completed runtime checks. The model still runs separately on the host or at a remote endpoint. An API URL using `127.0.0.1` inside a container points to that container: configure an address reachable from the container for live inference. CPU PDF/OCR tooling is included; no model weights or runtime model downloads are in the image.

For the configured Colima profile and host model, use:

```bash
make DOCKER='docker --context colima-claimlens' verify-submission
BASE_URL=http://host.docker.internal:8081/v1 PORT=8002 \
  make DOCKER='docker --context colima-claimlens' run
```

The profile must be running (`colima start claimlens`). Its separate Docker context does not replace your default context. The second command opens the container UI at http://localhost:8002 and retains the existing local model alias from `.env`. The native UI remains the usual presentation path at port 8000.

After preparing an input directory, output directory and evaluator endpoint/key:

```bash
make submission
docker run --rm --platform linux/amd64 \
  -e BASE_URL -e API_KEY -e LLM_NAME -e CONTEXT_TOKENS \
  -v "$PWD/data/input:/data:ro" -v "$PWD/output:/output" \
  claimlens:submission --input /data/cases.jsonl --output /output/predictions.jsonl
```

Keep gold labels outside the mounted input directory. The default Docker build is also the submission target; it excludes `.env`, the full dataset and precomputed predictions.

Each output contains `id`, integer `label`, matching `label_name`, `evidence: [{page, text}]`, and `metrics: {input_tokens, output_tokens, inference_time_ms}`. Case time includes parsing, all model passes, retries and validation; shared PDF extraction is cached within a batch. An unresolved model/validation/provider failure or missing usage causes a nonzero CLI exit, while later cases are still processed. Successful cases are saved atomically to `predictions.jsonl.partial.jsonl`; an existing complete output is preserved until the entire batch succeeds. The partial file is a recovery artifact, not a complete submission.

## Validation and current limits

```bash
make test
```

The latest completed suite passed **181 tests**, and the frontend interaction checks passed. Coverage includes both minimal and annotated task inputs, nine language pairs, exact quotation provenance, page numbering, imports, upload/URL boundaries, multilingual OCR, configuration, long-source coverage, cross-segment evidence, bounded evidence reduction, retries, partial batch preservation, call/timeout limits and token aggregation. Test inference is stubbed; these checks establish software behavior rather than Apertus accuracy.

Limits include 256-character case IDs, 2,000 claim/vote characters, 300,000 total source characters per check, 25 MB per PDF and 200 physical PDF pages. These are implementation limits, not confirmed organizer maxima. A library import can retain more text than the inference cap; attempting to check that document still fails explicitly. OCR is bounded separately. The model-status check confirms catalog availability, not prediction quality. The organizer's authenticated inference proxy and final submission acceptance remain unverified; current local performance belongs in the technical report.
