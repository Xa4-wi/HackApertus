"""Dataset export tests use in-memory rows and require no Hugging Face packages."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_dataset.py"
SPEC = importlib.util.spec_from_file_location("prepare_dataset", SCRIPT)
preparation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preparation)


def row(claim_language="de", reference_language="fr", label=0):
    return {"vote": "A synthetic vote", "claim": "Claim text", "claim_language": claim_language,
            "reference_string": "Reference text", "reference_language": reference_language,
            "entailment_label": label, "baseline_score": 0.99,
            "booklet_url": "https://example.test/booklet.pdf"}


class DatasetPreparationTests(unittest.TestCase):
    def test_inputs_are_whitelisted_and_supervision_is_separate(self):
        request, gold = preparation.convert_row(row(), "case-1")
        self.assertEqual(set(request), {"id", "vote", "claim", "reference"})
        self.assertEqual(set(request["claim"]), {"text", "language"})
        self.assertEqual(set(request["reference"]), {"text", "language"})
        self.assertEqual(gold, {"id": "case-1", "label": 0, "label_name": "entailment"})
        self.assertNotIn("baseline_score", json.dumps(request))
        self.assertNotIn("entailment_label", json.dumps(request))
        self.assertNotIn("booklet_url", request)

    def test_invalid_labels_languages_or_empty_fields_fail(self):
        for field, value in (("entailment_label", True), ("entailment_label", 3),
                             ("claim_language", "en"), ("reference_language", None),
                             ("reference_string", " "), ("claim", None)):
            sample = row()
            sample[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                preparation.convert_row(sample, "case-1")

    def test_all_language_pairs_and_label_balance_are_recorded(self):
        rows = [row(claim_language, reference_language, index % 3)
                for index, (claim_language, reference_language) in enumerate(
                    (c, r) for c in ("de", "fr", "it") for r in ("de", "fr", "it"))]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            stats = preparation.write_split(rows, "train", output)
            requests = [json.loads(line) for line in (output / stats["input_path"]).read_text().splitlines()]
            gold = [json.loads(line) for line in (output / stats["gold_path"]).read_text().splitlines()]
            self.assertEqual(stats["input_sha256"], preparation.sha256_file(output / stats["input_path"]))
        self.assertEqual(stats["rows"], 9)
        self.assertEqual(stats["labels"], {"contradiction": 3, "entailment": 3, "neutral": 3})
        self.assertEqual(len(stats["language_pairs"]), 9)
        self.assertTrue(all(count == 1 for count in stats["language_pairs"].values()))
        self.assertEqual([request["id"] for request in requests], [expected["id"] for expected in gold])
        self.assertEqual(stats["input_path"], "input/reference-train.jsonl")
        self.assertEqual(stats["gold_path"], "gold/reference-train.gold.jsonl")

    def test_duplicate_requests_are_reported_and_not_silently_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            stats = preparation.write_split([row(), row()], "train", Path(directory))
        self.assertEqual(stats["rows"], 2)
        self.assertEqual(stats["duplicate_request_rows"], 1)
        self.assertEqual(stats["conflicting_duplicate_requests"], 0)

    def test_conflicting_duplicate_labels_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            stats = preparation.write_split([row(label=0), row(label=2)], "train", Path(directory))
        self.assertEqual(stats["conflicting_duplicate_requests"], 1)

    def test_split_names_cannot_escape_export_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                preparation.write_split([row()], "../outside", Path(directory))


if __name__ == "__main__":
    unittest.main()
