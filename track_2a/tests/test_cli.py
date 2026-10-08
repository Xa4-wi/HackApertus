"""Official JSONL contract and local configuration boundary tests."""

import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from claimlens.booklets import prepare_case
from claimlens.cli import main, prediction_record, run_batch
from claimlens.config import PROJECT_ROOT, Settings, load_dotenv
from claimlens.config import public_config
from claimlens.models import DEFAULT_MODEL, ProviderError, ValidationError


CLAIMS = {"de": "Die jährliche Gebühr beträgt 200 Franken.",
          "fr": "La redevance annuelle est de 200 francs.",
          "it": "La tassa annuale ammonta a 200 franchi."}
SOURCES = {"de": "Ab 2028 beträgt die jährliche Gebühr 200 Franken.",
           "fr": "À partir de 2028, la redevance annuelle est de 200 francs.",
           "it": "Dal 2028, la tassa annuale ammonta a 200 franchi."}
SETTINGS = Settings("https://proxy.example/v1", "test-private-key", DEFAULT_MODEL, 30)


def reference_case(case_id="case-1", claim_language="de", source_language="de"):
    return {"id": case_id, "vote": "Fictional fee proposal",
            "claim": {"text": CLAIMS[claim_language], "language": claim_language},
            "reference": {"text": SOURCES[source_language], "language": source_language}}


def mock_completion(claim, passages, model, settings, claim_language="auto", *, vote=""):
    return ({"summary": "The supplied source states the amount.",
             "checks": [{"text": claim, "dimension": "general", "label": "entailment",
                         "explanation": "The amount agrees with the supplied source.",
                         "evidence": [{"passage_id": passages[0]["id"], "quote": passages[0]["text"]}]}]},
            {"input_tokens": 120, "output_tokens": 40, "context_tokens": None,
             "context_characters": sum(len(p["text"]) for p in passages),
             "inference_seconds": 0.025, "inference_time_ms": 25.0,
             "token_usage_source": "provider"})


def ui_result(label="entailment"):
    from claimlens.engine import check_claim
    proposal, claim, language = prepare_case(reference_case(), Path("."))
    with patch("claimlens.engine.request_completion", side_effect=mock_completion):
        result = check_claim(proposal, claim, DEFAULT_MODEL, "live", SETTINGS, claim_language=language)
    result["overall"] = label
    result["classification"] = {"entailment": 0, "neutral": 1, "contradiction": 2}[label]
    result["checks"][0]["label"] = label
    return result


