"""Generic JSON expansion uses an explicit shape and the same planned prompt."""

import json
import time
import unittest
from unittest.mock import Mock, patch

from claimlens.config import Settings
from claimlens.context import TokenBudget, source_units
from claimlens.fast import (GENERIC_QUERY_SHAPE, QUERY_OUTPUT_TOKENS, QUERY_PROMPT,
                            analyze_retrieval, query_messages, request_queries, validate_queries)
from claimlens.models import DEFAULT_MODEL, ValidationError


CLAIM = "La contribution annuelle est de 240 francs."
VOTE = "Nouvelle contribution annuelle"
REMOTE = Settings("https://evaluation.example/v1", context_tokens=16384)
LOCAL = Settings("http://127.0.0.1:8080/v1", local_model_id="local-apertus", context_tokens=16384)
QUERIES = {
    "claim_queries": {"de": "jährliche Gebühr 240 Franken", "fr": "contribution annuelle 240 francs",
                      "it": "contributo annuale 240 franchi"},
    "vote_queries": {"de": "Neue jährliche Gebühr", "fr": VOTE, "it": "Nuovo contributo annuale"},
}
USAGE = {"input_tokens": 100, "output_tokens": 30, "model_request_attempts": 1}


class GenericQueryTests(unittest.TestCase):
    def test_native_schema_query_messages_remain_identical(self):
        expected = [{"role": "system", "content": QUERY_PROMPT},
                    {"role": "user", "content": json.dumps({"claim": CLAIM, "claim_language": "fr", "vote": VOTE},
                                                             ensure_ascii=False, separators=(",", ":"))}]
        self.assertEqual(query_messages(CLAIM, "fr", VOTE), expected)
        with patch("claimlens.fast.request_json", return_value=(QUERIES, USAGE)) as request:
            request_queries(CLAIM, DEFAULT_MODEL, LOCAL, "fr", VOTE)
        payload = request.call_args.args[0]
        self.assertEqual(payload["messages"], expected)
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertNotIn(GENERIC_QUERY_SHAPE, payload["messages"][0]["content"])

    def test_generic_prompt_supplies_both_complete_language_objects(self):
        for vote in (VOTE, ""):
            with self.subTest(vote=vote), patch("claimlens.fast.request_json", return_value=(QUERIES, USAGE)) as request:
                request_queries(CLAIM, DEFAULT_MODEL, REMOTE, "fr", vote)
            payload = request.call_args.args[0]
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            self.assertEqual(payload["messages"], query_messages(CLAIM, "fr", vote, generic_json=True))
            prompt = payload["messages"][0]["content"]
            skeleton = json.loads(prompt.split("Required JSON structure:\n", 1)[1])
            self.assertEqual(set(skeleton), {"claim_queries", "vote_queries"})
            self.assertTrue(all(set(group) == {"de", "fr", "it"} for group in skeleton.values()))
            self.assertIn("all three vote phrase", prompt)

    def test_budget_checks_exact_generic_prompt_before_request(self):
        sources = [{"id": "page-1", "page": 1, "language": "de", "text": "Die jährliche Gebühr beträgt 240 Franken. " * 1000}]
        units = source_units(sources)
        indexed = {"units": units, "ranked_ids": [units[0]["id"]], "cache_hit": True,
                   "candidate_count": 1, "index_key": "synthetic"}
        planned = []
        original_fits = TokenBudget.fits

        def record(budget, messages, output_tokens, **kwargs):
            if output_tokens == QUERY_OUTPUT_TOKENS:
                planned.append(messages)
            return original_fits(budget, messages, output_tokens, **kwargs)

        completion = Mock(return_value=({"summary": "Synthetic result."}, USAGE))
        with patch.object(TokenBudget, "fits", autospec=True, side_effect=record), \
                patch("claimlens.fast.request_json", return_value=(QUERIES, USAGE)) as request, \
                patch("claimlens.fast.search", return_value=indexed):
            analyze_retrieval(CLAIM, sources, DEFAULT_MODEL, REMOTE, "fr", VOTE,
                              completion, [], time.monotonic())
        self.assertEqual(request.call_count, 1)
        self.assertEqual(planned, [request.call_args.args[0]["messages"]])
        self.assertIn(GENERIC_QUERY_SHAPE, planned[0][0]["content"])
        completion.assert_called_once()

    def test_missing_vote_translations_still_fail_validation(self):
        incomplete = {"claim_queries": QUERIES["claim_queries"], "vote_queries": {"fr": VOTE}}
        with self.assertRaisesRegex(ValidationError, "German, French and Italian") as raised:
            validate_queries(incomplete, CLAIM, VOTE)
        self.assertFalse(raised.exception.retryable)


if __name__ == "__main__":
    unittest.main()
