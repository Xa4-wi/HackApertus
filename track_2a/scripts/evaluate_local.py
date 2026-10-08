#!/usr/bin/env python3
"""Prepare, run and score a reproducible development evaluation, never training.

Gold labels are used only for stratified sampling and scoring. run_cases receives
only unlabeled inputs, and records failures instead of fabricating predictions.
"""

import argparse
import hashlib
import json
import math
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from claimlens.booklets import prepare_case
from claimlens.cli import prediction_record
from claimlens.config import Settings, load_dotenv
from claimlens.engine import check_claim
from claimlens.models import ClaimLensError


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    Path(path).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def fingerprint(case):
    return hashlib.sha256(json.dumps({k: v for k, v in case.items() if k != "id"},
                                    ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def index_ids(rows, kind):
    indexed = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip():
            raise ValueError("{} rows must have nonempty string IDs.".format(kind))
        if row["id"] in indexed:
            raise ValueError("Duplicate {} ID: {}".format(kind.lower(), row["id"]))
        indexed[row["id"]] = row
    return indexed


def evaluation_targets(inputs, gold):
    cases, targets = index_ids(inputs, "Input"), index_ids(gold, "Gold")
    if not cases or set(cases) != set(targets):
        raise ValueError("Nonempty input and gold files must have exactly matching IDs.")
    if any(type(row.get("label")) is not int or row["label"] not in range(3) for row in targets.values()):
        raise ValueError("Gold labels must be integers 0, 1, or 2.")
    return targets


def select_cases(inputs, gold, per_stratum=1, seed="20261008"):
    targets = evaluation_targets(inputs, gold)
    strata, seen = defaultdict(list), {}
    for case in inputs:
        digest = fingerprint(case)
        target = targets[case["id"]]
        if digest in seen:
            if seen[digest] != target["label"]:
                raise ValueError("Identical requests have conflicting gold labels.")
            continue
        seen[digest] = target["label"]
        source = case.get("reference", case.get("booklet"))
        key = (case["claim"]["language"], source["language"], target["label"])
        rank = hashlib.sha256((seed + digest).encode()).hexdigest()
        strata[key].append((rank, case, target))
    expected = {(claim, source, label) for claim in ("de", "fr", "it")
                for source in ("de", "fr", "it") for label in range(3)}
    if set(strata) != expected or any(len(rows) < per_stratum for rows in strata.values()):
        raise ValueError("Every language pair and label must have enough distinct requests.")
    selected = [item for key in sorted(strata) for item in sorted(strata[key])[:per_stratum]]
    return [item[1] for item in selected], [item[2] for item in selected]


def run_identity(inputs, settings):
    """Public helper for an explicit run manifest; never contains credentials.

    The known local artifact identifies the intended, pinned setup. Its alias
    does not attest which weights a running inference server actually loaded.
    """
    source_hash = hashlib.sha256(b"".join(path.read_bytes() for path in sorted(
        (PROJECT_ROOT / "src" / "claimlens").glob("*.py")))).hexdigest()
    served_model = settings.model_for_request(settings.model)
    artifact = {"runtime_verified": False,
                "note": "The model ID does not independently attest the runtime's loaded weights."}
    if settings.local_model_configured and served_model == "claimlens-apertus-v1.5-8b-q4":
        artifact.update({"intended_repository": "Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF",
                         "intended_revision": "248ec68a63e219e3f061e4c946fc8a20d63b9975",
                         "intended_sha256": "a037df8d87ff6caacee794ee85f55342f2152e0d359b7389033300c3bee5f299"})
    return {"schema_version": 2, "source_sha256": source_hash, "model": settings.model,
            "served_model": served_model, "model_artifact": artifact,
            "endpoint_sha256": hashlib.sha256(settings.base_url.encode()).hexdigest(),
            "request_timeout_seconds": settings.timeout,
            "document_timeout_seconds": getattr(settings, "document_timeout", None),
            "max_document_model_calls": getattr(settings, "max_document_model_calls", None),
            "context_tokens": getattr(settings, "context_tokens", None),
            "document_strategy": settings.document_strategy,
            "retrieval_prompt_tokens": settings.retrieval_prompt_tokens,
            "retrieval_timeout_seconds": settings.retrieval_timeout,
            "input_sha256": hashlib.sha256(Path(inputs).read_bytes()).hexdigest()}


def run_cases(inputs, output, settings, data_root, resume=False):
    output = Path(output)
    cases = read_jsonl(inputs)
    case_ids = set(index_ids(cases, "Input"))
    identity = run_identity(inputs, settings)
    identity_path = output.with_suffix(".run.json")
    records = []
    if output.exists():
        if not resume:
            raise ValueError("Results already exist; use --resume or a new output directory.")
        if not identity_path.exists() or json.loads(identity_path.read_text()) != identity:
            raise ValueError("Run identity is missing or changed (code, model, endpoint, limits, or inputs). Use a new output directory; old manifests are not migrated automatically.")
        records = read_jsonl(output)
        recorded_ids = set(index_ids(records, "Recorded result"))
        if not recorded_ids.issubset(case_ids):
            raise ValueError("Recorded results contain unknown input IDs; refusing to resume this run.")
    else:
        write_json(identity_path, identity)
    done = {row["id"] for row in records}
    cache = {}
    with output.open("a", encoding="utf-8") as stream:
        for position, case in enumerate(cases, 1):
            if case["id"] in done:
                continue
            start, result = time.perf_counter(), None
            record = {"id": case["id"], "status": "failed", "prediction": None}
            try:
                proposal, claim, language = prepare_case(case, data_root, cache)
                result = check_claim(proposal, claim, settings.model, "live", settings, claim_language=language)
                result["metrics"]["inference_time_ms"] = (time.perf_counter() - start) * 1000
                record["prediction"] = prediction_record(case["id"], result)
                record["status"] = "accepted"
            except (ClaimLensError, ValueError, OSError) as error:
                record["error"] = str(error)
            record["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
            if result is not None:
                record["metrics"] = result["metrics"]
                record["warnings"] = result.get("warnings", [])
                record["processing"] = result.get("processing", {})
                record["validation_degraded"] = result.get("validation_degraded", False)
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            records.append(record)
            print("{}/{} {} {} ({:.1f}s)".format(position, len(cases), case["id"], record["status"],
                  record["elapsed_ms"] / 1000), flush=True)
    return records


def score_records(inputs, gold, records):
    targets = {key: row["label"] for key, row in evaluation_targets(inputs, gold).items()}
    grouped = defaultdict(list)
    for row in records:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip():
            raise ValueError("Result records must have nonempty string IDs.")
        grouped[row["id"]].append(row)
    duplicate_ids = sorted(key for key, rows in grouped.items() if len(rows) > 1)
    unknown_ids = sorted(set(grouped) - set(targets))
    matrix = [[0] * 4 for _ in range(3)]  # Last column = failure/missing output.
    pairs, errors, times, tokens = {}, Counter(), [], Counter()
    valid_quotes, nonneutral, metric_rows = 0, 0, 0
    for case in inputs:
        target = targets[case["id"]]
        matches = grouped.get(case["id"], [])
        row = matches[0] if len(matches) == 1 else {}
        prediction = row.get("prediction") if row.get("status") == "accepted" else None
        error = "Duplicate result ID; no prediction accepted." if len(matches) > 1 else row.get("error", "No prediction produced.")
        if prediction is not None and (not isinstance(prediction, dict)
                                       or type(prediction.get("label")) is not int
                                       or prediction["label"] not in range(3)):
            prediction, error = None, "Invalid predicted label; expected integer 0, 1, or 2."
        label = prediction["label"] if prediction else 3
        matrix[target][label] += 1
        source = case.get("reference", case.get("booklet"))
        key = case["claim"]["language"] + "→" + source["language"]
        pair = pairs.setdefault(key, {"cases": 0, "accepted": 0, "correct": 0})
        pair["cases"] += 1
        pair["accepted"] += prediction is not None
        pair["correct"] += label == target
        if not prediction:
            errors[error if isinstance(error, str) else "No prediction produced."] += 1
        elif label != 1:
            nonneutral += 1
            valid_quotes += bool(prediction.get("evidence"))
        elapsed = row.get("elapsed_ms")
        if type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0:
            times.append(elapsed)
        metrics = row.get("metrics", {})
        if isinstance(metrics, dict) and all(type(metrics.get(key)) is int and metrics[key] >= 0
                                             for key in ("input_tokens", "output_tokens")):
            metric_rows += 1
            tokens.update({key: metrics[key] for key in ("input_tokens", "output_tokens")})
    classes = []
    for label, name in enumerate(("entailment", "neutral", "contradiction")):
        tp = matrix[label][label]
        fp = sum(matrix[other][label] for other in range(3) if other != label)
        fn = sum(matrix[label]) - tp  # Failures count against the expected class.
        classes.append({"label": label, "name": name, "support": sum(matrix[label]),
                        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0})
    accepted = sum(sum(row[:3]) for row in matrix)
    return {"recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "evaluation_type": "Stratified development sample; not held-out or an official benchmark",
            "cases": len(inputs), "accepted": accepted, "failures": len(inputs) - accepted,
            "accuracy_including_failures": sum(matrix[i][i] for i in range(3)) / len(inputs),
            "macro_f1_including_failures": sum(row["f1"] for row in classes) / 3,
            "classes": classes, "confusion_columns": ["entailment", "neutral", "contradiction", "failure"],
            "confusion_matrix": matrix, "language_pairs": pairs, "errors": dict(errors),
            "duplicate_output_ids": duplicate_ids, "duplicate_id_count": len(duplicate_ids),
            "duplicate_record_count": sum(len(grouped[key]) - 1 for key in duplicate_ids),
            "unknown_output_ids": unknown_ids,
            "unknown_output_count": sum(len(grouped[key]) for key in unknown_ids),
            "mean_case_ms": sum(times) / len(times) if times else None,
            "recorded_tokens": dict(tokens), "cases_with_token_metrics": metric_rows,
            "token_note": "Usage for failures before metrics return is unavailable. Totals cover unambiguous known result records only; duplicate and unknown IDs are excluded.",
            "accepted_nonneutral_with_quotes": valid_quotes, "accepted_nonneutral": nonneutral,
            "evidence_note": "Exact source presence is checked; semantic relevance and official Task A evidence overlap are not scored."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "score"))
    parser.add_argument("--directory", type=Path, default=PROJECT_ROOT / "output" / "v2-evaluation")
    parser.add_argument("--source-input", type=Path, default=PROJECT_ROOT / "data/local/ost/input/reference-train.jsonl")
    parser.add_argument("--source-gold", type=Path, default=PROJECT_ROOT / "data/local/ost/gold/reference-train.gold.jsonl")
    parser.add_argument("--per-stratum", type=int, default=1)
    parser.add_argument("--seed", default="20261008")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    if not 1 <= args.per_stratum <= 10:
        parser.error("--per-stratum must be between 1 and 10")
    root = args.directory
    root.mkdir(parents=True, exist_ok=True)
    inputs, gold, records = root / "input.jsonl", root / "gold.jsonl", root / "results.jsonl"
    if args.command == "prepare":
        if any((root / name).exists() for name in ("input.jsonl", "gold.jsonl", "results.jsonl")):
            parser.error("evaluation files already exist; choose another directory")
        cases, targets = select_cases(read_jsonl(args.source_input), read_jsonl(args.source_gold), args.per_stratum, args.seed)
        write_jsonl(inputs, cases)
        write_jsonl(gold, targets)
        write_json(root / "selection.json", {"seed": args.seed, "cases": len(cases), "per_pair_and_label": args.per_stratum,
                   "duplicates_removed": True, "stratified_using_labels": True,
                   "note": "Fixed before inference. Gold files are never passed to the model."})
        print("Prepared {} development cases across all nine language pairs.".format(len(cases)))
    else:
        if args.command == "run":
            load_dotenv()
            run_cases(inputs, records, Settings.from_env(), args.data_root or inputs.parent, args.resume)
        report = score_records(read_jsonl(inputs), read_jsonl(gold), read_jsonl(records))
        write_json(root / "summary.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
