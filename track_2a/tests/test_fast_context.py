"""Fast document selection keeps exact provenance and bounded live-call usage."""

import copy
from dataclasses import replace
import time
import unittest
from unittest.mock import patch

from claimlens.config import Settings
from claimlens.context import FINAL_OUTPUT_TOKENS, TokenBudget, source_units
from claimlens.engine import check_claim
from claimlens.fast import request_queries, validate_queries
from claimlens.llm import completion_messages
from claimlens.models import DEFAULT_MODEL, ProviderError, ValidationError


SETTINGS = Settings("https://proxy.example/v1", context_tokens=16384,
                    document_strategy="retrieval", retrieval_prompt_tokens=5000,
                    retrieval_timeout=120)
CLAIM = "Die jährliche Gebühr beträgt 200 Franken."
VOTE = "Gebührenvorlage"
SOURCES = [{"id": "original-{}".format(page), "page": page, "language": "fr",
            "text": ("Page {} : La redevance annuelle est de 200 francs pour les personnes concernées. ".format(page)) * 70}
           for page in (3, 7, 9, 12)]
QUERIES = {
    "claim_queries": {"de": "jährliche Gebühr 200 Franken", "fr": "redevance annuelle 200 francs", "it": "tassa annuale 200 franchi"},
    "vote_queries": {"de": "Gebührenvorlage", "fr": "projet de redevance", "it": "proposta tassa"},
}
QUERY_USAGE = {"input_tokens": 50, "output_tokens": 12, "model_request_attempts": 1}
FINAL_USAGE = {"input_tokens": 100, "output_tokens": 25, "model_request_attempts": 1}


def index_result(passages=SOURCES):
    units = source_units(passages)
    # Put one unit from each page first, then adjacent context.
    first = [next(unit["id"] for unit in units if unit["passage_id"] == source["id"])
             for source in passages]
    ranked = (first + [unit["id"] for unit in units if unit["id"] not in first])[:12]
    return {"units": units, "ranked_ids": ranked, "cache_hit": True,
            "index_key": "synthetic-index-hash", "candidate_count": len(units)}


def completion(claim, passages, *_args, **_kwargs):
    return ({"summary": "Synthetic format/provenance check.", "checks": [{
        "text": claim, "dimension": "general", "label": "neutral",
        "explanation": "Synthetic response, not a quality measurement.", "evidence": [],
    }]}, dict(FINAL_USAGE))


def check(passages=SOURCES, settings=SETTINGS, source_kind="booklet"):
    return check_claim({"passages": passages, "vote": VOTE, "source_kind": source_kind},
                       CLAIM, DEFAULT_MODEL, "live", settings, claim_language="auto")


