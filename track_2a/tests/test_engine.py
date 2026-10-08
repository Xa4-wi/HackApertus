"""Core boundary tests: no external endpoint or model inference is used."""

import copy
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from claimlens.config import Settings
from claimlens.corpus import load_corpus
from claimlens.engine import check_claim, validate_model_result
from claimlens.llm import _RejectRedirects, completion_url, request_completion
from claimlens.models import DEFAULT_MODEL, ProviderError, ValidationError


CLAIM = "The annual fee is CHF 200 from 2027."
PASSAGE = {
    "id": "p1", "text": "The annual fee is CHF 200 from 2028.", "page": 2,
    "title": "Fictional fee", "language": "de", "url": "",
    "attribution": "Fictional legal text",
}
MODEL_RESULT = {
    "summary": "The date differs from the source.",
    "checks": [{"text": CLAIM, "dimension": "general", "label": "contradiction",
                "explanation": "The source gives 2028, not 2027.",
                "evidence": [{"passage_id": "p1", "quote": PASSAGE["text"]}]}],
}
PROPOSAL = {
    "id": "fee", "title": "Fictional fee", "language": "de", "is_fixture": True,
    "passages": [PASSAGE], "examples": [{"claim": CLAIM, "result": MODEL_RESULT}],
}
SETTINGS = Settings("http://localhost:9000/v1", "test-secret-only", DEFAULT_MODEL, 30)


def provider_response(result=MODEL_RESULT, usage=None, finish_reason="stop"):
    response = {"choices": [{"message": {"content": json.dumps(result)},
                              "finish_reason": finish_reason}]}
    if usage is not None:
        response["usage"] = usage
    return io.BytesIO(json.dumps(response).encode("utf-8"))


