#!/usr/bin/env python3
"""Compare bounded real-model variants on nine frozen development requests.

Prepare once, run and score six tuning cases, then lock a candidate before
opening the three confirmation cases. Neither inference nor profiling reads
gold. A source snapshot can be selected without changing the active checkout.
"""

import argparse
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT.parent / "archive/track_2a/output"
STRATA = {
    "tuning": (("de", "de", 0), ("fr", "fr", 2), ("it", "it", 1),
               ("de", "fr", 1), ("fr", "it", 0), ("it", "de", 2)),
    "confirmation": (("de", "it", 2), ("fr", "de", 1), ("it", "fr", 0)),
}


def select_source(source_root):
    """Select the actual imported package before helper imports add active src."""
    source_root = Path(source_root).resolve()
    if not (source_root / "claimlens/__init__.py").is_file():
        raise ValueError("--source-root must contain a claimlens package.")
    existing = sys.modules.get("claimlens")
    if existing is not None and Path(existing.__file__).resolve().parent != source_root / "claimlens":
        raise ValueError("Another claimlens package is already loaded; run this variant in a fresh process.")
    sys.path.insert(0, str(source_root))
    importlib.import_module("claimlens")
    # Relocating Python code must not silently relocate its optional OCR assets.
    importlib.import_module("claimlens.ocr").LOCAL_TESSDATA = ROOT.parent / ".cache/tessdata"
    importlib.import_module("claimlens.library").DEFAULT_ROOT = ROOT / "data/local/library"
    sys.path.insert(0, str(ROOT / "scripts"))
    return importlib.import_module("evaluate_readiness")


def select_rows(rows, development_dates, forbidden_requests, seed, readiness):
    candidates = [(index, row) for index, row in readiness.ranked_rows(rows, seed)
                  if row["booklet_publish_date"] in set(development_dates)
                  and readiness.fingerprint(readiness.request_for(row, "unused")) not in forbidden_requests]
    chosen = {}
    for cohort, strata in STRATA.items():
        chosen[cohort] = []
        for target in strata:
            match = next(((index, row) for index, row in candidates if readiness.stratum(row) == target), None)
            if match is None:
                raise ValueError("No unseen development request for {}.".format(target))
            chosen[cohort].append(match)
    return chosen


def booklet_request_key(case):
    source = case.get("booklet") or case.get("reference") or {}
    return (case.get("vote", ""), case["claim"]["text"], case["claim"].get("language"), source.get("language"))


