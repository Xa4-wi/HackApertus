# ClaimLens — Track 2A / OST

ClaimLens assesses a claim against a Swiss voting booklet or supplied reference and returns **0 entailment, 1 neutral, or 2 contradiction**, with exact source quotations and physical PDF page references. German, French and Italian sources and claims can be combined independently. The local browser provides a booklet library and evidence review; the CLI is the evaluation interface.

This is the active project directory from the Hack Apertus template. The final technical report is directly available as [Markdown](technical_report.md) and [PDF](technical_report.pdf). Current measurements live in [validation.md](docs/validation.md), operational checks in [evaluation.md](docs/evaluation.md), and development history in the workspace's root `VERSION_HISTORY.md`. Historical outputs and the original template README are preserved under the workspace's `archive/`; they are not runtime dependencies or final delivery contents.

## Start locally

The model, dataset and booklet library are already downloaded on the configured Mac. Run these in separate terminals from this directory or the repository root:

```bash
make model-serve
```

```bash
make dev
```

Open **http://localhost:8000**. Search the library by date/title and source language, choose a booklet, name its proposal, enter a claim and select **Check claim**. Every check calls local Apertus. Claim checking is disabled when model availability is unknown or offline; browsing and importing remain available. **Refresh model status** checks after startup. Stop both terminals with `Ctrl+C` when finished.

The cached library contains 60 official PDFs, 20 per language. **Add a booklet** accepts an uploaded PDF or a direct HTTPS PDF URL on `bk.admin.ch`/`www.bk.admin.ch`. Imports retain original bytes and extracted pages without inference. The [presentation walkthrough](docs/presentation-walkthrough.md) explains the live interface, and the [120-second video script](docs/video-script.md) provides the recording sequence and narration. `PORT=8001 make dev` changes the UI port; configuration changes require restarting the relevant process.

## First-time setup

Python 3.9+ is supported. From `track_2a/`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
make dataset
make booklets
```

There are two dependency files: `requirements.txt` installs the application runtime used by Docker, and `requirements-dev.txt` includes that runtime plus local data preparation, evaluation and PDF report tools. Use `requirements-dev.txt` for the full local setup above.

`make dataset` downloads the pinned 1,488-row OST snapshot, preserving an existing copy. Unlabeled prediction inputs and gold labels are exported separately. `make booklets` imports official URL/language pairs into `data/local/library/` and resumes from cached PDFs. Internet access is needed for uncached downloads. See [data/README.md](data/README.md) for provenance; downloading the dataset does not train the model.

For optional OCR on macOS:

```bash
brew install poppler tesseract
make ocr-setup
.venv/bin/python scripts/import_booklets.py --refresh
```

The refresh command re-extracts cached PDFs after OCR setup. OCR attempts at most 20 scant-text pages and 180 seconds per extraction, subject to a shorter active case deadline. Without language metadata it uses German, French and Italian together. Page references always preserve 1-based physical PDF positions, including blank pages. Review OCR warnings and the original PDF because transcription can be inaccurate. Both Docker images include Poppler, Tesseract and these language packs.

## Model configuration

The selected local model is a pinned community Q4_K_M text conversion of **`swiss-ai/Apertus-v1.5-8B`**, running through llama.cpp and Apple Metal. The ignored `.env` uses:

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
RETRIEVAL_QUERY_MODE=multilingual
RETRIEVAL_CITATION_MODE=full
```

No key is needed for this local endpoint. [Local model setup](docs/local-model.md) documents installation, artifact hashes and launch settings. Keep `CONTEXT_TOKENS` equal to the server's `LOCAL_MODEL_CONTEXT`. The local alias is sent only to recognized local hosts.

The default remains a 5,000-token retrieval budget with multilingual queries and full contextual quotations. `RETRIEVAL_QUERY_MODE=source` and `RETRIEVAL_CITATION_MODE=prefix` remain experimental opt-in settings. The exact-prefix candidate retained the full input budget and matched tuning classifications, but weakened supporting evidence for an individual claim. It was therefore rejected for normal UI and CLI use; these experiments add no default latency improvement. See [current validation](docs/validation.md) for measurements and the per-case evidence review.

For a fresh endpoint setup, copy `.env.example` to `.env`; edit the existing file on the configured Mac. Set the supplied endpoint/key and canonical model ID, remove `LOCAL_MODEL_ID`, and use the provider's supported context window. Runtime `BASE_URL` and `API_KEY` override local configuration and the template-compatible `LLM_BASE_URL`/`LLM_API_KEY` aliases, including explicitly empty values. The browser permits local inference only; the CLI supports the organizer's injected remote proxy. Authenticated organizer access remains untested.

