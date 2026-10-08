# Local Apertus on Apple Silicon

ClaimLens can use Apertus v1.5 8B locally through llama.cpp, with no inference API key. This setup runs `llama-server` directly on macOS and binds it to `127.0.0.1:8081`. Docker Desktop is not required for this development workflow. The challenge's Docker submission remains a separate CPU application workflow; this Mac also has a Colima `claimlens` profile for container verification.

The selected model is a community Q4_K_M quantization of the Apertus v1.5 **text backbone**. It is an unofficial derivative, not the original multimodal checkpoint. The official checkpoint contains about 18.4GB of safetensors and no GGUF files; the selected GGUF is 5.06GB (4.71GiB). Runtime memory includes additional context and working buffers. This 16GiB Apple Silicon Mac is configured for a 16,384-token context and one inference request at a time. The default booklet pipeline retrieves selected original passages; the full-source segmented mode remains explicitly selectable.

## Prepare the model

From `track_2a/`:

```sh
brew install llama.cpp
python3 scripts/pull_local_model.py
```

The Python script uses only the standard library. It verifies the file size and SHA256 of an existing model, reuses the verified Docker Model Runner download when available, or downloads the pinned Hugging Face revision. New downloads use a temporary file and become available only after verification; failed or interrupted downloads are removed. A failed verification leaves existing files intact and exits with an error.

The canonical model path is `../.cache/models/apertus-v1.5-8b-q4_k_m.gguf`. Reusing an existing DMR cache creates a relative symlink to `../.cache/docker-models/blobs/sha256/<sha256>` and avoids a second copy. Keep that cache blob while using the symlink. Both directories are ignored by Git.

```sh
# Prepare from existing local weights, with no download:
python3 scripts/pull_local_model.py --offline

# Recheck the canonical file without changing anything:
python3 scripts/pull_local_model.py --verify-only
```

## Start inference and connect ClaimLens

```sh
bash scripts/serve_local_model.sh
```

Keep this terminal open. The script locates `llama-server` on `PATH`, then checks `/opt/homebrew/bin/llama-server`. It enables GPU offload, disables thinking and context shifting, sets one parallel request, limits the prompt cache to `LOCAL_MODEL_CACHE_MB=1024` MiB, and supplies a stable model alias. Browser origins are limited to the local ClaimLens UI. Stop it with `Ctrl+C`. The Makefile shortcut is `make model-serve`; start `make dev` in a second terminal.

Configure ClaimLens in `track_2a/.env`:

