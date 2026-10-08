"""Offline OCR boundary tests; no external programs or model downloads."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from claimlens.ocr import ocr_pages


class OCRTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.pdf = Path(self.temporary.name) / "private-document.pdf"
        self.pdf.write_bytes(b"mock PDF")
        self.calls = []
        self.languages = "deu\nfra\nita\n"
        self.text = b"Recognized source text"

    def process(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if "--list-langs" in command:
            kwargs["stdout"].write(self.languages.encode())
        elif command[0] == "tesseract":
            Path(command[2] + ".txt").write_bytes(self.text)
        return subprocess.CompletedProcess(command, 0)

    def invoke(self, pages, language="de", **kwargs):
        with patch("claimlens.ocr.shutil.which", side_effect=lambda name: name), \
                patch("claimlens.ocr.subprocess.run", side_effect=self.process):
            return ocr_pages(self.pdf, pages, language, **kwargs)

    def test_missing_tools_and_language_are_safe(self):
        with patch("claimlens.ocr.shutil.which", return_value=None), \
                patch("claimlens.ocr.subprocess.run") as run:
            text, warnings = ocr_pages(self.pdf, [3], "de")
        self.assertEqual(text, {})
        self.assertIn("unavailable", " ".join(warnings))
        run.assert_not_called()
        self.languages = "eng\n"
        text, warnings = self.invoke([3])
        self.assertEqual(text, {})
        self.assertIn("language data", " ".join(warnings))
        self.assertEqual(len(self.calls), 1)

    def test_preserves_numbering_language_bounds_and_cleanup(self):
        text, warnings = self.invoke([7, 3, 7], "fr")
        self.assertEqual(text, {7: self.text.decode(), 3: self.text.decode()})
        self.assertIn("approximate", " ".join(warnings))
        renders = [command for command, _ in self.calls if command[0] == "pdftoppm"]
        self.assertEqual([command[2] for command in renders], ["7", "3"])
        for command, kwargs in self.calls:
            self.assertLessEqual(kwargs["timeout"], 30)
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
            self.assertNotIn("shell", kwargs)
            if command[0] == "tesseract" and "--list-langs" not in command:
                self.assertEqual(command[-3:], ["-l", "fra", "txt"])
        self.assertEqual(renders[0][renders[0].index("-scale-to") + 1], "2000")
        self.assertFalse(Path(renders[0][-1]).parent.exists())

    def test_unspecified_language_recognizes_all_three_in_one_pass(self):
        text, warnings = self.invoke([7], "auto")
        self.assertEqual(text, {7: self.text.decode()})
        recognition = [command for command, _ in self.calls
                       if command[0] == "tesseract" and "--list-langs" not in command]
        self.assertEqual(len(recognition), 1)
        self.assertEqual(recognition[0][-3:], ["-l", "deu+fra+ita", "txt"])
        self.assertIn("approximate", " ".join(warnings))

    def test_unspecified_language_requires_complete_language_data(self):
        self.languages = "deu\nita\n"
        text, warnings = self.invoke([7], "auto")
        self.assertEqual(text, {})
        self.assertIn("unavailable: fra", " ".join(warnings))
        self.assertEqual(len(self.calls), 1)

    def test_unspecified_language_uses_complete_project_language_data(self):
        tessdata = Path(self.temporary.name) / "tessdata"
        tessdata.mkdir()
        for code in ("deu", "fra", "ita"):
            (tessdata / (code + ".traineddata")).write_bytes(b"fixture")
        environment = {key: value for key, value in os.environ.items() if key != "TESSDATA_PREFIX"}
        with patch("claimlens.ocr.LOCAL_TESSDATA", tessdata), patch.dict(os.environ, environment, clear=True):
            self.invoke([7], "auto")
        tesseract_calls = [command for command, _ in self.calls if command[0] == "tesseract"]
        self.assertTrue(all("--tessdata-dir" in command and str(tessdata) in command for command in tesseract_calls))

    def test_hard_page_limit_and_invalid_numbers(self):
        text, warnings = self.invoke([0, True, "1"] + list(range(1, 30)), max_pages=50)
        self.assertEqual(list(text), list(range(1, 21)))
        self.assertIn("page limit", " ".join(warnings))
        self.assertIn("invalid", " ".join(warnings))

    def test_shared_deadline_prevents_rendering(self):
        with patch("claimlens.ocr.time.monotonic", side_effect=[0, 0, 181]):
            text, warnings = self.invoke([2], timeout_seconds=1000)
        self.assertEqual(text, {})
        self.assertIn("time limit", " ".join(warnings))
        self.assertEqual(len(self.calls), 1)

    def test_process_failures_hide_paths_and_continue(self):
        original = self.process

        def fail_page(command, **kwargs):
            if command[0] == "pdftoppm" and command[2] == "2":
                raise subprocess.CalledProcessError(1, command, stderr="SECRET /private/path")
            return original(command, **kwargs)

        self.process = fail_page
        text, warnings = self.invoke([2, 4])
        self.assertEqual(list(text), [4])
        self.assertIn("page 2", " ".join(warnings))
        self.assertNotIn("SECRET", " ".join(warnings))
        self.assertNotIn(str(self.pdf), " ".join(warnings))

    def test_text_output_is_bounded(self):
        self.text = b"x" * 2_000_001
        text, warnings = self.invoke([2, 3])
        self.assertEqual(len(text[2]), 2_000_000)
        self.assertNotIn(3, text)
        self.assertIn("2 MB", " ".join(warnings))

    def test_project_language_data_and_explicit_environment_precedence(self):
        tessdata = Path(self.temporary.name) / "tessdata"
        tessdata.mkdir()
        (tessdata / "deu.traineddata").write_bytes(b"fixture")
        environment = {key: value for key, value in os.environ.items() if key != "TESSDATA_PREFIX"}
        with patch("claimlens.ocr.LOCAL_TESSDATA", tessdata), patch.dict(os.environ, environment, clear=True):
            self.invoke([1])
        tesseract_calls = [command for command, _ in self.calls if command[0] == "tesseract"]
        self.assertTrue(all("--tessdata-dir" in command and str(tessdata) in command for command in tesseract_calls))
        self.calls = []
        with patch("claimlens.ocr.LOCAL_TESSDATA", tessdata), patch.dict(os.environ, {"TESSDATA_PREFIX": "/configured/data"}):
            self.invoke([1])
        self.assertTrue(all("--tessdata-dir" not in command for command, _ in self.calls))


if __name__ == "__main__":
    unittest.main()
