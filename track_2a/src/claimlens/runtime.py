"""Read-only model availability checks; no inference or credential exposure."""

import json
from urllib.request import Request, build_opener

from .llm import _RejectRedirects


def model_status(settings):
    status = {"configured": bool(settings.base_url), "reachable": False,
              "local": settings.local_model_configured, "model": settings.model,
              "context_tokens": None, "message": "Configure a model endpoint to use live mode."}
    if not settings.base_url:
        return status
    headers = {"Accept": "application/json", "User-Agent": "ClaimLens/0.2"}
    if settings.api_key:
        headers["Authorization"] = "Bearer " + settings.api_key
    try:
        request = Request(settings.base_url.rstrip("/") + "/models", headers=headers)
        with build_opener(_RejectRedirects()).open(request, timeout=3) as response:
            raw = response.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError("oversized model catalog")
        models = json.loads(raw).get("data", [])
        served = settings.model_for_request(settings.model)
        selected = next((model for model in models if model.get("id") == served), None)
        status["reachable"] = selected is not None
        if selected is None:
            status["message"] = "The endpoint responds but does not list the selected model."
        else:
            context = selected.get("meta", {}).get("n_ctx")
            status["context_tokens"] = context if type(context) is int and context > 0 else None
            status["message"] = "Local Apertus is ready." if status["local"] else "The selected Apertus model is available."
    except Exception:
        status["message"] = "The model could not be reached. Start the local runtime or check its configuration."
    return status
