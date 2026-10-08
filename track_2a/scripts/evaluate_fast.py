#!/usr/bin/env python3
"""Prepare/run/score exactly three development booklet cases for latency checks.

This small experiment uses previously exercised ballot dates, not the frozen
final cohorts. The run command reads no gold and caps each case at 120 seconds.
It does not execute the nine-case booklet or 54-case reference evaluations.
"""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import evaluate_readiness as readiness
from claimlens.config import Settings, load_dotenv
from claimlens.models import ClaimLensError

STRATA = (("de", "fr", 0), ("fr", "it", 1), ("it", "de", 2))
MAX_CASES = 3
MAX_CASE_SECONDS = 120.0


def select_development_rows(rows, development_dates, forbidden_requests, seed):
    """Deterministic pre-inference choices; only development labels select rows."""
    candidates = [(index, row) for index, row in readiness.ranked_rows(rows, seed)
                  if row["booklet_publish_date"] in set(development_dates)
                  and readiness.fingerprint(readiness.request_for(row, "unused")) not in forbidden_requests]
    selected = []
    for target in STRATA:
        match = next(((index, row) for index, row in candidates if readiness.stratum(row) == target), None)
        if match is None:
            raise ValueError("No unseen development request available for {}.".format(target))
        selected.append(match)
    return selected


def prepare(args):
    from datasets import load_from_disk

    root = args.directory
    if root.exists() and any(root.iterdir()):
        raise ValueError("Use an empty directory; the three frozen cases will not be overwritten.")
    dataset = json.loads((args.dataset / "manifest.json").read_text())
    if dataset.get("revision") != readiness.DATASET_REVISION:
        raise ValueError("Use the pinned OST dataset snapshot.")
    split = json.loads((args.previous / "split.json").read_text())
    dates = split["development_dates"]
    if set(dates) & set(split["final_dates"]):
        raise ValueError("Development and final ballot dates overlap.")
    prior_paths = [ROOT / "output/v2-evaluation/input.jsonl", args.previous / "development/input/cases.jsonl"]
    forbidden = {readiness.fingerprint(case) for path in prior_paths for case in readiness.read_jsonl(path)}
    rows = list(load_from_disk(str(args.dataset / "dataset"))["train"])
    chosen = select_development_rows(rows, dates, forbidden, args.seed)
    library = readiness.library_index(args.library)
    for _, row in chosen:
        key = row["booklet_url"], row["reference_language"]
        if key not in library or not library[key][0].is_file():
            raise ValueError("A selected booklet is missing from the local library.")
    evaluator = args.previous / "official/evaluate.py"
    provenance = json.loads((evaluator.parent / "source.json").read_text())
    if readiness.sha256(evaluator) != provenance["sha256"]:
        raise ValueError("The preserved official evaluator does not match its recorded hash.")
    (root / "input/booklets").mkdir(parents=True)
    (root / "gold").mkdir()
    (root / "official").mkdir()
    shutil.copyfile(evaluator, root / "official/evaluate.py")
    shutil.copyfile(evaluator.parent / "source.json", root / "official/source.json")
    cases, gold, origins = [], [], []
    for index, row in chosen:
        identifier = "latency-dev-{:06d}-A".format(index)
        case = readiness.request_for(row, identifier)
        case.pop("reference")
        pdf, document = library[(row["booklet_url"], row["reference_language"])]
        relative = "booklets/{}.pdf".format(document["id"])
        shutil.copyfile(pdf, root / "input" / relative)
        case["booklet"] = {"path": relative, "language": row["reference_language"]}
        cases.append(case)
        gold.append({"id": identifier, "label": row["entailment_label"], "reference": row["reference_string"]})
        origins.append({"id": identifier, "dataset_row": index, "ballot_date": row["booklet_publish_date"],
                        "source_url": row["booklet_url"], "pdf_pages": document["page_count"],
                        "pdf_sha256": readiness.sha256(root / "input" / relative),
                        "original_reference_request_sha256": readiness.fingerprint(readiness.request_for(row, "unused"))})
    readiness.write_jsonl(root / "input/cases.jsonl", cases)
    readiness.write_jsonl(root / "gold/expected.jsonl", gold)
    readiness.write_json(root / "selection.json", {
        "cohort": "development-latency", "cases": MAX_CASES, "seed": args.seed,
        "input_sha256": readiness.sha256(root / "input/cases.jsonl"),
        "gold_sha256": readiness.sha256(root / "gold/expected.jsonl"), "sources": origins,
        "dataset": dataset["dataset"], "revision": readiness.DATASET_REVISION,
        "dataset_manifest_sha256": readiness.sha256(args.dataset / "manifest.json"),
        "dataset_arrow_sha256": {str(path.relative_to(args.dataset)): readiness.sha256(path)
                                 for path in sorted((args.dataset / "dataset").rglob("*.arrow"))},
        "prior_input_sha256": {str(path.relative_to(ROOT)): readiness.sha256(path) for path in prior_paths},
        "source_to_claim_language_pairs": ["{}->{}".format(source, claim) for source, claim, _ in STRATA],
        "development_dates_allowed": dates, "final_dates_excluded": split["final_dates"],
        "maximum_cases": MAX_CASES, "maximum_case_seconds": MAX_CASE_SECONDS,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": "Three balanced development cases frozen before inference. Gold is used only for selection/scoring. No final A/B gold was read. Not a benchmark or held-out accuracy estimate."})
    print("Frozen three development booklet cases; separate gold, original PDFs and provenance saved.")


def bounded_settings(settings):
    return replace(settings, document_strategy="retrieval", document_timeout=min(settings.document_timeout, MAX_CASE_SECONDS),
                   timeout=min(settings.timeout, MAX_CASE_SECONDS), retrieval_timeout=min(settings.retrieval_timeout, MAX_CASE_SECONDS),
                   retrieval_prompt_tokens=min(settings.retrieval_prompt_tokens, 5000))


def validate_small_cohort(folder):
    cases, selection = readiness.validate_frozen_inputs(folder)
    if len(cases) != MAX_CASES or selection.get("cohort") != "development-latency":
        raise ValueError("This experiment only runs its frozen three-case development cohort.")
    allowed_dates = set(selection["development_dates_allowed"])
    if any(origin["ballot_date"] not in allowed_dates or origin["ballot_date"] in selection["final_dates_excluded"]
           for origin in selection["sources"]):
        raise ValueError("A case does not belong to the allowed development dates.")
    return cases, selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "score"))
    parser.add_argument("--directory", type=Path, default=ROOT / "output/v5-latency")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/local/ost")
    parser.add_argument("--library", type=Path, default=ROOT / "data/local/library")
    parser.add_argument("--previous", type=Path, default=ROOT / "output/v4-readiness")
    parser.add_argument("--seed", default="claimlens-v5-latency-20261008")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args)
        else:
            validate_small_cohort(args.directory)
            if args.command == "run":
                load_dotenv()
                readiness.run(args.directory, bounded_settings(Settings.from_env()), args.resume)
            else:
                report = readiness.score(args.directory, args.directory / "official/evaluate.py")
                report["evaluation_type"] = "Three-case latency development experiment; not a held-out benchmark"
                report["small_sample_warning"] = "One case per chosen language pair and label; do not infer general accuracy or evaluation readiness."
                readiness.write_json(args.directory / "summary.json", report)
    except (ClaimLensError, ValueError, OSError) as error:
        parser.exit(2, "Latency experiment error: {}\n".format(error))


if __name__ == "__main__":
    main()
