#!/bin/sh
# Serve the verified Apertus GGUF on this machine's loopback interface.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
MODEL_PATH=${LOCAL_MODEL_PATH:-"$REPOSITORY_ROOT/.cache/models/apertus-v1.5-8b-q4_k_m.gguf"}
MODEL_CONTEXT=${LOCAL_MODEL_CONTEXT:-8192}
MODEL_PORT=${LOCAL_MODEL_PORT:-8081}
MODEL_ALIAS=claimlens-apertus-v1.5-8b-q4

if [ "${1:-}" = "--help" ]; then
    cat <<'HELP'
Usage: scripts/serve_local_model.sh

Serves the local Apertus v1.5 8B text GGUF at http://127.0.0.1:8081/v1.
Environment: LLAMA_SERVER_BIN, LOCAL_MODEL_PATH, LOCAL_MODEL_CONTEXT (8192),
             LOCAL_MODEL_PORT (8081).
Prepare and verify weights first: python3 scripts/pull_local_model.py
HELP
    exit 0
fi
if [ "$#" -ne 0 ]; then
    printf '%s\n' 'Unexpected argument. Use --help for usage.' >&2
    exit 2
fi

case "$MODEL_CONTEXT" in
    ''|*[!0-9]*) printf '%s\n' 'LOCAL_MODEL_CONTEXT must be a positive integer.' >&2; exit 2 ;;
esac
case "$MODEL_PORT" in
    ''|*[!0-9]*) printf '%s\n' 'LOCAL_MODEL_PORT must be an integer between 1 and 65535.' >&2; exit 2 ;;
esac
if [ "$MODEL_CONTEXT" -lt 1 ] || [ "$MODEL_PORT" -lt 1 ] || [ "$MODEL_PORT" -gt 65535 ]; then
    printf '%s\n' 'Context must be positive and port must be between 1 and 65535.' >&2
    exit 2
fi

if [ -z "${LLAMA_SERVER_BIN:-}" ]; then
    if command -v llama-server >/dev/null 2>&1; then
        LLAMA_SERVER_BIN=$(command -v llama-server)
    elif [ -x /opt/homebrew/bin/llama-server ]; then
        LLAMA_SERVER_BIN=/opt/homebrew/bin/llama-server
    else
        printf '%s\n' 'llama-server is missing. Install it with: brew install llama.cpp' >&2
        exit 1
    fi
fi
if [ ! -x "$LLAMA_SERVER_BIN" ]; then
    printf '%s\n' 'LLAMA_SERVER_BIN must point to an executable llama-server.' >&2
    exit 1
fi
if [ ! -f "$MODEL_PATH" ]; then
    printf '%s\n' "Model is missing. Run: python3 $SCRIPT_DIR/pull_local_model.py" >&2
    exit 1
fi

printf 'Serving %s at http://127.0.0.1:%s/v1 (context %s tokens)\n' "$MODEL_ALIAS" "$MODEL_PORT" "$MODEL_CONTEXT"
exec "$LLAMA_SERVER_BIN" \
    --model "$MODEL_PATH" \
    --host 127.0.0.1 \
    --port "$MODEL_PORT" \
    --alias "$MODEL_ALIAS" \
    --ctx-size "$MODEL_CONTEXT" \
    --parallel 1 \
    --no-context-shift \
    --reasoning off \
    --cors-origins http://127.0.0.1:8000,http://localhost:8000 \
    -ngl all \
    --metrics
