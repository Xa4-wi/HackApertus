#!/usr/bin/env python3
"""Download the public OST dataset and export separated input/gold JSONL files.

This utility does not run inference or download voting-booklet PDFs. Mount only
the generated input/ directory into the prediction container, never gold/ or
dataset/, because the latter contain expected labels.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_ID = "OSTswiss/MNLIoverSwissVotingBooklets"
DEFAULT_REVISION = "fc2b27600310778da6bbf445651ddbca22d86269"
LABEL_NAMES = {0: "entailment", 1: "neutral", 2: "contradiction"}
LANGUAGES = {"de", "fr", "it"}


def convert_row(row, case_id):
    """Whitelist model inputs; keep every supervision field in a separate file."""
    for name in ("vote", "claim", "reference_string"):
        if not isinstance(row.get(name), str) or not row[name].strip():
            raise ValueError("{}: missing or empty {}".format(case_id, name))
    for name in ("claim_language", "reference_language"):
        if row.get(name) not in LANGUAGES:
            raise ValueError("{}: unsupported {}".format(case_id, name))
    label = row.get("entailment_label")
    if type(label) is not int or label not in LABEL_NAMES:
        raise ValueError("{}: unsupported entailment_label".format(case_id))
    request = {
        "id": case_id,
        "vote": row["vote"],
        "claim": {"text": row["claim"], "language": row["claim_language"]},
        "reference": {"text": row["reference_string"], "language": row["reference_language"]},
    }
    gold = {"id": case_id, "label": label, "label_name": LABEL_NAMES[label]}
    return request, gold


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_split(rows, split_name, output_root):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", split_name):
        raise ValueError("Dataset split name is not safe for a local filename.")
    input_path = output_root / "input" / ("reference-" + split_name + ".jsonl")
    gold_path = output_root / "gold" / ("reference-" + split_name + ".gold.jsonl")
    input_path.parent.mkdir(parents=True, exist_ok=True)
    gold_path.parent.mkdir(parents=True, exist_ok=True)
    labels, claims, references, pairs = Counter(), Counter(), Counter(), Counter()
    lengths = {"claim_characters_max": 0, "reference_characters_max": 0}
    unique_votes, unique_booklet_urls, fingerprints = set(), set(), {}
    duplicates = 0
    with input_path.open("w", encoding="utf-8") as inputs, gold_path.open("w", encoding="utf-8") as golds:
        for index, row in enumerate(rows):
            case_id = "ost-{}-{:06d}".format(split_name, index)
            request, gold = convert_row(row, case_id)
            inputs.write(json.dumps(request, ensure_ascii=False) + "\n")
            golds.write(json.dumps(gold, ensure_ascii=False) + "\n")
            labels[gold["label_name"]] += 1
            claims[row["claim_language"]] += 1
            references[row["reference_language"]] += 1
            pairs[row["claim_language"] + "->" + row["reference_language"]] += 1
            lengths["claim_characters_max"] = max(lengths["claim_characters_max"], len(row["claim"]))
            lengths["reference_characters_max"] = max(lengths["reference_characters_max"], len(row["reference_string"]))
            unique_votes.add(row["vote"])
            if row.get("booklet_url"):
                unique_booklet_urls.add(row["booklet_url"])
            fingerprint = hashlib.sha256(json.dumps({key: value for key, value in request.items() if key != "id"},
                                                    sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
            duplicates += fingerprint in fingerprints
            fingerprints.setdefault(fingerprint, set()).add(gold["label"])
    row_count = sum(labels.values())
    if row_count == 0:
        raise ValueError("The dataset split is empty: " + split_name)
    return {
        "rows": row_count, "labels": dict(sorted(labels.items())),
        "claim_languages": dict(sorted(claims.items())),
        "reference_languages": dict(sorted(references.items())),
        "language_pairs": dict(sorted(pairs.items())),
        "unique_votes": len(unique_votes), "unique_booklet_urls": len(unique_booklet_urls),
        "duplicate_request_rows": duplicates,
        "conflicting_duplicate_requests": sum(len(labels) > 1 for labels in fingerprints.values()), **lengths,
        "input_path": str(input_path.relative_to(output_root)), "input_sha256": sha256_file(input_path),
        "gold_path": str(gold_path.relative_to(output_root)), "gold_sha256": sha256_file(gold_path),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default=DEFAULT_REVISION, help="Exact Hugging Face commit SHA (default: verified 2026-10-08 revision)")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "local" / "ost")
    parser.add_argument("--cache-dir", type=Path, default=PROJECT_ROOT.parent / ".cache" / "huggingface")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("--revision must be an exact 40-character commit SHA for reproducibility")
    output_root = args.output.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        parser.error("output directory is not empty; choose a new --output path to preserve existing data")
    cache = args.cache_dir.resolve()
    os.environ["HF_HOME"] = str(cache)
    os.environ["HF_HUB_CACHE"] = str(cache / "hub")
    os.environ["HF_DATASETS_CACHE"] = str(cache / "datasets")
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    try:
        from datasets import load_dataset
        from huggingface_hub import HfApi
    except ImportError:
        parser.error("install the development dependencies: python -m pip install -r requirements-dev.txt")
    info = HfApi().dataset_info(DATASET_ID, revision=args.revision, token=False)
    ds = load_dataset(DATASET_ID, revision=args.revision,
                      cache_dir=str(cache / "datasets"), token=False)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".ost-download-", dir=output_root.parent))
    try:
        split_stats = {name: write_split(rows, name, staging_root) for name, rows in ds.items()}
        ds.save_to_disk(str(staging_root / "dataset"))
        manifest = {
            "dataset": DATASET_ID,
            "source_url": "https://huggingface.co/datasets/" + DATASET_ID,
            "revision": info.sha,
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "license": info.card_data.get("license") if info.card_data else None,
            "python_version": platform.python_version(),
            "packages": {name: importlib.metadata.version(name) for name in ("datasets", "huggingface-hub", "pyarrow")},
            "dataset_path": "dataset",
            "splits": split_stats,
            "prediction_container_mount": "input/ only; do not mount gold/ or dataset/",
            "pdfs_downloaded": False,
            "inference_performed": False,
            "evaluation_note": "The upstream split name is preserved. No held-out test split or benchmark result is claimed.",
        }
        (staging_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(staging_root, output_root)
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)
    print(json.dumps({"output": str(output_root), "revision": info.sha, "splits": split_stats}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
