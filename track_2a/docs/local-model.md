# Local Apertus on Apple Silicon

ClaimLens can use Apertus v1.5 8B locally through llama.cpp, with no inference API key. This setup runs `llama-server` directly on macOS and binds it to `127.0.0.1:8081`. Docker Desktop is not installed or required for this development workflow. The challenge's Docker submission remains a separate workflow.

The selected model is a community Q4_K_M quantization of the Apertus v1.5 **text backbone**. It is an unofficial derivative, not the original multimodal checkpoint. The official checkpoint contains about 18.4GB of safetensors and no GGUF files; the selected GGUF is 5.06GB (4.71GiB). Runtime memory includes additional context and working buffers. On this 16GiB Apple Silicon Mac, start with the configured 8,192-token context and one request at a time.

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
```

`LLM_NAME` remains the selected Apertus family; `LOCAL_MODEL_ID` is the identifier sent to the local server. ClaimLens applies this alias only to configured local hosts. For official evaluation, use the organizer's injected proxy configuration and official served model identifiers. Results from this quantized derivative do not establish the performance of the organizer's model.

Local responses use a JSON schema that restricts labels, dimensions, passage identifiers, and verbatim claim highlights. Diagnostic highlights can cover up to eight contiguous words; the full claim is always available. Source quotations are independently checked against the input. A malformed or invented citation is still rejected, even if the JSON schema was satisfied.

Check readiness from a second terminal:

```sh
curl --fail http://127.0.0.1:8081/health
curl --fail http://127.0.0.1:8081/v1/models
```

`/health` returns HTTP 503 while the model loads, then HTTP 200 when it is ready. The API base URL for this direct llama.cpp runtime is `/v1`; Docker Model Runner's `/engines/v1` prefix does not apply here.

Optional launch settings:

```sh
LOCAL_MODEL_CONTEXT=4096 LOCAL_MODEL_PORT=8082 sh scripts/serve_local_model.sh
LLAMA_SERVER_BIN=/absolute/path/to/llama-server sh scripts/serve_local_model.sh
LOCAL_MODEL_PATH=/absolute/path/to/verified-model.gguf sh scripts/serve_local_model.sh
```

If memory pressure is high, close other applications or lower the context. If a prompt exceeds the configured context, reduce its source material or increase context within available memory. Update `BASE_URL` when changing the port. Custom model paths must point to the same verified artifact; the launcher itself checks file availability and does not repeat the 5GB checksum scan on every start.

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
