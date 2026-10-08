import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from claimlens.config import Settings
from claimlens.models import ValidationError
from claimlens.runtime import model_status
from claimlens.server import create_server


class LibraryHTTPTests(unittest.TestCase):
    def setUp(self):
        self.library = Mock()
        self.library.list_documents.return_value = [{"id": "booklet-test", "title": "Vote", "votes": ["Proposal"]}]
        self.library.import_pdf.return_value = self.library.list_documents.return_value[0]
        self.library.import_url.return_value = self.library.list_documents.return_value[0]
        self.settings = Settings("http://localhost:8081/v1", "private-secret")
        self.server = create_server(self.settings, port=0, library=self.library)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = response.status, response.getheader("Content-Type"), response.read()
        connection.close()
        return result

    def test_library_and_config_do_not_disclose_credentials(self):
        status, _, body = self.request("GET", "/api/config")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["documents"][0]["id"], "booklet-test")
        self.assertNotIn(b"private-secret", body)
        self.assertNotIn(b"8081", body)

    def test_raw_pdf_upload_preserves_bytes_and_passes_metadata(self):
        content = b"%PDF-1.4\nexample"
        status, _, _ = self.request("POST", "/api/booklets/upload?language=fr&title=Voting&vote=Proposal",
                                    content, {"Content-Type": "application/pdf"})
        self.assertEqual(status, 201)
        self.library.import_pdf.assert_called_once_with(content, language="fr", title="Voting", vote="Proposal")

    def test_cross_origin_import_is_rejected_before_download(self):
        status, _, _ = self.request("POST", "/api/booklets/import", b"{}",
                                   {"Content-Type": "application/json", "Origin": "https://other.example"})
        self.assertEqual(status, 403)
        self.library.import_url.assert_not_called()

    def test_matching_external_host_and_origin_cannot_rebind_local_api(self):
        headers = {"Host": "other.example", "Origin": "http://other.example", "Content-Type": "application/json"}
        self.assertEqual(self.request("POST", "/api/booklets/import", b"{}", headers)[0], 403)
        self.assertEqual(self.request("GET", "/api/library", headers={"Host": "other.example"})[0], 403)
        self.library.import_url.assert_not_called()

    def test_upload_size_and_content_type_are_enforced_before_reading(self):
        status, _, _ = self.request("POST", "/api/booklets/upload", b"", {"Content-Type": "application/pdf", "Content-Length": "25000001"})
        self.assertEqual(status, 400)
        status, _, _ = self.request("POST", "/api/booklets/upload", b"{}", {"Content-Type": "application/json"})
        self.assertEqual(status, 415)
        self.library.import_pdf.assert_not_called()

    def test_pdf_checks_require_live_mode_and_explicit_proposal(self):
        for data in ({"document_id": "booklet-test", "mode": "demo", "vote": "Proposal"},
                     {"document_id": "booklet-test", "mode": "live"}):
            status, _, _ = self.request("POST", "/api/check", json.dumps(data), {"Content-Type": "application/json"})
            self.assertEqual(status, 400)
        self.library.get_proposal.assert_not_called()

    def test_pdf_download_serves_original_bytes_and_rejects_unknown_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "original.pdf"
            path.write_bytes(b"%PDF-1.4\noriginal")
            self.library.pdf_path.return_value = path
            status, mime, body = self.request("GET", "/api/booklets/booklet-test/pdf")
            self.assertEqual((status, mime, body), (200, "application/pdf", path.read_bytes()))
        self.library.pdf_path.side_effect = ValidationError("Unknown booklet.")
        self.assertEqual(self.request("GET", "/api/booklets/unknown/pdf")[0], 400)


class RuntimeStatusTests(unittest.TestCase):
    def test_status_failure_does_not_expose_provider_or_key(self):
        settings = Settings("https://private.example/v1", "sensitive")
        with patch("claimlens.runtime.build_opener", side_effect=RuntimeError("sensitive")):
            status = model_status(settings)
        self.assertFalse(status["reachable"])
        self.assertTrue(status["configured"])
        self.assertNotIn("sensitive", str(status))
        self.assertNotIn("private.example", str(status))

    def test_unconfigured_status_makes_no_network_call(self):
        with patch("claimlens.runtime.build_opener") as network:
            self.assertFalse(model_status(Settings())["configured"])
        network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
