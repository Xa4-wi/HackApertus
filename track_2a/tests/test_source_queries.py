"""Source-language queries save calls without changing evidence or accounting."""

from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from claimlens.config import Settings
from claimlens.context import TokenBudget, source_units
from claimlens.engine import check_claim
from claimlens.fast import (known_source_language, request_source_queries,
                            source_query_messages, validate_source_queries)
from claimlens.models import DEFAULT_MODEL, ProviderError, ValidationError


CLAIM = "Die jährliche Gebühr beträgt nicht mehr als 200 Franken."
VOTE = "Gebührenvorlage"
SETTINGS = Settings("https://proxy.example/v1", context_tokens=16384,
                    document_strategy="retrieval", retrieval_prompt_tokens=5000)
QUERY = {"claim_query": "redevance annuelle ne dépasse pas 200 francs", "vote_query": "projet de redevance"}
MULTILINGUAL = {
    "claim_queries": {"de": "Gebühr nicht mehr als 200 Franken", "fr": QUERY["claim_query"], "it": "tassa non oltre 200 franchi"},
    "vote_queries": {"de": VOTE, "fr": QUERY["vote_query"], "it": "proposta tassa"},
}
QUERY_USAGE = {"input_tokens": 50, "output_tokens": 12, "model_request_attempts": 1}
FINAL_USAGE = {"input_tokens": 100, "output_tokens": 25, "model_request_attempts": 1}


def sources(language="fr"):
    return [{"id": "page-{}".format(page), "page": page, "language": language,
             "text": "La redevance annuelle ne dépasse pas 200 francs pour les personnes concernées. " * 70}
            for page in (3, 7, 9)]


def retrieved(passages):
    units = source_units(passages)
    return {"units": units, "ranked_ids": [units[0]["id"]], "cache_hit": False,
            "candidate_count": len(units)}


def completion(claim, passages, *_args, **_kwargs):
    return ({"summary": "Synthetic routing test.", "checks": [{
        "text": claim, "dimension": "general", "label": "neutral",
        "explanation": "Synthetic routing test, not measured quality.", "evidence": [],
    }]}, dict(FINAL_USAGE))


def check(passages, claim_language="de", settings=None):
    settings = settings or replace(SETTINGS, retrieval_query_mode="source")
    return check_claim({"passages": passages, "vote": VOTE, "source_kind": "booklet"},
                       CLAIM, DEFAULT_MODEL, "live", settings, claim_language=claim_language)


