"""Oversized evidence is reduced by bounded model selection, never truncation."""

import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from claimlens.config import Settings
from claimlens.context import (MAX_REDUCTION_ROUNDS, REDUCTION_PROMPT, TokenBudget,
                               request_reduction, source_units, validate_reduction)
from claimlens.engine import check_claim
from claimlens.models import DEFAULT_MODEL, ProviderError, ValidationError


CLAIM = "Eligible workers receive 200 francs from 2028."
SOURCES = [{"id": "page-{}".format(index), "page": index, "language": "fr",
            "text": "Original explanatory source text on page {} with necessary facts and qualifications.".format(index)}
           for index in range(1, 13)]
SETTINGS = Settings("https://evaluation.example/v1", context_tokens=8192, document_strategy="exhaustive")
USAGE = {"input_tokens": 100, "output_tokens": 10, "model_request_attempts": 1}


def extraction(_claim, units, *_args):
    return {"complete": True, "evidence_ids": [unit["id"] for unit in units]}, dict(USAGE)


def final_response(claim, passages, *_args, **_kwargs):
    return {"summary": "Source facts jointly support the claim.", "checks": [{
        "text": claim, "dimension": "general", "label": "entailment", "explanation": "Evidence from both pages.",
        "evidence": [{"passage_id": passage["id"], "quote": passage["text"]} for passage in passages]}]}, dict(USAGE)


def fits_windows(_budget, messages, _output_tokens):
    payload = json.loads(messages[1]["content"])
    if "units" in payload:
        return len(payload["units"]) <= 4
    return len(payload["passages"]) <= 2


