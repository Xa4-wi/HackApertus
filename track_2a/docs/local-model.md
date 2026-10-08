# Local Apertus on Apple Silicon

ClaimLens can use Apertus v1.5 8B locally through llama.cpp, with no inference API key. This setup runs `llama-server` directly on macOS and binds it to `127.0.0.1:8081`. Docker Desktop is not required for this development workflow. The challenge's Docker submission remains a separate CPU application workflow; this Mac also has a Colima `claimlens` profile for container verification.

The selected model is a community Q4_K_M quantization of the Apertus v1.5 **text backbone**. It is an unofficial derivative, not the original multimodal checkpoint. The official checkpoint contains about 18.4GB of safetensors and no GGUF files; the selected GGUF is 5.06GB (4.71GiB). Runtime memory includes additional context and working buffers. This 16GiB Apple Silicon Mac is configured for a 16,384-token context and one inference request at a time. V0.5 retrieves selected original passages for longer booklets by default; the full-source segmented mode remains explicitly selectable.

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

Keep this terminal open. The script locates `llama-server` on `PATH`, then checks `/opt/homebrew/bin/llama-server`. It enables GPU offload, disables thinking and context shifting, sets one parallel request, limits the prompt cache to `LOCAL_MODEL_CACHE_MB=1024` MiB, and supplies a stable model alias. Earlier runs used the runtime's implicit 8,192 MiB cache default. This lowers configured cache memory; its isolated speed effect has not been measured. Browser origins are limited to the local ClaimLens UI. Stop it with `Ctrl+C`. The Makefile shortcut is `make model-serve`; start `make dev` in a second terminal.

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
```

`LLM_NAME` remains the selected Apertus family; `LOCAL_MODEL_ID` is the identifier sent to the local server. ClaimLens applies this alias only to configured local hosts. For official evaluation, use the organizer's injected proxy configuration and official served model identifiers. Results from this quantized derivative do not establish the performance of the organizer's model.

The compact response design introduced in V0.4 asks the model for a compact JSON object containing `explanation`, `relation` and `evidence`. The explanation precedes one source-relation enum: `supported`, `not_enough_information` or `refuted`. Local decoding also restricts passage identifiers and exact source quotations. Retrieved-mode candidates retain contextual spans of about 900 characters, merging a tiny trailing fragment with preceding text up to 1,200 characters. The model returns the quotation text; Python checks it against the original source. Python preserves the submitted claim and converts the relation into one whole-claim UI assessment; the model no longer needs to copy the claim, select dimensions or generate diagnostic subchecks. The official external output remains unchanged:

| Internal relation | Official label | Official name |
| --- | --- | --- |
| `supported` | `0` | `entailment` |
| `not_enough_information` | `1` | `neutral` |
| `refuted` | `2` | `contradiction` |

The final model sees the complete source when it fits the fast input budget; longer booklets use selected original passages. Reference-only Task B inputs keep full-reference/exhaustive processing. Quote constraints validate permitted source text, while retrieval decides which passages enter the final prompt. Python independently validates source quotations and requires evidence for non-neutral predictions, even though the local schema allows an empty evidence list. A malformed or invented citation is rejected or marked invalid and cannot become a valid official prediction.

Ordinary JSON-object mode sometimes returns an exact quotation as a string rather than a citation object. The adapter binds that string only when it occurs verbatim in exactly one supplied passage. It does not guess between repeated passages, fuzzy-match a paraphrase or replace an explicitly supplied wrong passage ID. In retrieved mode, a unique exact anchor within the cited passage can be expanded to its containing original-source context. This retains the model's words and label, never crosses omitted text, and reports the expansion count in processing metadata and a warning. Task B and exhaustive citations retain their previous behavior. All normalized citations still pass the same independent validation.

Development experiments produced explanations describing missing information paired with contradiction labels. The smaller response and explicit source-relation vocabulary target that disagreement and V2's neutral-class failure. Their impact is measured by the [readiness harness](evaluation.md); a constrained JSON response or exact quote alone does not establish a correct NLI decision.

The historical V0.4 [27-case development run](../output/v4-readiness/development/summary.json) scored 25/27 correct and macro-F1 0.927451, including all nine neutral cases. This was a tuning cohort. The [54-case public-data Task B result](../output/v4-readiness/final-b-combined/summary.json) scored 50/54 correct and macro-F1 0.924722 with no failed predictions; the V0.4 full-booklet run was stopped after one accepted, unscored case took 458.53 seconds. The selected V0.5 [contextual-quotation development run](../output/v5-latency-context/summary.json) returned three correct labels, averaging 54.97 seconds (p95 70.63 seconds), with two calls per case and cached lexical indexes. Official evidence overlap remained 0.50; all three quotes independently verified on their physical pages. The earlier 39.15-second run returned exact but inadequate quotations and remains preserved. These same three cases were repeatedly used for tuning, not a fresh quality estimate; the nine-case Task A and 54-case Task B cohorts have not been rerun on V0.5.

A [timing-only repeat](../output/v5-latency-context/same-case-comparison/results.jsonl) of the earlier slow booklet took **56.11 seconds**, compared with **458.53 seconds** previously, with **4,363 versus 62,050 input tokens** and two versus six calls. This is one unscored case on the same model/hardware; its index was warm and the launcher cache changed from 8,192 to 1,024 MiB. The 8.17× observed improvement belongs to the combined setup and does not isolate any cache-specific or algorithm-specific benefit.

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
LOCAL_MODEL_CACHE_MB=1024 sh scripts/serve_local_model.sh
LLAMA_SERVER_BIN=/absolute/path/to/llama-server sh scripts/serve_local_model.sh
LOCAL_MODEL_PATH=/absolute/path/to/verified-model.gguf sh scripts/serve_local_model.sh
```