def prepare(args, readiness):
    root = args.directory
    # Source snapshots may already exist, but selection is immutable once made.
    if (root / "frozen").exists() or (root / "selection.json").exists():
        raise ValueError("Frozen efficiency cases already exist; they will not be replaced.")
    previous = ARCHIVE / "v4-readiness"
    prior_inputs = [ARCHIVE / "v2-evaluation/input.jsonl", previous / "development/input/cases.jsonl"]
    prior_selections = [ARCHIVE / "v5-latency-context/selection.json"]
    evaluator = previous / "official/evaluate.py"
    required = [*prior_inputs, *prior_selections, previous / "split.json", evaluator, evaluator.parent / "source.json"]
    if any(not path.is_file() for path in required):
        raise ValueError("Preserved prior inputs, split, v5 selection and evaluator are required; restore the local archive.")
    from datasets import load_from_disk

    dataset = json.loads((args.dataset / "manifest.json").read_text())
    if dataset.get("revision") != readiness.DATASET_REVISION:
        raise ValueError("Use the pinned OST dataset revision.")
    split = json.loads((previous / "split.json").read_text())
    dates, final_dates = split["development_dates"], split["final_dates"]
    if set(dates) & set(final_dates):
        raise ValueError("Development and final ballot dates overlap.")
    forbidden = {readiness.fingerprint(case) for path in prior_inputs for case in readiness.read_jsonl(path)}
    for path in prior_selections:
        forbidden.update(row["original_reference_request_sha256"]
                         for row in json.loads(path.read_text())["sources"])
    # Also exclude any other archived exact reference inputs; no gold is read.
    discovered = sorted({*ARCHIVE.rglob("input.jsonl"), *ARCHIVE.rglob("input/cases.jsonl")})
    old_booklet_requests = set()
    for path in discovered:
        for case in readiness.read_jsonl(path):
            if "reference" in case:
                forbidden.add(readiness.fingerprint(case))
            elif "booklet" in case:
                old_booklet_requests.add(booklet_request_key(case))
    rows = list(load_from_disk(str(args.dataset / "dataset"))["train"])
    forbidden.update(readiness.fingerprint(readiness.request_for(row, "unused")) for row in rows
                     if booklet_request_key(readiness.request_for(row, "unused")) in old_booklet_requests)
    chosen = select_rows(rows, dates, forbidden, args.seed, readiness)
    library = readiness.library_index(args.library)
    for cohort in chosen.values():
        for _, row in cohort:
            match = library.get((row["booklet_url"], row["reference_language"]))
            if match is None or not match[0].is_file():
                raise ValueError("A selected booklet is missing from the local library.")
    provenance = json.loads((evaluator.parent / "source.json").read_text())
    if readiness.sha256(evaluator) != provenance["sha256"]:
        raise ValueError("Official evaluator differs from its recorded hash.")
    (root / "official").mkdir(parents=True)
    shutil.copyfile(evaluator, root / "official/evaluate.py")
    shutil.copyfile(evaluator.parent / "source.json", root / "official/source.json")
    for cohort, selected in chosen.items():
        folder = root / "frozen" / cohort
        (folder / "input/booklets").mkdir(parents=True)
        (folder / "gold").mkdir()
        cases, gold, origins = [], [], []
        for index, row in selected:
            identifier = "efficiency-dev-{:06d}-A".format(index)
            case = readiness.request_for(row, identifier)
            case.pop("reference")
            pdf, document = library[(row["booklet_url"], row["reference_language"])]
            relative = "booklets/{}.pdf".format(document["id"])
            shutil.copyfile(pdf, folder / "input" / relative)
            case["booklet"] = {"path": relative, "language": row["reference_language"]}
            cases.append(case)
            gold.append({"id": identifier, "label": row["entailment_label"], "reference": row["reference_string"]})
            origins.append({"id": identifier, "dataset_row": index, "ballot_date": row["booklet_publish_date"],
                            "source_url": row["booklet_url"], "pdf_pages": document["page_count"],
                            "pdf_sha256": readiness.sha256(folder / "input" / relative),
                            "original_reference_request_sha256": readiness.fingerprint(readiness.request_for(row, "unused"))})
        readiness.write_jsonl(folder / "input/cases.jsonl", cases)
        readiness.write_jsonl(folder / "gold/expected.jsonl", gold)
        readiness.write_json(folder / "selection.json", {
            "cohort": "efficiency-" + cohort, "cases": len(cases), "seed": args.seed, "sources": origins,
            "input_sha256": readiness.sha256(folder / "input/cases.jsonl"),
            "gold_sha256": readiness.sha256(folder / "gold/expected.jsonl"),
            "source_to_claim_language_pairs": ["{}->{}".format(a, b) for a, b, _ in STRATA[cohort]],
            "development_dates_allowed": dates, "final_dates_excluded": final_dates})
    readiness.write_json(root / "selection.json", {
        "dataset": dataset["dataset"], "revision": readiness.DATASET_REVISION, "seed": args.seed,
        "dataset_manifest_sha256": readiness.sha256(args.dataset / "manifest.json"),
        "dataset_arrow_sha256": {str(path.relative_to(args.dataset)): readiness.sha256(path)
                                 for path in sorted((args.dataset / "dataset").rglob("*.arrow"))},
        "prior_files_sha256": {str(path.relative_to(ROOT.parent)): readiness.sha256(path)
                               for path in sorted(set([*required, *discovered]))},
        "cohorts": {name: readiness.sha256(root / "frozen" / name / "selection.json") for name in STRATA},
        "maximum_case_seconds": 120, "maximum_transport_attempts": 4,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "limitations": "Nine public development cases, three labels each and all nine language pairs. Six tuning cases; three separate confirmation cases. Not an accuracy benchmark or the private evaluation. No final gold read."})
    print("Frozen six tuning and three confirmation cases, all nine language pairs; gold stored separately.")


def bounded_settings(settings):
    return replace(settings, document_strategy="retrieval", timeout=min(settings.timeout, 120),
                   document_timeout=min(settings.document_timeout, 120), retrieval_timeout=min(settings.retrieval_timeout, 120),
                   max_document_model_calls=min(settings.max_document_model_calls, 4),
                   retrieval_prompt_tokens=min(settings.retrieval_prompt_tokens, 5000))


def trace_configuration(enabled):
    """Version the opt-in local diagnostic contract independently of settings."""
    return {"trace_prompts": bool(enabled), "schema_version": 1,
            "fields": ["messages", "source_passages", "response"],
            "transport_credentials_recorded": False}


