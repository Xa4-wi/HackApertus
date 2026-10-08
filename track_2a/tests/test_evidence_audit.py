import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("audit_evidence", Path(__file__).parents[1] / "scripts/audit_evidence.py")
auditor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auditor)


class EvidenceAuditTests(unittest.TestCase):
    def prediction(self, evidence, label=0):
        return {"id": "case", "label": label, "label_name": auditor.LABELS[label], "evidence": evidence,
                "metrics": {"input_tokens": 10, "output_tokens": 5, "inference_time_ms": 20}}

    def test_physical_page_keeps_blank_pages_and_detects_wrong_page(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.pdf").write_bytes(b"PDF fixture placeholder")
            case = {"id": "case", "booklet": {"path": "source.pdf"}}
            with patch.object(auditor, "pdf_pages", return_value=["", "The fee is 200 francs."]):
                correct = auditor.audit([case], [self.prediction([{"page": 2, "text": "The fee is 200 francs."}])], root)
                wrong = auditor.audit([case], [self.prediction([{"page": 1, "text": "The fee is 200 francs."}])], root)
            self.assertTrue(correct["all_checks_verified"])
            self.assertEqual(correct["documents"]["source.pdf"]["page_count"], 2)
            self.assertEqual(wrong["quote_status_counts"], {"wrong_physical_page": 1})
            self.assertEqual(wrong["results"][0]["quotes"][0]["quote_found_on_pages"], [2])

    def test_ocr_only_quote_is_unverified_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.pdf").write_bytes(b"PDF fixture placeholder")
            with patch.object(auditor, "pdf_pages", return_value=[""]):
                result = auditor.audit([{"id": "case", "booklet": {"path": "source.pdf"}}],
                    [self.prediction([{"page": 1, "text": "Visible in the scanned image"}])], root)
            self.assertFalse(result["all_checks_verified"])
            self.assertEqual(result["quote_status_counts"], {"unverified_pdf_text": 1})

    def test_reference_evidence_requires_exact_text_and_null_page(self):
        case = {"id": "case", "reference": {"text": "La taxe est de 200 francs."}}
        for citation, expected in [({"page": None, "text": "200 francs"}, "verified_exact_reference"),
                                   ({"page": 1, "text": "200 francs"}, "invalid_reference_page"),
                                   ({"page": None, "text": "300 francs"}, "quote_absent_from_reference")]:
            with self.subTest(citation=citation):
                result = auditor.audit([case], [self.prediction([citation])], ".")
                self.assertEqual(result["quote_status_counts"], {expected: 1})

    def test_contract_failures_are_separate_from_official_f1(self):
        case = {"id": "case", "reference": {"text": "Source"}}
        prediction = self.prediction([])
        prediction["metrics"]["input_tokens"] = float("nan")
        result = auditor.audit([case], [prediction], ".")
        self.assertFalse(result["all_checks_verified"])
        self.assertEqual(result["case_issue_counts"], {"invalid_metric_input_tokens": 1})
        result = auditor.audit([case], [prediction, prediction, dict(prediction, id="unknown")], ".")
        self.assertEqual(result["case_issue_counts"], {"duplicate_response": 1})
        self.assertEqual(result["unknown_prediction_ids"], ["unknown"])

    def test_task_a_requires_evidence_and_cannot_escape_input_root(self):
        case = {"id": "case", "booklet": {"path": "../outside.pdf"}}
        result = auditor.audit([case], [self.prediction([])], ".")
        self.assertEqual(result["case_issue_counts"], {"missing_required_booklet_evidence": 1})
        with self.assertRaisesRegex(ValueError, "escapes"):
            auditor.audit([case], [self.prediction([{"page": 1, "text": "quote"}])], ".")


if __name__ == "__main__":
    unittest.main()
