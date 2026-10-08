"""Offline integration checks for OST's PDF/JSONL submission boundary.

These synthetic PDF fixtures and stubbed HTTP responses test the interface,
not Apertus accuracy. No external requests or dataset labels are used.
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claimlens.booklets import extract_pdf
from claimlens.cli import run_batch
from claimlens.config import Settings


def write_text_pdf(path, texts):
    """Construct a tiny valid PDF with one ASCII text string per page."""
    page_ids = [4 + index * 2 for index in range(len(texts))]
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        ("<< /Type /Pages /Kids [{}] /Count {} >>".format(
            " ".join("{} 0 R".format(number) for number in page_ids), len(texts))).encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for page_id, text in zip(page_ids, texts):
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content = ("BT /F1 12 Tf 50 750 Td ({}) Tj ET".format(escaped)).encode("ascii")
        objects.extend([
            ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
             "/Resources << /Font << /F1 3 0 R >> >> /Contents {} 0 R >>".format(page_id + 1)).encode(),
            b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        ])
    document = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, value in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend("{} 0 obj\n".format(number).encode() + value + b"\nendobj\n")
    xref = len(document)
    document.extend("xref\n0 {}\n0000000000 65535 f \n".format(len(offsets)).encode())
    for offset in offsets[1:]:
        document.extend("{:010d} 00000 n \n".format(offset).encode())
    document.extend(("trailer\n<< /Size {} /Root 1 0 R >>\nstartxref\n{}\n%%EOF\n".format(
        len(offsets), xref)).encode())
    path.write_bytes(document)


class StubResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, maximum):
        return self.body[:maximum]


@unittest.skipUnless(importlib.util.find_spec("pypdf"), "Install requirements.txt for PDF integration checks")
class SubmissionIntegrationTests(unittest.TestCase):
    def test_pdf_pages_preserve_blank_page_offset(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "two-pages.pdf"
            write_text_pdf(path, ["", "La loi entre en vigueur en 2028."])
            passages = extract_pdf(path, "fr")
        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0]["page"], 2)
        self.assertEqual(passages[0]["language"], "fr")
        self.assertIn("La loi entre en vigueur en 2028.", passages[0]["text"])

    def test_mixed_tasks_multiple_pdfs_and_vote_reach_model(self):
        calls = []

        class StubOpener:
            def open(self, request, timeout):
                payload = json.loads(request.data)
                user = json.loads(payload["messages"][-1]["content"])
                calls.append({"url": request.full_url, "model": payload["model"], "user": user})
                passage = user["passages"][0]
                result = {
                    "summary": "Synthetic interface test response.",
                    "checks": [{
                        "text": user["claim"], "dimension": "general", "label": "entailment",
                        "explanation": "Synthetic interface test response.",
                        "evidence": [{"passage_id": passage["id"], "quote": passage["text"]}],
                    }],
                }
                body = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}],
                        "usage": {"prompt_tokens": 123, "completion_tokens": 45}}
                return StubResponse(json.dumps(body).encode())

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "booklets").mkdir()
            write_text_pdf(root / "booklets" / "first.pdf", ["", "La loi entre en vigueur en 2028."])
            write_text_pdf(root / "booklets" / "second.pdf", ["La legge entra in vigore nel 2029."])
            cases = [
                {"id": "a-first", "vote": "Premiere proposition", "booklet": {"path": "booklets/first.pdf", "language": "fr"},
                 "claim": {"text": "Die Regel gilt ab 2028.", "language": "de"}},
                {"id": "b-reference", "vote": "Referenzvorlage", "reference": {"text": "Die Regel gilt ab 2027.", "language": "de"},
                 "claim": {"text": "La legge si applica dal 2027.", "language": "it"}},
                {"id": "a-second", "vote": "Seconda proposta", "booklet": {"path": "booklets/second.pdf", "language": "it"},
                 "claim": {"text": "La loi entre en vigueur en 2029.", "language": "fr"}},
                {"id": "a-reused", "vote": "Premiere proposition", "booklet": {"path": "booklets/first.pdf", "language": "fr"},
                 "claim": {"text": "La legge si applica dal 2028.", "language": "it"}},
            ]
            input_path, output_path = root / "cases.jsonl", root / "output" / "predictions.jsonl"
            input_path.write_text("\n".join(json.dumps(case) for case in cases) + "\n", encoding="utf-8")
            settings = Settings(base_url="http://localhost:9000/v1", api_key="synthetic-test-key")
            with patch("claimlens.llm.build_opener", return_value=StubOpener()), \
                    patch("claimlens.booklets.extract_pdf", wraps=extract_pdf) as extractor:
                self.assertEqual(run_batch(input_path, output_path, settings, root), 4)
                self.assertEqual(extractor.call_count, 2)
            outputs = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual([item["id"] for item in outputs], [case["id"] for case in cases])
        self.assertEqual([item["evidence"][0]["page"] for item in outputs], [2, None, 1, 2])
        for request, case, response in zip(calls, cases, outputs):
            self.assertEqual(request["url"], "http://localhost:9000/v1/chat/completions")
            self.assertEqual(request["model"], settings.model)
            self.assertEqual(request["user"]["vote"], case["vote"])
            self.assertEqual(request["user"]["claim_language"], case["claim"]["language"])
            source = case.get("booklet", case.get("reference"))
            self.assertEqual(request["user"]["passages"][0]["language"], source["language"])
            self.assertEqual(set(response), {"id", "label", "label_name", "evidence", "metrics"})
            self.assertEqual((response["label"], response["label_name"]), (0, "entailment"))
            self.assertEqual(response["metrics"]["input_tokens"], 123)
            self.assertEqual(response["metrics"]["output_tokens"], 45)
            self.assertGreaterEqual(response["metrics"]["inference_time_ms"], 0)
            self.assertEqual(set(response["evidence"][0]), {"page", "text"})


if __name__ == "__main__":
    unittest.main()