class EngineTests(unittest.TestCase):
    def test_bundled_walkthrough_labels_and_quotes_pass_validation_offline(self):
        proposals = load_corpus()
        self.assertTrue(proposals)
        with patch("claimlens.engine.request_completion") as completion:
            for proposal in proposals:
                for example in proposal["examples"]:
                    with self.subTest(example=example["id"]):
                        result = check_claim(proposal, example["claim"], DEFAULT_MODEL, "demo", None)
                        self.assertEqual(result["overall"], example["result"]["overall"])
                        self.assertFalse(result["validation_degraded"])
                        self.assertEqual(result["metrics"]["inference_time_ms"], 0)
            completion.assert_not_called()

    def test_demo_is_exact_offline_and_does_not_mutate_corpus(self):
        with patch("claimlens.engine.request_completion") as completion:
            result = check_claim(PROPOSAL, CLAIM, DEFAULT_MODEL, "demo", None)
            completion.assert_not_called()
        self.assertEqual(result["classification"], 2)
        self.assertFalse(result["validation_degraded"])
        self.assertEqual(result["metrics"]["token_usage_source"], "not_called")
        self.assertEqual(result["metrics"]["input_tokens"], 0)
        result["checks"][0]["label"] = "neutral"
        result["passages"][0]["text"] = "Changed by caller"
        self.assertEqual(MODEL_RESULT["checks"][0]["label"], "contradiction")
        self.assertEqual(PASSAGE["text"], "The annual fee is CHF 200 from 2028.")

    def test_demo_rejects_custom_or_modified_claim_before_provider(self):
        with patch("claimlens.engine.request_completion") as completion:
            for claim in ("A custom claim.", CLAIM + " "):
                with self.subTest(claim=claim), self.assertRaises(ValidationError):
                    check_claim(PROPOSAL, claim, DEFAULT_MODEL, "demo", None)
            completion.assert_not_called()

    def test_invalid_claims_modes_models_and_languages_do_not_call_provider(self):
        with patch("claimlens.engine.request_completion") as completion:
            cases = [(None, DEFAULT_MODEL, "live", "de"),
                     (" " * 20, DEFAULT_MODEL, "live", "de"),
                     ("x" * 2001, DEFAULT_MODEL, "live", "de"),
                     (CLAIM, "other/model", "live", "de"),
                     (CLAIM, DEFAULT_MODEL, "automatic", "de"),
                     (CLAIM, DEFAULT_MODEL, "live", "en")]
            for claim, model, mode, language in cases:
                with self.subTest(case=(claim, model, mode, language)), self.assertRaises(ValidationError):
                    check_claim(PROPOSAL, claim, model, mode, SETTINGS, claim_language=language)
            completion.assert_not_called()

    def test_quote_and_passage_fabrications_are_visible_degradations(self):
        bad_citations = [[], [{"passage_id": "invented", "quote": PASSAGE["text"]}],
                         [{"passage_id": "p1", "quote": "The source says 2027."}],
                         [{"passage_id": "p1", "quote": " "}], [None]]
        for citations in bad_citations:
            result = copy.deepcopy(MODEL_RESULT)
            result["checks"][0]["evidence"] = citations
            with self.subTest(citations=citations):
                validated = validate_model_result(CLAIM, result, [PASSAGE])
                self.assertEqual(validated["overall"], "neutral")
                self.assertTrue(validated["validation_degraded"])
                self.assertTrue(validated["warnings"])

    def test_bad_span_or_unknown_label_is_rejected(self):
        for key, value in (("text", "not part of the claim"), ("label", "true"),
                           ("label", []), ("dimension", "confidence")):
            result = copy.deepcopy(MODEL_RESULT)
            result["checks"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValidationError):
                validate_model_result(CLAIM, result, [PASSAGE])

    def test_offsets_are_derived_from_claim(self):
        result = copy.deepcopy(MODEL_RESULT)
        result["checks"][0].update(start=900, end=901)
        validated = validate_model_result(CLAIM, result, [PASSAGE])
        self.assertEqual((validated["checks"][0]["start"], validated["checks"][0]["end"]),
                         (0, len(CLAIM)))

    def test_subclaim_does_not_override_whole_sentence_logic(self):
        claim = "The fee begins in 2027 or 2028."
        result = copy.deepcopy(MODEL_RESULT)
        result["checks"][0].update(text=claim, label="entailment")
        result["checks"].append({"text": "2027", "dimension": "date", "label": "contradiction",
                                 "explanation": "This alternative differs from the date stated.",
                                 "evidence": [{"passage_id": "p1", "quote": "2028"}]})
        validated = validate_model_result(claim, result, [PASSAGE])
        self.assertEqual(validated["overall"], "entailment")
        self.assertFalse(validated["validation_degraded"])

    def test_missing_whole_claim_is_degraded_neutral(self):
        result = copy.deepcopy(MODEL_RESULT)
        result["checks"][0].update(text="CHF 200", dimension="amount", label="entailment")
        validated = validate_model_result(CLAIM, result, [PASSAGE])
        self.assertEqual(validated["overall"], "neutral")
        self.assertTrue(validated["validation_degraded"])
        self.assertEqual(validated["checks"][0]["text"], CLAIM)

    def test_context_limit_and_duplicate_ids_fail_before_inference(self):
        proposals = [{"passages": [{"id": "a", "text": "a" * 160000},
                                    {"id": "b", "text": "b" * 160000}]},
                     {"passages": [PASSAGE, copy.deepcopy(PASSAGE)]}]
        with patch("claimlens.engine.request_completion") as completion:
            for proposal in proposals:
                with self.subTest(proposal_size=len(proposal["passages"])), self.assertRaises(ValidationError):
                    check_claim(proposal, CLAIM, DEFAULT_MODEL, "live", SETTINGS)
            completion.assert_not_called()

    def test_empty_corpus_abstains_without_provider(self):
        with patch("claimlens.engine.request_completion") as completion:
            result = check_claim({"passages": []}, CLAIM, DEFAULT_MODEL, "live", SETTINGS)
            completion.assert_not_called()
        self.assertEqual(result["classification"], 1)
        self.assertEqual(result["metrics"]["input_tokens"], 0)


