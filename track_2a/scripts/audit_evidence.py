#!/usr/bin/env python3
"""Audit exported prediction contracts and physical-page quote provenance offline.

This checker reads predictions and input PDFs/reference text, never gold or a
model. It deliberately does not use the engine's citation validator. Fresh PDF
text extraction may not reproduce OCR-only quotes; those remain unverified and
require comparison with the original page. Exact presence is not semantic proof.
"""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

LABELS = ("entailment", "neutral", "contradiction")


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pdf_pages(path):
    from pypdf import PdfReader

    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError("Cannot independently audit encrypted PDFs.")
    return [page.extract_text() or "" for page in reader.pages]


def audit(cases, predictions, data_root):
    expected, grouped = {}, {}
    for case in cases:
        identifier = case.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in expected:
            raise ValueError("Input cases need unique nonempty string IDs.")
        expected[identifier] = case
    invalid_prediction_rows = 0
    for prediction in predictions:
        if not isinstance(prediction, dict) or not isinstance(prediction.get("id"), str):
            invalid_prediction_rows += 1
            continue
        grouped.setdefault(prediction["id"], []).append(prediction)
    root, documents = Path(data_root).resolve(), {}
    results, statuses = [], Counter()
    for identifier, case in expected.items():
        matches = grouped.get(identifier, [])
        record = {"id": identifier, "task": "A" if "booklet" in case else "B", "issues": [], "quotes": []}
        results.append(record)
        if len(matches) != 1:
            record["issues"].append("missing_response" if not matches else "duplicate_response")
            continue
        prediction = matches[0]
        label = prediction.get("label")
        if type(label) is not int or label not in range(3):
            record["issues"].append("invalid_label")
        elif prediction.get("label_name") != LABELS[label]:
            record["issues"].append("mismatched_label_name")
        metrics = prediction.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        for key in ("input_tokens", "output_tokens", "inference_time_ms"):
            value = metrics.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                record["issues"].append("invalid_metric_" + key)
        citations = prediction.get("evidence")
        if not isinstance(citations, list):
            record["issues"].append("invalid_evidence_list")
            continue
        if "booklet" in case and label in (0, 2) and not citations:
            record["issues"].append("missing_required_booklet_evidence")
        pages = None
        if "booklet" in case and citations:
            path = (root / case["booklet"]["path"]).resolve()
            try:
                path.relative_to(root)
            except ValueError:
                raise ValueError("Booklet path escapes the supplied input directory.") from None
            key = str(path.relative_to(root))
            if key not in documents:
                text = pdf_pages(path)
                documents[key] = {"sha256": file_hash(path), "page_count": len(text), "texts": text,
                    "page_text_sha256": [hashlib.sha256(value.encode()).hexdigest() for value in text]}
            pages = documents[key]["texts"]
            record["pdf_sha256"] = documents[key]["sha256"]
        for index, citation in enumerate(citations):
            item = {"index": index, "counted_by_official_scorer": index < 5}
            record["quotes"].append(item)
            if not isinstance(citation, dict) or "page" not in citation or not isinstance(citation.get("text"), str) or not citation["text"].strip():
                item["status"] = "invalid_citation"
                continue
            quote, page = citation["text"], citation["page"]
            item.update({"page": page, "characters": len(quote), "quote_sha256": hashlib.sha256(quote.encode()).hexdigest()})
            if len(quote) > 5000:
                item["status"] = "quote_exceeds_limit"
            elif pages is None:
                item["status"] = ("invalid_reference_page" if page is not None else
                                  "verified_exact_reference" if quote in case["reference"]["text"] else "quote_absent_from_reference")
            elif type(page) is not int or not 1 <= page <= len(pages):
                item["status"] = "invalid_physical_page"
            elif quote in pages[page - 1]:
                item["status"] = "verified_exact_physical_page"
            else:
                other_pages = [number for number, text in enumerate(pages, 1) if quote in text]
                if other_pages:
                    item.update({"status": "wrong_physical_page", "quote_found_on_pages": other_pages})
                else:
                    item["status"] = "unverified_pdf_text"
                    item["note"] = "Quote not found in the fresh PDF text layer. OCR-only text or another extraction mismatch needs inspection of the original page."
        for item in record["quotes"]:
            statuses[item["status"]] += 1
            if not item["status"].startswith("verified_"):
                record["issues"].append(item["status"])
        record["issues"] = list(dict.fromkeys(record["issues"]))
    unknown_ids = sorted(set(grouped) - set(expected))
    issues = Counter(issue for result in results for issue in result["issues"])
    return {"cases": len(cases), "cases_with_issues": sum(bool(row["issues"]) for row in results),
            "all_checks_verified": not any(row["issues"] for row in results) and not unknown_ids and not invalid_prediction_rows,
            "unknown_prediction_ids": unknown_ids, "invalid_prediction_rows": invalid_prediction_rows,
            "case_issue_counts": dict(issues), "quote_status_counts": dict(statuses), "results": results,
            "documents": {key: {name: value for name, value in document.items() if name != "texts"} for key, document in documents.items()},
            "method": "Fresh pypdf extraction; exact substring matching on 1-based physical PDF pages. No gold, model call, OCR, or engine validator is used.",
            "limitations": "A verified quote proves location and exact extracted text only. It does not establish relevance, correct attribution, or a correct NLI label. OCR-only quotations remain unverified. Official fuzzy gold-passage scoring is separate."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    try:
        report = audit(read_jsonl(args.input), read_jsonl(args.predictions), args.data_root or args.input.parent)
        report.update({"input_sha256": file_hash(args.input), "predictions_sha256": file_hash(args.predictions),
                       "auditor_sha256": file_hash(__file__)})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("{} cases; {} with issues; quote statuses: {}".format(report["cases"], report["cases_with_issues"], report["quote_status_counts"]))
        return 0 if report["all_checks_verified"] else 1
    except (ValueError, OSError) as error:
        parser.exit(2, "Audit error: {}\n".format(error))


if __name__ == "__main__":
    raise SystemExit(main())
