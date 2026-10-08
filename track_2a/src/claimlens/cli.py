"""Official JSONL batch interface plus an explicitly marked offline walkthrough."""

import argparse
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

from .booklets import prepare_case
from .config import Settings, load_dotenv
from .corpus import load_corpus
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


def demo_proposal(proposal, claim, corpus):
    # Exact source AND claim matching: changing either cannot reuse a stored label.
    texts = [passage["text"] for passage in proposal["passages"]]
    for candidate in corpus:
        if (candidate.get("vote", candidate["title"]) == proposal["title"] and
                candidate["language"] == proposal["language"] and
                texts == [p["text"] for p in candidate["passages"]]):
            if any(example["claim"] == claim for example in candidate["examples"]):
                return candidate
    raise ValidationError("Offline CLI demo only accepts bundled demo-cases.jsonl references and claims. Use the default live mode for new cases.")


def run_batch(input_path, output_path, settings, data_root=None, demo=False):
    input_path, output_path = Path(input_path), Path(output_path)
    if input_path.resolve() == output_path.resolve():
        raise ValidationError("Input and output paths must differ.")
    if not demo and not settings.base_url:
        raise ValidationError("Live inference needs BASE_URL (or LLM_BASE_URL); configure an API key only if the endpoint requires one. Use --demo for the bundled offline walkthrough.")
    if data_root is None:
        data_root = Path("/data") if Path("/data").is_dir() else input_path.resolve().parent
    corpus = load_corpus() if demo else []
    cache, seen_ids, predictions = {}, set(), []
    with input_path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                started = time.perf_counter()
                case = json.loads(line)
                proposal, claim, claim_language = prepare_case(case, data_root, cache)
                for warning in proposal.get("warnings", []):
                    print("ClaimLens source warning: " + warning, file=sys.stderr)
                if case["id"] in seen_ids:
                    raise ValidationError("Input IDs must be unique.")
                seen_ids.add(case["id"])
                if demo:
                    proposal = demo_proposal(proposal, claim, corpus)
                result = check_claim(proposal, claim, settings.model, "demo" if demo else "live", settings,
                                     claim_language=claim_language)
                result["metrics"]["inference_time_ms"] = (time.perf_counter() - started) * 1000
                predictions.append(prediction_record(case["id"], result))
            except (ClaimLensError, ValueError) as exc:
                # The entire batch fails; infrastructure failures are never neutral predictions.
                raise ValidationError("Input line {}: {}".format(line_number, exc)) from None
    if not predictions:
        raise ValidationError("Input JSONL has no cases.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output_path.parent, delete=False) as output:
            temporary = output.name
            for prediction in predictions:
                output.write(json.dumps(prediction, ensure_ascii=False) + "\n")
        os.replace(temporary, output_path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return len(predictions)


def main(argv=None):
    parser = argparse.ArgumentParser(description="ClaimLens — OST Swiss voting booklet NLI")
    parser.add_argument("command", nargs="?", choices=("serve",), help="Start the local web prototype")
    parser.add_argument("--input", type=Path, help="Official request JSONL")
    parser.add_argument("--output", type=Path, help="Official prediction JSONL")
    parser.add_argument("--data-root", type=Path, help="PDF directory (default: /data in Docker, otherwise input directory)")
    parser.add_argument("--demo", action="store_true", help="Replay bundled examples without inference; never use for evaluation")
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
            count = run_batch(args.input, args.output, settings, args.data_root, args.demo)
            prefix = "OFFLINE DEMO (prewritten labels; no model call). " if args.demo else ""
            print("{}Wrote {} predictions to {}".format(prefix, count, args.output), file=sys.stderr)
        return 0
    except ClaimLensError as exc:
        print("ClaimLens: " + str(exc), file=sys.stderr)
        return 2
    except (OSError, UnicodeError):
        print("ClaimLens: could not read or write the requested local files. Check paths, permissions, and UTF-8 encoding.", file=sys.stderr)
        return 2