class ReductionTests(unittest.TestCase):
    def test_all_candidates_examined_each_round_with_exact_original_provenance(self):
        initial, rounds = [], []
        def read_all(claim, units, *args):
            initial.extend(units)
            return extraction(claim, units, *args)
        def reduce(_claim, units, _model, settings, language, vote, maximum_ids):
            self.assertEqual((language, vote), ("de", "Workers"))
            self.assertGreater(settings.max_document_model_calls, 0)
            rounds.append([unit["id"] for unit in units])
            # Keep the model-selected distributed facts, with some other units
            # in round one to force a second complete reduction pass.
            selected = [unit["id"] for unit in units if unit["page"] in (2, 11)]
            if len(rounds) <= 3:
                selected += [unit["id"] for unit in units if unit["id"] not in selected][:maximum_ids - len(selected)]
            return {"complete": True, "evidence_ids": selected}, dict(USAGE)
        with patch.object(TokenBudget, "fits", fits_windows), \
                patch("claimlens.context.request_extraction", side_effect=read_all) as extract, \
                patch("claimlens.context.request_reduction", side_effect=reduce) as reduction, \
                patch("claimlens.engine.request_completion", side_effect=final_response) as final:
            result = check_claim({"passages": SOURCES, "vote": "Workers"}, CLAIM,
                                 DEFAULT_MODEL, "live", SETTINGS, claim_language="de")
        self.assertEqual(initial, source_units(SOURCES))
        self.assertEqual([item for window in rounds[:3] for item in window], [unit["id"] for unit in initial])
        self.assertEqual([item for window in rounds[3:] for item in window], ["u1", "u2", "u5", "u6", "u9", "u11"])
        self.assertEqual([passage["page"] for passage in final.call_args.args[1]], [2, 11])
        for passage in final.call_args.args[1]:
            self.assertEqual(passage, SOURCES[passage["page"] - 1])
        self.assertEqual(final.call_count, 1)
        self.assertEqual(result["classification"], 0)
        self.assertEqual(result["passages"], SOURCES)
        calls = extract.call_count + reduction.call_count + final.call_count
        self.assertEqual(result["metrics"]["input_tokens"], calls * 100)
        self.assertEqual(result["metrics"]["output_tokens"], calls * 10)
        self.assertEqual(result["processing"]["model_calls"], calls)
        self.assertEqual(result["processing"]["reduction_rounds"], 2)
        self.assertEqual(result["processing"]["initial_selected_units"], 12)
        self.assertEqual(result["processing"]["selected_units"], 2)
        self.assertEqual(result["processing"]["reduction_candidates_examined"], 18)
        self.assertIn("can omit relevant facts", result["processing"]["coverage"])

    def test_invalid_reducer_output_fails_with_all_known_usage(self):
        invalid = [{"complete": False, "evidence_ids": []},
                   {"complete": True, "evidence_ids": ["invented"]},
                   {"complete": True, "evidence_ids": ["u1", "u1"]},
                   {"complete": True, "evidence_ids": ["u1", "u2", "u3"]}]
        for response in invalid:
            with self.subTest(response=response), patch.object(TokenBudget, "fits", fits_windows), \
                    patch("claimlens.context.request_extraction", side_effect=extraction) as extract, \
                    patch("claimlens.context.request_reduction", return_value=(response, dict(USAGE))) as reduction, \
                    patch("claimlens.engine.request_completion") as final, self.assertRaises(ValidationError) as raised:
                check_claim({"passages": SOURCES}, CLAIM, DEFAULT_MODEL, "live", SETTINGS)
            self.assertEqual(raised.exception.metrics["input_tokens"], (extract.call_count + reduction.call_count) * 100)
            final.assert_not_called()

    def test_nonprogress_fails_without_a_partial_verdict_or_whole_case_retry(self):
        def fits(_budget, messages, _output):
            payload = json.loads(messages[1]["content"])
            return "units" in payload and (messages[0]["content"] != REDUCTION_PROMPT or len(payload["units"]) <= 1)
        with patch.object(TokenBudget, "fits", fits), \
                patch("claimlens.context.request_extraction", side_effect=extraction), \
                patch("claimlens.context.request_reduction", side_effect=extraction) as reduction, \
                patch("claimlens.engine.request_completion") as final, self.assertRaisesRegex(ValidationError, "no progress") as raised:
            check_claim({"passages": SOURCES}, CLAIM, DEFAULT_MODEL, "live", SETTINGS)
        self.assertEqual(reduction.call_count, 12)
        self.assertFalse(raised.exception.retryable)
        self.assertEqual(raised.exception.metrics["model_request_attempts"], 13)
        final.assert_not_called()

    def test_reduction_call_budget_failure_occurs_before_additional_model_calls(self):
        with patch.object(TokenBudget, "fits", fits_windows), \
                patch("claimlens.context.request_extraction", side_effect=extraction) as extract, \
                patch("claimlens.context.request_reduction") as reduction, \
                patch("claimlens.engine.request_completion") as final, self.assertRaisesRegex(ValidationError, "remaining MAX_DOCUMENT") as raised:
            check_claim({"passages": SOURCES}, CLAIM, DEFAULT_MODEL, "live",
                        replace(SETTINGS, max_document_model_calls=4))
        self.assertFalse(raised.exception.retryable)
        self.assertEqual(raised.exception.metrics["input_tokens"], extract.call_count * 100)
        reduction.assert_not_called()
        final.assert_not_called()

    def test_deadline_includes_reduction_and_preserves_its_usage(self):
        elapsed = [0]
        def reduce(*_args):
            elapsed[0] = 11
            return {"complete": True, "evidence_ids": ["u1"]}, dict(USAGE)
        with patch.object(TokenBudget, "fits", fits_windows), \
                patch("claimlens.context.time.monotonic", side_effect=lambda: elapsed[0]), \
                patch("claimlens.context.request_extraction", side_effect=extraction), \
                patch("claimlens.context.request_reduction", side_effect=reduce), \
                patch("claimlens.engine.request_completion") as final, self.assertRaisesRegex(ProviderError, "DOCUMENT_TIMEOUT") as raised:
            check_claim({"passages": SOURCES}, CLAIM, DEFAULT_MODEL, "live", replace(SETTINGS, document_timeout=10))
        self.assertEqual(raised.exception.metrics["input_tokens"], 400)
        self.assertEqual(raised.exception.metrics["model_request_attempts"], 4)
        final.assert_not_called()

    def test_reducer_empty_selection_requires_all_windows_before_neutral(self):
        seen = []
        def reduce(_claim, units, *_args):
            seen.extend(unit["id"] for unit in units)
            return {"complete": True, "evidence_ids": []}, dict(USAGE)
        with patch.object(TokenBudget, "fits", fits_windows), \
                patch("claimlens.context.request_extraction", side_effect=extraction), \
                patch("claimlens.context.request_reduction", side_effect=reduce), \
                patch("claimlens.engine.request_completion") as final:
            result = check_claim({"passages": SOURCES}, CLAIM, DEFAULT_MODEL, "live", SETTINGS)
        self.assertEqual(seen, [unit["id"] for unit in source_units(SOURCES)])
        self.assertEqual(result["classification"], 1)
        self.assertEqual(result["processing"]["reduction_rounds"], 1)
        self.assertEqual(result["processing"]["selected_units"], 0)
        final.assert_not_called()

    def test_maximum_rounds_bound_reduction(self):
        def fits(_budget, messages, _output):
            return "units" in json.loads(messages[1]["content"])
        def reduce(_claim, units, *_args):
            maximum_ids = _args[-1]
            return {"complete": True, "evidence_ids": [unit["id"] for unit in units[:maximum_ids]]}, dict(USAGE)
        with patch.object(TokenBudget, "fits", fits), patch("claimlens.context.MAX_REDUCTION_ROUNDS", 2), \
                patch("claimlens.context.request_extraction", side_effect=extraction), \
                patch("claimlens.context.request_reduction", side_effect=reduce) as reduction, \
                patch("claimlens.engine.request_completion") as final, self.assertRaisesRegex(ValidationError, "bounded evidence-reduction rounds") as raised:
            check_claim({"passages": SOURCES}, CLAIM, DEFAULT_MODEL, "live", SETTINGS)
        self.assertEqual(MAX_REDUCTION_ROUNDS, 8)
        self.assertEqual(reduction.call_count, 2)
        self.assertFalse(raised.exception.retryable)
        self.assertEqual(raised.exception.metrics["input_tokens"], 300)
        final.assert_not_called()

    def test_remote_and_local_requests_share_limits_and_verbatim_units(self):
        units = source_units(SOURCES[:4])
        for local in (False, True):
            settings = replace(SETTINGS, base_url="http://localhost:8081/v1", local_model_id="apertus") if local else SETTINGS
            with self.subTest(local=local), patch("claimlens.context.request_json", return_value=({}, USAGE)) as request:
                request_reduction(CLAIM, units, DEFAULT_MODEL, settings, "de", "Workers", 2)
            payload = request.call_args.args[0]
            user = json.loads(payload["messages"][1]["content"])
            self.assertEqual(user["maximum_evidence_ids"], 2)
            self.assertEqual([unit["text"] for unit in user["units"]], [unit["text"] for unit in units])
            if local:
                schema = payload["response_format"]["json_schema"]["schema"]
                self.assertEqual(schema["properties"]["evidence_ids"]["maxItems"], 2)
                self.assertEqual(schema["properties"]["evidence_ids"]["items"]["enum"], [unit["id"] for unit in units])
            else:
                self.assertEqual(payload["response_format"], {"type": "json_object"})
        with self.assertRaises(ValidationError):
            validate_reduction({"complete": True, "evidence_ids": ["u1", "u2", "u3"]}, units, 2)


if __name__ == "__main__":
    unittest.main()
