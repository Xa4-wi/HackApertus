"""Official JSONL batch interface for live Apertus inference."""

import argparse
import json
import math
import os
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from .booklets import prepare_case, require_text
from .config import Settings, load_dotenv
from .engine import check_claim
from .models import ClaimLensError, ValidationError


def prediction_record(case_id, result):
    """Only the submission schema crosses this boundary, never UI metadata."""
    if result.get("validation_degraded"):
        raise ValidationError("Model output failed claim or citation validation; refusing to export it as a neutral prediction.")
    metrics = result["metrics"]
    required_metrics = {"input_tokens": metrics.get("input_tokens"),
                        "output_tokens": metrics.get("output_tokens"),
                        "inference_time_ms": metrics.get("inference_time_ms")}
    for key, value in required_metrics.items():
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValidationError("The provider did not report valid {}. Official predictions require actual usage and time; no estimate was substituted.".format(key))
    sources = {passage["id"]: passage for passage in result["passages"]}
    evidence, seen = [], set()
    if result["classification"] != 1:
        # The full-claim check drives NLI; diagnostic subchecks must not displace it.
        for check in result["checks"][:1]:
            if check["text"] != result["claim"] or check["dimension"] != "general":
                continue
            for citation in check["evidence"]:
                source = sources[citation["passage_id"]]
                key = (source["page"], citation["quote"])
                if key not in seen:
                    evidence.append({"page": source["page"], "text": citation["quote"]})
                    seen.add(key)
    return {"id": case_id, "label": result["classification"], "label_name": result["overall"],
            "evidence": evidence[:5], "metrics": required_metrics}


def _attempt_metrics(attempts, started):
    """Unknown usage stays unknown, even if a subsequent attempt succeeds."""
    metrics = dict(attempts[-1]) if attempts else {}
    for name in ("input_tokens", "output_tokens"):
        values = [entry.get(name) for entry in attempts]
        complete = all(type(value) in (int, float) and math.isfinite(value) and value >= 0
                       for value in values)
        metrics[name] = sum(values) if complete else None
        known_values = [entry.get("known_" + name, entry.get(name)) for entry in attempts]
        metrics["known_" + name] = sum(value for value in known_values
                                      if type(value) in (int, float) and math.isfinite(value) and value >= 0)
    elapsed = time.monotonic() - started
    metrics.update({"inference_time_ms": round(elapsed * 1000, 3),
                    "inference_seconds": round(elapsed, 6),
                    "model_request_attempts": sum(entry.get("model_request_attempts", 1) for entry in attempts),
                    "token_usage_source": "provider" if all(metrics[key] is not None for key in
                        ("input_tokens", "output_tokens")) else "incomplete_provider_usage"})
    return metrics


def predict_case(case, settings, data_root, cache=None):
    """Return (official prediction, detailed result) through one shared path.

    A malformed verdict gets one recovery attempt when its actual usage is
    known. The complete case, including recovery, shares one document deadline.
    Exceptions carry metrics/attempts for evaluation diagnostics; unsuccessful
    inference is never converted into a neutral prediction.
    """
    started, attempts, calls = time.monotonic(), [], 0
    try:
        deadline = (started + min(settings.document_timeout, settings.retrieval_timeout)
                    if settings.document_strategy == "retrieval" and isinstance(case, dict) and "booklet" in case else None)
        options = {"deadline": deadline} if deadline is not None else {}
        proposal, claim, language = prepare_case(case, data_root, cache, **options)
        fast_booklet = settings.document_strategy == "retrieval" and proposal.get("source_kind") != "reference"
        case_timeout = min(settings.document_timeout, settings.retrieval_timeout) if fast_booklet else settings.document_timeout
        call_limit = min(settings.max_document_model_calls, 4) if fast_booklet else settings.max_document_model_calls
        for warning in proposal.get("warnings", []):
            print("ClaimLens source warning: " + warning, file=sys.stderr)
        for attempt in range(1 if fast_booklet else 2):
            remaining = case_timeout - (time.monotonic() - started)
            if remaining <= 0 or calls >= call_limit:
                raise ValidationError("The case exhausted its inference time or model-call budget before recovery.")
            bounded = replace(settings, document_timeout=remaining,
                              timeout=min(settings.timeout, remaining),
                              max_document_model_calls=call_limit - calls)
            try:
                result = check_claim(proposal, claim, settings.model, "live", bounded,
                                     claim_language=language)
            except ClaimLensError as error:
                failed_metrics = getattr(error, "metrics", None) or {
                    "input_tokens": None, "output_tokens": None,
                    "model_request_attempts": getattr(error, "attempts", 0)}
                attempts.append(failed_metrics)
                calls += failed_metrics.get("model_request_attempts", getattr(error, "attempts", 1))
                if (not fast_booklet and attempt == 0 and isinstance(error, ValidationError) and
                        getattr(error, "retryable", True) and calls > 0 and
                        all(type(failed_metrics.get(key)) in (int, float) and
                            math.isfinite(failed_metrics[key]) and failed_metrics[key] >= 0
                            for key in ("input_tokens", "output_tokens"))):
                    print("ClaimLens: retrying case {} after invalid model structure.".format(
                        json.dumps(case["id"], ensure_ascii=False)), file=sys.stderr)
                    continue
                raise
            attempts.append(result["metrics"])
            calls += result["metrics"].get("model_request_attempts", result.get("processing", {}).get("model_calls", 1))
            result["metrics"] = _attempt_metrics(attempts, started)
            result.setdefault("processing", {}).update({"model_calls": calls,
                                                        "classification_attempts": attempt + 1})
            try:
                record = prediction_record(case["id"], result)
            except ValidationError:
                if (not fast_booklet and attempt == 0 and result.get("validation_degraded") and
                        all(result["metrics"].get(key) is not None for key in
                            ("input_tokens", "output_tokens"))):
                    print("ClaimLens: retrying case {} after invalid model evidence or verdict.".format(
                        json.dumps(case["id"], ensure_ascii=False)), file=sys.stderr)
                    continue
                raise
            if attempt:
                result.setdefault("warnings", []).append(
                    "An invalid model verdict was retried. Reported usage and time include every attempt.")
            return record, result
    except ClaimLensError as error:
        error.metrics = _attempt_metrics(attempts, started)
        error.attempts = error.metrics["model_request_attempts"]
        error.classification_attempts = len(attempts)
        raise


