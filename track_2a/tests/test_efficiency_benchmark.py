import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from claimlens.config import Settings

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("benchmark_efficiency", ROOT / "scripts/benchmark_efficiency.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)
sys.path.insert(0, str(ROOT / "scripts"))
import evaluate_readiness as readiness


class EfficiencyBenchmarkTests(unittest.TestCase):
    def rows(self):
        return [{"booklet_publish_date": date, "vote": "Proposal", "claim": "{} {} {} {} {}".format(date, source, claim, label, variant),
                 "claim_language": claim, "reference_language": source, "reference_string": "Original source",
                 "entailment_label": label}
                for date in ("development", "final") for targets in benchmark.STRATA.values()
                for source, claim, label in targets for variant in range(3)]

    def test_frozen_selection_covers_all_pairs_and_balances_both_cohorts(self):
        chosen = benchmark.select_rows(self.rows(), ["development"], set(), "seed", readiness)
        pairs = set()
        for cohort, targets in benchmark.STRATA.items():
            self.assertEqual([readiness.stratum(row) for _, row in chosen[cohort]], list(targets))
            self.assertTrue(all(row["booklet_publish_date"] == "development" for _, row in chosen[cohort]))
            labels = [row["entailment_label"] for _, row in chosen[cohort]]
            self.assertEqual([labels.count(label) for label in range(3)], [len(targets) // 3] * 3)
            pairs.update((a, b) for a, b, _ in targets)
        self.assertEqual(len(pairs), 9)
        reversed_rows = benchmark.select_rows(list(reversed(self.rows())), ["development"], set(), "seed", readiness)
        self.assertEqual({k: [row for _, row in v] for k, v in chosen.items()},
                         {k: [row for _, row in v] for k, v in reversed_rows.items()})

    def test_previously_exercised_requests_cannot_reenter_selection(self):
        chosen = benchmark.select_rows(self.rows(), ["development"], set(), "seed", readiness)
        forbidden = {readiness.fingerprint(readiness.request_for(row, "unused")) for group in chosen.values() for _, row in group}
        new = benchmark.select_rows(self.rows(), ["development"], forbidden, "seed", readiness)
        self.assertFalse(any(readiness.fingerprint(readiness.request_for(row, "unused")) in forbidden
                             for group in new.values() for _, row in group))
        with self.assertRaisesRegex(ValueError, "No unseen"):
            benchmark.select_rows(self.rows(), [], forbidden, "seed", readiness)

    def test_limits_bound_real_cli_work_and_preserve_smaller_budgets(self):
        settings = benchmark.bounded_settings(Settings(timeout=500, document_timeout=1000, retrieval_timeout=200,
                                                        max_document_model_calls=48, retrieval_prompt_tokens=6000))
        self.assertEqual((settings.timeout, settings.document_timeout, settings.retrieval_timeout), (120, 120, 120))
        self.assertEqual((settings.max_document_model_calls, settings.retrieval_prompt_tokens), (4, 5000))
        smaller = benchmark.bounded_settings(Settings(timeout=10, retrieval_prompt_tokens=2000, max_document_model_calls=2))
        self.assertEqual((smaller.timeout, smaller.retrieval_prompt_tokens, smaller.max_document_model_calls), (10, 2000, 2))

    def test_identity_hashes_loaded_package_and_omits_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            package = folder / "claimlens"
            package.mkdir()
            (package / "__init__.py").write_text("")
            source = package / "engine.py"
            source.write_text("FIRST = 1\n")
            inputs = folder / "inputs.jsonl"
            inputs.write_text("{}\n")
            with patch.dict(sys.modules, {"claimlens": SimpleNamespace(__file__=str(package / "__init__.py"))}):
                before = benchmark.run_identity(inputs, Settings(api_key="secret-value", base_url="http://private.invalid"), readiness)
                traced = benchmark.run_identity(inputs, Settings(api_key="secret-value", base_url="http://private.invalid"), readiness,
                                                trace_prompts=True)
                source.write_text("SECOND = 2\n")
                after = benchmark.run_identity(inputs, Settings(api_key="secret-value", base_url="http://private.invalid"), readiness)
            self.assertNotEqual(before["source_sha256"], after["source_sha256"])
            self.assertEqual(before["source_package"], str(package.resolve()))
            self.assertNotIn("secret-value", json.dumps(before))
            self.assertNotIn("private.invalid", json.dumps(before))
            self.assertNotEqual(before["diagnostics_sha256"], traced["diagnostics_sha256"])
            self.assertFalse(before["diagnostics"]["trace_prompts"])
            self.assertTrue(traced["diagnostics"]["trace_prompts"])

    def test_transport_profiler_keeps_results_and_restores_aliases_on_failure(self):
        calls = []
        def transport(data, settings, passages):
            calls.append(data)
            if data.get("fail"):
                raise ValueError("bad response")
            return {"relation": "supported"}, {"input_tokens": 20, "output_tokens": 3}
        modules = {"claimlens." + name: SimpleNamespace(request_json=transport) for name in ("llm", "fast", "context")}
        stages = []
        with patch.object(benchmark.importlib, "import_module", side_effect=modules.__getitem__):
            with self.assertRaisesRegex(ValueError, "bad response"):
                with benchmark.profile_requests(stages):
                    result, usage = modules["claimlens.fast"].request_json({"max_tokens": 100}, None, [])
                    self.assertEqual(result, {"relation": "supported"})
                    self.assertEqual(usage["input_tokens"], 20)
                    modules["claimlens.context"].request_json({"fail": True}, None, [{"text": "Source"}])
        self.assertTrue(all(module.request_json is transport for module in modules.values()))
        self.assertEqual([stage["stage"] for stage in stages], ["query_expansion", "assessment"])
        self.assertEqual([stage["status"] for stage in stages], ["accepted", "failed"])
        self.assertEqual(stages[1]["metrics"], {})

    def test_opt_in_traces_preserve_exact_public_prompts_and_query_without_transport_secrets(self):
        response = {"claim_queries": {"de": "genaue Frage", "fr": "question exacte", "it": "domanda esatta"}}
        messages = [{"role": "system", "content": "System instructions\nverbatim"},
                    {"role": "user", "content": "Source €\nClaim", "headers": "private-header"}]
        passages = [{"id": "page-1", "text": "Exact source\npassage", "page": 1, "gold_label": "private-gold"}]
        settings = Settings(api_key="private-api-key", base_url="http://private-endpoint.invalid")
        def transport(data, received_settings, received_passages):
            self.assertIs(received_settings, settings)
            self.assertIs(received_passages, passages)
            self.assertIs(data["messages"], messages)
            return response, {"input_tokens": 20, "output_tokens": 3}
        modules = {"claimlens." + name: SimpleNamespace(request_json=transport) for name in ("llm", "fast", "context")}
        stages, traces = [], []
        with patch.object(benchmark.importlib, "import_module", side_effect=modules.__getitem__):
            with benchmark.profile_requests(stages, traces):
                returned, _ = modules["claimlens.fast"].request_json(
                    {"messages": messages, "headers": "private-top-header", "api_key": settings.api_key,
                     "url": settings.base_url}, settings, passages)
                returned["claim_queries"]["de"] = "Changed after transport"
                messages[1]["content"] = "Changed after transport"
                passages[0]["text"] = "Changed after transport"
        self.assertEqual(traces[0]["messages"][1], {"role": "user", "content": "Source €\nClaim"})
        self.assertEqual(traces[0]["source_passages"], [{"id": "page-1", "text": "Exact source\npassage", "page": 1}])
        self.assertEqual(traces[0]["response"]["claim_queries"]["de"], "genaue Frage")
        self.assertNotIn("private-", json.dumps(traces))
        self.assertNotIn("messages", stages[0])

    def test_trace_keeps_failed_request_prompt_without_exception_body(self):
        def transport(data, settings, passages):
            raise ValueError("private-provider-body")
        modules = {"claimlens." + name: SimpleNamespace(request_json=transport) for name in ("llm", "fast", "context")}
        traces = []
        with patch.object(benchmark.importlib, "import_module", side_effect=modules.__getitem__):
            with self.assertRaises(ValueError), benchmark.profile_requests([], traces):
                modules["claimlens.llm"].request_json({"messages": [{"role": "user", "content": "Public source"}]}, None, [])
        self.assertEqual(traces[0]["status"], "failed")
        self.assertIsNone(traces[0]["response"])
        self.assertNotIn("private-provider-body", json.dumps(traces))

    def test_confirmation_cannot_run_before_candidate_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(directory=Path(directory), cohort="confirmation", variant="baseline")
            with self.assertRaisesRegex(ValueError, "Lock a candidate"):
                benchmark.confirm_locked(args, Settings(), readiness)

    def test_variant_name_cannot_escape_experiment_directory(self):
        for name in ("../outside", "nested/name", "", "/tmp/results", "x" * 65):
            with self.assertRaisesRegex(ValueError, "simple variant"):
                benchmark.variant_path(SimpleNamespace(directory=Path("root"), variant=name, cohort="tuning"))

    def test_run_does_not_need_or_copy_gold(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frozen = root / "frozen/tuning"
            (frozen / "input").mkdir(parents=True)
            case = {"id": "case", "claim": {"text": "Claim", "language": "de"},
                    "reference": {"text": "Source", "language": "de"}}
            readiness.write_jsonl(frozen / "input/cases.jsonl", [case])
            selection = {"sources": [{"id": "case"}], "input_sha256": readiness.sha256(frozen / "input/cases.jsonl")}
            readiness.write_json(frozen / "selection.json", selection)
            args = SimpleNamespace(directory=root, cohort="tuning", variant="test", resume=False, trace_prompts=True)
            result = ({"id": "case", "label": 1}, {"metrics": {"input_tokens": 10, "output_tokens": 1}})
            with patch.object(benchmark, "validate_cohort", return_value=([case], selection)), \
                    patch("claimlens.cli.predict_case", return_value=result):
                records = benchmark.run(args, Settings(), readiness)
            self.assertEqual(records[0]["status"], "accepted")
            self.assertFalse((root / "runs/test/tuning/gold").exists())
            self.assertFalse((frozen / "gold").exists())
            diagnostics = root / "runs/test/tuning" / records[0]["diagnostic_trace"]["path"]
            self.assertEqual(json.loads(diagnostics.read_text()), {"id": "case", "schema_version": 1, "stages": []})
            args.resume = True
            with patch.object(benchmark, "validate_cohort", return_value=([case], selection)), \
                    patch("claimlens.cli.predict_case", side_effect=AssertionError("Already completed")):
                self.assertEqual(benchmark.run(args, Settings(), readiness), records)
                args.trace_prompts = False
                with self.assertRaisesRegex(ValueError, "identity changed"):
                    benchmark.run(args, Settings(), readiness)
                args.trace_prompts = True
                diagnostics.write_text("{}")
                with self.assertRaisesRegex(ValueError, "diagnostic trace is missing or changed"):
                    benchmark.run(args, Settings(), readiness)

    def test_diagnostic_path_does_not_accept_request_id_as_path(self):
        root = Path("root/runs/test/tuning")
        path = benchmark.trace_path(root, "../../secret")
        self.assertEqual(path.parent, root / "diagnostics")
        self.assertRegex(path.name, r"^[0-9a-f]{64}\.json$")


if __name__ == "__main__":
    unittest.main()
