"""Local model aliases must never change the official remote model contract."""

import io
import json
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claimlens.config import Settings, load_dotenv
from claimlens.corpus import public_config
from claimlens.engine import check_claim
from claimlens.llm import claim_spans, request_completion
from claimlens.models import ALLOWED_MODELS, DEFAULT_MODEL, ValidationError


LOCAL_MODEL = "hf.co/Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF:Q4_K_M"
LOCAL_ENDPOINT = "http://127.0.0.1:12434/engines/v1"
CLAIM = "Die Gebühr beträgt 200 Franken."
PASSAGE = {"id": "p1", "text": CLAIM, "title": "Synthetic source", "language": "de"}
MODEL_RESULT = {
    "summary": "The source states the same fee.",
    "checks": [{"text": CLAIM, "dimension": "general", "label": "entailment",
                "explanation": "The amount matches the supplied source.",
                "evidence": [{"passage_id": "p1", "quote": CLAIM}]}],
}
PROPOSAL = {"id": "test", "title": "Synthetic proposal", "passages": [PASSAGE],
            "examples": [{"id": "example", "claim": CLAIM, "result": MODEL_RESULT}]}


def response(result=None):
    return io.BytesIO(json.dumps({
        "choices": [{"message": {"content": json.dumps(MODEL_RESULT if result is None else result)}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 30, "completion_tokens": 15},
    }).encode("utf-8"))


class LocalModelConfigurationTests(unittest.TestCase):
    def test_local_alias_keeps_canonical_name_and_positional_compatibility(self):
        with patch.dict(os.environ, {"LLM_BASE_URL": LOCAL_ENDPOINT,
                                    "LOCAL_MODEL_ID": LOCAL_MODEL}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.model, DEFAULT_MODEL)
        self.assertEqual(settings.local_model_id, LOCAL_MODEL)
        self.assertEqual(settings.model_for_request(DEFAULT_MODEL), LOCAL_MODEL)
        self.assertEqual(Settings(LOCAL_ENDPOINT, "", DEFAULT_MODEL, 30).local_model_id, "")

    def test_only_exact_local_hosts_activate_alias(self):
        local_hosts = ("127.0.0.1", "localhost", "LOCALHOST", "[::1]",
                       "model-runner.docker.internal", "host.docker.internal")
        for host in local_hosts:
            with self.subTest(host=host):
                settings = Settings("http://" + host + ":12434/engines/v1", local_model_id=LOCAL_MODEL)
                self.assertTrue(settings.local_model_configured)
                self.assertEqual(settings.available_models, (DEFAULT_MODEL,))
                self.assertEqual(settings.model_for_request(DEFAULT_MODEL), LOCAL_MODEL)
        other_hosts = ("proxy.example", "localhost.proxy.example", "127.0.0.1.proxy.example",
                       "host.docker.internal.proxy.example", "127.0.0.2", "gateway.docker.internal")
        for host in other_hosts:
            with self.subTest(host=host):
                settings = Settings("http://" + host + "/v1", local_model_id=LOCAL_MODEL)
                self.assertFalse(settings.local_model_configured)
                self.assertEqual(settings.available_models, ALLOWED_MODELS)
                for model in ALLOWED_MODELS:
                    self.assertEqual(settings.model_for_request(model), model)

    def test_no_endpoint_or_alias_does_not_restrict_model_selection(self):
        for settings in (Settings(local_model_id=LOCAL_MODEL), Settings(LOCAL_ENDPOINT)):
            with self.subTest(settings=settings):
                self.assertFalse(settings.local_model_configured)
                self.assertEqual(settings.available_models, ALLOWED_MODELS)

    def test_evaluator_variables_override_local_dotenv_without_alias_leakage(self):
        with tempfile.TemporaryDirectory() as directory:
            dotenv = Path(directory) / ".env"
            dotenv.write_text("LLM_BASE_URL=" + LOCAL_ENDPOINT + "\nLOCAL_MODEL_ID=" + LOCAL_MODEL
                              + "\nLLM_NAME=" + DEFAULT_MODEL + "\nLLM_API_KEY=local-test-key\n", encoding="utf-8")
            injected = {"BASE_URL": "https://evaluation.example/v1", "API_KEY": "evaluation-test-key",
                        "LLM_NAME": ALLOWED_MODELS[1]}
            with patch.dict(os.environ, injected, clear=True):
                load_dotenv(dotenv)
                settings = Settings.from_env()
        self.assertEqual(settings.base_url, injected["BASE_URL"])
        self.assertEqual(settings.api_key, injected["API_KEY"])
        self.assertEqual(settings.model, ALLOWED_MODELS[1])
        self.assertEqual(settings.local_model_id, LOCAL_MODEL)
        self.assertFalse(settings.local_model_configured)
        self.assertEqual(settings.model_for_request(settings.model), ALLOWED_MODELS[1])

    def test_explicit_empty_evaluation_endpoint_cannot_fall_back_locally(self):
        with patch.dict(os.environ, {"BASE_URL": "", "LLM_BASE_URL": LOCAL_ENDPOINT,
                                    "LOCAL_MODEL_ID": LOCAL_MODEL}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.base_url, "")
        visible = public_config(settings, [PROPOSAL])
        self.assertFalse(visible["live_ready"])
        self.assertFalse(visible["local_model_configured"])
        self.assertEqual([item["id"] for item in visible["models"]], list(ALLOWED_MODELS))

    def test_dotenv_alias_preserves_inherited_value_and_is_literal(self):
        with tempfile.TemporaryDirectory() as directory:
            dotenv = Path(directory) / ".env"
            dotenv.write_text("LOCAL_MODEL_ID='$(literal-only)'\n", encoding="utf-8")
            with patch.dict(os.environ, {"LOCAL_MODEL_ID": LOCAL_MODEL}, clear=True):
                load_dotenv(dotenv)
                self.assertEqual(os.environ["LOCAL_MODEL_ID"], LOCAL_MODEL)
            with patch.dict(os.environ, {}, clear=True):
                load_dotenv(dotenv)
                self.assertEqual(os.environ["LOCAL_MODEL_ID"], "$(literal-only)")

    def test_alias_cannot_replace_canonical_llm_name(self):
        with patch.dict(os.environ, {"LLM_NAME": LOCAL_MODEL, "LOCAL_MODEL_ID": LOCAL_MODEL}, clear=True):
            with self.assertRaisesRegex(ValidationError, "LLM_NAME"):
                Settings.from_env()

    def test_alias_validation_cannot_interfere_with_remote_evaluation(self):
        for alias in ("invalid alias", "x" * 501):
            with self.subTest(alias_length=len(alias)):
                with patch.dict(os.environ, {"BASE_URL": LOCAL_ENDPOINT, "LOCAL_MODEL_ID": alias}, clear=True):
                    with self.assertRaisesRegex(ValidationError, "LOCAL_MODEL_ID"):
                        Settings.from_env()
                with patch.dict(os.environ, {"BASE_URL": "https://evaluation.example/v1", "LOCAL_MODEL_ID": alias}, clear=True):
                    settings = Settings.from_env()
                    self.assertEqual(settings.model_for_request(DEFAULT_MODEL), DEFAULT_MODEL)

    def test_public_local_config_lists_only_configured_canonical_model(self):
        settings = Settings(LOCAL_ENDPOINT, "synthetic-private-key", local_model_id=LOCAL_MODEL)
        config = public_config(settings, [PROPOSAL])
        self.assertEqual(len(config["models"]), 1)
        self.assertEqual(config["models"][0]["id"], DEFAULT_MODEL)
        self.assertIn("local", config["models"][0]["label"])
        self.assertTrue(config["local_model_configured"])
        self.assertTrue(config["live_ready"])  # Configured, not a runtime health probe.
        visible = json.dumps(config)
        self.assertNotIn("synthetic-private-key", visible)
        self.assertNotIn(LOCAL_ENDPOINT, visible)
        self.assertNotIn(LOCAL_MODEL, visible)

    def test_public_request_timeout_leaves_backend_a_margin(self):
        for timeout in (1, 120, 300, 600):
            with self.subTest(timeout=timeout):
                settings = Settings(LOCAL_ENDPOINT, "synthetic-private-key", timeout=timeout,
                                    local_model_id=LOCAL_MODEL)
                config = public_config(settings, [PROPOSAL])
                self.assertEqual(config["request_timeout_seconds"], timeout + 10)
                self.assertNotIn("synthetic-private-key", json.dumps(config))
                self.assertNotIn(LOCAL_ENDPOINT, json.dumps(config))


class LocalModelTransportTests(unittest.TestCase):
    def test_local_request_sends_served_alias_and_identifies_application(self):
        settings = Settings(LOCAL_ENDPOINT, local_model_id=LOCAL_MODEL)
        with patch("claimlens.llm.build_opener") as opener:
            opener.return_value.open.return_value = response()
            request_completion(CLAIM, [PASSAGE], DEFAULT_MODEL, settings, "de")
            request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, LOCAL_ENDPOINT + "/chat/completions")
        self.assertEqual(json.loads(request.data)["model"], LOCAL_MODEL)
        self.assertEqual(request.get_header("User-agent"), "ClaimLens/0.1")

    def test_local_transport_constrains_shape_and_claim_length_during_decoding(self):
        settings = Settings(LOCAL_ENDPOINT, local_model_id=LOCAL_MODEL)
        passages = [PASSAGE, {**PASSAGE, "id": "other-page", "text": "Another source passage."}]
        with patch("claimlens.llm.build_opener") as opener:
            opener.return_value.open.return_value = response()
            request_completion(CLAIM, passages, DEFAULT_MODEL, settings, "de")
            request = json.loads(opener.return_value.open.call_args.args[0].data)
        response_format = request["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])
        schema = response_format["json_schema"]["schema"]
        self.assertEqual(set(schema["required"]), {"summary", "checks"})
        self.assertFalse(schema["additionalProperties"])
        checks = schema["properties"]["checks"]
        self.assertEqual((checks["minItems"], checks["maxItems"]), (1, 16))
        check = checks["items"]
        self.assertFalse(check["additionalProperties"])
        self.assertEqual(set(check["required"]), {"text", "dimension", "label", "explanation", "evidence"})
        properties = check["properties"]
        allowed_text = properties["text"]["enum"]
        self.assertIn(CLAIM, allowed_text)
        self.assertIn("200 Franken.", allowed_text)
        self.assertTrue(all(text and text in CLAIM for text in allowed_text))
        self.assertNotIn("nachdem", allowed_text)
        self.assertEqual(set(properties["dimension"]["enum"]),
                         {"general", "amount", "date", "scope", "qualifier", "attribution"})
        self.assertNotIn("amount, date, scope", properties["dimension"]["enum"])
        self.assertEqual(set(properties["label"]["enum"]), {"entailment", "neutral", "contradiction"})
        citation = properties["evidence"]["items"]
        self.assertEqual(set(citation["properties"]["passage_id"]["enum"]), {"p1", "other-page"})
        self.assertFalse(citation["additionalProperties"])

    def test_allowed_claim_spans_preserve_punctuation_and_original_whitespace(self):
        claim = "  Die  jährliche,\tGebühr\nbeträgt CHF 200.  "
        spans = claim_spans(claim)
        self.assertIn(claim, spans)
        self.assertIn("jährliche,\tGebühr", spans)
        self.assertIn("Die  jährliche,\tGebühr\nbeträgt", spans)
        self.assertIn("CHF 200.", spans)
        self.assertNotIn("jährliche, Gebühr", spans)
        self.assertTrue(all(span and span in claim for span in spans))
        self.assertEqual(len(spans), len(set(spans)))

    def test_long_claim_is_available_whole_while_diagnostic_phrases_are_bounded(self):
        words = ["word{}".format(index) for index in range(14)]
        claim = " ".join(words)
        spans = claim_spans(claim)
        self.assertIn(claim, spans)
        self.assertIn(" ".join(words[:8]), spans)
        self.assertNotIn(" ".join(words[:9]), spans)
        self.assertTrue(all(span == claim or len(span.split()) <= 8 for span in spans))
        self.assertTrue(all(span in claim for span in spans))

    def test_claim_and_final_instruction_follow_source_content(self):
        settings = Settings(LOCAL_ENDPOINT, local_model_id=LOCAL_MODEL)
        with patch("claimlens.llm.build_opener") as opener:
            opener.return_value.open.return_value = response()
            request_completion(CLAIM, [PASSAGE], DEFAULT_MODEL, settings, "de", vote="Specified proposal")
            request = json.loads(opener.return_value.open.call_args.args[0].data)
        content = json.loads(request["messages"][1]["content"])
        keys = list(content)
        self.assertLess(keys.index("passages"), keys.index("claim"))
        self.assertLess(keys.index("claim"), keys.index("task"))
        self.assertEqual(content["claim"], CLAIM)
        self.assertEqual(content["vote"], "Specified proposal")

    def test_local_response_still_requires_exact_claim_text(self):
        settings = Settings(LOCAL_ENDPOINT, local_model_id=LOCAL_MODEL)
        result = copy.deepcopy(MODEL_RESULT)
        result["checks"][0]["text"] = "Wrong words"
        with patch("claimlens.llm.build_opener") as opener:
            opener.return_value.open.return_value = response(result)
            with self.assertRaisesRegex(ValidationError, "exact substring"):
                check_claim(PROPOSAL, CLAIM, DEFAULT_MODEL, "live", settings)

    def test_local_response_still_requires_grounded_quotes_and_whole_claim(self):
        settings = Settings(LOCAL_ENDPOINT, local_model_id=LOCAL_MODEL)
        invented_quote = copy.deepcopy(MODEL_RESULT)
        invented_quote["checks"][0]["evidence"][0]["quote"] = "The source never said this."
        partial_claim = copy.deepcopy(MODEL_RESULT)
        partial_claim["checks"][0].update(text="200 Franken", dimension="amount")
        for model_result in (invented_quote, partial_claim):
            with self.subTest(result=model_result), patch("claimlens.llm.build_opener") as opener:
                opener.return_value.open.return_value = response(model_result)
                result = check_claim(PROPOSAL, CLAIM, DEFAULT_MODEL, "live", settings)
            self.assertEqual(result["classification"], 1)
            self.assertTrue(result["validation_degraded"])

    def test_remote_transport_ignores_alias_for_both_official_models(self):
        settings = Settings("https://evaluation.example/v1", local_model_id=LOCAL_MODEL)
        for model in ALLOWED_MODELS:
            with self.subTest(model=model), patch("claimlens.llm.build_opener") as opener:
                opener.return_value.open.return_value = response()
                request_completion(CLAIM, [PASSAGE], model, settings)
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(json.loads(request.data)["model"], model)
                self.assertEqual(json.loads(request.data)["response_format"], {"type": "json_object"})

    def test_unconfigured_local_endpoint_preserves_generic_proxy_contract(self):
        settings = Settings(LOCAL_ENDPOINT)
        with patch("claimlens.llm.build_opener") as opener:
            opener.return_value.open.return_value = response()
            request_completion(CLAIM, [PASSAGE], DEFAULT_MODEL, settings)
            request = json.loads(opener.return_value.open.call_args.args[0].data)
        self.assertEqual(request["response_format"], {"type": "json_object"})

    def test_mismatched_selection_fails_before_demo_or_live_inference(self):
        settings = Settings(LOCAL_ENDPOINT, local_model_id=LOCAL_MODEL)
        with patch("claimlens.engine.request_completion") as completion:
            for mode in ("demo", "live"):
                with self.subTest(mode=mode), self.assertRaisesRegex(ValidationError, "LLM_NAME"):
                    check_claim(PROPOSAL, CLAIM, ALLOWED_MODELS[1], mode, settings)
            completion.assert_not_called()
        with patch("claimlens.llm.build_opener") as opener:
            with self.assertRaisesRegex(ValidationError, "LLM_NAME"):
                request_completion(CLAIM, [PASSAGE], ALLOWED_MODELS[1], settings)
            opener.assert_not_called()

    def test_live_metadata_preserves_canonical_and_served_ids(self):
        settings = Settings(LOCAL_ENDPOINT, local_model_id=LOCAL_MODEL)
        with patch("claimlens.llm.build_opener") as opener:
            opener.return_value.open.return_value = response()
            result = check_claim(PROPOSAL, CLAIM, DEFAULT_MODEL, "live", settings)
        self.assertEqual(result["model"], DEFAULT_MODEL)
        self.assertEqual(result["served_model"], LOCAL_MODEL)
        self.assertEqual(result["classification"], 0)
        self.assertEqual(result["metrics"]["input_tokens"], 30)
        for proposal, mode in ((PROPOSAL, "demo"), ({"passages": []}, "live")):
            with self.subTest(mode=mode), patch("claimlens.engine.request_completion") as completion:
                result = check_claim(proposal, CLAIM, DEFAULT_MODEL, mode, settings)
                self.assertIsNone(result["served_model"])
                completion.assert_not_called()


if __name__ == "__main__":
    unittest.main()