class FastContextTests(unittest.TestCase):
    def test_small_booklet_uses_complete_source_and_one_call(self):
        source = [{**SOURCES[0], "text": "La redevance annuelle est de 200 francs."}]
        with patch("claimlens.fast.request_queries") as expand, \
                patch("claimlens.fast.search") as search, \
                patch("claimlens.engine.request_completion", side_effect=completion) as final:
            result = check(source)
        expand.assert_not_called()
        search.assert_not_called()
        self.assertEqual(final.call_args.args[1], source)
        self.assertEqual(result["processing"]["strategy"], "full")
        self.assertFalse(result["processing"]["query_expansion"])
        self.assertEqual(result["processing"]["model_calls"], 1)
        self.assertEqual(result["metrics"]["input_tokens"], 100)

    def test_long_booklet_has_two_calls_with_bounded_exact_source_excerpts(self):
        with patch("claimlens.fast.request_queries", return_value=(QUERIES, QUERY_USAGE)) as expand, \
                patch("claimlens.fast.search", return_value=index_result()) as search, \
                patch("claimlens.engine.request_completion", side_effect=completion) as final, \
                patch("claimlens.context.request_extraction") as exhaustive:
            result = check()
        exhaustive.assert_not_called()
        self.assertEqual(expand.call_count, 1)
        self.assertEqual(final.call_count, 1)
        self.assertEqual(expand.call_args.args[3], "auto")
        self.assertEqual(search.call_args.args[1], [CLAIM] + list(QUERIES["claim_queries"].values()))
        self.assertEqual(search.call_args.args[2], [VOTE, "projet de redevance", "proposta tassa"])
        evidence = final.call_args.args[1]
        self.assertTrue(final.call_args.kwargs["retrieved"])
        self.assertEqual(final.call_args.args[0], CLAIM)
        budget = TokenBudget(SETTINGS, time.monotonic() + 30)
        self.assertTrue(budget.fits(completion_messages(CLAIM, evidence, "auto", vote=VOTE, retrieved=True),
                                   FINAL_OUTPUT_TOKENS, prompt_tokens=5000))
        for passage in evidence:
            source = next(item for item in SOURCES if item["id"] == passage["id"])
            self.assertEqual(source["page"], passage["page"])
            for excerpt in passage["text"].split("\n[... omitted ...]\n"):
                self.assertIn(excerpt, source["text"])
        self.assertLess(sum(len(p["text"]) for p in evidence), sum(len(p["text"]) for p in SOURCES))
        self.assertEqual(result["metrics"]["input_tokens"], 150)
        self.assertEqual(result["metrics"]["output_tokens"], 37)
        self.assertEqual(result["processing"]["model_calls"], 2)
        self.assertEqual(result["processing"]["strategy"], "retrieval")
        self.assertTrue(result["processing"]["index_cache_hit"])
        self.assertEqual(result["processing"]["selected_source_pages"], sorted(p["page"] for p in evidence))
        self.assertIn("Other pages were not examined", result["processing"]["coverage"])

    def test_reference_task_keeps_complete_supplied_source_above_fast_budget(self):
        reference = [{"id": "reference-1", "page": None, "language": "fr", "text": "Source française. " * 400}]
        with patch("claimlens.fast.request_queries") as expand, \
                patch("claimlens.fast.search") as search, \
                patch("claimlens.engine.request_completion", side_effect=completion) as final:
            result = check(reference, source_kind="reference")
        expand.assert_not_called()
        search.assert_not_called()
        self.assertEqual(final.call_args.args[1], reference)
        self.assertEqual(result["processing"]["strategy"], "full")

    def test_empty_retrieval_is_failure_with_query_usage_and_no_fallback(self):
        empty = index_result()
        empty["ranked_ids"] = []
        with patch("claimlens.fast.request_queries", return_value=(QUERIES, QUERY_USAGE)), \
                patch("claimlens.fast.search", return_value=empty), \
                patch("claimlens.engine.request_completion") as final, \
                patch("claimlens.context.request_extraction") as exhaustive, \
                self.assertRaisesRegex(ValidationError, "No source passages matched") as raised:
            check()
        final.assert_not_called()
        exhaustive.assert_not_called()
        self.assertFalse(raised.exception.retryable)
        self.assertEqual(raised.exception.metrics["input_tokens"], 50)
        self.assertEqual(raised.exception.metrics["model_request_attempts"], 1)

    def test_retrieval_cannot_supply_invented_text_or_wrong_pages(self):
        for field, value in (("text", "Query translation invented as evidence"), ("page", 999)):
            invalid = copy.deepcopy(index_result())
            invalid["units"][0][field] = value
            with self.subTest(field=field), \
                    patch("claimlens.fast.request_queries", return_value=(QUERIES, QUERY_USAGE)), \
                    patch("claimlens.fast.search", return_value=invalid), \
                    patch("claimlens.engine.request_completion") as final, \
                    self.assertRaisesRegex(ValidationError, "exact source text"):
                check()
            final.assert_not_called()

    def test_invalid_expansion_stops_before_search_and_retains_usage(self):
        with patch("claimlens.fast.request_queries", return_value=({"claim_queries": "not an object"}, QUERY_USAGE)), \
                patch("claimlens.fast.search") as search, \
                patch("claimlens.engine.request_completion") as final, \
                self.assertRaises(ValidationError) as raised:
            check()
        search.assert_not_called()
        final.assert_not_called()
        self.assertFalse(raised.exception.retryable)
        self.assertEqual(raised.exception.metrics["output_tokens"], 12)

    def test_unknown_expansion_usage_prevents_spending_on_final_call(self):
        usage = {**QUERY_USAGE, "input_tokens": None}
        with patch("claimlens.fast.request_queries", return_value=(QUERIES, usage)), \
                patch("claimlens.fast.search") as search, \
                patch("claimlens.engine.request_completion") as final, \
                self.assertRaisesRegex(ValidationError, "complete token usage") as raised:
            check()
        search.assert_not_called()
        final.assert_not_called()
        self.assertIsNone(raised.exception.metrics["input_tokens"])
        self.assertEqual(raised.exception.metrics["output_tokens"], 12)

    def test_expansion_and_final_share_deadline_and_four_attempt_budget(self):
        now = [0.0]
        def expansion(*args):
            self.assertLessEqual(args[2].timeout, 120)
            self.assertEqual(args[2].max_document_model_calls, 3)
            now[0] = 25.0
            return QUERIES, {**QUERY_USAGE, "model_request_attempts": 3}
        def final_call(claim, passages, model, settings, *args, **kwargs):
            self.assertLessEqual(settings.timeout, 95)
            self.assertEqual(settings.max_document_model_calls, 1)
            return completion(claim, passages)
        with patch("claimlens.fast.request_queries", side_effect=expansion), \
                patch("claimlens.fast.search", return_value=index_result()), \
                patch("claimlens.engine.request_completion", side_effect=final_call), \
                patch("time.monotonic", side_effect=lambda: now[0]):
            result = check()
        self.assertEqual(result["processing"]["model_calls"], 4)
        self.assertEqual(result["metrics"]["inference_time_ms"], 25000)

    def test_expired_fast_deadline_rejects_completed_query_before_final(self):
        now = [0.0]
        def expansion(*_args):
            now[0] = 121.0
            return QUERIES, QUERY_USAGE
        with patch("claimlens.fast.request_queries", side_effect=expansion), \
                patch("claimlens.fast.search") as search, \
                patch("claimlens.engine.request_completion") as final, \
                patch("time.monotonic", side_effect=lambda: now[0]), \
                self.assertRaises(ProviderError) as raised:
            check()
        search.assert_not_called()
        final.assert_not_called()
        self.assertEqual(raised.exception.metrics["input_tokens"], 50)
        self.assertEqual(raised.exception.metrics["model_request_attempts"], 1)
        self.assertFalse(raised.exception.retryable)

    def test_claim_that_cannot_fit_fails_before_any_inference(self):
        with patch("claimlens.fast.request_queries") as expand, \
                patch("claimlens.engine.request_completion") as final, \
                self.assertRaisesRegex(ValidationError, "cannot fit the fast prompt budget"):
            check(settings=replace(SETTINGS, retrieval_prompt_tokens=100))
        expand.assert_not_called()
        final.assert_not_called()

    def test_local_count_rechecks_a_cached_estimate_for_tighter_prompt_budget(self):
        settings = replace(SETTINGS, base_url="http://localhost:8081/v1", local_model_id="local-apertus")
        budget = TokenBudget(settings, time.monotonic() + 20)
        messages = [{"role": "user", "content": "x" * 1100}]
        with patch.object(budget, "_local_count", return_value=100) as tokenize:
            self.assertTrue(budget.fits(messages, 3000))
            tokenize.assert_not_called()
            self.assertTrue(budget.fits(messages, 3000, prompt_tokens=1000))
        tokenize.assert_called_once_with(messages)


