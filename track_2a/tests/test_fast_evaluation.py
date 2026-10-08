import importlib.util
import json
from dataclasses import replace
from pathlib import Path
import tempfile
from types import SimpleNamespace
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

    def test_prepare_requires_preserved_history_before_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(directory=root / "new-run", previous=root / "absent-archive",
                                   prior_inputs=root / "absent-input.jsonl")
            with self.assertRaisesRegex(ValueError, "Restore the local evaluation archive"):
                evaluation.prepare(args)
            self.assertFalse(args.directory.exists())

    def test_prepare_records_external_archive_provenance_without_changing_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(directory=root / "new-run", dataset=root / "dataset",
                library=root / "library", previous=root / "archive/readiness",
                prior_inputs=root / "archive/reference/input.jsonl", seed="fixed")
            args.dataset.mkdir()
            (args.previous / "development/input").mkdir(parents=True)
            (args.previous / "official").mkdir()
            args.prior_inputs.parent.mkdir(parents=True)
            args.prior_inputs.write_text("")
            previous_input = args.previous / "development/input/cases.jsonl"
            previous_input.write_text("")
            evaluation.readiness.write_json(args.dataset / "manifest.json",
                {"dataset": "test-dataset", "revision": evaluation.readiness.DATASET_REVISION})
            evaluation.readiness.write_json(args.previous / "split.json",
                {"development_dates": ["development"], "final_dates": ["final"]})
            evaluator = args.previous / "official/evaluate.py"
            evaluator.write_text("# preserved scorer\n")
            evaluation.readiness.write_json(evaluator.parent / "source.json",
                {"sha256": evaluation.readiness.sha256(evaluator)})
            rows, library = [], {}
            for index, (source, claim, label) in enumerate(evaluation.STRATA):
                row = {"booklet_publish_date": "development", "vote": "A proposal",
                    "claim": "Claim " + str(index), "claim_language": claim,
                    "reference_language": source, "reference_string": "A passage",
                    "entailment_label": label, "booklet_url": "https://example.invalid/" + source}
                pdf = root / (source + ".pdf")
                pdf.write_bytes(b"PDF fixture copied without parsing")
                library[(row["booklet_url"], source)] = (pdf, {"id": source, "page_count": 1})
                rows.append(row)
            archive_before = {path: path.read_bytes() for path in (root / "archive").rglob("*") if path.is_file()}
            with patch.dict("sys.modules", {"datasets": SimpleNamespace(load_from_disk=lambda _: {"train": rows})}), \
                    patch.object(evaluation.readiness, "library_index", return_value=library):
                evaluation.prepare(args)
            selection = json.loads((args.directory / "selection.json").read_text())
            self.assertEqual(selection["cases"], 3)
            self.assertEqual(selection["prior_input_path_base"], "track_2a")
            recorded = {(evaluation.ROOT / path).resolve(): digest
                        for path, digest in selection["prior_input_sha256"].items()}
            self.assertEqual(recorded, {path.resolve(): evaluation.readiness.sha256(path)
                                       for path in (args.prior_inputs, previous_input)})
            self.assertEqual(archive_before, {path: path.read_bytes() for path in archive_before})


if __name__ == "__main__":
    unittest.main()
