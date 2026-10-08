# Local Apertus on Apple Silicon

ClaimLens can use Apertus v1.5 8B locally through llama.cpp, with no inference API key. This setup runs `llama-server` directly on macOS and binds it to `127.0.0.1:8081`. Docker Desktop is not required for this development workflow. The challenge's Docker submission remains a separate CPU application workflow; this Mac also has a Colima `claimlens` profile for container verification.

The selected model is a community Q4_K_M quantization of the Apertus v1.5 **text backbone**. It is an unofficial derivative, not the original multimodal checkpoint. The official checkpoint contains about 18.4GB of safetensors and no GGUF files; the selected GGUF is 5.06GB (4.71GiB). Runtime memory includes additional context and working buffers. This 16GiB Apple Silicon Mac is configured for a 16,384-token context and one inference request at a time. Long documents are processed in bounded segments when they do not fit that window.

## Prepare the model

From `track_2a/`:

```sh
brew install llama.cpp
python3 scripts/pull_local_model.py
```

The Python script uses only the standard library. It verifies the file size and SHA256 of an existing model, reuses the verified Docker Model Runner download when available, or downloads the pinned Hugging Face revision. New downloads use a temporary file and become available only after verification; failed or interrupted downloads are removed. A failed verification leaves existing files intact and exits with an error.

The canonical model path is `../.cache/models/apertus-v1.5-8b-q4_k_m.gguf`. Reusing the earlier DMR cache creates a relative symlink to `../.cache/docker-models/blobs/sha256/<sha256>` and avoids a second copy. Keep that cache blob while using the symlink. Both directories are ignored by Git.

```sh
# Prepare from existing local weights, with no download:
python3 scripts/pull_local_model.py --offline

# Recheck the canonical file without changing anything:
python3 scripts/pull_local_model.py --verify-only
```

## Start inference and connect ClaimLens

```sh
sh scripts/serve_local_model.sh
```

