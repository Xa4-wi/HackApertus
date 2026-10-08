"""Efficiency settings remain explicit, reproducible and native-endpoint scoped."""

from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from claimlens.config import Settings, load_dotenv
from claimlens.context import TokenBudget
from claimlens.engine import check_claim
from claimlens.models import DEFAULT_MODEL, ValidationError


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("efficiency_evaluation", ROOT / "scripts/evaluate_local.py")
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)

MODE_ENV = {"RETRIEVAL_QUERY_MODE": "source", "RETRIEVAL_CITATION_MODE": "prefix"}
BODY = ("La nouvelle mesure prévoit des moyens financiers supplémentaires pour "
        "la biodiversité. Le coût annuel est de 240 millions de francs. "
        "Ces moyens financent les mesures des cantons et de la Confédération.")
CLAIM = "Le coût annuel est de 240 millions de francs."
USAGE = {"input_tokens": 1234, "output_tokens": 123, "model_request_attempts": 1}


class EfficiencyConfigurationTests(unittest.TestCase):
    def test_defaults_preserve_existing_multilingual_and_full_quote_behavior(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.retrieval_query_mode, "multilingual")
        self.assertEqual(settings.retrieval_citation_mode, "full")

    def test_every_supported_mode_combination_can_be_selected_from_environment(self):
        for query in ("multilingual", "source"):
            for citation in ("full", "prefix"):
                with self.subTest(query=query, citation=citation), patch.dict(os.environ, {
                        "RETRIEVAL_QUERY_MODE": " " + query + " ",
                        "RETRIEVAL_CITATION_MODE": " " + citation + " "}, clear=True):
                    settings = Settings.from_env()
                self.assertEqual((settings.retrieval_query_mode, settings.retrieval_citation_mode),
                                 (query, citation))

    def test_empty_and_unknown_modes_fail_before_any_endpoint_is_used(self):
        for name in MODE_ENV:
            for value in ("", "auto", "true", "SOURCE", "PREFIX", "source;prefix"):
                with self.subTest(name=name, value=value), \
                        patch.dict(os.environ, {name: value}, clear=True), \
                        self.assertRaisesRegex(ValidationError, name):
                    Settings.from_env()

    def test_dotenv_whitelist_loads_modes_and_inherited_values_take_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("RETRIEVAL_QUERY_MODE='source'\nRETRIEVAL_CITATION_MODE=\"prefix\"\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                load_dotenv(path)
                settings = Settings.from_env()
                self.assertEqual((settings.retrieval_query_mode, settings.retrieval_citation_mode),
                                 ("source", "prefix"))
            with patch.dict(os.environ, {"RETRIEVAL_QUERY_MODE": "multilingual",
                                         "RETRIEVAL_CITATION_MODE": "full"}, clear=True):
                load_dotenv(path)
                settings = Settings.from_env()
                self.assertEqual((settings.retrieval_query_mode, settings.retrieval_citation_mode),
                                 ("multilingual", "full"))
            for name in MODE_ENV:
                with self.subTest(inherited_empty=name), patch.dict(os.environ, {name: ""}, clear=True):
                    load_dotenv(path)
                    with self.assertRaisesRegex(ValidationError, name):
                        Settings.from_env()

    def test_run_identity_pins_both_modes_and_rejects_cross_mode_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, output = root / "input.jsonl", root / "results.jsonl"
            evaluation.write_jsonl(inputs, [{"id": "one", "claim": {"text": CLAIM, "language": "fr"},
                                            "reference": {"text": BODY, "language": "fr"}}])
            evaluation.write_jsonl(output, [{"id": "one", "status": "failed"}])
            settings = Settings("http://localhost:8081/v1", api_key="private-test-credential")
            identity = evaluation.run_identity(inputs, settings)
            self.assertEqual(identity["retrieval_query_mode"], "multilingual")
            self.assertEqual(identity["retrieval_citation_mode"], "full")
            self.assertNotIn(settings.api_key, json.dumps(identity))
            evaluation.write_json(output.with_suffix(".run.json"), identity)
            for change in ({"retrieval_query_mode": "source"}, {"retrieval_citation_mode": "prefix"}):
                altered = replace(settings, **change)
                with self.subTest(change=change), patch.object(evaluation, "check_claim") as inference:
                    changed_identity = evaluation.run_identity(inputs, altered)
                    self.assertNotEqual(identity, changed_identity)
                    self.assertEqual(changed_identity["source_sha256"], identity["source_sha256"])
                    self.assertEqual(changed_identity["input_sha256"], identity["input_sha256"])
                    with self.assertRaisesRegex(ValueError, "identity is missing or changed"):
                        evaluation.run_cases(inputs, output, altered, root, resume=True)
                inference.assert_not_called()

    @unittest.skipUnless(shutil.which("make"), "make is not available in this runtime")
    def test_make_forwards_explicit_modes_including_empty_without_baking_in_defaults(self):
        for selection in ({}, MODE_ENV, {name: "" for name in MODE_ENV}):
            environment = {key: value for key, value in os.environ.items() if key not in MODE_ENV}
            environment.update(selection)
            with self.subTest(selection=selection):
                # A dry run validates the actual Make expansion without running
                # Docker, creating directories, or contacting the model.
                result = subprocess.run(["make", "-n", "run", "DOCKER=docker", "IMAGE=claimlens:review"],
                                        cwd=ROOT, env=environment, text=True, capture_output=True,
                                        check=True, timeout=10)
                for name in MODE_ENV:
                    forwarded = bool(re.search(r"-e\s+" + name + r"(?:\s|$)", result.stdout))
                    self.assertEqual(forwarded, name in selection)


class EfficiencyRuntimeIntegrationTests(unittest.TestCase):
    def run_check(self, settings, *, source_kind="booklet", long=True):
        passage = {"id": "page-7", "page": 7, "language": "fr", "text": BODY}
        if long:
            passage["text"] += "\n\n" + "Les routes cantonales sont entretenues chaque année. " * 150
        proposal = {"source_kind": source_kind, "passages": [passage], "vote": "Biodiversité"}
        unit = {"id": "u1", "passage_id": passage["id"], "page": passage["page"],
                "start": 0, "end": len(BODY), "text": BODY}
        captured = []
        def provider(data, passed_settings, passages):
            captured.append((data, passed_settings, passages))
            if data["response_format"]["type"] == "json_schema":
                quotes = data["response_format"]["json_schema"]["schema"]["properties"]["evidence"]["items"]["anyOf"][0]["properties"]["quote"]["enum"]
                quote = quotes[0]
            else:
                quote = BODY
            return ({"relation": "supported", "explanation": "The source states the annual amount.",
                     "evidence": [{"passage_id": passage["id"], "quote": quote}]}, dict(USAGE))
        with patch.object(TokenBudget, "_local_count", side_effect=OSError("Tokenizer disabled for offline test")), \
                patch("claimlens.fast.search", return_value={"units": [unit], "ranked_ids": ["u1"], "candidate_count": 1}), \
                patch("claimlens.fast.request_queries") as multilingual, \
                patch("claimlens.fast.request_source_queries") as targeted, \
                patch("claimlens.llm.request_json", side_effect=provider):
            result = check_claim(proposal, CLAIM, DEFAULT_MODEL, "live", settings, claim_language="fr")
        multilingual.assert_not_called()
        targeted.assert_not_called()
        return result, captured

    def test_native_prefix_setting_survives_fast_limits_and_expands_public_evidence(self):
        settings = Settings("http://localhost:8081/v1", local_model_id="local-apertus",
                            context_tokens=16384, retrieval_query_mode="source", retrieval_citation_mode="prefix")
        result, captured = self.run_check(settings)
        self.assertEqual(len(captured), 1)
        data, passed_settings, passages = captured[0]
        self.assertEqual(passed_settings.retrieval_query_mode, "source")
        self.assertEqual(passed_settings.retrieval_citation_mode, "prefix")
        self.assertLessEqual(passed_settings.document_timeout, 120)
        self.assertLessEqual(passed_settings.max_document_model_calls, 4)
        self.assertEqual(data["model"], "local-apertus")
        quote, = data["response_format"]["json_schema"]["schema"]["properties"]["evidence"]["items"]["anyOf"][0]["properties"]["quote"]["enum"]
        self.assertLess(len(quote), len(BODY))
        self.assertTrue(BODY.startswith(quote))
        self.assertEqual(result["checks"][0]["evidence"], [{"passage_id": "page-7", "quote": BODY}])
        self.assertEqual(result["classification"], 0)
        self.assertEqual(result["processing"]["evidence_context_expanded"], 1)
        self.assertEqual(result["processing"]["query_strategy"], "original_source")
        self.assertEqual(result["processing"]["citation_mode"], "prefix")
        self.assertEqual(result["processing"]["model_calls"], 1)
        self.assertEqual(result["metrics"]["output_tokens"], USAGE["output_tokens"])
        self.assertFalse(result["validation_degraded"])

    def test_remote_endpoint_keeps_generic_full_quotes_despite_local_alias_and_prefix_setting(self):
        settings = Settings("https://evaluation.example/v1", local_model_id="local-apertus",
                            context_tokens=16384, retrieval_query_mode="source", retrieval_citation_mode="prefix")
        result, captured = self.run_check(settings)
        self.assertEqual(len(captured), 1)
        data, passed_settings, _ = captured[0]
        self.assertFalse(passed_settings.local_model_configured)
        self.assertEqual(data["model"], DEFAULT_MODEL)
        self.assertEqual(data["response_format"], {"type": "json_object"})
        self.assertEqual(result["checks"][0]["evidence"][0]["quote"], BODY)
        self.assertNotIn("evidence_context_expanded", result["processing"])
        self.assertEqual(result["processing"]["citation_mode"], "full")
        self.assertEqual(result["metrics"]["output_tokens"], USAGE["output_tokens"])

    def test_short_booklet_and_reference_ignore_prefix_mode_for_full_source(self):
        settings = Settings("http://localhost:8081/v1", local_model_id="local-apertus",
                            context_tokens=16384, retrieval_query_mode="source", retrieval_citation_mode="prefix")
        for source_kind in ("booklet", "reference"):
            with self.subTest(source_kind=source_kind):
                result, captured = self.run_check(settings, source_kind=source_kind, long=False)
            self.assertEqual(result["processing"]["strategy"], "full")
            self.assertNotIn("evidence_context_expanded", result["processing"])
            data, passed_settings, _ = captured[0]
            quotes = data["response_format"]["json_schema"]["schema"]["properties"]["evidence"]["items"]["anyOf"][0]["properties"]["quote"]["enum"]
            self.assertIn(BODY, quotes)
            self.assertTrue(all(quote.endswith(".") for quote in quotes))
            if source_kind == "reference":
                self.assertEqual(passed_settings.document_strategy, "exhaustive")
            else:
                self.assertEqual(result["processing"]["citation_mode"], "full")

    def test_native_full_citation_mode_is_reported_without_expansion(self):
        settings = Settings("http://localhost:8081/v1", local_model_id="local-apertus",
                            context_tokens=16384, retrieval_query_mode="source", retrieval_citation_mode="full")
        result, _ = self.run_check(settings)
        self.assertEqual(result["processing"]["citation_mode"], "full")
        self.assertNotIn("evidence_context_expanded", result["processing"])


if __name__ == "__main__":
    unittest.main()
