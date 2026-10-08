"""Long-document boundaries use synthetic sources and stubbed inference only."""

import io
import json
import os
import time
import unittest
from dataclasses import replace
from unittest.mock import patch
from urllib.error import URLError

from claimlens.config import Settings
from claimlens.context import (TokenBudget, aggregate_metrics, consolidate,
                               segment_units, source_units, validate_extraction)
from claimlens.engine import check_claim
from claimlens.llm import completion_messages, quote_candidates
from claimlens.models import DEFAULT_MODEL, ProviderError, ValidationError


CLAIM = "All eligible workers receive CHF 200 from 2028."
SOURCES = [
    {"id": "original-page-4", "page": 4, "language": "fr", "text": "Les travailleurs de la catégorie A sont les travailleurs éligibles."},
    {"id": "original-page-5", "page": 5, "language": "fr", "text": "Cette autre proposition concerne une route cantonale.\n" * 500},
    {"id": "original-page-20", "page": 20, "language": "fr", "text": "Tous les travailleurs de la catégorie A reçoivent 200 CHF à partir de 2028."},
]
SETTINGS = Settings("https://evaluation.example/v1", context_tokens=8192)
USAGE = {"input_tokens": 100, "output_tokens": 10, "context_tokens": None}


def final_result(claim, passages, *_args, **_kwargs):
    return {"summary": "The definition and payment rule jointly support the claim.",
            "checks": [{"text": claim, "dimension": "general", "label": "entailment",
                        "explanation": "The two source pages jointly supply eligibility and payment details.",
                        "evidence": [{"passage_id": passage["id"], "quote": passage["text"]}
                                     for passage in passages]}]}, dict(USAGE)


class CoverageTests(unittest.TestCase):
    def test_quotations_keep_explanatory_context_instead_of_isolated_headings(self):
        heading = "Retraite à 67 ans"
        explanation = "Si la prévision se vérifie, l’âge de la retraite atteindra 67 ans en 2043."
        source = heading + "\n" + explanation
        candidates = quote_candidates([{"text": source}])
        self.assertNotIn(heading, candidates)
        self.assertIn(explanation, candidates)
        self.assertIn(source, candidates)
        self.assertTrue(all(quote in source for quote in candidates))
        self.assertEqual(quote_candidates([{"text": "Le montant est 200 CHF."}]), ["Le montant est 200 CHF."])

    def test_oversized_page_is_partitioned_without_losing_any_character(self):
        text = "  Französische Wörter!\n\n" + "LongWord" * 1000 + "\n শেষ multilingual text.  "
        passages = [{"id": "page-7", "page": 7, "language": "de", "text": text}]
        units = source_units(passages)
        self.assertGreater(len(units), 5)
        self.assertEqual("".join(unit["text"] for unit in units), text)
        self.assertTrue(all(unit["page"] == 7 and unit["passage_id"] == "page-7" for unit in units))
        self.assertEqual([(unit["start"], unit["end"]) for unit in units][0][0], 0)
        self.assertEqual(units[-1]["end"], len(text))
        for first, second in zip(units, units[1:]):
            self.assertEqual(first["end"], second["start"])
        segments = segment_units(units, lambda selected: len(selected) <= 3)
        self.assertEqual([unit for segment in segments for unit in segment], units)
        self.assertTrue(all(1 <= len(segment) <= 3 for segment in segments))

    def test_selected_units_preserve_original_ids_pages_and_exact_spans(self):
        units = source_units(SOURCES)
        selected = {units[0]["id"], units[2]["id"], units[4]["id"], units[-1]["id"]}
        evidence = consolidate(SOURCES, units, selected)
        self.assertEqual([passage["id"] for passage in evidence], [p["id"] for p in SOURCES])
        self.assertEqual([passage["page"] for passage in evidence], [4, 5, 20])
        for passage in evidence:
            original = next(p for p in SOURCES if p["id"] == passage["id"])
            for quote in passage["text"].split("\n[... omitted ...]\n"):
                self.assertIn(quote, original["text"])
            for quote in quote_candidates([passage]):
                self.assertIn(quote, original["text"])

    def test_unfit_unit_fails_without_silently_discarding_it(self):
        units = source_units(SOURCES)
        with self.assertRaisesRegex(ValidationError, "cannot fit"):
            segment_units(units, lambda _segment: False)


