# ClaimLens — Track 2A / OST

An inspectable claim-checking prototype for Swiss voting booklets. It combines the official NLI output with a review panel showing amounts, dates, scope, and source attribution. **Default model: `swiss-ai/Apertus-v1.5-8B`**. The local configuration serves a Q4_K_M text conversion of 8B. A remote endpoint can also offer `swiss-ai/Apertus-v1.5-70B`; the local dropdown shows only the installed model.

The original [Academia Challenges instructions](docs/upstream-track-2a.md) are preserved from the template. The chosen challenge requires Apertus v1.5, all German/French/Italian source–claim combinations, tasks A and B, and a CLI. See [verified requirements](docs/event-requirements.md) and the [exact solution API contract](docs/solution-api.md).

## Offline walkthrough

From this directory (or the repository root):

```bash
make dev
# Open http://localhost:8000
make demo
# Writes output/demo-predictions.jsonl without inference.
```

Python 3.9+ runs the walkthrough with standard-library dependencies. These results are **prewritten demonstrations**, not predictions from the selected model. One example preserves the OST dataset's label; three are locally authored examples. Custom claims are rejected in demo mode. The example source is a French reference passage, not the full booklet; its PDF page is therefore deliberately `null`.

```bash
make run
```

`make run` builds and runs the **demo** Docker target. `make submission` builds **`claimlens:submission`**, the separate prediction target without demo data or stored labels. Both target `linux/amd64`; no GPU is required in the application container. Remote inference handles the model. `PORT=8001 make dev` changes the local UI port.

## Local Apertus on this Mac

The dataset and quantized model are already downloaded, llama.cpp is installed, and `.env` points to the local API. Start these in separate terminals from the repository root or this directory:

```bash
make model-serve
make dev
```

Open http://localhost:8000 and choose **Live Apertus**. Inference runs on the Mac through llama.cpp with Apple Metal. No key or Hugging Face login is needed for this public quantized artifact. The downloaded model is a community text conversion of Apertus v1.5 8B, not the complete multimodal checkpoint. See [local model setup](docs/local-model.md) for pinned provenance, reinstall instructions, and resource limits.

```dotenv
LLM_NAME=swiss-ai/Apertus-v1.5-8B
BASE_URL=http://127.0.0.1:8081/v1
API_KEY=
LOCAL_MODEL_ID=claimlens-apertus-v1.5-8b-q4
LLM_TIMEOUT_SECONDS=300
```

The runtime reserves 8,192 tokens for prompt and output together. Longer references or full booklets may need a larger context and more RAM. Inputs are never silently truncated. `LOCAL_MODEL_CONTEXT=16384 make model-serve` increases the limit after stopping the existing model server; memory use will grow. The downloaded snapshot contains 1,488 rows and all nine language pairs. See [data/README.md](data/README.md) to load it from disk or reproduce the download with `make dataset` after installing `requirements-data.txt`.

## Remote endpoint or evaluation proxy

```bash
cp .env.example .env
```

For a fresh checkout, copy the example above; on this configured Mac, edit the existing `.env` instead. Set your endpoint, API key, and model, and remove `LOCAL_MODEL_ID`. CSCS development URL documented by the organizer: `https://api.inference.cscs.ch/v1`. Restart the server after configuration, select **Live Apertus**, and submit a claim to make one remote request. The key stays on the Python server and is never sent to the browser.

| Setting | Purpose |
| --- | --- |
| `LLM_NAME` | `swiss-ai/Apertus-v1.5-8B` or `swiss-ai/Apertus-v1.5-70B` |
| `BASE_URL`, `API_KEY` | Official OST runtime endpoint and key; evaluation injects a proxy here |
| `LLM_BASE_URL`, `LLM_API_KEY` | Generic template-compatible aliases |
| `LLM_TIMEOUT_SECONDS` | Request timeout, default 120; accepted range 1–600 |
| `LOCAL_MODEL_ID` | Optional local runtime alias; used only for explicitly recognized local hostnames |

Runtime environment beats `.env`, including across endpoint/key aliases. If both alias forms are present at the same level, OST's `BASE_URL` and `API_KEY` win. An explicitly empty runtime value does not fall back to a file or another provider. Every model call uses the resolved endpoint. No automatic retry or provider fallback is performed.

Live compatibility requires an OpenAI-compatible `/chat/completions` API with JSON-object output and usage reporting. Local llama.cpp supplies this API. Remote provider access remains unverified; no paid inference has been performed. An injected remote evaluation URL ignores the local alias and receives the official model identifier.

If the application runs inside Docker, `127.0.0.1` refers to that container. Use a model service reachable from the container and configure its actual URL. The verified Mac setup runs both processes directly on the host; `make run` remains the template's Docker path and requires Docker Desktop.

## Official CLI

Install the small PDF dependency for local task A execution:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

The CLI accepts UTF-8 JSONL with both task types in one file:

```json
{"id":"case-B","vote":"Example proposal","claim":{"text":"Die Regel gilt ab 2028.","language":"de"},"reference":{"text":"La règle s’applique à partir de 2028.","language":"fr"}}
{"id":"case-A","vote":"Exact proposal name","claim":{"text":"La règle s’applique en 2028.","language":"fr"},"booklet":{"path":"booklets/example.pdf","language":"it"}}
```

These two lines illustrate the format; they are not official voting content. Each case needs exactly one source. PDF paths must remain within `/data` in the evaluation container, or the input file's directory locally (`--data-root` can select another directory). The parser preserves 1-based **PDF page positions**, not printed page labels. It does not perform OCR.

```bash
PYTHONPATH=src .venv/bin/python -m claimlens \
  --input /path/to/cases.jsonl --output output/predictions.jsonl
```

After building the prediction image and exporting the runtime endpoint/key:

```bash
make submission
docker run --rm --platform linux/amd64 \
  -e BASE_URL -e API_KEY -e LLM_NAME \
  -v "$PWD/data:/data:ro" -v "$PWD/output:/output" \
  claimlens:submission --input /data/cases.jsonl --output /output/predictions.jsonl
```

Create the output directory and prepare `cases.jsonl`/PDFs separately before this command. Only inference-ready inputs belong in `/data`; keep gold labels outside the container. The default Docker build is also the submission target. `.env`, the original labeled OST sample, and stored demo judgments are excluded from that image.

Each prediction contains `id`, integer `label`, matching lowercase `label_name`, `evidence: [{page, text}]`, and `metrics: {input_tokens, output_tokens, inference_time_ms}`. Token counts come from the provider. Case time includes parsing, model request, and validation; shared PDF parsing is cached within the batch. The UI separately reports model-request duration and character count; it does not invent a context-only token count.

Malformed input, invalid model JSON/citations, unavailable endpoints, and missing provider usage make the CLI exit nonzero. They are never exported as a fabricated neutral answer. Output is replaced atomically only after the entire batch succeeds. Neutral is reserved for a valid assessment of insufficient evidence.

## Checks and limits

```bash
make test
```

Tests use local fixtures and mocked provider responses. They cover quote integrity, classification mapping, environment precedence, nine language combinations, both CLI task types, PDF page numbering, and error handling. They do **not** measure Apertus accuracy.

The live baseline sends every extracted page, including potentially contradictory passages. Limits: 300,000 source characters, 2,000 claim characters, 25 MB/PDF, 200 PDF pages. Oversized inputs fail explicitly; no document is silently truncated. The endpoint may impose a smaller token window. All quantities, claims, and forecasts remain relative to the selected source. Exact quotes establish provenance, not proof that the model's interpretation is correct.

See [technical_report.md](technical_report.md) for observed validation, remaining work, and licensing.