def run_identity(inputs, settings, readiness, *, trace_prompts=False):
    import claimlens

    package = Path(claimlens.__file__).resolve().parent
    sources = {str(path.relative_to(package)): readiness.sha256(path) for path in sorted(package.rglob("*.py"))}
    public = asdict(settings)
    public.pop("api_key", None)
    public["endpoint_sha256"] = hashlib.sha256(public.pop("base_url").encode()).hexdigest()
    diagnostics = trace_configuration(trace_prompts)
    return {"schema_version": 1, "source_package": str(package), "source_files_sha256": sources,
            "source_sha256": hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest(),
            "settings": public, "served_model": settings.model_for_request(settings.model),
            "input_sha256": readiness.sha256(inputs), "runner_sha256": readiness.sha256(__file__),
            "diagnostics": diagnostics,
            "diagnostics_sha256": hashlib.sha256(json.dumps(diagnostics, sort_keys=True).encode()).hexdigest(),
            "runtime_asset_paths": {"local_tessdata": str(ROOT.parent / ".cache/tessdata"),
                                    "tessdata_prefix": os.environ.get("TESSDATA_PREFIX"),
                                    "library": str(ROOT / "data/local/library")},
            "runtime_weights_verified": False}


@contextmanager
def profile_requests(records, traces=None):
    """Observe existing transport calls without altering prompts or settings."""
    modules = [importlib.import_module("claimlens." + name) for name in ("llm", "fast", "context")]
    original = modules[0].request_json

    def measured(data, settings, passages):
        started = time.perf_counter()
        record = {"stage": "assessment" if passages else "query_expansion", "status": "failed",
                  "requested_max_tokens": data.get("max_tokens"),
                  "prompt_characters": sum(len(message.get("content", "")) for message in data.get("messages", [])),
                  "source_passages": len(passages)}
        # Whitelist prompt fields: never serialize settings, headers, URLs or
        # arbitrary transport data. These development inputs are public text.
        trace = None if traces is None else {
            "stage": record["stage"], "status": "failed",
            "messages": deepcopy([{key: message[key] for key in ("role", "content") if key in message}
                                   for message in data.get("messages", [])]),
            "source_passages": deepcopy([{key: passage[key] for key in
                ("id", "text", "title", "page", "language", "attribution") if key in passage}
                for passage in passages]),
            "response": None}
        try:
            result, metrics = original(data, settings, passages)
            record.update({"status": "accepted", "metrics": metrics})
            if trace is not None:
                # Snapshot before production quote expansion mutates a result.
                trace.update({"status": "accepted", "response": deepcopy(result)})
            return result, metrics
        except Exception as error:
            record["metrics"] = getattr(error, "metrics", {})
            raise
        finally:
            record["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
            records.append(record)
            if trace is not None:
                traces.append(trace)

    patched = []
    for module in modules:
        if getattr(module, "request_json", None) is original:
            patched.append(module)
            module.request_json = measured
    try:
        yield
    finally:
        for module in patched:
            module.request_json = original


def validate_cohort(root, cohort, readiness):
    manifest = json.loads((root / "selection.json").read_text())
    folder = root / "frozen" / cohort
    if readiness.sha256(folder / "selection.json") != manifest["cohorts"][cohort]:
        raise ValueError("Frozen cohort selection has changed.")
    cases, selection = readiness.validate_frozen_inputs(folder)
    if selection.get("cohort") != "efficiency-" + cohort or len(cases) != len(STRATA[cohort]):
        raise ValueError("This harness only runs its frozen six/three development cohorts.")
    if any(row["ballot_date"] not in selection["development_dates_allowed"]
           or row["ballot_date"] in selection["final_dates_excluded"] for row in selection["sources"]):
        raise ValueError("A case does not belong to the development dates.")
    return cases, selection


def variant_path(args):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", args.variant):
        raise ValueError("Use a simple variant name of letters, digits, underscores and hyphens.")
    return args.directory / "runs" / args.variant / args.cohort


def comparison_identity(identity):
    return {key: value for key, value in identity.items() if key != "input_sha256"}


def confirm_locked(args, settings, readiness):
    if args.cohort != "confirmation":
        return
    path = args.directory / "candidate-lock.json"
    if not path.is_file():
        raise ValueError("Lock a candidate after tuning before running any confirmation cases.")
    lock = json.loads(path.read_text())
    if args.variant not in ("baseline", lock["variant"]):
        raise ValueError("Confirmation only permits the locked candidate and baseline.")
    tuning = args.directory / "runs" / args.variant / "tuning/results.run.json"
    previous = json.loads(tuning.read_text())
    current = run_identity(args.directory / "frozen/confirmation/input/cases.jsonl", settings, readiness,
                           trace_prompts=getattr(args, "trace_prompts", False))
    if comparison_identity(current) != comparison_identity(previous):
        raise ValueError("Confirmation source/configuration differs from its tuning run.")
    if args.variant == lock["variant"] and readiness.sha256(tuning) != lock["tuning_identity_sha256"]:
        raise ValueError("Locked candidate identity changed.")
    if args.variant == lock["variant"] and readiness.sha256(tuning.parent / "results.jsonl") != lock["tuning_results_sha256"]:
        raise ValueError("Locked candidate tuning results changed.")


def trace_path(folder, identifier):
    # A request ID is data, never a filename supplied by a caller.
    name = hashlib.sha256(identifier.encode()).hexdigest()
    return folder / "diagnostics" / (name + ".json")


def validate_traces(folder, records, readiness):
    for record in records:
        path = trace_path(folder, record["id"])
        expected = record.get("diagnostic_trace", {})
        if (expected.get("path") != str(path.relative_to(folder)) or not path.is_file()
                or readiness.sha256(path) != expected.get("sha256")):
            raise ValueError("A saved diagnostic trace is missing or changed; preserve these results.")


def run(args, settings, readiness):
    from claimlens.cli import predict_case
    from claimlens.models import ClaimLensError

    cases, selection = validate_cohort(args.directory, args.cohort, readiness)
    confirm_locked(args, settings, readiness)
    folder = variant_path(args)
    frozen = args.directory / "frozen" / args.cohort
    if not folder.exists():
        folder.mkdir(parents=True)
        shutil.copytree(frozen / "input", folder / "input")
        shutil.copyfile(frozen / "selection.json", folder / "selection.json")
    else:
        readiness.validate_frozen_inputs(folder)
        if json.loads((folder / "selection.json").read_text()) != selection:
            raise ValueError("Variant inputs differ from the frozen cohort.")
    trace_prompts = getattr(args, "trace_prompts", False)
    identity = run_identity(folder / "input/cases.jsonl", settings, readiness, trace_prompts=trace_prompts)
    identity_path, results_path = folder / "results.run.json", folder / "results.jsonl"
    records = []
    if identity_path.exists() or results_path.exists():
        if not args.resume or not identity_path.exists() or json.loads(identity_path.read_text()) != identity:
            raise ValueError("Results exist or run identity changed; resume requires identical code, inputs and settings.")
        records = readiness.read_jsonl(results_path) if results_path.exists() else []
        if not set(readiness.index_ids(records, "Recorded result")).issubset(readiness.index_ids(cases, "Input")):
            raise ValueError("Recorded results contain unknown IDs.")
        if trace_prompts:
            validate_traces(folder, records, readiness)
    else:
        readiness.write_json(identity_path, identity)
    done, cache = {record["id"] for record in records}, {}
    with results_path.open("a", encoding="utf-8") as stream:
        for position, case in enumerate(cases, 1):
            if case["id"] in done:
                continue
            if run_identity(folder / "input/cases.jsonl", settings, readiness, trace_prompts=trace_prompts) != identity:
                raise ValueError("Selected source/configuration changed during inference; preserve these partial results.")
            readiness.validate_frozen_inputs(folder)
            started, stages = time.perf_counter(), []
            traces = [] if trace_prompts else None
            record = {"id": case["id"], "status": "failed", "prediction": None}
            try:
                with profile_requests(stages, traces):
                    prediction, result = predict_case(case, settings, folder / "input", cache)
                record.update({"status": "accepted", "prediction": prediction, "metrics": result["metrics"],
                               "warnings": result.get("warnings", []), "processing": result.get("processing", {})})
            except (ClaimLensError, ValueError, OSError) as error:
                record.update({"error": str(error), "metrics": getattr(error, "metrics", {}),
                               "attempts": getattr(error, "attempts", None)})
            record.update({"elapsed_ms": round((time.perf_counter() - started) * 1000, 3), "stages": stages})
            record["outside_transport_ms"] = round(max(0, record["elapsed_ms"] - sum(stage["elapsed_ms"] for stage in stages)), 3)
            if run_identity(folder / "input/cases.jsonl", settings, readiness, trace_prompts=trace_prompts) != identity:
                record["source_changed_during_case"] = True
            if traces is not None:
                path = trace_path(folder, case["id"])
                path.parent.mkdir(exist_ok=True)
                readiness.write_json(path, {"id": case["id"], "schema_version": 1, "stages": traces})
                record["diagnostic_trace"] = {"path": str(path.relative_to(folder)), "sha256": readiness.sha256(path)}
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            records.append(record)
            readiness.export_predictions(records, folder / "predictions.jsonl")
            print("{} {}/{} {} {} ({:.1f}s)".format(args.variant, position, len(cases), case["id"], record["status"], record["elapsed_ms"] / 1000), flush=True)
            if record.get("source_changed_during_case"):
                raise ValueError("Source changed during the case; its result is flagged and the run stopped.")
    return records


def lock_candidate(args, readiness):
    folder = args.directory / "runs" / args.variant / "tuning"
    records = readiness.read_jsonl(folder / "results.jsonl")
    if len(records) != len(STRATA["tuning"]):
        raise ValueError("Complete all six tuning cases before locking a candidate.")
    path = args.directory / "candidate-lock.json"
    if path.exists():
        raise ValueError("A candidate is already locked; confirmation cannot be reused for variant selection.")
    readiness.write_json(path, {"variant": args.variant,
        "tuning_identity_sha256": readiness.sha256(folder / "results.run.json"),
        "tuning_results_sha256": readiness.sha256(folder / "results.jsonl"),
        "locked_at_utc": datetime.now(timezone.utc).isoformat()})
    print("Candidate locked before confirmation: " + args.variant)


def score(args, readiness):
    from audit_evidence import audit

    cases, _ = validate_cohort(args.directory, args.cohort, readiness)
    folder = variant_path(args)
    # Gold is copied/read only by this explicit scoring operation.
    (folder / "gold").mkdir(exist_ok=True)
    shutil.copyfile(args.directory / "frozen" / args.cohort / "gold/expected.jsonl", folder / "gold/expected.jsonl")
    report = readiness.score(folder, args.directory / "official/evaluate.py")
    report["evaluation_type"] = "Small development efficiency comparison: " + args.cohort
    records = readiness.read_jsonl(folder / "results.jsonl")
    stages = {}
    for record in records:
        for stage in record.get("stages", []):
            total = stages.setdefault(stage["stage"], {"calls": 0, "elapsed_ms": 0, "input_tokens": 0, "output_tokens": 0, "complete_usage_calls": 0})
            total["calls"] += 1
            total["elapsed_ms"] += stage["elapsed_ms"]
            metrics = stage.get("metrics", {})
            if all(type(metrics.get(key)) is int for key in ("input_tokens", "output_tokens")):
                total["complete_usage_calls"] += 1
                for key in ("input_tokens", "output_tokens"):
                    total[key] += metrics[key]
    report["stage_totals"] = stages
    report["small_sample_warning"] = "One request per language pair; public development dates only. Exact citations do not establish semantic support. Confirmation is not the private benchmark."
    readiness.write_json(folder / "summary.json", report)
    readiness.write_json(folder / "evidence-audit.json", audit(cases, readiness.read_jsonl(folder / "predictions.jsonl"), folder / "input"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "score", "lock"))
    parser.add_argument("--directory", type=Path, default=ROOT / "output/evaluations/efficiency")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/local/ost")
    parser.add_argument("--library", type=Path, default=ROOT / "data/local/library")
    parser.add_argument("--source-root", type=Path, default=ROOT / "src")
    parser.add_argument("--cohort", choices=tuple(STRATA), default="tuning")
    parser.add_argument("--variant", default="baseline")
    parser.add_argument("--query-mode", choices=("multilingual", "source"))
    parser.add_argument("--citation-mode", choices=("full", "prefix"))
    parser.add_argument("--seed", default="claimlens-efficiency-20261008-v1")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--trace-prompts", action="store_true",
                        help="Save local public-development prompt, source and model-response diagnostics; excludes transport credentials.")
    args = parser.parse_args()
    try:
        readiness = select_source(args.source_root)
        variant_path(args)
        if args.command == "prepare":
            prepare(args, readiness)
        elif args.command == "lock":
            lock_candidate(args, readiness)
        elif args.command == "score":
            score(args, readiness)
        else:
            from claimlens.config import Settings, load_dotenv
            load_dotenv(ROOT / ".env")
            settings = bounded_settings(Settings.from_env())
            for argument, field in ((args.query_mode, "retrieval_query_mode"),
                                    (args.citation_mode, "retrieval_citation_mode")):
                if argument is not None:
                    if not hasattr(settings, field):
                        raise ValueError("Selected source does not support " + field)
                    settings = replace(settings, **{field: argument})
            run(args, settings, readiness)
    except (ValueError, OSError) as error:
        parser.exit(2, "Efficiency experiment error: {}\n".format(error))


if __name__ == "__main__":
    main()
