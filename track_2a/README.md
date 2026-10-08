# ClaimLens — Track 2A / OST, V2

ClaimLens checks a claim against a Swiss voting booklet and returns **0 entailment, 1 neutral, or 2 contradiction**, with exact source quotations and original PDF page references. German, French and Italian claims and booklets can be combined independently. The browser supports booklet selection/import; the CLI follows the official task A/PDF and task B/reference contract.

The current local model is a Q4_K_M text conversion of **`swiss-ai/Apertus-v1.5-8B`**. A remote endpoint can also offer `swiss-ai/Apertus-v1.5-70B`. The local selector shows only the installed model. See the preserved [template instructions](docs/upstream-track-2a.md), [challenge requirements](docs/event-requirements.md) and [solution API contract](docs/solution-api.md).

## Start locally

The dataset, model and booklet library are already downloaded on this Mac. Start these in separate terminals from this directory or the repository root:

```bash
make model-serve
```

```bash
make dev
```

Open **http://localhost:8000**. Check the model status, select **Voting booklets**, choose a language/date and enter the specific proposal being checked. A booklet can cover several proposals. Select the claim language, write a claim and choose **Live Apertus**. Results retain original source-language quotations and link to the cached PDF pages.

The library contains 60 official PDFs, 20 per source language. **Add a voting booklet** accepts a direct HTTPS PDF URL on `bk.admin.ch`/`www.bk.admin.ch` or an uploaded PDF. Imports save local copies, validate PDF limits and extract pages; they do not run inference. Existing cached source URLs are reused. This is a document importer, not open-ended web browsing by the model.

**Guided walkthrough → Demo** gives an immediate offline presentation using four prewritten claims against one real French reference. It makes no model calls and accepts only the stored claims. One example preserves an OST label; three are locally authored. Reference evidence has no PDF page number. `make demo` writes those examples to `output/demo-predictions.jsonl`. See the [three-minute presentation guide](docs/presentation-walkthrough.md).

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

PDF pages with little extractable text receive a bounded OCR attempt: at most 20 pages and 180 seconds per extraction. Unreadable pages and OCR usage remain visible as warnings. Page references always use physical, 1-based PDF page positions, including blank pages. OCR transcription is approximate; open the original PDF to inspect the evidence. The Docker images already install Poppler, Tesseract and the three language packs.

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

| Setting | Purpose |
| --- | --- |
| `LLM_NAME` | Official Apertus v1.5 8B or 70B model ID |
| `BASE_URL`, `API_KEY` | Official runtime endpoint/key; evaluator values take precedence |
| `LLM_BASE_URL`, `LLM_API_KEY` | Generic template-compatible aliases |
| `LOCAL_MODEL_ID` | Optional served alias, enabled only on recognized local hostnames |
| `LLM_TIMEOUT_SECONDS` | Per-inference-request timeout; default 120, allowed 1–600 seconds; local file uses 300 |
| `CONTEXT_TOKENS` | Total prompt/output context; default 8,192, allowed 4,096–262,144; local file uses 16,384 |
| `DOCUMENT_TIMEOUT_SECONDS` | Total model-analysis budget, including context planning; default 1,800, maximum 3,600 seconds |
| `MAX_DOCUMENT_MODEL_CALLS` | Extraction plus final inference-call limit; default 48, allowed 2–128 |

`CONTEXT_TOKENS` must match the actual serving runtime. The local launcher now defaults to 16,384; when changing it, update both the launcher's `LOCAL_MODEL_CONTEXT` and the application's `CONTEXT_TOKENS`.

Runtime environment overrides `.env`, including across endpoint/key aliases. An explicitly empty runtime endpoint does not fall back to a local file or another provider. Remote evaluator URLs ignore the local model alias and receive the official model ID. Keys stay in Python and are never sent to the browser. There is no automatic model retry or provider fallback.

## How long documents are handled

