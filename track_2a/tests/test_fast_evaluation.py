import importlib.util
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from claimlens.config import Settings

spec = importlib.util.spec_from_file_location("evaluate_fast", Path(__file__).parents[1] / "scripts/evaluate_fast.py")
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


class FastEvaluationTests(unittest.TestCase):
    def rows(self):
        return [{"booklet_publish_date": date, "vote": "A proposal", "claim": "{} {} {}".format(date, label, variant),
                 "claim_language": claim, "reference_language": source, "reference_string": "A passage",
                 "entailment_label": label}
                for date in ("development", "final") for source, claim, label in evaluation.STRATA for variant in range(3)]

    def test_frozen_choices_use_development_only_and_exclude_old_requests(self):
        rows = self.rows()
        forbidden = {evaluation.readiness.fingerprint(evaluation.readiness.request_for(rows[0], "unused"))}
        chosen = evaluation.select_development_rows(rows, ["development"], forbidden, "fixed")
        self.assertEqual(len(chosen), 3)
        self.assertEqual([evaluation.readiness.stratum(row) for _, row in chosen], list(evaluation.STRATA))
        self.assertTrue(all(row["booklet_publish_date"] == "development" for _, row in chosen))
        self.assertFalse(any(evaluation.readiness.fingerprint(evaluation.readiness.request_for(row, "unused")) in forbidden for _, row in chosen))
        reversed_chosen = evaluation.select_development_rows(list(reversed(rows)), ["development"], forbidden, "fixed")
        self.assertEqual([row for _, row in chosen], [row for _, row in reversed_chosen])

    def test_runtime_caps_are_enforced_without_relaxing_lower_limits(self):
        configured = Settings(timeout=300, document_timeout=1800, document_strategy="exhaustive",
                              retrieval_timeout=200, retrieval_prompt_tokens=7000)
        bounded = evaluation.bounded_settings(configured)
        self.assertEqual((bounded.document_timeout, bounded.timeout, bounded.retrieval_timeout), (120, 120, 120))
        self.assertEqual(bounded.document_strategy, "retrieval")
        self.assertEqual(bounded.retrieval_prompt_tokens, 5000)
        lower = evaluation.bounded_settings(replace(configured, timeout=20, document_timeout=40,
                                                   retrieval_timeout=30, retrieval_prompt_tokens=3000))
        self.assertEqual((lower.timeout, lower.document_timeout, lower.retrieval_timeout), (20, 40, 30))
        self.assertEqual(lower.retrieval_prompt_tokens, 3000)

    def test_runner_refuses_broad_cohort_or_final_dates(self):
        selection = {"cohort": "development-latency", "development_dates_allowed": ["development"],
                     "final_dates_excluded": ["final"], "sources": [{"ballot_date": "development"}] * 3}
        with patch.object(evaluation.readiness, "validate_frozen_inputs", return_value=([{}] * 9, selection)):
            with self.assertRaisesRegex(ValueError, "three-case"):
                evaluation.validate_small_cohort(Path("unused"))
        selection["sources"] = [{"ballot_date": "final"}] * 3
        with patch.object(evaluation.readiness, "validate_frozen_inputs", return_value=([{}] * 3, selection)):
            with self.assertRaisesRegex(ValueError, "development dates"):
                evaluation.validate_small_cohort(Path("unused"))


if __name__ == "__main__":
    unittest.main()