class SourceQueryRoutingTests(unittest.TestCase):
    def test_same_known_language_skips_query_model_for_each_supported_language(self):
        for language in ("de", "fr", "it"):
            passages = sources(language)
            with self.subTest(language=language), \
                    patch("claimlens.fast.request_source_queries") as targeted, \
                    patch("claimlens.fast.request_queries") as multilingual, \
                    patch("claimlens.fast.search", return_value=retrieved(passages)) as search, \
                    patch("claimlens.engine.request_completion", side_effect=completion) as final:
                result = check(passages, language)
            targeted.assert_not_called()
            multilingual.assert_not_called()
            self.assertEqual(search.call_args.args[1:3], ([CLAIM], [VOTE]))
            self.assertEqual(final.call_count, 1)
            self.assertEqual(final.call_args.args[0], CLAIM)
            self.assertTrue(final.call_args.kwargs["retrieved"])
            self.assertEqual(result["metrics"]["input_tokens"], 100)
            self.assertEqual(result["metrics"]["output_tokens"], 25)
            self.assertEqual(result["processing"]["model_calls"], 1)
            self.assertEqual(result["processing"]["query_strategy"], "original_source")
            self.assertEqual(result["processing"]["source_language"], language)
            self.assertFalse(result["processing"]["query_expansion"])
            self.assertEqual(result["processing"]["query_expansion_output_limit"], 0)
            self.assertNotIn("multilingual retrieval", result["processing"]["coverage"])

    def test_all_cross_language_and_auto_claims_translate_only_to_source_language(self):
        for source_language in ("de", "fr", "it"):
            for claim_language in ("de", "fr", "it", "auto"):
                if source_language == claim_language:
                    continue
                passages = sources(source_language)
                with self.subTest(source=source_language, claim=claim_language), \
                        patch("claimlens.fast.request_source_queries", return_value=(QUERY, QUERY_USAGE)) as targeted, \
                        patch("claimlens.fast.request_queries") as multilingual, \
                        patch("claimlens.fast.search", return_value=retrieved(passages)) as search, \
                        patch("claimlens.engine.request_completion", side_effect=completion):
                    result = check(passages, claim_language)
                multilingual.assert_not_called()
                self.assertEqual(targeted.call_count, 1)
                self.assertEqual(targeted.call_args.args[3:], (claim_language, VOTE, source_language))
                self.assertEqual(search.call_args.args[1:3], ([CLAIM, QUERY["claim_query"]], [VOTE, QUERY["vote_query"]]))
                self.assertEqual(result["metrics"]["input_tokens"], 150)
                self.assertEqual(result["metrics"]["output_tokens"], 37)
                self.assertEqual(result["processing"]["model_calls"], 2)
                self.assertEqual(result["processing"]["query_strategy"], "source_language")
                self.assertEqual(result["processing"]["query_expansion_output_limit"], 128)

    def test_mixed_unknown_or_missing_source_metadata_preserves_multilingual_path(self):
        alternatives = [sources("auto"), sources(None), sources("en"),
                        sources([]), sources({}), sources(42), sources(True), sources()]
        alternatives[-1][1]["language"] = "de"
        missing = sources()
        del missing[1]["language"]
        alternatives.append(missing)
        for passages in alternatives:
            with self.subTest(languages=[p.get("language") for p in passages]), \
                    patch("claimlens.fast.request_source_queries") as targeted, \
                    patch("claimlens.fast.request_queries", return_value=(MULTILINGUAL, QUERY_USAGE)) as multilingual, \
                    patch("claimlens.fast.search", return_value=retrieved(passages)), \
                    patch("claimlens.engine.request_completion", side_effect=completion):
                result = check(passages)
            targeted.assert_not_called()
            self.assertEqual(multilingual.call_count, 1)
            self.assertEqual(result["processing"]["query_strategy"], "multilingual")
            self.assertIsNone(result["processing"]["source_language"])
            self.assertEqual(result["processing"]["query_expansion_output_limit"], 384)

    def test_multilingual_setting_keeps_expansion_even_when_languages_match(self):
        passages = sources("de")
        with patch("claimlens.fast.request_source_queries") as targeted, \
                patch("claimlens.fast.request_queries", return_value=(MULTILINGUAL, QUERY_USAGE)) as multilingual, \
                patch("claimlens.fast.search", return_value=retrieved(passages)), \
                patch("claimlens.engine.request_completion", side_effect=completion):
            result = check(passages, "de", replace(SETTINGS, retrieval_query_mode="multilingual"))
        targeted.assert_not_called()
        self.assertEqual(multilingual.call_count, 1)
        self.assertEqual(result["processing"]["model_calls"], 2)

    def test_short_full_source_still_needs_no_queries(self):
        passages = [{**sources()[0], "text": "La redevance annuelle est de 200 francs."}]
        with patch("claimlens.fast.request_source_queries") as targeted, \
                patch("claimlens.fast.request_queries") as multilingual, \
                patch("claimlens.fast.search") as search, \
                patch("claimlens.engine.request_completion", side_effect=completion) as final:
            result = check(passages)
        targeted.assert_not_called()
        multilingual.assert_not_called()
        search.assert_not_called()
        self.assertEqual(final.call_args.args[1], passages)
        self.assertEqual(result["processing"]["query_strategy"], "none_full_source")
        self.assertEqual(result["processing"]["query_expansion_output_limit"], 0)
        self.assertEqual(result["processing"]["citation_mode"], "full")

    def test_query_planning_uses_actual_generic_messages_and_128_output_tokens(self):
        passages = sources()
        planned = []
        original = TokenBudget.fits
        def fits(budget, messages, output_tokens, **kwargs):
            planned.append((messages, output_tokens))
            return original(budget, messages, output_tokens, **kwargs)
        with patch.object(TokenBudget, "fits", fits), \
                patch("claimlens.fast.request_source_queries", return_value=(QUERY, QUERY_USAGE)), \
                patch("claimlens.fast.search", return_value=retrieved(passages)), \
                patch("claimlens.engine.request_completion", side_effect=completion):
            check(passages)
        self.assertIn((source_query_messages(CLAIM, "de", VOTE, "fr", generic_json=True), 128), planned)

    def test_source_query_and_final_share_deadline_and_four_attempt_budget(self):
        now = [0.0]
        passages = sources()
        def expansion(claim, model, settings, *args):
            self.assertEqual(settings.max_document_model_calls, 3)
            self.assertLessEqual(settings.timeout, 120)
            now[0] = 25.0
            return QUERY, {**QUERY_USAGE, "model_request_attempts": 3}
        def final(claim, evidence, model, settings, *args, **kwargs):
            self.assertEqual(settings.max_document_model_calls, 1)
            self.assertLessEqual(settings.timeout, 95)
            return completion(claim, evidence)
        with patch("claimlens.fast.request_source_queries", side_effect=expansion), \
                patch("claimlens.fast.search", return_value=retrieved(passages)), \
                patch("claimlens.engine.request_completion", side_effect=final), \
                patch("time.monotonic", side_effect=lambda: now[0]):
            result = check(passages)
        self.assertEqual(result["processing"]["model_calls"], 4)
        self.assertEqual(result["metrics"]["inference_time_ms"], 25000)

    def test_unknown_query_usage_stops_before_search_and_final_inference(self):
        for key in ("input_tokens", "output_tokens"):
            with self.subTest(key=key), \
                    patch("claimlens.fast.request_source_queries", return_value=(QUERY, {**QUERY_USAGE, key: None})), \
                    patch("claimlens.fast.search") as search, \
                    patch("claimlens.engine.request_completion") as final, \
                    self.assertRaisesRegex(ValidationError, "complete token usage") as raised:
                check(sources())
            search.assert_not_called()
            final.assert_not_called()
            self.assertIsNone(raised.exception.metrics[key])

    def test_expired_source_query_retains_usage_and_never_starts_final(self):
        now = [0.0]
        def expansion(*_args):
            now[0] = 121.0
            return QUERY, QUERY_USAGE
        with patch("claimlens.fast.request_source_queries", side_effect=expansion), \
                patch("claimlens.fast.search") as search, \
                patch("claimlens.engine.request_completion") as final, \
                patch("time.monotonic", side_effect=lambda: now[0]), \
                self.assertRaises(ProviderError) as raised:
            check(sources())
        search.assert_not_called()
        final.assert_not_called()
        self.assertFalse(raised.exception.retryable)
        self.assertEqual(raised.exception.metrics["input_tokens"], 50)

    def test_malformed_source_queries_do_not_start_retrieval_or_final(self):
        for invalid in ({"claim_query": ""}, {**QUERY, "claim_query": []}, {**QUERY, "extra": "fact"}):
            with self.subTest(query=invalid), \
                    patch("claimlens.fast.request_source_queries", return_value=(invalid, QUERY_USAGE)), \
                    patch("claimlens.fast.search") as search, \
                    patch("claimlens.engine.request_completion") as final, \
                    self.assertRaises(ValidationError) as raised:
                check(sources())
            search.assert_not_called()
            final.assert_not_called()
            self.assertEqual(raised.exception.metrics["output_tokens"], 12)


