# ClaimLens — Track 2A / OST, v0.5

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
DOCUMENT_STRATEGY=retrieval
RETRIEVAL_PROMPT_TOKENS=5000
RETRIEVAL_TIMEOUT_SECONDS=120
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
| `DOCUMENT_STRATEGY` | `retrieval` by default for booklets; `exhaustive` explicitly enables the older full-source segmentation mode; Task B always uses full-reference/exhaustive processing |
| `RETRIEVAL_PROMPT_TOKENS` | Final input budget, default 5,000, allowed 1,500–12,000; also bounded by the configured context minus output reserve |
| `RETRIEVAL_TIMEOUT_SECONDS` | Retrieval case budget, default 120 seconds, allowed 1–300; includes source preparation in the CLI |
| `DOCUMENT_TIMEOUT_SECONDS` | Total case-analysis/recovery budget, default 1,800, maximum 3,600 seconds; retrieval uses the smaller deadline |
| `MAX_DOCUMENT_MODEL_CALLS` | Total inference-attempt limit, default 48, allowed 2–128; retrieval additionally caps it at four |

`CONTEXT_TOKENS` must match the actual serving runtime. The local launcher now defaults to 16,384; when changing it, update both the launcher's `LOCAL_MODEL_CONTEXT` and the application's `CONTEXT_TOKENS`.

Runtime environment overrides `.env`, including across endpoint/key aliases. An explicitly empty runtime endpoint does not fall back to a local file or another provider. Remote evaluator URLs ignore the local model alias and receive the official model ID. Keys stay in Python and are never sent to the browser. Transient transport/JSON failures receive bounded retries against the same endpoint. Retrieval booklets receive one pipeline attempt with at most four total transport attempts; a rejected verdict does not restart it. Exhaustive/reference cases can retry a rejected verdict once when usage is known, within the shared case budget. Unknown billed usage prevents an official prediction instead of being replaced by an estimate. There is no provider fallback.

The compact prompt introduced in V0.4 distinguishes missing information from an explicit contradiction about the same entity, time and condition. The model returns only `explanation`, `relation` and `evidence`, explaining its decision before selecting `supported`, `not_enough_information` or `refuted`. Python maps those relations to the official labels 0/1/2, preserves the original claim and creates one whole-claim assessment for the UI. The model need not copy the claim or generate diagnostic dimensions/subchecks. Local decoding constrains the relation and exact quotations; retrieved-mode candidates retain roughly 900 characters of context, with a tiny trailing fragment merged up to 1,200 characters. Independent Python validation still requires valid evidence for entailment and contradiction. This design addresses observed explanation/label disagreements and is assessed through real inference, not presumed to improve accuracy because formatting tests pass.

For ordinary JSON-object endpoints, an evidence string can be converted into a citation only when it appears verbatim in exactly one supplied passage. In retrieved mode, a unique exact anchor within its cited passage may be expanded to the containing original-source context. Python preserves the quoted words, leaves the label unchanged and reports the expansion count in processing metadata and a warning. It never joins across omitted text. Ambiguous text, paraphrases and an explicitly supplied incorrect passage ID are not repaired into valid evidence. Task B and exhaustive quotation behavior remain unchanged. A local canonical-ID/JSON-object protocol smoke passed with 514 input tokens, 60 output tokens and 3,152.339 ms; see [the recorded result](output/v4-readiness/local-api-protocol-smoke.json). This used the local Apertus server, not the organizer's proxy.

## How booklets are handled

1. Extract and retain the supplied PDF pages and original page numbers. Browser imports already cache PDF bytes and extracted text; the CLI caches extraction within a batch.
2. If the complete source fits the default 5,000-token planned input budget, assess it in one Apertus call. Reserve 3,000 final output tokens plus a safety margin within the configured context.
3. For a longer booklet, ask Apertus for concise claim and proposal search phrases in German, French and Italian, with at most 384 output tokens. This also handles missing language metadata. Generated phrases locate evidence; they never become evidence or replace the original claim.
4. Rank exact paragraph-sized spans locally with BM25 and normalized word matching. Proposal terms boost matches, while neighboring passages supply context. Up to 12 candidate units are packed into the final input budget without rewriting their text.
5. Make one final Apertus assessment of the original claim and selected source passages. Python maps the relation to label 0/1/2 and independently validates every quotation against original source text and physical PDF pages.

The local index is built on first search and cached under the operating system's temporary directory (`claimlens-retrieval-v1`). Its key hashes extracted text, provenance metadata and the indexing version, so an OCR/text refresh invalidates it. The cache contains lexical statistics, not predictions or gold labels. Returned evidence always comes from the current supplied document. No web search or answer cache is used during inference.

For the configured local runtime, planning can render the actual chat template and tokenize it through llama.cpp. If those endpoints are unavailable, the conservative UTF-8 byte estimate can select less text than the token budget would permit. Estimates are never reported as actual usage. The UI labels retrieved results **Selected passages**, shows selected page/unit counts, and warns that unselected pages were not examined by the model. Search can miss distributed evidence, qualifications and counter-evidence, especially for neutral decisions.

The default retrieval budget is 120 seconds across preparation, planning, query expansion, search, final assessment and retries, with at most four transport attempts. It does not repeat the whole pipeline or automatically start exhaustive analysis. No matches, malformed queries, invalid quotes, unknown usage or an exhausted budget produce an explicit failure, never a fabricated neutral answer. PDF preparation checks the deadline between pages and limits OCR subprocesses to the remaining time; an in-process PDF parser cannot be forcibly interrupted mid-page.

