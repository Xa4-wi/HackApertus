"""Presentation slide 24 inputs and optional metadata validation.

Fixtures reproduce the two input examples. Synthetic PDFs and model responses
exercise interoperability only; they are not model accuracy measurements.
"""

import copy
from contextlib import redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from claimlens.booklets import prepare_case
from claimlens.cli import run_batch
from claimlens.config import Settings
from claimlens.models import ValidationError
from test_submission import StubResponse, write_text_pdf


ADVANCED = {
    "id": "case-0042",
    "booklet": {"path": "booklets/2024_11_24_de.pdf"},
    "vote": "Étape d'aménagement 2023 des routes nationales",
    "claim": {"text": "La proposition entraînera une augmentation de la TVA."},
}
BEGINNER = {
    "id": "case-0043",
    "reference": {"text": "Der Bundesrat und der Nationalrat lehnen die Volksinitiative ab. "
                          "Die Initiative bringt zahlreiche neue Vorschriften mit sich."},
    "claim": {"text": "Le Conseil fédéral recommande d'accepter l'initiative."},
}


class PresentationInputTests(unittest.TestCase):
    def test_exact_beginner_example_uses_only_supplied_reference(self):
        original = copy.deepcopy(BEGINNER)
        with patch("claimlens.booklets.extract_pdf") as extractor:
            proposal, claim, language = prepare_case(BEGINNER, Path("/not-used"))
        extractor.assert_not_called()
        self.assertEqual(BEGINNER, original)
        self.assertEqual(claim, BEGINNER["claim"]["text"])
        self.assertEqual((language, proposal["language"], proposal["vote"]), ("auto", "auto", ""))
        self.assertEqual(len(proposal["passages"]), 1)
        self.assertEqual(proposal["passages"][0]["text"], BEGINNER["reference"]["text"])
        self.assertIsNone(proposal["passages"][0]["page"])
        self.assertEqual(proposal["passages"][0]["title"], "Supplied reference")

    def test_exact_advanced_example_does_not_infer_language_from_filename(self):
        original = copy.deepcopy(ADVANCED)
        with tempfile.TemporaryDirectory() as directory, \
                patch("claimlens.booklets.extract_pdf", return_value=[]) as extractor:
            root = Path(directory).resolve()
            proposal, claim, language = prepare_case(ADVANCED, root)
            extractor.assert_called_once_with(root / ADVANCED["booklet"]["path"], "auto", metadata={})
        self.assertEqual(ADVANCED, original)
        self.assertEqual((language, proposal["language"]), ("auto", "auto"))
        self.assertEqual(proposal["vote"], ADVANCED["vote"])
        self.assertEqual(claim, ADVANCED["claim"]["text"])

    def test_languages_can_be_omitted_independently_and_all_pairs_preserved(self):
        for claim_language in (None, "de", "fr", "it"):
            for source_language in (None, "de", "fr", "it"):
                with self.subTest(claim=claim_language, source=source_language):
                    case = copy.deepcopy(BEGINNER)
                    if claim_language:
                        case["claim"]["language"] = claim_language
                    if source_language:
                        case["reference"]["language"] = source_language
                    proposal, _, language = prepare_case(case, Path("."))
                    self.assertEqual(language, claim_language or "auto")
                    self.assertEqual(proposal["language"], source_language or "auto")

    def test_explicit_invalid_languages_are_not_treated_as_absent(self):
        for template, source in ((BEGINNER, "reference"), (ADVANCED, "booklet")):
            for field in ("claim", source):
                for value in (None, "", "auto", "en", "DE", 1, True, [], {}):
                    with self.subTest(source=source, field=field, value=value):
                        case = copy.deepcopy(template)
                        case[field]["language"] = value
                        with patch("claimlens.booklets.extract_pdf") as extractor, \
                                self.assertRaisesRegex(ValidationError, field + r"\.language"):
                            prepare_case(case, Path("."))
                        extractor.assert_not_called()

    def test_absent_vote_is_optional_only_for_reference_and_invalid_vote_rejected(self):
        case = copy.deepcopy(ADVANCED)
        del case["vote"]
        with self.assertRaisesRegex(ValidationError, "vote"):
            prepare_case(case, Path("."))
        for value in (None, "", "  ", 1, {}, "x" * 2001):
            case = copy.deepcopy(BEGINNER)
            case["vote"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValidationError, "vote"):
                prepare_case(case, Path("."))

    def test_missing_metadata_does_not_relax_required_text_or_source_exclusivity(self):
        for field in ("claim", "reference"):
            for value in (None, "", "  ", 0, [], {}):
                case = copy.deepcopy(BEGINNER)
                case[field]["text"] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    prepare_case(case, Path("."))
        case = copy.deepcopy(BEGINNER)
        case["booklet"] = ADVANCED["booklet"]
        with self.assertRaisesRegex(ValidationError, "exactly one"):
            prepare_case(case, Path("."))

    def test_metadata_free_booklet_cannot_escape_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            outside = root / "outside.pdf"
            outside.write_bytes(b"not a PDF")
            (data / "linked.pdf").symlink_to(outside)
            for path in ("../outside.pdf", str(outside), "linked.pdf"):
                case = copy.deepcopy(ADVANCED)
                case["booklet"]["path"] = path
                with self.subTest(path=path), patch("claimlens.booklets.extract_pdf") as extractor, \
                        self.assertRaisesRegex(ValidationError, "inside"):
                    prepare_case(case, data)
                extractor.assert_not_called()

    def test_path_resolution_failures_are_safe_validation_errors(self):
        for error in (ValueError("private invalid path"), OSError("private inaccessible path"),
                      RuntimeError("private symlink loop")):
            with self.subTest(error=type(error).__name__), \
                    patch("claimlens.booklets.Path.resolve", side_effect=error), \
                    self.assertRaisesRegex(ValidationError, "Could not resolve booklet.path") as raised:
                prepare_case(ADVANCED, Path("."))
            self.assertNotIn("private", str(raised.exception))

    def test_null_byte_path_does_not_abort_later_batch_cases(self):
        def completion(claim, *_args, **_kwargs):
            return ({"summary": "Synthetic interface check.", "checks": [{
                "text": claim, "dimension": "general", "label": "neutral",
                "explanation": "Synthetic interface check.", "evidence": [],
            }]}, {"input_tokens": 10, "output_tokens": 5, "context_tokens": None})

        invalid = copy.deepcopy(ADVANCED)
        invalid["booklet"]["path"] = "bad\x00path.pdf"
        before, after = copy.deepcopy(BEGINNER), copy.deepcopy(BEGINNER)
        before["id"], after["id"] = "before", "after"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path, output_path = root / "cases.jsonl", root / "predictions.jsonl"
            input_path.write_text("\n".join(json.dumps(case) for case in (before, invalid, after)), encoding="utf-8")
            stderr = io.StringIO()
            with patch("claimlens.engine.request_completion", side_effect=completion) as infer, \
                    redirect_stderr(stderr), self.assertRaisesRegex(ValidationError, "1 of 3 cases failed"):
                run_batch(input_path, output_path, Settings("https://proxy.example/v1"), root)
            records = [json.loads(line) for line in
                       (root / "predictions.jsonl.partial.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertFalse(output_path.exists())
        self.assertEqual(infer.call_count, 2)
        self.assertEqual([record["id"] for record in records], ["before", "after"])
        self.assertIn("booklet.path must not contain null bytes", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "Install requirements.txt for PDF checks")
    def test_language_free_scanned_pdf_reaches_multilingual_ocr(self):
        recovered = "Il Consiglio federale respinge la proposta di aumentare l'imposta."
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / ADVANCED["booklet"]["path"]
            pdf.parent.mkdir()
            write_text_pdf(pdf, [""])
            with patch("claimlens.booklets.ocr_pages", return_value=({1: recovered}, [])) as ocr:
                proposal, _, _ = prepare_case(ADVANCED, root)
            ocr.assert_called_once_with(pdf.resolve(), [1], "auto")
        self.assertEqual(proposal["passages"][0]["text"], recovered)
        self.assertEqual(proposal["passages"][0]["language"], "auto")
        self.assertEqual(proposal["passages"][0]["page"], 1)
        self.assertEqual(proposal["ocr_pages"], [1])

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "Install requirements.txt for PDF checks")
    def test_both_presentation_examples_run_through_cli_and_engine(self):
        requests = []

        class StubOpener:
            def open(self, request, timeout):
                payload = json.loads(request.data)
                user = json.loads(payload["messages"][-1]["content"])
                requests.append(user)
                passage = user["passages"][0]
                result = {"summary": "Synthetic contract check.", "checks": [{
                    "text": user["claim"], "dimension": "general", "label": "contradiction",
                    "explanation": "Synthetic contract check.",
                    "evidence": [{"passage_id": passage["id"], "quote": passage["text"]}],
                }]}
                return StubResponse(json.dumps({
                    "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}],
                    "usage": {"prompt_tokens": 123, "completion_tokens": 45},
                }).encode())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / ADVANCED["booklet"]["path"]
            pdf.parent.mkdir()
            write_text_pdf(pdf, ["Die Vorlage sieht keine Erhoehung der Mehrwertsteuer vor."])
            input_path, output_path = root / "cases.jsonl", root / "predictions.jsonl"
            input_path.write_text("\n".join(json.dumps(case) for case in (ADVANCED, BEGINNER)), encoding="utf-8")
            with patch("claimlens.llm.build_opener", return_value=StubOpener()):
                self.assertEqual(run_batch(input_path, output_path, Settings("https://proxy.example/v1"), root), 2)
            outputs = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([item["id"] for item in outputs], [ADVANCED["id"], BEGINNER["id"]])
        self.assertEqual([item["evidence"][0]["page"] for item in outputs], [1, None])
        self.assertEqual([item["claim_language"] for item in requests], ["auto", "auto"])
        self.assertEqual([item["vote"] for item in requests], [ADVANCED["vote"], ""])
        self.assertEqual(requests[1]["passages"][0]["text"], BEGINNER["reference"]["text"])


if __name__ == "__main__":
    unittest.main()
