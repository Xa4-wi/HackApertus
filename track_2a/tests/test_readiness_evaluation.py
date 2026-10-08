import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from claimlens.config import Settings
from claimlens.models import ValidationError

spec = importlib.util.spec_from_file_location("evaluate_readiness", Path(__file__).parents[1] / "scripts/evaluate_readiness.py")
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


class ReadinessEvaluationTests(unittest.TestCase):
    def rows(self):
        rows = []
        for date in ("seen", "smoke", "unseen"):
            for source in evaluation.LANGUAGES:
                for claim in evaluation.LANGUAGES:
                    for label in range(3):
                        for variant in range(4):
                            rows.append({"vote": "Translated proposal " + source,
                                "claim": "{} {} {} {} {}".format(date, source, claim, label, variant),
                                "claim_language": claim, "reference_language": source,
                                "reference_string": "Source " + source,
                                "entailment_label": label, "booklet_publish_date": date})
        return rows

    def test_date_split_excludes_all_translations_and_prior_smoke(self):
        rows = self.rows()
        old = evaluation.request_for(rows[0], "old")
        cohorts, excluded = evaluation.split_rows(rows, [old], "fixed", smoke_dates=("smoke",))
        self.assertEqual(excluded, ["seen", "smoke"])
        self.assertEqual({key: len(value) for key, value in cohorts.items()},
                         {"development": 27, "final-b": 27, "final-b-extension": 27, "final-a": 9})
        for name, chosen in cohorts.items():
            dates = {row["booklet_publish_date"] for _, row in chosen}
            self.assertTrue(dates <= ({"seen", "smoke"} if name == "development" else {"unseen"}))
        b_claims = {evaluation.claim_key(row) for name in ("final-b", "final-b-extension") for _, row in cohorts[name]}
        a_claims = {evaluation.claim_key(row) for _, row in cohorts["final-a"]}
        self.assertFalse(a_claims & b_claims)
        self.assertEqual(len({evaluation.stratum(row)[:2] for _, row in cohorts["final-a"]}), 9)
        self.assertEqual(sorted(row["entailment_label"] for _, row in cohorts["final-a"]), [0] * 3 + [1] * 3 + [2] * 3)

    def test_selection_is_independent_of_row_order_and_rejects_unknown_prior(self):
        rows = self.rows()
        old = evaluation.request_for(rows[0], "old")
        first, _ = evaluation.split_rows(rows, [old], "fixed", smoke_dates=())
        second, _ = evaluation.split_rows(list(reversed(rows)), [old], "fixed", smoke_dates=())
        self.assertEqual({key: [row for _, row in selected] for key, selected in first.items()},
                         {key: [row for _, row in selected] for key, selected in second.items()})
        old["claim"]["text"] = "Never present in this dataset"
        with self.assertRaisesRegex(ValueError, "do not match"):
            evaluation.split_rows(rows, [old], "fixed")

    def test_duplicate_requests_do_not_pad_strata_or_hide_conflicting_labels(self):
        row = self.rows()[0]
        self.assertEqual(len(evaluation.ranked_rows([row, dict(row)], "fixed")), 1)
        with self.assertRaisesRegex(ValueError, "conflicting"):
            evaluation.ranked_rows([row, dict(row, entailment_label=1)], "fixed")
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            evaluation.select_stratified([(0, row)], per_stratum=2)

    def test_missing_and_failed_cases_count_without_inventing_token_usage(self):
        cases = [{"id": str(index)} for index in range(3)]
        records = [{"id": "0", "status": "accepted", "elapsed_ms": 200,
                    "metrics": {"input_tokens": 12, "output_tokens": 3}},
                   {"id": "1", "status": "failed", "elapsed_ms": 700,
                    "metrics": {"input_tokens": None, "output_tokens": None}}]
        result = evaluation.timing_summary(cases, records)
        self.assertEqual(result["failed_or_missing_cases"], 2)
        self.assertEqual(result["total_recorded_tokens"], {"input_tokens": 12, "output_tokens": 3})
        self.assertEqual(result["cases_with_complete_token_metrics"], 1)
        self.assertEqual(result["mean_case_ms"], 450)
        self.assertEqual(result["p95_case_ms"], 700)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            evaluation.timing_summary(cases, records + [records[0]])
        with self.assertRaisesRegex(ValueError, "unknown"):
            evaluation.timing_summary(cases, [{"id": "unknown"}])

    def frozen_folder(self, root):
        folder = root / "final-b"
        (folder / "input").mkdir(parents=True)
        cases = [evaluation.request_for(row, str(index)) for index, row in enumerate(self.rows()[:2])]
        evaluation.write_jsonl(folder / "input/cases.jsonl", cases)
        evaluation.write_json(folder / "selection.json", {"input_sha256": evaluation.sha256(folder / "input/cases.jsonl"),
            "sources": [{"id": case["id"]} for case in cases]})
        return folder, cases

    def test_runner_uses_shared_cli_pipeline_and_does_not_need_gold(self):
        with tempfile.TemporaryDirectory() as directory:
            folder, cases = self.frozen_folder(Path(directory))
            prediction = {"id": cases[1]["id"], "label": 1, "label_name": "neutral", "evidence": [],
                          "metrics": {"input_tokens": 12, "output_tokens": 3, "inference_time_ms": 10}}
            failure = ValidationError("Provider failed")
            failure.metrics = {"input_tokens": None, "output_tokens": None}
            failure.attempts = 2
            with patch("claimlens.cli.predict_case", side_effect=[failure, (prediction, {"metrics": prediction["metrics"]})]) as inference:
                records = evaluation.run(folder, Settings(base_url="http://localhost:8081/v1"))
            self.assertEqual(inference.call_count, 2)
            self.assertEqual([row["status"] for row in records], ["failed", "accepted"])
            self.assertEqual(evaluation.read_jsonl(folder / "predictions.jsonl"), [prediction])
            self.assertFalse((folder / "gold").exists())
            with patch("claimlens.cli.predict_case") as inference:
                evaluation.run(folder, Settings(base_url="http://localhost:8081/v1"), resume=True)
                inference.assert_not_called()

    def test_frozen_inputs_and_run_identity_cannot_silently_change(self):
        with tempfile.TemporaryDirectory() as directory:
            folder, cases = self.frozen_folder(Path(directory))
            (folder / "input/cases.jsonl").write_text("{}\n")
            with self.assertRaisesRegex(ValueError, "Frozen input"):
                evaluation.validate_frozen_inputs(folder)


if __name__ == "__main__":
    unittest.main()