class BatchTests(unittest.TestCase):
    def test_offline_demo_flag_is_not_an_application_mode(self):
        with self.assertRaises(SystemExit) as exited, patch("sys.stderr", new_callable=io.StringIO):
            main(["--demo"])
        self.assertEqual(exited.exception.code, 2)

    def test_nine_language_pairs_keep_all_source_text_and_official_schema(self):
        cases = [reference_case(claim_lang + "-" + source_lang, claim_lang, source_lang)
                 for claim_lang in ("de", "fr", "it") for source_lang in ("de", "fr", "it")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path, output_path = root / "input.jsonl", root / "predictions.jsonl"
            input_path.write_text("\n".join(json.dumps(case) for case in cases), encoding="utf-8")
            with patch("claimlens.engine.request_completion", side_effect=mock_completion) as completion:
                self.assertEqual(run_batch(input_path, output_path, SETTINGS, root), 9)
            rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(completion.call_args_list), 9)
        for case, row, call in zip(cases, rows, completion.call_args_list):
            with self.subTest(case=case["id"]):
                self.assertEqual(set(row), {"id", "label", "label_name", "evidence", "metrics"})
                self.assertEqual(row["id"], case["id"])
                self.assertEqual((row["label"], row["label_name"]), (0, "entailment"))
                self.assertEqual(row["evidence"], [{"page": None, "text": case["reference"]["text"]}])
                self.assertEqual(set(row["metrics"]), {"input_tokens", "output_tokens", "inference_time_ms"})
                self.assertEqual(row["metrics"]["input_tokens"], 120)
                self.assertGreaterEqual(row["metrics"]["inference_time_ms"], 0)
                self.assertEqual(call.args[1][0]["text"], case["reference"]["text"])
                self.assertEqual(call.args[1][0]["language"], case["reference"]["language"])
                self.assertEqual(call.args[4], case["claim"]["language"])
                self.assertEqual(call.kwargs["vote"], case["vote"])

    def test_failed_batch_does_not_replace_previous_predictions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path, output_path = root / "input.jsonl", root / "predictions.jsonl"
            input_path.write_text(json.dumps(reference_case()) + "\n" + json.dumps(reference_case()), encoding="utf-8")
            output_path.write_text("previous successful results\n", encoding="utf-8")
            with patch("claimlens.engine.request_completion", side_effect=mock_completion):
                with self.assertRaisesRegex(ValidationError, "IDs must be unique"):
                    run_batch(input_path, output_path, SETTINGS, root)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "previous successful results\n")

    def test_provider_failure_is_an_error_not_neutral_prediction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path, output_path = root / "input.jsonl", root / "output.jsonl"
            input_path.write_text(json.dumps(reference_case()), encoding="utf-8")
            with patch("claimlens.engine.request_completion", side_effect=ProviderError("Endpoint unavailable.")):
                with self.assertRaisesRegex(ValidationError, "Endpoint unavailable"):
                    run_batch(input_path, output_path, SETTINGS, root)
            self.assertFalse(output_path.exists())

    def test_input_and_output_cannot_be_same_file(self):
        with self.assertRaisesRegex(ValidationError, "must differ"):
            run_batch("same.jsonl", "same.jsonl", SETTINGS)

    def test_missing_proxy_fails_before_reading_or_inference(self):
        with self.assertRaisesRegex(ValidationError, "BASE_URL"):
            run_batch("not-created.jsonl", "output.jsonl", Settings())

    def test_cli_reports_failure_without_credentials_or_traceback(self):
        stderr, stdout = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"BASE_URL": "", "API_KEY": "test-private-key"}, clear=True), \
                patch("claimlens.cli.load_dotenv"), redirect_stderr(stderr), redirect_stdout(stdout):
            status = main(["--input", "missing.jsonl", "--output", "out.jsonl"])
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn("test-private-key", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


class SubmissionBoundaryTests(unittest.TestCase):
    def test_neutral_has_no_evidence_even_if_diagnostic_checks_do(self):
        result = ui_result("neutral")
        self.assertTrue(result["checks"][0]["evidence"])
        self.assertEqual(prediction_record("case", result)["evidence"], [])

    def test_only_first_whole_claim_check_exports_evidence(self):
        result = ui_result()
        second = copy.deepcopy(result["checks"][0])
        second["label"] = "contradiction"
        second["evidence"][0]["quote"] = "2028"
        result["checks"].append(second)
        record = prediction_record("case", result)
        self.assertEqual(record["evidence"], [{"page": None, "text": SOURCES["de"]}])

    def test_missing_nonfinite_or_negative_usage_cannot_be_submitted(self):
        for value in (None, float("nan"), float("inf"), -1, True):
            result = ui_result()
            result["metrics"]["input_tokens"] = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                prediction_record("case", result)

    def test_degraded_model_output_cannot_be_submitted(self):
        result = ui_result("neutral")
        result["validation_degraded"] = True
        with self.assertRaises(ValidationError):
            prediction_record("case", result)



class BookletInputTests(unittest.TestCase):
    def test_reference_and_booklet_are_mutually_exclusive(self):
        case = reference_case()
        case["booklet"] = {"path": "booklet.pdf", "language": "de"}
        with self.assertRaisesRegex(ValidationError, "exactly one"):
            prepare_case(case, Path("."))
        del case["booklet"]
        del case["reference"]
        with self.assertRaisesRegex(ValidationError, "exactly one"):
            prepare_case(case, Path("."))

    def test_booklet_cannot_escape_data_root_by_parent_absolute_or_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_root = root / "data"
            data_root.mkdir()
            outside = root / "outside.pdf"
            outside.write_bytes(b"not a real PDF")
            (data_root / "linked.pdf").symlink_to(outside)
            for supplied_path in ("../outside.pdf", str(outside), "linked.pdf"):
                case = reference_case()
                del case["reference"]
                case["booklet"] = {"path": supplied_path, "language": "de"}
                with self.subTest(path=supplied_path), patch("claimlens.booklets.extract_pdf") as extract:
                    with self.assertRaisesRegex(ValidationError, "inside"):
                        prepare_case(case, data_root)
                    extract.assert_not_called()

    def test_booklet_extraction_cache_retains_language(self):
        with tempfile.TemporaryDirectory() as directory:
            root, cache = Path(directory), {}
            case = reference_case()
            del case["reference"]
            case["booklet"] = {"path": "booklet.pdf", "language": "de"}
            with patch("claimlens.booklets.extract_pdf", return_value=[{"id": "p1", "text": "source"}]) as extract:
                prepare_case(case, root, cache)
                prepare_case(case, root, cache)
                self.assertEqual(extract.call_count, 1)
                case["booklet"]["language"] = "fr"
                prepare_case(case, root, cache)
                self.assertEqual(extract.call_count, 2)


class ConfigurationTests(unittest.TestCase):
    def test_proxy_variables_override_aliases_including_explicit_empty_values(self):
        environment = {"BASE_URL": "https://proxy.example/v1/", "API_KEY": "proxy-key",
                       "LLM_BASE_URL": "https://alias.example/v1", "LLM_API_KEY": "alias-key"}
        with patch.dict(os.environ, environment, clear=True):
            settings = Settings.from_env()
            self.assertEqual(settings.base_url, "https://proxy.example/v1")
            self.assertEqual(settings.api_key, "proxy-key")
            os.environ["BASE_URL"] = ""
            os.environ["API_KEY"] = ""
            settings = Settings.from_env()
            self.assertEqual((settings.base_url, settings.api_key), ("", ""))

    def test_dotenv_values_are_literal_and_do_not_override_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('API_KEY=file-key\nLLM_NAME="' + DEFAULT_MODEL + '"\nLLM_API_KEY=$(must_not_execute)\nUNRELATED=ignored\n', encoding="utf-8")
            with patch.dict(os.environ, {"API_KEY": "existing-key"}, clear=True):
                load_dotenv(path)
                self.assertEqual(os.environ["API_KEY"], "existing-key")
                self.assertEqual(os.environ["LLM_NAME"], DEFAULT_MODEL)
                self.assertNotIn("LLM_API_KEY", os.environ)
                self.assertNotIn("UNRELATED", os.environ)
            with patch.dict(os.environ, {}, clear=True):
                load_dotenv(path)
                self.assertEqual(os.environ["LLM_API_KEY"], "$(must_not_execute)")
                self.assertNotIn("UNRELATED", os.environ)

    def test_invalid_configuration_has_safe_typed_errors(self):
        for environment in ({"BASE_URL": "https://[broken"}, {"LLM_TIMEOUT_SECONDS": "nan"},
                            {"LLM_NAME": "unapproved-model"}, {"BASE_URL": "https://user:secret@example.com"}):
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True):
                with self.assertRaises(ValidationError) as raised:
                    Settings.from_env()
                self.assertNotIn("secret", str(raised.exception))

    def test_public_browser_config_excludes_keys_provider_url_and_answers(self):
        proposal, claim, _ = prepare_case(reference_case(), Path("."))
        proposal["examples"] = [{"id": "sample", "claim": claim, "result": {"answer-secret": "answer"}}]
        visible = json.dumps(public_config(SETTINGS))
        for hidden in ("test-private-key", "proxy.example", "answer-secret", SOURCES["de"]):
            self.assertNotIn(hidden, visible)


if __name__ == "__main__":
    unittest.main()
