"""Fast booklet routing must preserve the reference contract and case limits."""

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from claimlens.booklets import extract_pdf, prepare_case
from claimlens.cli import predict_case
from claimlens.config import Settings, load_dotenv, public_config
from claimlens.engine import check_claim
from claimlens.llm import completion_messages
from claimlens.models import DEFAULT_MODEL, ValidationError


CLAIM = "La redevance annuelle est de 200 francs."
PASSAGE = {"id": "page-2", "page": 2, "language": "fr", "text": CLAIM}
SETTINGS = Settings("https://proxy.example/v1")


def assessment():
    return {"summary": "The stated amount matches.", "checks": [{
        "text": CLAIM, "dimension": "general", "label": "entailment",
        "explanation": "The stated amount matches.",
        "evidence": [{"passage_id": PASSAGE["id"], "quote": CLAIM}],
    }]}


class FastContractsTests(unittest.TestCase):
    def test_fast_configuration_defaults_overrides_and_invalid_limits(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()
        self.assertEqual((settings.document_strategy, settings.retrieval_prompt_tokens,
                          settings.retrieval_timeout), ("retrieval", 5000, 120))
        for key, value in (("DOCUMENT_STRATEGY", "guess"), ("RETRIEVAL_PROMPT_TOKENS", "1499"),
                           ("RETRIEVAL_PROMPT_TOKENS", "12001"), ("RETRIEVAL_PROMPT_TOKENS", "nan"),
                           ("RETRIEVAL_TIMEOUT_SECONDS", "nan"), ("RETRIEVAL_TIMEOUT_SECONDS", "301")):
            with self.subTest(key=key, value=value), patch.dict(os.environ, {key: value}, clear=True):
                with self.assertRaises(ValidationError):
                    Settings.from_env()
        self.assertEqual(public_config(settings)["request_timeout_seconds"], 130)
        self.assertEqual(public_config(replace(settings, document_strategy="exhaustive"))["request_timeout_seconds"], 1810)

    def test_injected_strategy_overrides_dotenv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("DOCUMENT_STRATEGY=retrieval\nRETRIEVAL_PROMPT_TOKENS=4500\nRETRIEVAL_TIMEOUT_SECONDS=90\n")
            with patch.dict(os.environ, {"DOCUMENT_STRATEGY": "exhaustive"}, clear=True):
                load_dotenv(path)
                settings = Settings.from_env()
        self.assertEqual((settings.document_strategy, settings.retrieval_prompt_tokens,
                          settings.retrieval_timeout), ("exhaustive", 4500, 90))

    def test_reference_routing_preserves_full_source_even_with_fast_default(self):
        case = {"id": "one", "claim": {"text": CLAIM}, "reference": {"text": CLAIM}}
        proposal, claim, language = prepare_case(case, Path("."))
        response = assessment()
        response["checks"][0]["evidence"][0]["passage_id"] = "reference-1"
        with patch("claimlens.engine.analyze_document", return_value=(response,
                {"input_tokens": 12, "output_tokens": 4, "context_tokens": None}, {"strategy": "full"})) as analyze:
            result = check_claim(proposal, claim, DEFAULT_MODEL, "live", SETTINGS, claim_language=language)
        self.assertEqual(analyze.call_args.args[3].document_strategy, "exhaustive")
        self.assertEqual(analyze.call_args.args[1][0]["text"], CLAIM)
        self.assertEqual(result["classification"], 0)

    def test_retrieved_prompt_never_claims_every_segment_was_read(self):
        messages = completion_messages(CLAIM, [PASSAGE], retrieved=True)
        text = messages[0]["content"]
        self.assertIn("not the full booklet", text)
        self.assertNotIn("EVERY segment", text)
        self.assertIn("never quote across", text)

    def test_failed_fast_case_has_one_pipeline_attempt_and_retains_usage(self):
        case = {"id": "one", "claim": {"text": CLAIM}, "booklet": {"path": "booklet.pdf"}}
        proposal = {"passages": [PASSAGE], "source_kind": "booklet"}
        error = ValidationError("Invalid final model evidence.")
        error.metrics = {"input_tokens": 800, "output_tokens": 40, "model_request_attempts": 2}
        with patch("claimlens.cli.prepare_case", return_value=(proposal, CLAIM, "fr")), \
                patch("claimlens.cli.check_claim", side_effect=error) as infer, \
                self.assertRaises(ValidationError) as caught:
            predict_case(case, SETTINGS, Path("."))
        self.assertEqual(infer.call_count, 1)
        bounded = infer.call_args.args[4]
        self.assertLessEqual(bounded.document_timeout, 120)
        self.assertEqual(bounded.max_document_model_calls, 4)
        self.assertEqual(caught.exception.metrics["input_tokens"], 800)
        self.assertEqual(caught.exception.metrics["output_tokens"], 40)

    def test_pdf_preparation_time_is_deducted_before_inference(self):
        now = [0.0]
        def prepare(*args, **kwargs):
            self.assertEqual(kwargs["deadline"], 120)
            now[0] = 121
            return {"source_kind": "booklet"}, CLAIM, "fr"
        case = {"id": "one", "booklet": {"path": "booklet.pdf"}}
        with patch("claimlens.cli.time.monotonic", side_effect=lambda: now[0]), \
                patch("claimlens.cli.prepare_case", side_effect=prepare), \
                patch("claimlens.cli.check_claim") as infer, \
                self.assertRaisesRegex(ValidationError, "time or model-call budget"):
            predict_case(case, SETTINGS, Path("."))
        infer.assert_not_called()

    def test_ocr_receives_remaining_case_time_and_late_source_is_rejected(self):
        now = [5.0]
        def ocr(*args, **kwargs):
            self.assertEqual(kwargs["timeout_seconds"], 5)
            now[0] = 11
            return {1: CLAIM}, []
        reader = SimpleNamespace(is_encrypted=False, pages=[Mock(extract_text=Mock(return_value=""))])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "one.pdf"
            path.write_bytes(b"%PDF-test")
            with patch("pypdf.PdfReader", return_value=reader), \
                    patch("claimlens.booklets.time.monotonic", side_effect=lambda: now[0]), \
                    patch("claimlens.booklets.ocr_pages", side_effect=ocr), \
                    self.assertRaisesRegex(ValidationError, "PDF preparation exceeded"):
                extract_pdf(path, "fr", deadline=10)


if __name__ == "__main__":
    unittest.main()
