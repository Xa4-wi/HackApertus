#!/usr/bin/env python3
"""Import official booklet PDFs referenced by an OST snapshot, without labels."""

import argparse
from datetime import datetime, timezone
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from claimlens.library import BookletLibrary, official_url
from claimlens.models import ValidationError


def source_rows(dataset_path=None, jsonl_path=None):
    if jsonl_path is not None:
        with jsonl_path.open(encoding="utf-8") as source:
            for line in source:
                if line.strip():
                    yield json.loads(line)
        return
    try:
        from datasets import DatasetDict, load_from_disk
    except ImportError:
        raise ValidationError("Snapshot import needs requirements-data.txt, or provide --jsonl.") from None
    snapshot = load_from_disk(str(dataset_path))
    splits = snapshot.values() if isinstance(snapshot, DatasetDict) else [snapshot]
    for split in splits:
        # Only these three public source fields reach the importer or manifest.
        selected = split.select_columns(["booklet_url", "reference_language", "vote"])
        yield from selected


def collect_sources(rows):
    sources, failures = {}, []
    for index, row in enumerate(rows, start=1):
        try:
            if not isinstance(row, dict):
                raise ValidationError("Source row must be an object.")
            url = official_url(row.get("booklet_url"))
            language = row.get("reference_language")
            if language not in ("de", "fr", "it"):
                raise ValidationError("Source row language must be de, fr, or it.")
            vote = row.get("vote", "")
            if not isinstance(vote, str) or len(vote) > 2000 or "\x00" in vote:
                raise ValidationError("Source row has an invalid vote title.")
            key = (url, language)
            source = sources.setdefault(key, {"url": url, "language": language, "votes": []})
            if vote.strip() and vote.strip() not in source["votes"]:
                source["votes"].append(vote.strip())
        except ValidationError as error:
            failures.append({"row": index, "error": str(error)})
    return sorted(sources.values(), key=lambda item: (item["url"], item["language"])), failures


def write_manifest(path, manifest):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".import-manifest-", delete=False) as output:
            temporary = Path(output.name)
            json.dump(manifest, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "data/local/ost/dataset",
                        help="A datasets.save_to_disk snapshot (default: prepared local OST snapshot)")
    inputs.add_argument("--jsonl", type=Path, help="Raw OST rows with booklet_url, reference_language, and vote")
    parser.add_argument("--library", type=Path, help="Library directory (default: CLAIMLENS_LIBRARY or data/local/library)")
    parser.add_argument("--manifest", type=Path, help="Import report (default: LIBRARY/import-manifest.json)")
    parser.add_argument("--limit", type=int, help="Import only the first N unique source URL/language pairs")
    parser.add_argument("--refresh", action="store_true", help="Retry extraction and local OCR on cached PDFs without downloading again")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    library = BookletLibrary(args.library)
    manifest_path = args.manifest or library.root / "import-manifest.json"
    try:
        sources, invalid = collect_sources(source_rows(args.dataset, args.jsonl))
    except (OSError, ValueError, KeyError, ValidationError):
        print("Could not read the source snapshot. Prepare the OST dataset or provide valid raw JSONL rows.", file=sys.stderr)
        return 1
    chosen = sources[:args.limit] if args.limit else sources
    manifest = {"schema_version": 1, "started_at": datetime.now(timezone.utc).isoformat(),
                "source_kind": "raw_jsonl" if args.jsonl else "datasets_snapshot",
                "source_fields": ["booklet_url", "reference_language", "vote"],
                "unique_sources": len(sources), "selected_sources": len(chosen),
                "invalid_rows": invalid, "items": [], "status": "running"}
    status, refreshed = "aborted", set()
    write_manifest(manifest_path, manifest)
    try:
        for index, source in enumerate(chosen, start=1):
            date = re.search(r"\d{4}-\d{2}-\d{2}", source["url"])
            title = "Voting booklet{} ({})".format(" " + date.group() if date else "", source["language"].upper())
            item = {"url": source["url"], "language": source["language"], "votes": source["votes"]}
            try:
                document = library.import_url(source["url"], source["language"], title=title,
                                              vote=source["votes"][0] if source["votes"] else "")
                for vote in source["votes"][1:]:
                    document = library.import_url(source["url"], source["language"], vote=vote)
                if args.refresh and document["id"] not in refreshed:
                    document = library.refresh_extraction(document["id"])
                    refreshed.add(document["id"])
                item.update({"status": "imported", "document_id": document["id"],
                             "page_count": document["page_count"], "character_count": document["character_count"],
                             "warnings": document["warnings"]})
                print("[{}/{}] {}: {} pages, {} characters, {} warnings".format(
                    index, len(chosen), title, document["page_count"], document["character_count"], len(document["warnings"])), flush=True)
            except (ValidationError, OSError, HTTPException) as error:
                if isinstance(error, ValidationError):
                    message = str(error)
                elif isinstance(error, HTTPException):
                    message = "The booklet download was incomplete or invalid. Try again later."
                else:
                    message = "Could not store the booklet in the local library."
                item.update({"status": "failed", "error": message})
                print("[{}/{}] {}: {}".format(index, len(chosen), title, message), file=sys.stderr, flush=True)
            manifest["items"].append(item)
            write_manifest(manifest_path, manifest)
        status = "complete"
    except KeyboardInterrupt:
        status = "interrupted"
    except Exception:
        # Preserve progress without publishing false completion or exception details
        # that may contain paths, response bodies, or credentials.
        manifest["error"] = "Import aborted after an unexpected error. Re-run to resume unfinished sources."
        print(manifest["error"], file=sys.stderr)
    finally:
        failed = sum(item["status"] == "failed" for item in manifest["items"])
        manifest.update({"status": status,
                         "finished_at": datetime.now(timezone.utc).isoformat(),
                         "imported": sum(item["status"] == "imported" for item in manifest["items"]),
                         "failed": failed, "unprocessed": len(chosen) - len(manifest["items"])})
        write_manifest(manifest_path, manifest)
    print("Imported {}; failed {}; rejected source rows {}. Report: {}".format(
        manifest["imported"], manifest["failed"], len(invalid), manifest_path))
    return 130 if status == "interrupted" else (1 if status == "aborted" or failed or invalid else 0)


if __name__ == "__main__":
    raise SystemExit(main())
