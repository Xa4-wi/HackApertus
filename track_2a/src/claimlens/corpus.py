"""Load the small, attributed walkthrough corpus; no runtime downloads."""

import json

from .config import PROJECT_ROOT
from .models import ValidationError


def load_corpus():
    return json.loads((PROJECT_ROOT / "data" / "corpus.json").read_text(encoding="utf-8"))["proposals"]


def find_proposal(proposals, proposal_id):
    for proposal in proposals:
        if proposal["id"] == proposal_id:
            return proposal
    raise ValidationError("Select one of the bundled proposals.")


def public_config(settings, proposals):
    return {
        "models": [{"id": model, "label": "Apertus 1.5 · " + ("70B" if "70B" in model else "8B")
                    + (" · local" if settings.local_model_configured else "")}
                   for model in settings.available_models],
        "default_model": settings.model,
        "live_ready": bool(settings.base_url),
        "local_model_configured": settings.local_model_configured,
        "request_timeout_seconds": settings.timeout + 10,
        "proposals": [{key: value for key, value in proposal.items() if key not in {"passages", "examples"}} | {
            "examples": [{key: value for key, value in example.items() if key != "result"} for example in proposal["examples"]]
        } for proposal in proposals],
    }
