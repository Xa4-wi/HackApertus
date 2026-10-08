"""Local configuration. Evaluation proxy variables always take precedence."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .models import ALLOWED_MODELS, DEFAULT_MODEL, ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_MODEL_HOSTS = frozenset(("127.0.0.1", "localhost", "::1",
                               "model-runner.docker.internal", "host.docker.internal"))


def load_dotenv(path=None):
    """Read literal KEY=value entries without executing shell syntax."""
    path = path or PROJECT_ROOT / ".env"
    if not path.exists():
        return
    inherited = set(os.environ)
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key not in {"BASE_URL", "API_KEY", "LLM_NAME", "LLM_BASE_URL", "LLM_API_KEY", "LLM_TIMEOUT_SECONDS", "LOCAL_MODEL_ID", "CONTEXT_TOKENS", "DOCUMENT_TIMEOUT_SECONDS", "MAX_DOCUMENT_MODEL_CALLS"}:
            continue
        if key in {"BASE_URL", "LLM_BASE_URL"} and inherited.intersection({"BASE_URL", "LLM_BASE_URL"}):
            continue
        if key in {"API_KEY", "LLM_API_KEY"} and inherited.intersection({"API_KEY", "LLM_API_KEY"}):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    base_url: str = ""
    api_key: str = ""
    model: str = DEFAULT_MODEL
    timeout: float = 120.0
    local_model_id: str = ""
    context_tokens: int = 8192
    document_timeout: float = 1800.0
    max_document_model_calls: int = 48

    @property
    def local_model_configured(self):
        """Whether this endpoint uses a local alias; this is not a health check.

        Exact host matching keeps a local GGUF alias out of an injected remote
        evaluation proxy. Redirects are rejected separately by the transport.
        """
        if not self.local_model_id:
            return False
        try:
            endpoint = urlsplit(self.base_url)
            return endpoint.scheme in ("http", "https") and endpoint.hostname in LOCAL_MODEL_HOSTS
        except ValueError:
            return False

    @property
    def available_models(self):
        return (self.model,) if self.local_model_configured else ALLOWED_MODELS

    def model_for_request(self, model):
        """Resolve the transport ID without changing the canonical selection."""
        if model not in ALLOWED_MODELS:
            raise ValidationError("Select one of the configured Apertus models.")
        if not self.local_model_configured:
            return model
        if model != self.model:
            raise ValidationError("The local endpoint is configured only for LLM_NAME. Select that model or reconfigure the local runtime.")
        return self.local_model_id

    @classmethod
    def from_env(cls):
        # Presence, not truthiness: an explicitly empty proxy must not fall back.
        base_url = os.environ.get("BASE_URL", os.environ.get("LLM_BASE_URL", "")).strip().rstrip("/")
        api_key = os.environ.get("API_KEY", os.environ.get("LLM_API_KEY", ""))
        model = os.environ.get("LLM_NAME", DEFAULT_MODEL) or DEFAULT_MODEL
        if model not in ALLOWED_MODELS:
            raise ValidationError("LLM_NAME must be a supported Apertus v1.5 model ID.")
        local_model_id = os.environ.get("LOCAL_MODEL_ID", "").strip()
        try:
            timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "120"))
        except ValueError:
            raise ValidationError("LLM_TIMEOUT_SECONDS must be a number.") from None
        if not 1 <= timeout <= 600:
            raise ValidationError("LLM_TIMEOUT_SECONDS must be between 1 and 600.")
        if base_url:
            try:
                parts = urlsplit(base_url)
                parts.port
            except ValueError:
                raise ValidationError("The model base URL is malformed.") from None
            if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
                raise ValidationError("The model base URL must be an HTTP(S) endpoint without credentials, query or fragment.")
        try:
            context_tokens = int(os.environ.get("CONTEXT_TOKENS", "8192"))
            document_timeout = float(os.environ.get("DOCUMENT_TIMEOUT_SECONDS", "1800"))
            max_calls = int(os.environ.get("MAX_DOCUMENT_MODEL_CALLS", "48"))
        except ValueError:
            raise ValidationError("Context, document timeout and model-call limits must be numbers.") from None
        if not 4096 <= context_tokens <= 262144:
            raise ValidationError("CONTEXT_TOKENS must be between 4096 and 262144 and match the serving runtime.")
        if not 1 <= document_timeout <= 3600:
            raise ValidationError("DOCUMENT_TIMEOUT_SECONDS must be between 1 and 3600.")
        if not 2 <= max_calls <= 128:
            raise ValidationError("MAX_DOCUMENT_MODEL_CALLS must be between 2 and 128.")
        settings = cls(base_url, api_key, model, timeout, local_model_id,
                       context_tokens, document_timeout, max_calls)
        if settings.local_model_configured and (
                len(local_model_id) > 500 or any(character.isspace() for character in local_model_id)):
            raise ValidationError("LOCAL_MODEL_ID must be a model identifier of at most 500 characters without whitespace.")
        return settings
