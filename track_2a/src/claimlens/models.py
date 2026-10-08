"""Shared labels, limits, and user-safe application errors."""

DEFAULT_MODEL = "swiss-ai/Apertus-v1.5-8B"
ALLOWED_MODELS = (DEFAULT_MODEL, "swiss-ai/Apertus-v1.5-70B")
LABELS = frozenset(("entailment", "contradiction", "neutral"))
CLASSIFICATIONS = {"entailment": 0, "neutral": 1, "contradiction": 2}
DIMENSIONS = frozenset(("amount", "date", "scope", "qualifier", "attribution", "general"))
MAX_CLAIM_LENGTH = 2000
MAX_CHECKS = 16
MAX_CONTEXT_CHARACTERS = 300_000


class ClaimLensError(Exception):
    """An error whose message is safe to return to the browser."""

    status_code = 400


class ValidationError(ClaimLensError):
    """The input or model response does not meet the application contract."""


class ProviderError(ClaimLensError):
    """A model provider failed; response bodies and secrets are never exposed."""

    status_code = 502

    def __init__(self, message, *, metrics=None, attempts=1):
        super().__init__(message)
        self.metrics = metrics
        self.attempts = attempts


def overall_label(checks):
    """Read the first, validated whole-claim check; do not combine subclaims."""
    return checks[0]["label"] if checks else "neutral"