class SourceQueryFormatTests(unittest.TestCase):
    def test_request_stays_on_selected_endpoint_with_strict_local_schema(self):
        for local in (False, True):
            settings = (replace(SETTINGS, base_url="http://localhost:8081/v1", local_model_id="local-apertus")
                        if local else SETTINGS)
            with self.subTest(local=local), patch("claimlens.fast.request_json", return_value=(QUERY, QUERY_USAGE)) as request:
                actual, usage = request_source_queries(CLAIM, DEFAULT_MODEL, settings, "de", VOTE, "fr")
            data, passed_settings, evidence = request.call_args.args
            self.assertIs(passed_settings, settings)
            self.assertEqual(evidence, [])
            self.assertEqual(actual, QUERY)
            self.assertEqual(usage, QUERY_USAGE)
            self.assertEqual(data["max_tokens"], 128)
            self.assertEqual(data["model"], "local-apertus" if local else DEFAULT_MODEL)
            self.assertEqual(data["messages"], source_query_messages(CLAIM, "de", VOTE, "fr", generic_json=not local))
            self.assertEqual(json.loads(data["messages"][1]["content"])["source_language"], "fr")
            self.assertIn("numbers, negations, conditions and qualifications", data["messages"][0]["content"])
            if local:
                schema = data["response_format"]["json_schema"]["schema"]
                self.assertEqual(set(schema["properties"]), {"claim_query", "vote_query"})
                self.assertFalse(schema["additionalProperties"])
                self.assertEqual(schema["properties"]["claim_query"]["maxLength"], 240)
            else:
                self.assertEqual(data["response_format"], {"type": "json_object"})

    def test_generic_missing_title_hint_uses_original_without_retry(self):
        for vote in (VOTE, "", "x" * 241):
            with self.subTest(vote=vote), \
                    patch("claimlens.fast.request_json", return_value=({"claim_query": QUERY["claim_query"]}, QUERY_USAGE)) as request:
                result, _ = request_source_queries(CLAIM, DEFAULT_MODEL, SETTINGS, "de", vote, "fr")
            claims, votes = validate_source_queries(result, CLAIM, vote)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(claims, [CLAIM, QUERY["claim_query"]])
            self.assertEqual(votes, [vote] if vote else [])

    def test_optional_empty_title_does_not_discard_original_vote(self):
        queries, votes = validate_source_queries({**QUERY, "vote_query": ""}, CLAIM, VOTE)
        self.assertEqual(queries[0], CLAIM)
        self.assertEqual(votes, [VOTE])
        self.assertEqual(validate_source_queries({**QUERY, "vote_query": ""}, CLAIM, "")[1], [])

    def test_bad_claims_titles_structure_and_hallucinated_title_are_rejected(self):
        malformed = [None, [], {"claim_query": "phrase"}, {**QUERY, "extra": "fact"}]
        malformed += [{**QUERY, "claim_query": value} for value in (None, "", " ", "x" * 241, [])]
        malformed += [{**QUERY, "vote_query": value} for value in (None, [], "x" * 241)]
        for invalid in malformed:
            with self.subTest(query=invalid), self.assertRaises(ValidationError):
                validate_source_queries(invalid, CLAIM, VOTE)
        with self.assertRaises(ValidationError):
            validate_source_queries(QUERY, CLAIM, "")

    def test_language_detection_requires_every_passage_to_agree(self):
        self.assertIsNone(known_source_language([]))
        self.assertIsNone(known_source_language([{"language": "fr"}, {}]))
        self.assertIsNone(known_source_language([{"language": "fr"}, {"language": "auto"}]))
        self.assertEqual(known_source_language([{"language": "fr"}] * 3), "fr")

    def test_nonstring_language_metadata_is_unknown_without_hashing_it(self):
        for value in ([], {}, ["fr"], {"code": "fr"}, True, 42):
            with self.subTest(value=value):
                self.assertIsNone(known_source_language([{"language": value}]))
                self.assertIsNone(known_source_language([{"language": "fr"}, {"language": value}]))


if __name__ == "__main__":
    unittest.main()