```dotenv
BASE_URL=http://127.0.0.1:8081/v1
API_KEY=
LLM_NAME=swiss-ai/Apertus-v1.5-8B
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

`LLM_NAME` remains the selected Apertus family; `LOCAL_MODEL_ID` is the identifier sent to the local server. ClaimLens applies this alias only to configured local hosts. For official evaluation, use the organizer's injected proxy configuration and official served model identifiers. Results from this quantized derivative do not establish the performance of the organizer's model.

Current measurements and their limitations are recorded in [validation.md](validation.md). The application validates quotations against original source text, but a valid quote or constrained JSON response alone does not establish a correct classification.

Check readiness from a second terminal:

```sh
curl --fail http://127.0.0.1:8081/health
curl --fail http://127.0.0.1:8081/v1/models
make check-endpoint
```

`/health` returns HTTP 503 while the model loads, then HTTP 200 when it is ready. `make check-endpoint` goes further: it makes one real synthetic prediction through the production CLI and reports the model, label, observed usage and elapsed time. It is a connection/format smoke check, not a quality evaluation. The API base URL for this direct llama.cpp runtime is `/v1`; Docker Model Runner's `/engines/v1` prefix does not apply here.

The recorded generic JSON retrieval smoke passed against the local server. It checks protocol compatibility, not access to the organizer's authenticated proxy or general model accuracy; see [validation.md](validation.md).

Optional launch settings:

```sh
LOCAL_MODEL_CONTEXT=8192 LOCAL_MODEL_PORT=8082 bash scripts/serve_local_model.sh
LOCAL_MODEL_CACHE_MB=1024 bash scripts/serve_local_model.sh
LLAMA_SERVER_BIN=/absolute/path/to/llama-server bash scripts/serve_local_model.sh
LOCAL_MODEL_PATH=/absolute/path/to/verified-model.gguf bash scripts/serve_local_model.sh
```

If memory pressure is high, close other applications or lower the context. Keep the application's `CONTEXT_TOKENS` equal to the runtime's `LOCAL_MODEL_CONTEXT`, and restart both processes after changing them. For the example above, set `CONTEXT_TOKENS=8192` and update `BASE_URL` to port 8082. The retrieval input budget also shrinks when the runtime context is smaller. Explicit `DOCUMENT_STRATEGY=exhaustive` can examine a larger source in segments, subject to its separate call/time budgets. Custom model paths must point to the same verified artifact; the launcher itself checks file availability and does not repeat the 5GB checksum scan on every start.

## Context, caching and case limits

The launcher defaults to `LOCAL_MODEL_CONTEXT=16384`; application `CONTEXT_TOKENS` must match it. The default `DOCUMENT_STRATEGY=retrieval` limits the final prompt to `RETRIEVAL_PROMPT_TOKENS=5000`, or the context minus 3,000 output tokens and a safety margin, whichever is smaller. Short sources use one call; longer booklets use multilingual query expansion, local BM25 retrieval and one final assessment. Task B always uses its full supplied reference. The [technical report](../technical_report.md) explains the method.

Keep `RETRIEVAL_QUERY_MODE=multilingual` and `RETRIEVAL_CITATION_MODE=full` for the baseline workflow. The following options remain experimental and disabled by default:

- `RETRIEVAL_QUERY_MODE=source` skips query generation only when every passage has the same known source language and the claim metadata matches it. Otherwise, a known source language receives one targeted query with a 128-token output cap; unknown or mixed source languages retain multilingual expansion. This option remains experimental and was not adopted for normal use.
- `RETRIEVAL_CITATION_MODE=prefix` applies only to retrieved passages on a configured native local endpoint. The model emits a registered exact prefix, and Python restores its full original quotation. When any candidate has at least 200 characters and 25 whitespace-delimited words, shorter candidates cannot be cited; all candidates remain available if every candidate is short. All selected source text still reaches the classifier. This structural filter can remove short decisive evidence and does not establish relevance.

The fixed exact-prefix comparison retained multilingual queries and the full 5,000-token input budget. Matching tuning classifications still concealed a loss of useful supporting passages, so the candidate was rejected for normal use. The application retains full quotations; these experiments add no default UI or CLI latency improvement. See [validation.md](validation.md) for paired timings, token counts and per-case evidence reviews. Prefix mode has no effect on generic remote JSON endpoints, short full-source processing or Task B. Retrieval processing metadata records the actual query strategy and effective citation mode; restored quotes do not add to provider-reported output-token usage.

The default retrieval deadline is 120 seconds across source preparation, planning, model calls and transport retries, with at most four inference attempts. There is no whole-pipeline retry or automatic exhaustive fallback. PDF deadlines are checked between pages; an in-process parser cannot be interrupted mid-page. Explicit `DOCUMENT_STRATEGY=exhaustive` examines source segments within separate defaults of 1,800 seconds and 48 attempts. Neither mode guarantees that selected evidence is complete.

The lexical index is cached in the operating system's temporary directory under `claimlens-retrieval-v1`, keyed by source text, provenance and index version. It stores lexical statistics, not predictions. Browser imports separately cache PDF bytes and page text. These caches reduce repeated work but do not replace inference. The UI reports cache use and selected-page coverage.

For local planning, ClaimLens can use the same server's `/apply-template` and `/tokenize` endpoints. Otherwise, a conservative UTF-8 byte estimate can admit fewer passages than actual token counting would. These estimates never replace observed provider usage. Token/time totals include every model pass and retry; context-only usage remains `null` when unavailable.

Run `make evaluate-prepare`, `make evaluate` and `make evaluate-score` separately from browser checks on the single inference slot. New development records go under `output/evaluations/latency`; see [evaluation.md](evaluation.md) for archive prerequisites and fresh directories. Weights, local caches and `.env` are excluded from the prediction image and clean handoff.

## Pinned provenance

| Property | Value |
| --- | --- |
| Official source | [swiss-ai/Apertus-v1.5-8B](https://huggingface.co/swiss-ai/Apertus-v1.5-8B) |
| Text conversion | [andreasmartin/apertus-v1.5-8b-text](https://huggingface.co/andreasmartin/apertus-v1.5-8b-text) |
| GGUF repository | [Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF](https://huggingface.co/Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF) |
| GGUF revision | `248ec68a63e219e3f061e4c946fc8a20d63b9975` |
| Filename | `apertus-v1.5-8b-text-q4_k_m.gguf` |
| Size | `5059027136` bytes |
| SHA256 | `a037df8d87ff6caacee794ee85f55342f2152e0d359b7389033300c3bee5f299` |
| License | Apache 2.0; see the source model's usage policy and derivative notices |
| Metadata checked | 2026-10-08 |

The conversion author documents preserved text-backbone weights, removed image/audio components, tokenizer changes, and added special-token output rows. The subsequent quantization changes numerical precision. The pinned SHA256 identifies the downloaded artifact; it is not a guarantee of output accuracy. See the [conversion methodology](https://huggingface.co/andreasmartin/apertus-v1.5-8b-text#conversion-methodology) and [pinned GGUF files](https://huggingface.co/Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF/tree/248ec68a63e219e3f061e4c946fc8a20d63b9975).

Runtime references: [llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md), [Homebrew llama.cpp package](https://formulae.brew.sh/formula/llama.cpp), and [Docker Model Runner API documentation](https://docs.docker.com/ai/model-runner/api-reference/).
