import importlib.util
import json
from dataclasses import replace
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claimlens.config import Settings

spec = importlib.util.spec_from_file_location("evaluate_local", Path(__file__).parents[1] / "scripts/evaluate_local.py")
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


class EvaluationTests(unittest.TestCase):
    def cases(self):
        inputs, gold = [], []
        for claim in ("de", "fr", "it"):
            for source in ("de", "fr", "it"):
                for label in range(3):
                    case_id = claim + source + str(label)
                    inputs.append({"id": case_id, "vote": "Proposal",
                                   "claim": {"text": case_id, "language": claim},
                                   "reference": {"text": "Source", "language": source}})
                    gold.append({"id": case_id, "label": label})
        return inputs, gold

    def test_sampling_covers_nine_pairs_three_labels_without_gold_in_inputs(self):
        inputs, gold = self.cases()
        chosen, targets = evaluation.select_cases(inputs, gold)
        self.assertEqual(len(chosen), 27)
        self.assertEqual({x["id"] for x in chosen}, {x["id"] for x in targets})
        self.assertTrue(all(set(x) == {"id", "vote", "claim", "reference"} for x in chosen))
        self.assertEqual((chosen, targets), evaluation.select_cases(list(reversed(inputs)), gold))

    def test_failed_and_missing_cases_reduce_accuracy_and_f1(self):
        inputs, gold = self.cases()
        records = [{"id": c["id"], "status": "accepted", "prediction": {"label": g["label"], "evidence": []}}
                   for c, g in zip(inputs, gold)]
        self.assertEqual(evaluation.score_records(inputs, gold, records)["macro_f1_including_failures"], 1)
        records[0] = {"id": inputs[0]["id"], "status": "failed", "error": "Invalid source quote"}
        records.pop()
        report = evaluation.score_records(inputs, gold, records)
        self.assertEqual(report["failures"], 2)
        self.assertAlmostEqual(report["accuracy_including_failures"], 25 / 27)
        self.assertLess(report["macro_f1_including_failures"], 1)
        self.assertEqual(sum(row[3] for row in report["confusion_matrix"]), 2)

    def test_duplicate_requests_cannot_fill_sampling_quota(self):
        inputs, gold = self.cases()
        duplicate = dict(inputs[0], id="duplicate")
        with self.assertRaisesRegex(ValueError, "distinct requests"):
            evaluation.select_cases(inputs + [duplicate], gold + [{"id": "duplicate", "label": 0}], per_stratum=2)

    def test_missing_usage_is_reported_as_partial_not_zero_cost(self):
        inputs, gold = self.cases()
        report = evaluation.score_records(inputs, gold, [{"id": inputs[0]["id"], "status": "failed"}])
        self.assertEqual(report["cases_with_token_metrics"], 0)
        self.assertEqual(report["recorded_tokens"], {})
        self.assertIsNone(report["mean_case_ms"])

    def test_duplicate_known_results_fail_instead_of_last_winning(self):
        inputs, gold = self.cases()
        records = [{"id": case["id"], "status": "accepted", "prediction": {"label": target["label"], "evidence": []},
                    "metrics": {"input_tokens": 10, "output_tokens": 2}, "elapsed_ms": 50}
                   for case, target in zip(inputs, gold)]
        records.append(dict(records[0]))
        records.append(dict(records[0]))
        report = evaluation.score_records(inputs, gold, records)
        self.assertEqual(report["accepted"], 26)
        self.assertEqual(report["failures"], 1)
        self.assertAlmostEqual(report["accuracy_including_failures"], 26 / 27)
        self.assertEqual(report["duplicate_output_ids"], [inputs[0]["id"]])
        self.assertEqual(report["duplicate_id_count"], 1)
        self.assertEqual(report["duplicate_record_count"], 2)
        self.assertEqual(report["errors"]["Duplicate result ID; no prediction accepted."], 1)
        self.assertEqual(report["cases_with_token_metrics"], 26)
        self.assertEqual(report["recorded_tokens"], {"input_tokens": 260, "output_tokens": 52})

    def test_unknown_results_are_explicit_and_do_not_fill_missing_cases(self):
        inputs, gold = self.cases()
        records = [{"id": "unexpected", "status": "accepted", "prediction": {"label": 0, "evidence": []},
                    "metrics": {"input_tokens": 100, "output_tokens": 20}}] * 2
        report = evaluation.score_records(inputs, gold, records)
        self.assertEqual(report["unknown_output_ids"], ["unexpected"])
        self.assertEqual(report["unknown_output_count"], 2)
        self.assertEqual(report["duplicate_id_count"], 1)
        self.assertEqual(report["accepted"], 0)
        self.assertEqual(report["failures"], 27)
        self.assertEqual(report["recorded_tokens"], {})

    def test_duplicate_input_or_gold_ids_are_rejected(self):
        inputs, gold = self.cases()
        for bad_inputs, bad_gold, message in ((inputs + [inputs[0]], gold, "Duplicate input"),
                                              (inputs, gold + [gold[0]], "Duplicate gold")):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    evaluation.select_cases(bad_inputs, bad_gold)
                with self.assertRaisesRegex(ValueError, message):
                    evaluation.score_records(bad_inputs, bad_gold, [])

    def test_conflicting_duplicate_requests_are_not_silently_sampled(self):
        inputs, gold = self.cases()
        duplicate = dict(inputs[0], id="conflict")
        with self.assertRaisesRegex(ValueError, "conflicting gold"):
            evaluation.select_cases(inputs + [duplicate], gold + [{"id": "conflict", "label": 1}])

    def test_invalid_labels_are_failures_including_boolean_and_negative(self):
        inputs, gold = self.cases()
        for label in (True, -1, 3, "0", 0.0):
            record = {"id": inputs[0]["id"], "status": "accepted", "prediction": {"label": label}}
            with self.subTest(label=label):
                report = evaluation.score_records(inputs, gold, [record])
                self.assertEqual(report["accepted"], 0)
                self.assertEqual(report["failures"], 27)

    def test_run_identity_pins_endpoint_limits_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = Path(directory) / "input.jsonl"
            inputs.write_text("{}\n")
            settings = Settings(base_url="http://127.0.0.1:8081/v1", api_key="SECRET-KEY",
                                local_model_id="claimlens-apertus-v1.5-8b-q4")
            identity = evaluation.run_identity(inputs, settings)
            self.assertEqual(identity["schema_version"], 2)
            self.assertEqual(len(identity["endpoint_sha256"]), 64)
            self.assertNotIn(settings.base_url, json.dumps(identity))
            self.assertNotIn(settings.api_key, json.dumps(identity))
            self.assertFalse(identity["model_artifact"]["runtime_verified"])
            self.assertEqual(identity["model_artifact"]["intended_revision"], "248ec68a63e219e3f061e4c946fc8a20d63b9975")
            for change in ({"base_url": "http://127.0.0.1:8082/v1"}, {"timeout": 50},
                           {"document_timeout": 100}, {"max_document_model_calls": 10}, {"context_tokens": 16384}):
                with self.subTest(change=change):
                    self.assertNotEqual(evaluation.run_identity(inputs, replace(settings, **change)), identity)
            self.assertEqual(evaluation.run_identity(inputs, replace(settings, api_key="ROTATED-KEY")), identity)

    def test_resume_refuses_old_manifest_and_invalid_record_ids_without_inference(self):
        cases, _ = self.cases()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs, output = root / "input.jsonl", root / "results.jsonl"
            evaluation.write_jsonl(inputs, cases)
            record = {"id": cases[0]["id"], "status": "failed"}
            evaluation.write_jsonl(output, [record])
            settings = Settings(base_url="http://localhost:8081/v1")
            evaluation.write_json(output.with_suffix(".run.json"), {"model": settings.model})
            with patch.object(evaluation, "check_claim") as inference:
                with self.assertRaisesRegex(ValueError, "not migrated automatically"):
                    evaluation.run_cases(inputs, output, settings, root, resume=True)
                identity = evaluation.run_identity(inputs, settings)
                evaluation.write_json(output.with_suffix(".run.json"), identity)
                for records, message in (([record, record], "Duplicate recorded result"),
                                         ([{"id": "unknown", "status": "failed"}], "unknown input IDs")):
                    evaluation.write_jsonl(output, records)
                    with self.assertRaisesRegex(ValueError, message):
                        evaluation.run_cases(inputs, output, settings, root, resume=True)
                inference.assert_not_called()


if __name__ == "__main__":
    unittest.main()
