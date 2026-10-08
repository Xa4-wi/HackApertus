"""Rejected intermediate/final answers still contribute their observed usage."""

import unittest
from unittest.mock import patch

from claimlens.config import Settings
from claimlens.engine import check_claim
from claimlens.models import DEFAULT_MODEL, ProviderError, ValidationError


class FailureAccountingTests(unittest.TestCase):
    def test_invalid_final_structure_keeps_completed_usage(self):
        usage = {"input_tokens": 80, "output_tokens": 20}
        with patch("claimlens.engine.request_completion", return_value=({}, usage)):
            with self.assertRaises(ValidationError) as caught:
                check_claim({"passages": [{"id": "p1", "text": "A short source."}]},
                            "A claim.", DEFAULT_MODEL, "live", Settings("https://proxy.example/v1", document_strategy="exhaustive"))
        self.assertEqual(caught.exception.metrics["input_tokens"], 80)
        self.assertEqual(caught.exception.metrics["output_tokens"], 20)

    def test_later_segment_error_keeps_prior_and_failed_call_usage(self):
        source = {"id": "p1", "text": "Source with enough text to require many segments. " * 500}
        failure = ProviderError("Failed after a measured response.", metrics={
            "input_tokens": 70, "output_tokens": 7, "model_request_attempts": 2})
        with patch("claimlens.context.request_extraction", side_effect=[
                ({"complete": True, "evidence_ids": []}, {"input_tokens": 100, "output_tokens": 10}),
                failure]):
            with self.assertRaises(ProviderError) as caught:
                check_claim({"passages": [source]}, "A claim.", DEFAULT_MODEL, "live",
                            Settings("https://proxy.example/v1", context_tokens=8192, document_strategy="exhaustive"))
        self.assertEqual(caught.exception.metrics["input_tokens"], 170)
        self.assertEqual(caught.exception.metrics["output_tokens"], 17)
        self.assertEqual(caught.exception.metrics["model_request_attempts"], 3)

    def test_unknown_failed_usage_does_not_erase_known_partial_counts(self):
        source = {"id": "p1", "text": "Source with enough text to require many segments. " * 500}
        failure = ProviderError("Unknown remote usage.", metrics={
            "input_tokens": None, "output_tokens": None,
            "known_input_tokens": 70, "known_output_tokens": 7})
        with patch("claimlens.context.request_extraction", side_effect=[
                ({"complete": True, "evidence_ids": []}, {"input_tokens": 100, "output_tokens": 10}),
                failure]):
            with self.assertRaises(ProviderError) as caught:
                check_claim({"passages": [source]}, "A claim.", DEFAULT_MODEL, "live",
                            Settings("https://proxy.example/v1", context_tokens=8192, document_strategy="exhaustive"))
        self.assertIsNone(caught.exception.metrics["input_tokens"])
        self.assertIsNone(caught.exception.metrics["output_tokens"])
        self.assertEqual(caught.exception.metrics["known_input_tokens"], 170)
        self.assertEqual(caught.exception.metrics["known_output_tokens"], 17)