class QueryFormatTests(unittest.TestCase):
    def test_expansion_uses_bounded_same_endpoint_model_and_strict_local_schema(self):
        for local in (False, True):
            settings = replace(SETTINGS, base_url="http://localhost:8081/v1", local_model_id="local-apertus") if local else SETTINGS
            with self.subTest(local=local), patch("claimlens.fast.request_json", return_value=(QUERIES, QUERY_USAGE)) as request:
                request_queries(CLAIM, DEFAULT_MODEL, settings, "auto", VOTE)
            data, used_settings, source = request.call_args.args
            self.assertIs(used_settings, settings)
            self.assertEqual(source, [])
            self.assertEqual(data["max_tokens"], 384)
            self.assertEqual(data["model"], "local-apertus" if local else DEFAULT_MODEL)
            self.assertEqual(data["response_format"]["type"], "json_schema" if local else "json_object")

    def test_queries_require_all_languages_and_reject_oversized_or_hallucinated_vote(self):
        malformed = []
        for value in (None, "", "x" * 241):
            invalid = copy.deepcopy(QUERIES)
            invalid["claim_queries"]["fr"] = value
            malformed.append(invalid)
        invalid = copy.deepcopy(QUERIES)
        del invalid["claim_queries"]["it"]
        malformed.append(invalid)
        for invalid in malformed:
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                validate_queries(invalid, CLAIM, VOTE)
        with self.assertRaises(ValidationError):
            validate_queries(QUERIES, CLAIM, "")
        valid = copy.deepcopy(QUERIES)
        valid["vote_queries"] = {language: "" for language in ("de", "fr", "it")}
        claims, votes = validate_queries(valid, CLAIM, "")
        self.assertEqual(claims[0], CLAIM)
        self.assertEqual(votes, [])


if __name__ == "__main__":
    unittest.main()
