import contextlib
from http.client import IncompleteRead
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "import_booklets", Path(__file__).parents[1] / "scripts/import_booklets.py")
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


class ImportScriptTests(unittest.TestCase):
    def run_import(self, outcomes):
        rows = [{"booklet_url": "https://www.bk.admin.ch/{}.pdf".format(index),
                 "reference_language": "de", "vote": "Proposal"}
                for index in range(len(outcomes))]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            source.write_text("".join(json.dumps(row) + "\n" for row in rows))
            manifest_path = root / "report.json"
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(importer.BookletLibrary, "import_url", side_effect=outcomes), \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = importer.main(["--jsonl", str(source), "--library", str(root / "library"),
                                      "--manifest", str(manifest_path)])
            return code, json.loads(manifest_path.read_text()), stdout.getvalue() + stderr.getvalue()

    @staticmethod
    def document():
        return {"id": "test-document", "page_count": 3, "character_count": 100, "warnings": []}

    def test_unexpected_error_aborts_without_false_completion_or_error_leak(self):
        code, manifest, output = self.run_import([
            self.document(), RuntimeError("SECRET remote response"), self.document()])
        self.assertEqual(code, 1)
        self.assertEqual(manifest["status"], "aborted")
        self.assertEqual((manifest["selected_sources"], manifest["imported"],
                          manifest["failed"], manifest["unprocessed"]), (3, 1, 0, 2))
        self.assertEqual(len(manifest["items"]), 1)
        self.assertIn("unexpected error", manifest["error"])
        self.assertNotIn("SECRET", json.dumps(manifest) + output)

    def test_keyboard_interrupt_retains_partial_progress(self):
        code, manifest, _ = self.run_import([self.document(), KeyboardInterrupt()])
        self.assertEqual(code, 130)
        self.assertEqual(manifest["status"], "interrupted")
        self.assertEqual((manifest["imported"], manifest["failed"], manifest["unprocessed"]), (1, 0, 1))

    def test_incomplete_http_response_fails_one_source_and_continues(self):
        code, manifest, output = self.run_import([
            IncompleteRead(b"SECRET remote response", 100), self.document()])
        self.assertEqual(code, 1)
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual((manifest["imported"], manifest["failed"], manifest["unprocessed"]), (1, 1, 0))
        self.assertEqual([item["status"] for item in manifest["items"]], ["failed", "imported"])
        self.assertIn("download was incomplete", manifest["items"][0]["error"])
        self.assertNotIn("SECRET", json.dumps(manifest) + output)

    def test_success_is_complete_with_no_unprocessed_sources(self):
        code, manifest, _ = self.run_import([self.document(), self.document()])
        self.assertEqual(code, 0)
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual((manifest["imported"], manifest["failed"], manifest["unprocessed"]), (2, 0, 0))


if __name__ == "__main__":
    unittest.main()