class ProviderTests(unittest.TestCase):
    def test_outbound_request_keeps_vote_and_source_attribution(self):
        with patch("claimlens.llm.build_opener") as opener:
            opener.return_value.open.return_value = provider_response(usage={"prompt_tokens": 42, "completion_tokens": 20})
            result, metrics = request_completion(CLAIM, [PASSAGE], DEFAULT_MODEL, SETTINGS, "fr", vote="Specified vote")
            request = opener.return_value.open.call_args.args[0]
            outbound = json.loads(request.data)
            content = json.loads(outbound["messages"][1]["content"])
        self.assertEqual(result, MODEL_RESULT)
        self.assertEqual(content["vote"], "Specified vote")
        self.assertEqual(content["claim_language"], "fr")
        self.assertEqual(content["passages"][0]["attribution"], PASSAGE["attribution"])
        self.assertEqual(metrics["input_tokens"], 42)
        self.assertEqual(metrics["output_tokens"], 20)
        self.assertIsNone(metrics["context_tokens"])
        self.assertEqual(metrics["context_characters"], len(PASSAGE["text"]))
        self.assertGreaterEqual(metrics["inference_time_ms"], 0)

    def test_missing_or_invalid_token_usage_is_not_estimated(self):
        for usage in (None, {"prompt_tokens": True, "completion_tokens": -1}):
            with self.subTest(usage=usage), patch("claimlens.llm.build_opener") as opener:
                opener.return_value.open.return_value = provider_response(usage=usage)
                _, metrics = request_completion(CLAIM, [PASSAGE], DEFAULT_MODEL, SETTINGS)
            self.assertIsNone(metrics["input_tokens"])
            self.assertIsNone(metrics["output_tokens"])
            self.assertEqual(metrics["token_usage_source"], "not_supplied")

    def test_incomplete_or_malformed_response_is_an_error(self):
        responses = [provider_response(finish_reason="length"), io.BytesIO(b"not json"),
                     io.BytesIO(b'{"choices": []}'), io.BytesIO(b"x" * 1_048_577)]
        for response in responses:
            with self.subTest(response=response), patch("claimlens.llm.build_opener") as opener:
                opener.return_value.open.return_value = response
                with self.assertRaises(ProviderError):
                    request_completion(CLAIM, [PASSAGE], DEFAULT_MODEL, SETTINGS)

    def test_provider_failure_never_exposes_body_key_or_url(self):
        failures = [HTTPError("https://private.example", 401, "test-secret-only", {},
                              io.BytesIO(b"test-secret-only and private claim")),
                    URLError("test-secret-only at private.example")]
        for failure in failures:
            with self.subTest(failure=type(failure)), patch("claimlens.llm.build_opener") as opener:
                opener.return_value.open.side_effect = failure
                with self.assertRaises(ProviderError) as raised:
                    request_completion(CLAIM, [PASSAGE], DEFAULT_MODEL, SETTINGS)
            message = str(raised.exception)
            self.assertNotIn("test-secret-only", message)
            self.assertNotIn("private.example", message)
            self.assertNotIn("private claim", message)

    def test_redirects_are_rejected_without_forwarding_authorization(self):
        with self.assertRaises(ProviderError):
            _RejectRedirects().redirect_request(None, None, 302, "", {}, "https://other.example")

    def test_operator_configured_http_and_https_proxy_policy(self):
        self.assertEqual(completion_url("https://example.com/v1/"), "https://example.com/v1/chat/completions")
        for host in ("localhost", "127.0.0.1", "[::1]", "host.docker.internal", "gateway.docker.internal", "proxy:8000", "operator.example"):
            with self.subTest(host=host):
                self.assertEqual(completion_url("http://" + host + "/v1"),
                                 "http://" + host + "/v1/chat/completions")
        for url in ("ftp://remote.example/v1", "https://user:secret@example.com/v1",
                    "https://example.com/v1?key=secret", "https://[broken", "https://example.com:bad"):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                completion_url(url)

    def test_configured_maximum_timeout_is_accepted_by_transport(self):
        settings = Settings("http://localhost/v1", "", DEFAULT_MODEL, 600)
        with patch("claimlens.llm.build_opener") as opener:
            opener.return_value.open.return_value = provider_response()
            request_completion(CLAIM, [PASSAGE], DEFAULT_MODEL, settings)
            self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 600)


if __name__ == "__main__":
    unittest.main()
