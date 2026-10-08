"""Recovery preserves successful predictions and accounts for every attempt."""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from claimlens.cli import predict_case, run_batch
from claimlens.config import Settings
from claimlens.llm import request_json
from claimlens.models import DEFAULT_MODEL, ProviderError, ValidationError


SETTINGS = Settings("https://proxy.example/v1", "private-token", DEFAULT_MODEL, 30)
CASE = {"id": "one", "vote": "A fee", "claim": {"text": "Die Gebühr beträgt 200 Franken.", "language": "de"},
        "reference": {"text": "Die Gebühr beträgt 200 Franken.", "language": "de"}}


def result(*, degraded=False, inputs=20, outputs=5):
    return {"claim": CASE["claim"]["text"], "classification": 0, "overall": "entailment",
            "validation_degraded": degraded,
            "passages": [{"id": "reference-1", "page": None}],
            "checks": [{"text": CASE["claim"]["text"], "dimension": "general",
                        "evidence": [{"passage_id": "reference-1", "quote": CASE["reference"]["text"]}]}],
            "metrics": {"input_tokens": inputs, "output_tokens": outputs, "inference_time_ms": 1},
            "processing": {"model_calls": 1}}


class PredictionRecoveryTests(unittest.TestCase):
    def test_invalid_verdict_recovers_and_counts_both_inferences(self):
        with patch("claimlens.cli.check_claim", side_effect=[result(degraded=True), result()]) as infer, \
                redirect_stderr(io.StringIO()):
            record, detailed = predict_case(CASE, SETTINGS, Path("."))
        self.assertEqual(infer.call_count, 2)
        self.assertEqual(record["metrics"]["input_tokens"], 40)
        self.assertEqual(record["metrics"]["output_tokens"], 10)
        self.assertEqual(detailed["processing"]["model_calls"], 2)
        self.assertEqual(detailed["processing"]["classification_attempts"], 2)
        self.assertLessEqual(infer.call_args_list[1].args[4].document_timeout,
                             infer.call_args_list[0].args[4].document_timeout)

    def test_invalid_verdict_stops_after_two_attempts_with_usage(self):
        with patch("claimlens.cli.check_claim", side_effect=[result(degraded=True), result(degraded=True)]) as infer, \
                redirect_stderr(io.StringIO()), self.assertRaises(ValidationError) as raised:
            predict_case(CASE, SETTINGS, Path("."))
        self.assertEqual(infer.call_count, 2)
        self.assertEqual(raised.exception.metrics["input_tokens"], 40)
        self.assertEqual(raised.exception.attempts, 2)

    def test_structural_validation_error_with_known_usage_can_recover(self):
        error = ValidationError("Model response checks were not an array.")
        error.metrics = {"input_tokens": 8, "output_tokens": 4, "model_request_attempts": 1}
        with patch("claimlens.cli.check_claim", side_effect=[error, result()]) as infer, redirect_stderr(io.StringIO()):
            record, _ = predict_case(CASE, SETTINGS, Path("."))
        self.assertEqual(infer.call_count, 2)
        self.assertEqual(record["metrics"]["input_tokens"], 28)
        self.assertEqual(record["metrics"]["output_tokens"], 9)

    def test_capacity_failure_does_not_repeat_the_entire_analysis(self):
        from claimlens.context import capacity_error
        error = capacity_error("Evidence reduction made no progress.")
        error.metrics = {"input_tokens": 12000, "output_tokens": 300, "model_request_attempts": 3}
        with patch("claimlens.cli.check_claim", side_effect=error) as infer, self.assertRaises(ValidationError) as raised:
            predict_case(CASE, SETTINGS, Path("."))
        self.assertEqual(infer.call_count, 1)
        self.assertEqual(raised.exception.metrics["input_tokens"], 12000)
        self.assertEqual(raised.exception.attempts, 3)

    def test_transport_retries_count_towards_the_case_model_call_budget(self):
        invalid = result(degraded=True)
        invalid["metrics"]["model_request_attempts"] = 2
        with patch("claimlens.cli.check_claim", return_value=invalid) as infer, redirect_stderr(io.StringIO()), \
                self.assertRaisesRegex(ValidationError, "model-call budget") as raised:
            predict_case(CASE, replace(SETTINGS, max_document_model_calls=2), Path("."))
        self.assertEqual(infer.call_count, 1)
        self.assertEqual(raised.exception.metrics["input_tokens"], 20)
        self.assertEqual(raised.exception.attempts, 2)

    def test_unknown_usage_never_becomes_a_valid_prediction(self):
        with patch("claimlens.cli.check_claim", return_value=result(degraded=True, inputs=None)) as infer, \
                self.assertRaises(ValidationError) as raised:
            predict_case(CASE, SETTINGS, Path("."))
        self.assertEqual(infer.call_count, 1)
        self.assertIsNone(raised.exception.metrics["input_tokens"])
        self.assertEqual(raised.exception.metrics["output_tokens"], 5)

    def test_failed_recovery_retains_prior_usage_and_unknown_failure(self):
        error = ProviderError("Unavailable.", metrics={"input_tokens": None, "output_tokens": None})
        with patch("claimlens.cli.check_claim", side_effect=[result(degraded=True), error]), \
                redirect_stderr(io.StringIO()), self.assertRaises(ProviderError) as raised:
            predict_case(CASE, SETTINGS, Path("."))
        self.assertIsNone(raised.exception.metrics["input_tokens"])
        self.assertEqual(raised.exception.metrics["known_input_tokens"], 20)

    def test_batch_keeps_successes_after_a_failed_middle_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, output = root / "input.jsonl", root / "out.jsonl"
            cases = [{**copy.deepcopy(CASE), "id": str(index)} for index in range(3)]
            inputs.write_text("\n".join(json.dumps(case) for case in cases), encoding="utf-8")
            output.write_text("old successful output\n", encoding="utf-8")
            stderr = io.StringIO()
            with patch("claimlens.cli.check_claim", side_effect=[result(), ProviderError("Unavailable."), result()]) as infer, \
                    redirect_stderr(stderr), self.assertRaisesRegex(ValidationError, "1 of 3 cases failed"):
                run_batch(inputs, output, SETTINGS, root)
            self.assertEqual(infer.call_count, 3)
            self.assertEqual(output.read_text(), "old successful output\n")
            saved = [json.loads(line) for line in (root / "out.jsonl.partial.jsonl").read_text().splitlines()]
            self.assertEqual([row["id"] for row in saved], ["0", "2"])
            self.assertIn('"id": "1"', stderr.getvalue())
            self.assertNotIn("private-token", stderr.getvalue())

    def test_successful_batch_promotes_checkpoint_and_cleans_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, output = root / "input.jsonl", root / "out.jsonl"
            inputs.write_text(json.dumps(CASE), encoding="utf-8")
            with patch("claimlens.cli.check_claim", return_value=result()):
                self.assertEqual(run_batch(inputs, output, SETTINGS, root), 1)
            self.assertEqual(json.loads(output.read_text())["id"], "one")
            self.assertFalse((root / "out.jsonl.partial.jsonl").exists())

    def test_malformed_input_preserves_both_old_output_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, output = root / "input.jsonl", root / "out.jsonl"
            checkpoint = root / "out.jsonl.partial.jsonl"
            inputs.write_text(json.dumps(CASE) + "\nnot json", encoding="utf-8")
            output.write_text("old output", encoding="utf-8")
            checkpoint.write_text("old checkpoint", encoding="utf-8")
            with patch("claimlens.cli.check_claim") as infer, self.assertRaisesRegex(ValidationError, "line 2"):
                run_batch(inputs, output, SETTINGS, root)
            infer.assert_not_called()
            self.assertEqual(output.read_text(), "old output")
            self.assertEqual(checkpoint.read_text(), "old checkpoint")