class HierarchicalTests(unittest.TestCase):
    def test_all_segments_examined_and_distributed_facts_reach_final_reasoning(self):
        seen = []
        def extraction(_claim, units, _model, _settings, language, vote):
            self.assertEqual((language, vote), ("de", "Workers benefit"))
            seen.extend(units)
            selected = [unit["id"] for unit in units if unit["passage_id"] != "original-page-5"]
            return {"evidence_ids": selected, "complete": True}, dict(USAGE)
        with patch("claimlens.context.request_extraction", side_effect=extraction) as extract, \
                patch("claimlens.engine.request_completion", side_effect=final_result) as final:
            result = check_claim({"passages": SOURCES, "vote": "Workers benefit"}, CLAIM,
                                 DEFAULT_MODEL, "live", SETTINGS, claim_language="de")
        self.assertGreater(extract.call_count, 1)
        self.assertEqual(seen, source_units(SOURCES))
        self.assertEqual(final.call_count, 1)
        final_sources = final.call_args.args[1]
        self.assertEqual([p["page"] for p in final_sources], [4, 20])
        self.assertTrue(final.call_args.kwargs["consolidated"])
        self.assertEqual(result["classification"], 0)
        self.assertFalse(result["validation_degraded"])
        self.assertEqual(result["passages"], SOURCES)
        calls = extract.call_count + 1
        self.assertEqual(result["metrics"]["input_tokens"], 100 * calls)
        self.assertEqual(result["metrics"]["output_tokens"], 10 * calls)
        self.assertEqual(result["processing"]["model_calls"], calls)
        self.assertEqual(result["processing"]["strategy"], "hierarchical")
        self.assertEqual(result["processing"]["source_pages"], 3)
        self.assertEqual(result["processing"]["segments"], extract.call_count)

    def test_invalid_or_unfinished_extraction_cannot_produce_a_verdict(self):
        for response in ({"complete": True, "evidence_ids": ["invented-unit"]},
                         {"complete": False, "evidence_ids": []}):
            with self.subTest(response=response), \
                    patch("claimlens.context.request_extraction", return_value=(response, USAGE)), \
                    patch("claimlens.engine.request_completion") as final:
                with self.assertRaisesRegex(ValidationError, "No partial verdict"):
                    check_claim({"passages": SOURCES}, CLAIM, DEFAULT_MODEL, "live", SETTINGS)
                final.assert_not_called()

    def test_consolidation_overflow_does_not_drop_evidence_or_vote_chunk_labels(self):
        def extraction(_claim, units, *_args):
            return {"complete": True, "evidence_ids": [unit["id"] for unit in units]}, USAGE
        with patch("claimlens.context.request_extraction", side_effect=extraction), \
                patch("claimlens.engine.request_completion") as final:
            with self.assertRaisesRegex(ValidationError, "selected evidence exceeds"):
                check_claim({"passages": SOURCES}, CLAIM, DEFAULT_MODEL, "live", SETTINGS)
            final.assert_not_called()

    def test_call_budget_failure_happens_before_model_inference(self):
        with patch("claimlens.context.request_extraction") as extract, \
                patch("claimlens.engine.request_completion") as final:
            with self.assertRaisesRegex(ValidationError, "MAX_DOCUMENT_MODEL_CALLS"):
                check_claim({"passages": SOURCES}, CLAIM, DEFAULT_MODEL, "live",
                            replace(SETTINGS, max_document_model_calls=2))
            extract.assert_not_called()
            final.assert_not_called()

    def test_no_evidence_is_explicit_neutral_after_all_segments(self):
        with patch("claimlens.context.request_extraction", return_value=({"complete": True, "evidence_ids": []}, USAGE)) as extract, \
                patch("claimlens.engine.request_completion") as final:
            result = check_claim({"passages": SOURCES}, CLAIM, DEFAULT_MODEL, "live", SETTINGS)
        final.assert_not_called()
        self.assertGreater(extract.call_count, 1)
        self.assertEqual(result["classification"], 1)
        self.assertEqual(result["processing"]["model_calls"], extract.call_count)
        self.assertIn("No relevant evidence", result["summary"])

    def test_document_deadline_includes_extraction_and_rejects_partial_result(self):
        now = [0.0]
        def extraction(*_args):
            now[0] = 11
            return {"complete": True, "evidence_ids": []}, USAGE
        with patch("claimlens.context.time.monotonic", side_effect=lambda: now[0]), \
                patch("claimlens.context.request_extraction", side_effect=extraction), \
                patch("claimlens.engine.request_completion") as final:
            with self.assertRaisesRegex(ProviderError, "DOCUMENT_TIMEOUT_SECONDS"):
                check_claim({"passages": SOURCES}, CLAIM, DEFAULT_MODEL, "live",
                            replace(SETTINGS, document_timeout=10))
            final.assert_not_called()

    def test_missing_usage_in_any_pass_remains_unknown_in_total(self):
        metrics = aggregate_metrics([USAGE, {"input_tokens": None, "output_tokens": 4}], SOURCES, time.monotonic())
        self.assertIsNone(metrics["input_tokens"])
        self.assertEqual(metrics["output_tokens"], 14)
        self.assertEqual(metrics["token_usage_source"], "incomplete_provider_usage")
        self.assertIsNone(metrics["context_tokens"])