If memory pressure is high, close other applications or lower the context. Keep the application's `CONTEXT_TOKENS` equal to the runtime's `LOCAL_MODEL_CONTEXT`, and restart both processes after changing them. For the example above, set `CONTEXT_TOKENS=8192` and update `BASE_URL` to port 8082. The retrieval input budget also shrinks when the runtime context is smaller. Explicit `DOCUMENT_STRATEGY=exhaustive` can examine a larger source in segments, subject to its separate call/time budgets. Custom model paths must point to the same verified artifact; the launcher itself checks file availability and does not repeat the 5GB checksum scan on every start.

## Context planning and longer booklets

The launcher defaults to `LOCAL_MODEL_CONTEXT=16384`; keep application `CONTEXT_TOKENS` equal to it. With `DOCUMENT_STRATEGY=retrieval`, final input is capped at `RETRIEVAL_PROMPT_TOKENS=5000` by default, or the context minus 3,000 output tokens and a safety margin, whichever is smaller. A source that fits is assessed directly in one model call.

For a longer booklet, one Apertus call produces German, French and Italian claim/proposal search phrases, capped at 384 output tokens. Local BM25 ranks paragraph-sized original spans, boosts proposal terms and includes neighboring context. At most 12 candidate units are considered for the final prompt. One final Apertus call assesses the unchanged claim against the packed original excerpts. Translated queries are search terms only; quotations remain in the source language with their original physical PDF pages.

The index is created on the first search and cached under the operating system's temporary directory in `claimlens-retrieval-v1`. Its key includes extracted text, source metadata and the index version. An OCR/text change invalidates it; current text is always used to reconstruct returned evidence. This stores lexical statistics, not answers. Browser imports separately cache PDF bytes and page extraction, so a reused library item needs neither a download nor another extraction. Cold index creation is included in the case time.

The default retrieval deadline is 120 seconds, shared across source preparation, planning, both model calls and any transport retries. At most four inference attempts are allowed in total. The CLI never repeats the whole retrieval pipeline or falls back automatically to exhaustive analysis. Unknown usage, malformed expansion, empty search results, invalid citations or exhausted budgets fail explicitly. Deadline checks occur between PDF pages and OCR subprocess timeouts respect the remaining budget; the in-process PDF parser cannot be interrupted within a single page operation.

The UI labels retrieval **Selected passages** and reports selected pages/units, cache use, query expansion and total call count. Its coverage warning matters: the model did not read unselected pages. Retrieval may omit a qualification, counter-evidence or facts distributed across the booklet. A weak search score does not establish neutrality or calibrated confidence.

Set `DOCUMENT_STRATEGY=exhaustive` to retain the earlier method: Apertus examines every source segment, selects original units, then ranks oversized selections in at most eight reduction rounds before the final assessment. Even this mode can omit relevant evidence during selection/reduction. Its default limits remain 1,800 seconds and 48 attempts. A rejected verdict may receive one recovery attempt when usage is known; fixed capacity failures do not restart analysis. **Task B always uses full-reference/exhaustive processing**, regardless of the booklet strategy, and never supplements a supplied reference with other material.

For local planning, ClaimLens can call the same server's `/apply-template` and `/tokenize` endpoints to measure the rendered prompt. Otherwise it uses a conservative UTF-8 byte estimate, which can admit fewer passages than actual token counting would. Planning estimates never replace provider-reported input/output usage. Usage and elapsed time include expansion, assessment and all retries, or every extraction/reduction pass in exhaustive mode. Context-only usage stays `null` when unavailable.

The model catalog checks availability without inference; `make check-endpoint` checks an actual prediction. Run the three-case development check separately from browser checks on the single local slot; see [evaluation instructions](evaluation.md). The legacy `make evaluate` points to historical V2 artifacts and rejects changed code. The three-case V0.5 measurements do not isolate the effect of the cache setting; old V0.4 scores also do not establish current retrieval quality.

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