def response(content='{"ok": true}', inputs=20, outputs=5):
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                                 "usage": {"prompt_tokens": inputs, "completion_tokens": outputs}}).encode())


def http_error(status):
    return HTTPError("https://proxy.example/v1/chat/completions", status, "private provider body", {}, io.BytesIO(b"private body"))


class TransportRecoveryTests(unittest.TestCase):
    def request(self, effects, settings=SETTINGS):
        opener = Mock()
        opener.open.side_effect = effects
        with patch("claimlens.llm.build_opener", return_value=opener), patch("claimlens.llm.time.sleep"):
            value = request_json({"messages": [], "model": DEFAULT_MODEL}, settings, [])
        return value, opener

    def test_rate_limit_then_success_reports_success_usage(self):
        (_, metrics), opener = self.request([http_error(429), response()])
        self.assertEqual(opener.open.call_count, 2)
        self.assertEqual(metrics["input_tokens"], 20)
        self.assertEqual(metrics["output_tokens"], 5)
        self.assertEqual(metrics["model_request_attempts"], 2)

    def test_invalid_json_completion_usage_is_included_on_recovery(self):
        (_, metrics), opener = self.request([response("invalid JSON", 7, 3), response()])
        self.assertEqual(opener.open.call_count, 2)
        self.assertEqual(metrics["input_tokens"], 27)
        self.assertEqual(metrics["output_tokens"], 8)

    def test_ambiguous_server_failure_keeps_total_usage_unknown(self):
        (_, metrics), opener = self.request([http_error(503), response()])
        self.assertEqual(opener.open.call_count, 2)
        self.assertIsNone(metrics["input_tokens"])
        self.assertIsNone(metrics["output_tokens"])
        self.assertEqual(metrics["known_input_tokens"], 20)
        self.assertEqual(metrics["known_output_tokens"], 5)

    def test_access_denied_is_not_retried_and_error_has_no_provider_body(self):
        opener = Mock()
        opener.open.side_effect = http_error(401)
        with patch("claimlens.llm.build_opener", return_value=opener), self.assertRaises(ProviderError) as raised:
            request_json({}, SETTINGS, [])
        self.assertEqual(opener.open.call_count, 1)
        self.assertNotIn("private", str(raised.exception))

    def test_invalid_completion_stops_at_three_attempts_and_retains_usage(self):
        opener = Mock()
        opener.open.side_effect = [response("bad") for _ in range(3)]
        with patch("claimlens.llm.build_opener", return_value=opener), patch("claimlens.llm.time.sleep"), \
                self.assertRaises(ProviderError) as raised:
            request_json({}, SETTINGS, [])
        self.assertEqual(opener.open.call_count, 3)
        self.assertEqual(raised.exception.metrics["input_tokens"], 60)
        self.assertEqual(raised.exception.metrics["output_tokens"], 15)

    def test_retries_share_one_deadline(self):
        elapsed = [0]
        opener = Mock()
        def unavailable(*args, **kwargs):
            self.assertLessEqual(kwargs["timeout"], 0.15)
            elapsed[0] += 0.1
            raise http_error(429)
        opener.open.side_effect = unavailable
        with patch("claimlens.llm.build_opener", return_value=opener), \
                patch("claimlens.llm.time.monotonic", side_effect=lambda: elapsed[0]), \
                patch("claimlens.llm.time.sleep") as sleep, self.assertRaises(ProviderError):
            request_json({}, replace(SETTINGS, timeout=0.15), [])
        self.assertEqual(opener.open.call_count, 1)
        sleep.assert_not_called()

    def test_transport_obeys_remaining_document_call_budget(self):
        opener = Mock()
        opener.open.side_effect = [response("bad"), response("bad")]
        with patch("claimlens.llm.build_opener", return_value=opener), patch("claimlens.llm.time.sleep"), \
                self.assertRaises(ProviderError):
            request_json({}, replace(SETTINGS, max_document_model_calls=2), [])
        self.assertEqual(opener.open.call_count, 2)

    def test_late_success_is_rejected_with_its_actual_usage(self):
        elapsed = [0]
        body = response().getvalue()
        class SlowResponse(io.BytesIO):
            def read(self, size=-1):
                elapsed[0] += 0.2
                return super().read(size)
        opener = Mock()
        opener.open.return_value = SlowResponse(body)
        with patch("claimlens.llm.build_opener", return_value=opener), \
                patch("claimlens.llm.time.monotonic", side_effect=lambda: elapsed[0]), \
                self.assertRaisesRegex(ProviderError, "exceeded.*timeout") as raised:
            request_json({}, replace(SETTINGS, timeout=0.15), [])
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual(raised.exception.metrics["input_tokens"], 20)
        self.assertEqual(raised.exception.metrics["output_tokens"], 5)
        self.assertEqual(raised.exception.metrics["inference_time_ms"], 200)


if __name__ == "__main__":
    unittest.main()