1. Extract and retain every supplied source page with its original page number. Reference-only cases use only the supplied reference.
2. If the complete source and reserved output fit the context, assess the claim in one model call.
3. Otherwise partition the entire source into contiguous units. Every segment is examined by Apertus for supporting, opposing, conditional and partial evidence. The model selects unit IDs; Python reconstructs exact excerpts from the original pages.
4. Assess the full claim once against all selected excerpts together. Labels from individual chunks are never voted or aggregated.
5. Independently validate the claim highlights, labels and every cited quotation against the original source. The first whole-claim assessment supplies the final classification.

For the configured local runtime, planning can render the actual chat template and tokenize it through llama.cpp. A conservative UTF-8 byte estimate is used when a tokenizer is unavailable, and for requests that clearly fit. Remote evaluation uses only the configured inference endpoint's chat-completions API. Planning estimates are never reported as actual usage.

The final inference pass reserves up to 3,000 output tokens; extraction passes reserve 1,600. Total provider-reported input/output tokens include every model pass. The UI reports full-source/hierarchical strategy, source coverage, segment count, model-call count and elapsed analysis time. Context-only tokens remain `null` because the provider does not report them separately.

Examining every segment is not a guarantee of selecting every relevant fact. Missing facts, OCR errors or mistaken interpretation can still affect classification. Invalid/incomplete extraction, too many required calls, a timeout or evidence that cannot fit the final context produces an explicit error. Sources are never silently truncated to manufacture a verdict.

## Development evaluation

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

Current observations belong in [technical_report.md](technical_report.md); test counts alone are not evidence of model accuracy.

The presentation PDF is `output/pdf/claimlens-v2-report.pdf`. To regenerate it from the completed local evaluation, baseline comparison and smoke-test artifacts:

```bash
.venv/bin/python -m pip install -r requirements-report.txt
make report
```

The detailed Markdown report and the shorter generated PDF cover the same recorded version. Report generation does not run inference. Its required measurement files are local outputs; they must exist before building the PDF.

## Official CLI and Docker

The CLI accepts UTF-8 JSONL with both task types in one file:

```json
{"id":"case-B","vote":"Example proposal","claim":{"text":"Die Regel gilt ab 2028.","language":"de"},"reference":{"text":"La règle s’applique à partir de 2028.","language":"fr"}}
{"id":"case-A","vote":"Exact proposal name","claim":{"text":"La règle s’applique en 2028.","language":"fr"},"booklet":{"path":"booklets/example.pdf","language":"it"}}
```

These illustrate the schema; they are not official voting material. Each case needs exactly one source. The CLI never imports unrelated online material. PDF paths stay inside the input directory, or an explicitly supplied `--data-root` (`/data` in evaluation).

```bash
PYTHONPATH=src .venv/bin/python -m claimlens \
  --input /path/to/cases.jsonl --output output/predictions.jsonl
```

The template's Docker workflow is:

```bash
make run         # Interactive demo image, persistent local booklet-library mount
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

Keep gold labels outside the mounted input directory. The default Docker build is also the submission target; it excludes `.env`, the full dataset and stored demo judgments.

Each output contains `id`, integer `label`, matching `label_name`, `evidence: [{page, text}]`, and `metrics: {input_tokens, output_tokens, inference_time_ms}`. Case time includes parsing, all model passes and validation; shared PDF extraction is cached within a batch. Invalid model output/citations, provider failures or missing usage cause a nonzero CLI exit, and an existing output file is preserved until the entire batch succeeds.

## Validation and current limits

```bash
make test
```

Tests cover nine language pairs, both task types, exact quotation provenance, page numbering, imports, upload/URL boundaries, OCR behavior, configuration, long-source coverage, cross-segment evidence, call/timeout limits and token aggregation. Test inference is stubbed; these checks establish software behavior rather than Apertus accuracy.

Limits include 2,000 claim characters, 300,000 total source characters per check, 25 MB per PDF and 200 physical PDF pages. A library import can retain more text than the inference cap; attempting to check that document still fails explicitly. OCR is bounded separately. The model-status check confirms catalog availability, not prediction quality. The organizer's inference proxy and a larger independent quality evaluation remain follow-up work.
