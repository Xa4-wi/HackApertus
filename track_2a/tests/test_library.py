"""Security, cache integrity, and physical-page provenance for the PDF library."""

import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request

from claimlens.library import BookletLibrary, OfficialRedirects, _download_pdf, official_url
from claimlens.booklets import prepare_case
from claimlens.models import ValidationError
from test_submission import write_text_pdf


URL = "https://www.bk.admin.ch/dam/de/booklet.pdf"
TEXT = "The original parliamentary proposal takes effect on the first day of 2028."


class Response(io.BytesIO):
    def __init__(self, content, final_url=URL, headers=None):
        super().__init__(content)
        self.final_url = final_url
        self.headers = headers or {}

    def geturl(self):
        return self.final_url


class URLTests(unittest.TestCase):
    def test_exact_https_hosts_only_and_no_credentials(self):
        for value in ("http://www.bk.admin.ch/a.pdf", "https://www.bk.admin.ch.evil.example/a.pdf",
                      "https://evil.example/a.pdf", "https://www.bk.admin.ch@evil.example/a.pdf",
                      "https://x:secret@www.bk.admin.ch/a.pdf", "https://www.bk.admin.ch:8080/a.pdf",
                      "file:///tmp/booklet.pdf", "https://www.bk.admin.ch/\na.pdf", "https://[invalid"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                official_url(value)
        self.assertEqual(official_url(URL + "?download=1#page=2"), URL + "?download=1")

    def test_external_redirect_is_rejected_before_following(self):
        with self.assertRaises(ValidationError):
            OfficialRedirects().redirect_request(Request(URL), None, 302, "Found", {}, "https://elsewhere.example/a.pdf")

    def test_response_size_signature_and_final_host_are_checked(self):
        for body, final, headers in ((b"not PDF", URL, {}),
                                     (b"%PDF-test", "https://evil.example/a.pdf", {}),
                                     (b"%PDF-test", URL, {"Content-Length": "25000001"})):
            with patch("claimlens.library.build_opener") as opener:
                opener.return_value.open.return_value = Response(body, final, headers)
                with self.assertRaises(ValidationError):
                    _download_pdf(URL)
        with patch("claimlens.library.MAX_PDF_BYTES", 8), patch("claimlens.library.build_opener") as opener:
            opener.return_value.open.return_value = Response(b"%PDF-too-large-with-no-length")
            with self.assertRaises(ValidationError):
                _download_pdf(URL)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.library = BookletLibrary(self.root / "library")
        self.pdf = self.root / "input.pdf"
        write_text_pdf(self.pdf, ["", TEXT])
        self.content = self.pdf.read_bytes()
        self.ocr = patch("claimlens.booklets.ocr_pages", return_value=({}, ["OCR unavailable."]))
        self.ocr.start()

    def tearDown(self):
        self.ocr.stop()
        self.temporary.cleanup()

    def test_list_missing_library_does_not_write(self):
        self.assertEqual(self.library.list_documents(), [])
        self.assertFalse(self.library.root.exists())

    def test_dedup_votes_language_and_original_page_provenance(self):
        first = self.library.import_pdf(self.content, "de", title="Official booklet", vote="First vote")
        second = self.library.import_pdf(self.content, "de", vote="Second vote")
        other_language = self.library.import_pdf(self.content, "fr")
        self.assertEqual(first["id"], second["id"])
        self.assertNotEqual(first["id"], other_language["id"])
        self.assertEqual(second["votes"], ["First vote", "Second vote"])
        self.assertEqual(second["page_count"], 2)
        self.assertNotIn("passages", second)
        self.assertNotIn("entailment_label", json.dumps(second))
        proposal = self.library.get_proposal(first["id"], vote="Second vote")
        self.assertEqual(proposal["vote"], "Second vote")
        self.assertEqual([p["page"] for p in proposal["passages"]], [2])
        self.assertEqual(proposal["passages"][0]["text"], TEXT)
        self.assertEqual(proposal["passages"][0]["url"], first["pdf_url"] + "#page=2")
        self.assertEqual(proposal["examples"], [])
        self.assertFalse(proposal["is_fixture"])
        self.assertTrue(proposal["warnings"])
        self.assertEqual(self.library.pdf_path(first["id"]).read_bytes(), self.content)

    def test_url_cache_resumes_without_network_or_extraction(self):
        with patch("claimlens.library._download_pdf", return_value=(self.content, URL)) as download:
            first = self.library.import_url(URL, "de", vote="One")
            with patch("claimlens.library._extract", side_effect=AssertionError("must reuse cache")):
                second = self.library.import_url(URL, "de", vote="Two")
        self.assertEqual(download.call_count, 1)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["source_url"], URL)
        self.assertEqual(second["votes"], ["One", "Two"])

    def test_failed_extraction_does_not_publish_partial_document(self):
        with patch("claimlens.library._extract", side_effect=ValidationError("Invalid PDF")):
            with self.assertRaises(ValidationError):
                self.library.import_pdf(self.content, "de")
        self.assertEqual(self.library.list_documents(), [])
        self.assertEqual(list(self.library.root.iterdir()), [])

    def test_path_traversal_and_symlinked_pdf_are_rejected(self):
        for identifier in ("../input.pdf", "/etc/passwd", "booklet-de-" + "a" * 64 + "/../x"):
            with self.assertRaises(ValidationError):
                self.library.pdf_path(identifier)
        document = self.library.import_pdf(self.content, "de")
        pdf = self.library.pdf_path(document["id"])
        pdf.unlink()
        pdf.symlink_to(self.pdf)
        with self.assertRaises(ValidationError):
            self.library.pdf_path(document["id"])

    def test_refresh_ocr_preserves_original_page_numbers_and_detects_pdf_changes(self):
        document = self.library.import_pdf(self.content, "de")
        with patch("claimlens.booklets.ocr_pages", return_value=({1: TEXT}, ["OCR text is approximate."])):
            refreshed = self.library.refresh_extraction(document["id"])
        self.assertEqual(refreshed["ocr_pages"], [1])
        proposal = self.library.get_proposal(document["id"])
        self.assertEqual([p["page"] for p in proposal["passages"]], [1, 2])
        self.assertEqual(proposal["passages"][0]["extraction"], "ocr")
        self.library.pdf_path(document["id"]).write_bytes(self.content + b"changed")
        with self.assertRaises(ValidationError):
            self.library.refresh_extraction(document["id"])

    def test_configured_library_environment(self):
        with patch.dict("os.environ", {"CLAIMLENS_LIBRARY": str(self.root / "configured")}):
            self.assertEqual(BookletLibrary().root, (self.root / "configured").resolve())

    def test_official_cli_keeps_coverage_warnings_when_reusing_pdf_cache(self):
        case = {"id": "scan-case", "vote": "The proposal", "booklet": {"path": "input.pdf", "language": "de"},
                "claim": {"text": "The law begins in 2028.", "language": "de"}}
        cache = {}
        first, _, _ = prepare_case(case, self.root, cache)
        second, _, _ = prepare_case(case, self.root, cache)
        self.assertEqual(first["page_count"], 2)
        self.assertEqual(first["incomplete_pages"], [1])
        self.assertEqual(first["warnings"], second["warnings"])
        self.assertIn("OCR unavailable", " ".join(second["warnings"]))


class ImporterTests(unittest.TestCase):
    def test_source_collection_uses_only_public_provenance_not_labels(self):
        script = Path(__file__).resolve().parents[1] / "scripts/import_booklets.py"
        spec = importlib.util.spec_from_file_location("import_booklets", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = [{"booklet_url": URL, "reference_language": "de", "vote": "A", "entailment_label": 2,
                 "claim": "This must not be copied", "reference_string": "Nor this"},
                {"booklet_url": URL, "reference_language": "de", "vote": "B", "entailment_label": 0}]
        sources, failures = module.collect_sources(rows)
        self.assertEqual(failures, [])
        self.assertEqual(sources, [{"url": URL, "language": "de", "votes": ["A", "B"]}])


if __name__ == "__main__":
    unittest.main()