Set `DOCUMENT_STRATEGY=exhaustive` and restart the application to compare the previous method. It reads every source segment, selects original evidence units and, if necessary, reduces them in at most eight rounds before a joint verdict. Selection can still omit relevant facts. **Task B reference inputs always use the full-reference/exhaustive path**, even when retrieval is the configured booklet default. All model passes and retries contribute to reported tokens and elapsed time; context-only tokens remain `null` because the provider does not report them separately.

## Evaluation and readiness

The V0.5 retrieval implementation has a separate three-case development latency check in `scripts/evaluate_fast.py`. It uses previously exercised ballot dates, one case for each label and the pairs DE→FR, FR→IT and IT→DE. The selected [contextual-quotation run](output/v5-latency-context/summary.json) produced **3/3 correct labels**, no failures, **54.97 seconds mean / 70.63 seconds p95**, and **12,819 input / 1,632 output tokens** total. Each case used two model calls and a cached lexical index; PDF extraction was repeated. Official gold-passage overlap was **0.50 (1/2 non-neutral cases)**, while all three returned quotes independently verified on their actual PDF pages. These same three cases were reused for tuning, so this is not a fresh quality estimate and cannot establish general readiness. The new version has not rerun the full nine-case Task A or 54-case Task B cohorts. See the [evaluation guide](docs/evaluation.md) and [technical report](technical_report.md).

From `track_2a/`, prepare a new directory, then run and score it:

```bash
.venv/bin/python scripts/evaluate_fast.py prepare --directory output/my-v5-latency
.venv/bin/python scripts/evaluate_fast.py run --directory output/my-v5-latency
.venv/bin/python scripts/evaluate_fast.py score --directory output/my-v5-latency
```

The selected version also repeated the previously slow booklet as a [timing-only comparison](output/v5-latency-context/same-case-comparison/results.jsonl): **56.11 seconds versus 458.53 seconds** (8.17× faster), **4,363 versus 62,050 input tokens** (92.97% fewer), and two versus six calls. It used the same model/hardware, a warm index and a smaller runtime cache (1,024 versus 8,192 MiB). This one unscored case measures the combined setup change and cannot establish quality or isolate retrieval's effect.

The earlier 39.15-second run in `output/v5-latency/` is preserved: its labels were correct but its two exact quotations were an attribution-only footer and a broken hyphenated line. The chosen version returns fuller context. See [the development history](docs/evaluation.md#development-history) for the repeated experiments.

Run evaluation separately from browser checks on the single local model. Preserve old artifacts; changed source/model/input identities cannot resume an older run. The runner retains failures and exports only validated predictions, with source/run hashes, measured usage, latency and selected-page coverage.

Historical **V0.4** observations remain available:

- The [27-case development run](output/v4-readiness/development/summary.json) achieved **25/27 correct**, **macro-F1 0.927451**, with all nine neutral cases correct and no failed predictions. Mean time was **17.8 seconds**, p95 **30.7 seconds**. This was a tuning cohort.
- The [combined Task B cohorts](output/v4-readiness/final-b-combined/summary.json) achieved **50/54 correct**, **macro-F1 0.924722**, with 54 accepted predictions and no failures. Independent audits verified all **34 returned quotations**. Mean time was **15.85 seconds**, p95 **27.74 seconds**. These measurements retain their original source identity and are not a V0.5 rerun.
- The V0.4 exhaustive Task A run was stopped for latency redesign after one accepted, unscored output: **458.53 seconds**, **62,050 input / 661 output tokens**, **six calls** and **one reduction round**. The following case was interrupted with incomplete usage. The nine-case cohort remains incomplete; no Task A F1 is claimed.

These small public-data cohorts are separate from the organizers' private benchmark. Historical failures and source snapshots remain preserved. Container software checks passed; reviewed report regeneration and authenticated organizer-endpoint verification remain separate tasks.

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

The current Markdown report is [technical_report.md](technical_report.md). Build its PDF with:

```bash
.venv/bin/python -m pip install -r requirements-report.txt
make report
```

`make report` uses `scripts/build_submission_report.py` and writes `output/pdf/claimlens-v5-report.pdf`, with a source/PDF hash manifest. The builder enforces the six-page limit. The report identifies **OneLegedCoder - Xavier**. Earlier V0.4/V2 PDFs are historical artifacts. Regenerate the V0.5 PDF from the selected implementation's measurements and inspect its pages before submission. Rebuild it after those results are recorded and inspect every rendered page before submission. See [report reproduction](docs/evaluation.md#build-and-review-the-report). Report generation makes no model calls.

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

The selected V0.5 source passed **233 Python tests locally and 233 tests inside the `linux/amd64` submission image**, using a read-only filesystem, no network and temporary writable storage. The frontend smoke check also passed. Coverage includes both minimal and annotated task inputs, nine language pairs, exact quotation provenance, page numbering, imports, upload/URL boundaries, multilingual OCR, retrieval/cache behavior, full-reference routing, exhaustive long-source coverage, bounded evidence reduction, retries, partial batch preservation, call/deadline limits and token aggregation. Test inference is stubbed; these checks establish software behavior rather than Apertus accuracy.

Limits include 256-character case IDs, 2,000 claim/vote characters, 300,000 total source characters per check, 25 MB per PDF and 200 physical PDF pages. These are implementation limits, not confirmed organizer maxima. A library import can retain more text than the inference cap; attempting to check that document still fails explicitly. OCR is bounded separately. The model-status check confirms catalog availability, not prediction quality. The organizer's authenticated inference proxy and final submission acceptance remain unverified; current local performance belongs in the technical report.
