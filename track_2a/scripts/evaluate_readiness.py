#!/usr/bin/env python3
"""Freeze date-separated public-data checks, run the CLI pipeline, score officially.

These are local public-data holdouts, never the organizers' private benchmark.
Only ``prepare`` and ``score`` read gold; ``run`` receives input cases alone.
Install requirements-dev.txt to execute the unmodified official scorer.
Preparation requires preserved prior inputs from the local repository archive,
or an explicit --prior-inputs file; these artifacts are not in clean checkouts.
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unicodedata

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARCHIVED_OUTPUT = PROJECT_ROOT.parent / "archive/track_2a/output"
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from evaluate_local import evaluation_targets, fingerprint, index_ids, read_jsonl, run_identity, write_json, write_jsonl
from claimlens.config import Settings, load_dotenv
from claimlens.models import ClaimLensError

LANGUAGES = ("de", "fr", "it")
DATASET_REVISION = "fc2b27600310778da6bbf445651ddbca22d86269"
OFFICIAL_URL = "https://gitlab.com/ifsoftware/hackapertus-starter/-/raw/main/evaluate.py"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def claim_key(row):
    text = " ".join(unicodedata.normalize("NFKC", row["claim"]).casefold().split())
    return row["claim_language"], text


def request_for(row, case_id):
    return {"id": case_id, "vote": row["vote"],
            "claim": {"text": row["claim"], "language": row["claim_language"]},
            "reference": {"text": row["reference_string"], "language": row["reference_language"]}}


def stratum(row):
    # Same orientation as the official evaluator: source -> claim.
    return row["reference_language"], row["claim_language"], row["entailment_label"]


def ranked_rows(rows, seed):
    seen = {}
    for index, row in enumerate(rows):
        case = request_for(row, "unused")
        digest = fingerprint(case)
        if digest in seen:
            if seen[digest][1]["entailment_label"] != row["entailment_label"]:
                raise ValueError("Duplicate requests have conflicting gold labels.")
            continue
        seen[digest] = (index, row)
    return sorted(seen.values(), key=lambda item: hashlib.sha256(
        (seed + fingerprint(request_for(item[1], "unused"))).encode()).hexdigest())


def select_stratified(candidates, per_stratum=1, forbidden_claims=None, sparse=False):
    excluded = forbidden_claims or set()
    pools = defaultdict(list)
    for index, row in candidates:
        if claim_key(row) not in excluded:
            pools[stratum(row)].append((index, row))
    selected = []
    for source_index, source in enumerate(LANGUAGES):
        for claim_index, claim in enumerate(LANGUAGES):
            labels = [(source_index + claim_index) % 3] if sparse else range(3)
            for label in labels:
                key = source, claim, label
                # Never pad a stratum with duplicate requests.
                if len(pools[key]) < per_stratum:
                    raise ValueError("Insufficient distinct holdout cases for {}.".format(key))
                selected.extend(pools[key][:per_stratum])
    return selected


def split_rows(rows, prior_inputs, seed, smoke_dates=("2024-03-03",)):
    """Group all translations/proposals from one ballot date on the same side.

    Date groups are stricter than translated vote titles. Previously exercised
    dates (including the known full-booklet smoke) are development-only.
    """
    prior = {fingerprint(case) for case in prior_inputs}
    dates = set(smoke_dates)
    found = set()
    for row in rows:
        key = fingerprint(request_for(row, "unused"))
        if key in prior:
            dates.add(row["booklet_publish_date"])
            found.add(key)
    if prior - found:
        raise ValueError("Previously evaluated cases do not match this pinned dataset.")
    candidates = ranked_rows(rows, seed)
    development = [(i, row) for i, row in candidates
                   if row["booklet_publish_date"] in dates
                   and fingerprint(request_for(row, "unused")) not in prior]
    final = [(i, row) for i, row in candidates if row["booklet_publish_date"] not in dates]
    selected_b = select_stratified(final, per_stratum=2)
    # The first and second ranked request in each stratum make separate,
    # frozen 27-case cohorts; the extension is not a replacement after scoring.
    primary, extension = selected_b[::2], selected_b[1::2]
    selected_a = select_stratified(final, forbidden_claims={claim_key(row) for _, row in selected_b}, sparse=True)
    return {"development": select_stratified(development), "final-b": primary,
            "final-b-extension": extension, "final-a": selected_a}, sorted(dates)


def library_index(library):
    result = {}
    for path in sorted(Path(library).glob("*/document.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for url in document.get("source_urls", [document.get("source_url")]):
            if url:
                result[(url, document["language"])] = (path.parent / "original.pdf", document)
    return result


def prepare(args):
    root = args.directory
    if root.exists() and any(root.iterdir()):
        raise ValueError("Choose an empty evaluation directory; frozen cases are never overwritten.")
    if not args.prior_inputs.is_file():
        raise ValueError("Preserved prior inputs are missing: {}. Restore the local evaluation archive "
                         "or pass --prior-inputs with the original inputs; do not substitute a new cohort."
                         .format(args.prior_inputs))
    from datasets import load_from_disk

    manifest = json.loads((args.dataset / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("revision") != DATASET_REVISION:
        raise ValueError("This preparation requires the pinned OST dataset revision.")
    rows = list(load_from_disk(str(args.dataset / "dataset"))["train"])
    cohorts, excluded_dates = split_rows(rows, read_jsonl(args.prior_inputs), args.seed)
    library = library_index(args.library)
    # Resolve every PDF before creating the frozen directory.
    for _, row in cohorts["final-a"]:
        key = row["booklet_url"], row["reference_language"]
        if key not in library or not library[key][0].is_file():
            raise ValueError("A selected full booklet is not present in the local library.")
    if not args.evaluator.is_file():
        raise ValueError("Supply the downloaded official starter evaluate.py using --evaluator.")
    root.mkdir(parents=True, exist_ok=True)
    official = root / "official"
    official.mkdir()
    shutil.copyfile(args.evaluator, official / "evaluate.py")
    write_json(official / "source.json", {"source_url": OFFICIAL_URL, "sha256": sha256(args.evaluator),
               "downloaded_snapshot": "Unmodified downloaded starter evaluator; pinned by content hash",
               "copied_at_utc": datetime.now(timezone.utc).isoformat()})
    selections = {}
    for name, chosen in cohorts.items():
        folder = root / name
        (folder / "input" / "booklets").mkdir(parents=True)
        (folder / "gold").mkdir()
        cases, gold, sources = [], [], []
        for index, row in chosen:
            task = "A" if name == "final-a" else "B"
            case_id = "ost-train-{:06d}-{}".format(index, task)
            case = request_for(row, case_id)
            target = {"id": case_id, "label": row["entailment_label"], "reference": row["reference_string"]}
            origin = {"id": case_id, "dataset_row": index, "ballot_date": row["booklet_publish_date"],
                      "source_url": row["booklet_url"]}
            if task == "A":
                pdf, metadata = library[(row["booklet_url"], row["reference_language"])]
                relative = "booklets/{}.pdf".format(metadata["id"])
                dest = folder / "input" / relative
                if not dest.exists():
                    shutil.copyfile(pdf, dest)
                case.pop("reference")
                case["booklet"] = {"path": relative, "language": row["reference_language"]}
                origin.update({"pdf_sha256": sha256(dest), "pdf_pages": metadata["page_count"]})
            cases.append(case)
            gold.append(target)
            sources.append(origin)
        write_jsonl(folder / "input/cases.jsonl", cases)
        write_jsonl(folder / "gold/expected.jsonl", gold)
        selection = {"cohort": name, "cases": len(cases), "seed": args.seed,
                     "input_sha256": sha256(folder / "input/cases.jsonl"),
                     "gold_sha256": sha256(folder / "gold/expected.jsonl"),
                     "sources": sources, "gold_used_only_for_selection_and_scoring": True,
                     "strata_source_to_claim_label": dict(Counter("{}->{}:{}".format(*stratum(row)) for _, row in chosen))}
        write_json(folder / "selection.json", selection)
        selections[name] = {key: value for key, value in selection.items() if key not in ("sources", "strata_source_to_claim_label")}
    write_json(root / "split.json", {"dataset": manifest["dataset"], "revision": DATASET_REVISION,
        "dataset_manifest_sha256": sha256(args.dataset / "manifest.json"),
        "local_dataset_arrow_sha256": {str(path.relative_to(args.dataset)): sha256(path)
                                      for path in sorted((args.dataset / "dataset").rglob("*.arrow"))},
        "prior_inputs_sha256": sha256(args.prior_inputs), "seed": args.seed,
        "development_dates": excluded_dates, "final_dates": sorted({row["booklet_publish_date"] for _, row in cohorts["final-b"] + cohorts["final-a"] + cohorts["final-b-extension"]}),
        "split_unit": "ballot publication date, grouping all source languages and proposals",
        "case_deduplication": "identical input requests; normalized same-language claim excluded across final A and B",
        "limitations": "Public dataset only. No assurance against model pretraining exposure. Small local holdout; not the private benchmark. Task A keeps upstream reference-task labels, as in official preparation.",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(), "cohorts": selections})
    print("Frozen development27, finalB27, additionalB27, finalA9. Gold is stored separately.")


def validate_frozen_inputs(folder):
    selection = json.loads((folder / "selection.json").read_text(encoding="utf-8"))
    path = folder / "input/cases.jsonl"
    if sha256(path) != selection["input_sha256"]:
        raise ValueError("Frozen input cases have changed.")
    cases = read_jsonl(path)
    index_ids(cases, "Input")
    origins = {row["id"]: row for row in selection["sources"]}
    for case in cases:
        if "booklet" in case:
            pdf = folder / "input" / case["booklet"]["path"]
            if sha256(pdf) != origins[case["id"]]["pdf_sha256"]:
                raise ValueError("Frozen input PDF has changed.")
    return cases, selection


def export_predictions(records, path):
    predictions = [row["prediction"] for row in records if row.get("status") == "accepted"]
    temporary = path.with_suffix(".tmp")
    write_jsonl(temporary, predictions)
    temporary.replace(path)


def run(folder, settings, resume=False):
    from claimlens.cli import predict_case

    cases, _ = validate_frozen_inputs(folder)
    records_path = folder / "results.jsonl"
    identity = run_identity(folder / "input/cases.jsonl", settings)
    identity["readiness_runner_sha256"] = sha256(__file__)
    identity_path = folder / "results.run.json"
    records = []
    if records_path.exists():
        if not resume or not identity_path.exists() or json.loads(identity_path.read_text()) != identity:
            raise ValueError("Results exist or run identity changed; resume only unchanged code, model, limits and inputs.")
        records = read_jsonl(records_path)
        if not set(index_ids(records, "Recorded result")).issubset(index_ids(cases, "Input")):
            raise ValueError("Recorded results contain unknown IDs.")
    else:
        write_json(identity_path, identity)
    done, cache = {record["id"] for record in records}, {}
    with records_path.open("a", encoding="utf-8") as stream:
        for position, case in enumerate(cases, 1):
            if case["id"] in done:
                continue
            if run_identity(folder / "input/cases.jsonl", settings) != {key: value for key, value in identity.items() if key != "readiness_runner_sha256"}:
                raise ValueError("Inference code changed during the run; stop and preserve these results.")
            started = time.perf_counter()
            record = {"id": case["id"], "status": "failed", "prediction": None}
            try:
                prediction, result = predict_case(case, settings, folder / "input", cache)
                record.update({"status": "accepted", "prediction": prediction, "metrics": result["metrics"],
                               "warnings": result.get("warnings", []), "processing": result.get("processing", {})})
            except (ClaimLensError, ValueError, OSError) as error:
                record.update({"error": str(error), "metrics": getattr(error, "metrics", {}),
                               "attempts": getattr(error, "attempts", None)})
            record["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            records.append(record)
            export_predictions(records, folder / "predictions.jsonl")
            print("{}/{} {} {} ({:.1f}s)".format(position, len(cases), case["id"], record["status"], record["elapsed_ms"] / 1000), flush=True)
    return records


def percentile(values, probability):
    if not values:
        return None
    ordered = sorted(values)
    # Nearest-rank percentile, explicitly useful even for the nine-case smoke.
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def timing_summary(cases, records):
    known = set(index_ids(cases, "Input"))
    indexed = index_ids(records, "Result")
    unknown = sorted(set(indexed) - known)
    if unknown:
        raise ValueError("Results contain unknown case IDs.")
    times, totals, complete_usage = [], Counter(), 0
    for record in records:
        elapsed = record.get("elapsed_ms")
        if type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0:
            times.append(elapsed)
        metrics = record.get("metrics", {})
        if all(type(metrics.get(key)) in (int, float) and math.isfinite(metrics[key]) and metrics[key] >= 0 for key in ("input_tokens", "output_tokens")):
            complete_usage += 1
            totals.update({key: metrics[key] for key in ("input_tokens", "output_tokens")})
    return {"cases": len(cases), "recorded": len(records),
            "failed_or_missing_cases": sum(indexed.get(case["id"], {}).get("status") != "accepted" for case in cases),
            "mean_case_ms": sum(times) / len(times) if times else None,
            "p95_case_ms": percentile(times, 0.95), "p95_method": "nearest rank",
            "maximum_case_ms": max(times) if times else None, "total_recorded_tokens": dict(totals),
            "cases_with_complete_token_metrics": complete_usage,
            "usage_note": "Known usage only; failures without provider usage are not counted as zero tokens. Includes retry usage when reported by the shared CLI pipeline."}


def score(folder, evaluator=None):
    cases, selection = validate_frozen_inputs(folder)
    gold_path = folder / "gold/expected.jsonl"
    if sha256(gold_path) != selection["gold_sha256"]:
        raise ValueError("Frozen gold labels have changed.")
    evaluation_targets(cases, read_jsonl(gold_path))
    records = read_jsonl(folder / "results.jsonl")
    timing = timing_summary(cases, records)
    export_predictions(records, folder / "predictions.jsonl")
    evaluator = evaluator or folder.parent / "official/evaluate.py"
    provenance = json.loads((evaluator.parent / "source.json").read_text())
    if sha256(evaluator) != provenance["sha256"]:
        raise ValueError("Official evaluator differs from its frozen snapshot.")
    process = subprocess.run([sys.executable, str(evaluator), "--predictions", str(folder / "predictions.jsonl"),
        "--expected", str(gold_path), "--cases", str(folder / "input/cases.jsonl"), "--json", str(folder / "official-score.json")],
        capture_output=True, text=True, timeout=120)
    (folder / "official-score.log").write_text(process.stdout + process.stderr, encoding="utf-8")
    if process.returncode:
        raise ValueError("Official evaluator failed; install requirements-dev.txt and inspect official-score.log.")
    official = json.loads((folder / "official-score.json").read_text())
    report = {"cohort": selection["cohort"], "evaluation_type": "Public-data local holdout" if selection["cohort"].startswith("final") else "Development sample; may be used for tuning",
              "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "official_evaluator": provenance,
              "official_score": official, "runtime": timing,
              "private_benchmark_tested": False, "organizer_endpoint_tested": False,
              "interpretation": "Meeting the local score threshold is not a guarantee of private benchmark performance; token/time ranking requires the official run."}
    write_json(folder / "summary.json", report)
    print(process.stdout, end="")
    print("Failures or missing: {}; mean {:.1f}s; p95 {:.1f}s".format(timing["failed_or_missing_cases"], (timing["mean_case_ms"] or 0) / 1000, (timing["p95_case_ms"] or 0) / 1000))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "score"))
    parser.add_argument("--directory", type=Path, required=True, help="Root for prepare; cohort directory for run/score")
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "data/local/ost")
    parser.add_argument("--library", type=Path, default=PROJECT_ROOT / "data/local/library")
    parser.add_argument("--prior-inputs", type=Path, default=ARCHIVED_OUTPUT / "v2-evaluation/input.jsonl",
                        help="Preserved earlier inputs required by prepare; defaults to the local archive")
    parser.add_argument("--evaluator", type=Path, default=Path("/private/tmp/hackapertus-starter-evaluate.py"))
    parser.add_argument("--seed", default="claimlens-v4-readiness-20261008")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args)
        elif args.command == "run":
            load_dotenv()
            run(args.directory, Settings.from_env(), args.resume)
        else:
            score(args.directory)
    except (ClaimLensError, ValueError, OSError) as error:
        parser.exit(2, "Evaluation error: {}\n".format(error))


if __name__ == "__main__":
    main()