def _write_predictions(path, predictions):
    """Replace one JSONL atomically; interruption never leaves a partial line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as output:
            temporary = output.name
            for prediction in predictions:
                output.write(json.dumps(prediction, ensure_ascii=False) + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def run_batch(input_path, output_path, settings, data_root=None):
    input_path, output_path = Path(input_path), Path(output_path)
    checkpoint = output_path.with_name(output_path.name + ".partial.jsonl")
    if input_path.resolve() in (output_path.resolve(), checkpoint.resolve()):
        raise ValidationError("Input and output paths must differ.")
    if not settings.base_url:
        raise ValidationError("Live inference needs BASE_URL (or LLM_BASE_URL); configure an API key only if the endpoint requires one.")
    if data_root is None:
        data_root = Path("/data") if Path("/data").is_dir() else input_path.resolve().parent
    cache, seen_ids, cases, predictions, failures = {}, set(), [], [], []
    # Reject malformed JSON and ambiguous IDs before inference or file changes.
    with input_path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                case = json.loads(line)
                if not isinstance(case, dict):
                    raise ValidationError("Each input line must be a JSON object.")
                require_text(case.get("id"), "id", 256)
                if case["id"] in seen_ids:
                    raise ValidationError("Input IDs must be unique.")
                seen_ids.add(case["id"])
                cases.append((line_number, case))
            except (ClaimLensError, ValueError) as exc:
                raise ValidationError("Input line {}: {}".format(line_number, exc)) from None
    if not cases:
        raise ValidationError("Input JSONL has no cases.")
    # This file belongs to the new, validated input batch; never expose stale
    # successes from an earlier invocation as this run's checkpoint.
    _write_predictions(checkpoint, [])
    for line_number, case in cases:
        try:
            prediction, _ = predict_case(case, settings, data_root, cache)
            predictions.append(prediction)
            _write_predictions(checkpoint, predictions)
        except ClaimLensError as error:
            diagnostic = {"line": line_number, "id": case["id"], "error": str(error),
                          "metrics": getattr(error, "metrics", None),
                          "attempts": getattr(error, "attempts", 0)}
            failures.append(diagnostic)
            print("ClaimLens case failed: " + json.dumps(diagnostic, ensure_ascii=False), file=sys.stderr)
    if failures:
        raise ValidationError("{} of {} cases failed; {} successful predictions {}. First failure: {}".format(
            len(failures), len(cases), len(predictions),
            "saved to " + str(checkpoint) if predictions else "were produced",
            failures[0]["error"]))
    _write_predictions(output_path, predictions)
    checkpoint.unlink(missing_ok=True)
    return len(predictions)


def main(argv=None):
    parser = argparse.ArgumentParser(description="ClaimLens — OST Swiss voting booklet NLI")
    parser.add_argument("command", nargs="?", choices=("serve",), help="Start the local web prototype")
    parser.add_argument("--input", type=Path, help="Official request JSONL")
    parser.add_argument("--output", type=Path, help="Official prediction JSONL")
    parser.add_argument("--data-root", type=Path, help="PDF directory (default: /data in Docker, otherwise input directory)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    try:
        load_dotenv()
        settings = Settings.from_env()
        if args.command == "serve":
            from .server import serve
            serve(settings, args.host, args.port)
        else:
            if not args.input or not args.output:
                parser.error("supply --input and --output, or use the serve command")
            count = run_batch(args.input, args.output, settings, args.data_root)
            print("Wrote {} predictions to {}".format(count, args.output), file=sys.stderr)
        return 0
    except ClaimLensError as exc:
        print("ClaimLens: " + str(exc), file=sys.stderr)
        return 2
    except (OSError, UnicodeError):
        print("ClaimLens: could not read or write the requested local files. Check paths, permissions, and UTF-8 encoding.", file=sys.stderr)
        return 2