Keep this terminal open. The script locates `llama-server` on `PATH`, then checks `/opt/homebrew/bin/llama-server`. It enables GPU offload, disables thinking and context shifting, sets one parallel request, and supplies a stable model alias. Browser origins are limited to the local ClaimLens UI. Stop it with `Ctrl+C`. The Makefile shortcut is `make model-serve`; start `make dev` in a second terminal.

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
```

`LLM_NAME` remains the selected Apertus family; `LOCAL_MODEL_ID` is the identifier sent to the local server. ClaimLens applies this alias only to configured local hosts. For official evaluation, use the organizer's injected proxy configuration and official served model identifiers. Results from this quantized derivative do not establish the performance of the organizer's model.

V0.4 asks the model for a compact JSON object containing `explanation`, `relation` and `evidence`. The explanation precedes one source-relation enum: `supported`, `not_enough_information` or `refuted`. Local decoding also restricts passage identifiers and exact source sentence/paragraph quotations. Python preserves the submitted claim and converts the relation into one whole-claim UI assessment; the model no longer needs to copy the claim, select dimensions or generate diagnostic subchecks. The official external output remains unchanged:

| Internal relation | Official label | Official name |
| --- | --- | --- |
| `supported` | `0` | `entailment` |
| `not_enough_information` | `1` | `neutral` |
| `refuted` | `2` | `contradiction` |

The model still reads all supplied source text; quotation candidates are not a relevance filter. Python independently validates source quotations and requires evidence for non-neutral predictions, even though the local schema allows an empty evidence list. A malformed or invented citation is rejected or marked invalid and cannot become a valid official prediction.

Ordinary JSON-object mode sometimes returns an exact quotation as a string rather than a citation object. The adapter binds that string only when it occurs verbatim in exactly one supplied passage. It does not guess between repeated passages, fuzzy-match a paraphrase or replace an explicitly supplied wrong passage ID. All normalized citations still pass the same independent validation.

Development experiments produced explanations describing missing information paired with contradiction labels. The smaller response and explicit source-relation vocabulary target that disagreement and V2's neutral-class failure. Their impact is measured by the [readiness harness](evaluation.md); a constrained JSON response or exact quote alone does not establish a correct NLI decision.

The completed [27-case development run](../output/v4-readiness/development/summary.json) scored 25/27 correct and macro-F1 0.927451, including all nine neutral cases. This was a tuning cohort. The [54-case public-data Task B result](../output/v4-readiness/final-b-combined/summary.json) scored 50/54 correct and macro-F1 0.924722 with no failed predictions; the nine full-booklet Task A cases are still being evaluated after a context-overflow fix.

Check readiness from a second terminal:

```sh
curl --fail http://127.0.0.1:8081/health
curl --fail http://127.0.0.1:8081/v1/models
make check-endpoint
```

`/health` returns HTTP 503 while the model loads, then HTTP 200 when it is ready. `make check-endpoint` goes further: it makes one real synthetic prediction through the production CLI and reports the model, label, observed usage and elapsed time. It is a connection/format smoke check, not a quality evaluation. The API base URL for this direct llama.cpp runtime is `/v1`; Docker Model Runner's `/engines/v1` prefix does not apply here.

A smoke check against the local server using the canonical `swiss-ai/Apertus-v1.5-8B` ID and ordinary JSON-object mode passed with 514 input tokens, 60 output tokens and 3,152.339 ms. Its [saved result](../output/v4-readiness/local-api-protocol-smoke.json) checks the generic endpoint protocol against local inference. It does not establish access to or behavior of the organizer's authenticated proxy.

Optional launch settings:

```sh
LOCAL_MODEL_CONTEXT=8192 LOCAL_MODEL_PORT=8082 sh scripts/serve_local_model.sh
LLAMA_SERVER_BIN=/absolute/path/to/llama-server sh scripts/serve_local_model.sh
LOCAL_MODEL_PATH=/absolute/path/to/verified-model.gguf sh scripts/serve_local_model.sh
```

If memory pressure is high, close other applications or lower the context. Keep the application's `CONTEXT_TOKENS` equal to the runtime's `LOCAL_MODEL_CONTEXT`, and restart both processes after changing them. For the example above, set `CONTEXT_TOKENS=8192` and update `BASE_URL` to port 8082. ClaimLens can examine the full document in segments and reduce oversized selected evidence through bounded model passes; it reports an error if the evidence still cannot fit within the remaining budget. Custom model paths must point to the same verified artifact; the launcher itself checks file availability and does not repeat the 5GB checksum scan on every start.

## Context planning and longer booklets

The launcher defaults to `LOCAL_MODEL_CONTEXT=16384`. The matching application configuration is `CONTEXT_TOKENS=16384`; a fresh generic `.env.example` should be adjusted for the selected runtime. The budget includes the prompt and the final response, with 3,000 tokens reserved for final output and a safety margin.

When the complete source does not fit, ClaimLens reads all of it in ordered segments. Apertus selects potentially relevant source-unit IDs, including counter-evidence and partial facts. Python reconstructs verbatim excerpts and the final model pass reasons jointly across them. Original PDF page IDs are retained. The application never combines chunk labels by voting.

If those excerpts are still too large, Apertus ranks the selected original units in windows, examining every candidate in each reduction round. At most eight rounds retain fewer units until the final prompt fits. Text is not paraphrased, and original IDs and physical page numbers remain attached. Reduction can remove relevant evidence; the processing record reports the rounds and candidate counts, and the coverage description discloses that limitation.

Where needed, the local planner calls llama.cpp's `/apply-template` and `/tokenize` endpoints on this same local origin to measure the rendered prompt. When those APIs are unavailable, it uses an explicitly identified conservative byte-based estimate. Neither method replaces provider-reported usage: results aggregate actual prompt/completion tokens and latency over every extraction, reduction, final and retry pass, with context-only usage left `null`.

The default total analysis limit is 1,800 seconds and 48 inference attempts, including reduction and transport retries; each local model request and its bounded retries share a 300-second timeout. The CLI may retry invalid structure/citations once when all billed usage is known, within the remaining case deadline and call budget. Fixed context/call-capacity constraints do not trigger another full analysis. Usage is aggregated across attempts; unknown usage is never replaced with zero. An unrecovered invalid extraction, exhausted budget, non-progressing reduction or final evidence that still will not fit is an explicit error. Every segment being examined does not guarantee that selection and reduction retain every relevant fact.

The browser's model status uses the model catalog to check availability without running inference. If it says the runtime is unavailable, start `make model-serve`, wait for model loading to finish and refresh the status. Run [readiness evaluation](evaluation.md) separately from browser claim checks on the single local inference slot. The legacy `make evaluate` defaults to historical V2 artifacts and rejects changed code; use the current harness for V0.4 runs.

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