class TokenPlanningTests(unittest.TestCase):
    def test_context_and_total_document_limits_are_configurable_and_bounded(self):
        with patch.dict(os.environ, {"CONTEXT_TOKENS": "16384", "DOCUMENT_TIMEOUT_SECONDS": "900",
                                     "MAX_DOCUMENT_MODEL_CALLS": "20"}, clear=True):
            settings = Settings.from_env()
        self.assertEqual((settings.context_tokens, settings.document_timeout,
                          settings.max_document_model_calls), (16384, 900, 20))
        for key, value in (("CONTEXT_TOKENS", "1000"), ("CONTEXT_TOKENS", "unknown"),
                           ("DOCUMENT_TIMEOUT_SECONDS", "nan"), ("DOCUMENT_TIMEOUT_SECONDS", "3601"),
                           ("MAX_DOCUMENT_MODEL_CALLS", "1"), ("MAX_DOCUMENT_MODEL_CALLS", "129")):
            with self.subTest(key=key, value=value), patch.dict(os.environ, {key: value}, clear=True):
                with self.assertRaises(ValidationError):
                    Settings.from_env()

    def test_remote_evaluator_never_receives_extra_tokenizer_requests(self):
        settings = replace(SETTINGS, local_model_id="ignored-local-alias")
        budget = TokenBudget(settings, time.monotonic() + 60)
        with patch("claimlens.context.build_opener") as opener:
            self.assertFalse(budget.fits(completion_messages(CLAIM, SOURCES), 3000))
            opener.assert_not_called()
        self.assertEqual(budget.method, "conservative_utf8_bytes")

    def test_local_count_renders_exact_chat_template_then_tokenizes_same_origin(self):
        settings = replace(SETTINGS, base_url="http://127.0.0.1:8081/v1", local_model_id="local-apertus")
        messages = completion_messages(CLAIM, SOURCES)
        budget = TokenBudget(settings, time.monotonic() + 60)
        with patch("claimlens.context.build_opener") as opener:
            opener.return_value.open.side_effect = [
                io.BytesIO(json.dumps({"prompt": "Rendered chat template"}).encode()),
                io.BytesIO(json.dumps({"tokens": [1, 2, 3]}).encode())]
            self.assertTrue(budget.fits(messages, 3000))
            calls = opener.return_value.open.call_args_list
        self.assertEqual([call.args[0].full_url for call in calls],
                         ["http://127.0.0.1:8081/apply-template", "http://127.0.0.1:8081/tokenize"])
        self.assertEqual(json.loads(calls[0].args[0].data)["messages"], messages)
        self.assertEqual(json.loads(calls[1].args[0].data)["content"], "Rendered chat template")
        self.assertEqual(budget.method, "local_tokenizer")

    def test_unavailable_local_tokenizer_uses_disclosed_conservative_estimate(self):
        settings = replace(SETTINGS, base_url="http://localhost:12434/engines/v1", local_model_id="local-apertus")
        budget = TokenBudget(settings, time.monotonic() + 60)
        with patch("claimlens.context.build_opener") as opener:
            opener.return_value.open.side_effect = URLError("Unavailable")
            self.assertFalse(budget.fits(completion_messages(CLAIM, SOURCES), 3000))
            self.assertFalse(budget.fits(completion_messages(CLAIM + " Again.", SOURCES), 3000))
            self.assertEqual(opener.return_value.open.call_count, 1)
        self.assertEqual(budget.method, "conservative_utf8_bytes")

    def test_invalid_extraction_types_are_rejected(self):
        units = source_units(SOURCES)
        for response in (None, {}, {"complete": 1, "evidence_ids": []},
                         {"complete": True, "evidence_ids": [None]},
                         {"complete": True, "evidence_ids": "u1"}):
            with self.subTest(response=response), self.assertRaises(ValidationError):
                validate_extraction(response, units)


if __name__ == "__main__":
    unittest.main()