`make check-endpoint` sends one real synthetic request through the production CLI and reports the validated prediction and provider usage. It checks connectivity and format, not benchmark accuracy. See [endpoint instructions](docs/solution-api.md#check-an-organizer-endpoint).

## Processing and coverage

1. Extract the source and retain original page numbers. Browser imports cache PDF bytes and text; the CLI reuses PDF extraction within a batch.
2. If the source fits the default 5,000-token input budget, assess it in one Apertus call.
3. Otherwise, ask Apertus for concise German, French and Italian claim/proposal search phrases, with at most 384 output tokens.
4. Rank original paragraph-sized spans using local BM25, proposal terms and neighboring context. Pack up to 12 candidate units into the final input budget without rewriting evidence.
5. Ask Apertus to assess the original claim against selected passages. Python maps its relation to the official label and independently verifies every citation.

The lexical index is created on first search and cached in the operating system's temporary directory under `claimlens-retrieval-v1`. Its key includes source text, provenance and index version. It stores lexical statistics, not answers or gold labels. Inference uses only the supplied source; it performs no web search.

The UI reports **Selected passages**, selected pages/units, cache use, token usage and call count. Unselected pages were not read by the model; retrieval can miss relevant qualifications or counter-evidence. Retrieved quotes retain surrounding original text. An unambiguous exact anchor returned by a generic JSON endpoint may be expanded to its original context, with that expansion disclosed. A matching quotation alone does not establish a correct interpretation.

The default retrieval deadline is 120 seconds across preparation, planning, model calls and retries, with at most four transport attempts. There is one pipeline attempt and no automatic exhaustive fallback. Empty retrieval, malformed output, invalid citations, unknown usage and exhausted budgets fail explicitly. PDF checks occur between pages and bound OCR subprocesses; they cannot interrupt an in-process parser within one page operation.

`DOCUMENT_STRATEGY=exhaustive` explicitly examines every source segment before evidence selection/reduction and a final verdict, within separate call/time limits. **Task B always uses full-reference/exhaustive processing** and only its supplied reference. All model passes and retries count toward reported usage and time. See [API limits and retry behavior](docs/solution-api.md).

## Official JSONL CLI and Docker

Each line supplies exactly one source. Language metadata is optional; Task A requires its proposal name and Task B may omit it. These synthetic examples contain no gold labels:

```json
{"id":"case-B","claim":{"text":"Die Regel gilt ab 2028."},"reference":{"text":"La règle s’applique à partir de 2028."}}
{"id":"case-A","vote":"Exact proposal name","claim":{"text":"La règle s’applique en 2028.","language":"fr"},"booklet":{"path":"booklets/example.pdf","language":"it"}}
```

```bash
PYTHONPATH=src .venv/bin/python -m claimlens --input /path/to/cases.jsonl --output output/predictions.jsonl
```

PDF paths must stay inside the input directory or an explicit `--data-root` (`/data` in evaluation). The CLI does not retrieve unrelated online material. The [API contract](docs/solution-api.md) lists the accepted input forms and exact output fields.

```bash
make run                # Interactive Docker application
make submission         # Separate claimlens:submission prediction image
make verify-submission  # Isolated Task A/B interface checks
```

Both images target `linux/amd64`. Models run separately on the host or at the supplied endpoint; the image contains no model weights or runtime model downloads. For the configured Colima profile, start `colima start --profile claimlens` and pass `DOCKER='docker --context colima-claimlens'` to Make. Inside a container `127.0.0.1` addresses the container itself; for a reachable host model use `BASE_URL=http://host.docker.internal:8081/v1`.

After preparing `data/input/cases.jsonl`, its PDFs, an output directory and exported evaluator credentials, run from `track_2a/`:

```bash
make submission
docker run --rm --platform linux/amd64 -e BASE_URL -e API_KEY -e LLM_NAME -e CONTEXT_TOKENS -v "$PWD/data/input:/data:ro" -v "$PWD/output:/output" claimlens:submission --input /data/cases.jsonl --output /output/predictions.jsonl
```

Keep gold labels outside `/data`. Each successful output includes `id`, `label`, `label_name`, `evidence: [{page, text}]` and `metrics: {input_tokens, output_tokens, inference_time_ms}`. Failed batches exit nonzero while retaining successful responses in `OUTPUT.partial.jsonl`; the requested complete output is replaced only when every case succeeds. Partial files are recovery artifacts.

## Validation and project files

Run `make test` and `make test-ui` for software checks. Use [evaluation.md](docs/evaluation.md) for live model evaluation and report generation. [validation.md](docs/validation.md) records current checks, measured quality, latency, token usage and limitations. Neither software tests nor small development samples establish private-benchmark readiness.

| Directory / file | Role |
| --- | --- |
| `src/claimlens/` | CLI, API, retrieval, model transport, PDF/OCR and frontend |
| `tests/` | Software and interface checks |
| `scripts/` | Model/data preparation, evaluation, audit and report tools |
| `docs/` | Current operational and requirements documentation |
| `data/README.md` | Dataset provenance and preparation instructions |
| `requirements.txt` / `requirements-dev.txt` | Application runtime / full local development and reporting dependencies |
| `technical_report.md` / `technical_report.pdf` | Final report source and reviewed PDF in the required template directory |
| `output/` | Ignored new predictions/evaluation work; preserve completed records in the archive |

`make report` creates `technical_report.pdf` beside `technical_report.md`; its build manifest and page-review artifacts belong in `output/report/`. There is no separate `submission/` folder. `make submission` and `make verify-submission` remain the prediction-image build and interface-check commands.

The root [README](../README.md#validation-and-delivery) describes final delivery: the root `README.md`, `LICENSE` and `Makefile`, plus this project's source, configuration examples, documentation and both reports. Exclude `data/local/`, `.env`, `.venv`, root `.cache/`, evaluation gold, archived experiments and generated working outputs. The former export remains in `../archive/legacy-submission/` for historical reference.
