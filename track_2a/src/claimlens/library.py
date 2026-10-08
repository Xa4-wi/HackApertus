"""Local PDF library with official-source downloads and page-level provenance."""

import copy
import hashlib
import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .booklets import extract_pdf, language as validate_language
from .models import ValidationError


DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "data/local/library"
MAX_PDF_BYTES = 25_000_000
MAX_PAGES = 200
MAX_TEXT_CHARACTERS = 2_000_000
ALLOWED_HOSTS = {"bk.admin.ch", "www.bk.admin.ch"}
DOCUMENT_ID = re.compile(r"booklet-(de|fr|it)-[0-9a-f]{64}\Z")
_WRITE_LOCK = threading.RLock()


def official_url(value):
    """Validate the initial URL and every redirect before making a request."""
    try:
        if not isinstance(value, str) or len(value) > 4096 or any(c.isspace() or ord(c) < 32 for c in value):
            raise ValueError
        parts = urlsplit(value)
        if (parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS
                or parts.port not in (None, 443) or parts.username is not None
                or parts.password is not None or "\\" in value):
            raise ValueError
        return urlunsplit(("https", parts.netloc.lower(), parts.path or "/", parts.query, ""))
    except (ValueError, TypeError):
        raise ValidationError("Use an HTTPS booklet URL on bk.admin.ch or www.bk.admin.ch, without credentials or a custom port.") from None


class OfficialRedirects(HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, request, response, code, message, headers, new_url):
        return super().redirect_request(request, response, code, message, headers, official_url(new_url))


def _download_pdf(url):
    url = official_url(url)
    request = Request(url, headers={"User-Agent": "ClaimLens/2.0 (official booklet import)", "Accept": "application/pdf"})
    started = time.monotonic()
    try:
        with build_opener(OfficialRedirects()).open(request, timeout=20) as response:
            final_url = official_url(response.geturl())
            length = response.headers.get("Content-Length")
            if length is not None:
                try:
                    if not 0 <= int(length) <= MAX_PDF_BYTES:
                        raise ValidationError("Booklet PDF must be no larger than 25 MB.")
                except ValueError:
                    raise ValidationError("The booklet server returned an invalid file size.") from None
            chunks, received = [], 0
            while True:
                if time.monotonic() - started > 90:
                    raise ValidationError("The booklet download exceeded its time limit. Try again later.")
                chunk = response.read(min(65536, MAX_PDF_BYTES + 1 - received))
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_PDF_BYTES:
                    raise ValidationError("Booklet PDF must be no larger than 25 MB.")
                chunks.append(chunk)
            content = b"".join(chunks)
    except ValidationError:
        raise
    except HTTPError as error:
        raise ValidationError("The official booklet server returned HTTP {}. Try another official PDF URL.".format(error.code)) from None
    except (URLError, OSError, TimeoutError):
        raise ValidationError("Could not download the official booklet. Check the URL and try again later.") from None
    _validate_pdf(content)
    return content, final_url


def _validate_pdf(content):
    if not isinstance(content, bytes) or not content or len(content) > MAX_PDF_BYTES:
        raise ValidationError("Booklet must be a PDF no larger than 25 MB.")
    if not content.startswith(b"%PDF-"):
        raise ValidationError("The supplied file is not a PDF.")


def _text(value, name, maximum, default=""):
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise ValidationError("{} must be text of at most {} characters.".format(name, maximum))
    return value.strip() or default


def _atomic_json(path, value):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".metadata-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _extract(path, source_language):
    metadata = {}
    passages = extract_pdf(path, source_language, metadata=metadata, allow_empty=True)
    for passage in passages:
        # A transient import directory must never become a public title.
        passage.pop("title", None)
        passage.pop("url", None)
        passage.pop("attribution", None)
    return metadata["page_count"], passages, metadata["warnings"], metadata["ocr_pages"]


class BookletLibrary:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("CLAIMLENS_LIBRARY") or DEFAULT_ROOT).expanduser().resolve()

    def _directory(self, document_id):
        if not isinstance(document_id, str) or not DOCUMENT_ID.fullmatch(document_id):
            raise ValidationError("Unknown booklet identifier.")
        path = self.root / document_id
        if path.is_symlink() or path.resolve().parent != self.root:
            raise ValidationError("The cached booklet path is invalid.")
        return path

    def _read(self, document_id):
        path = self._directory(document_id) / "document.json"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 12_000_000:
            raise ValidationError("The booklet is unavailable or its metadata is invalid.")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if document["id"] != document_id or not isinstance(document["passages"], list):
                raise ValueError
            if document["language"] not in {"de", "fr", "it"}:
                raise ValueError
            return document
        except (OSError, ValueError, KeyError, TypeError):
            raise ValidationError("The cached booklet metadata could not be read.") from None

    @staticmethod
    def _metadata(document):
        fields = ("id", "title", "language", "source_url", "source_urls", "pdf_url", "page_count",
                  "character_count", "votes", "warnings", "imported_at", "content_sha256", "ocr_pages", "extracted_at")
        return copy.deepcopy({field: document[field] for field in fields if field in document})

    def list_documents(self):
        if not self.root.is_dir():
            return []
        documents = []
        for directory in self.root.iterdir():
            if not DOCUMENT_ID.fullmatch(directory.name):
                continue
            try:
                document = self._read(directory.name)
                self.pdf_path(directory.name)
                documents.append(self._metadata(document))
            except ValidationError:
                continue
        return sorted(documents, key=lambda item: (item.get("title", ""), item["id"]))

    def _merge(self, document, title="", vote="", source_urls=()):
        if title:
            document["title"] = title
        if vote and vote not in document["votes"]:
            document["votes"].append(vote)
            document["votes"].sort()
        for url in source_urls:
            if url and url not in document["source_urls"]:
                document["source_urls"].append(url)
        if not document["source_url"] and document["source_urls"]:
            document["source_url"] = document["source_urls"][0]
        _atomic_json(self._directory(document["id"]) / "document.json", document)
        return self._metadata(document)

    def import_url(self, url, language, title="", vote=""):
        url = official_url(url)
        validate_language(language, "Booklet language")
        title, vote = _text(title, "Title", 500), _text(vote, "Vote", 2000)
        with _WRITE_LOCK:
            for cached in self.list_documents():
                if cached["language"] == language and url in cached.get("source_urls", []):
                    return self._merge(self._read(cached["id"]), title, vote)
        content, final_url = _download_pdf(url)
        return self._import(content, language, title, vote, source_urls=(url, final_url))

    def import_pdf(self, content, language, title="", vote=""):
        return self._import(content, language, title, vote)

    def _import(self, content, language, title="", vote="", source_urls=()):
        _validate_pdf(content)
        validate_language(language, "Booklet language")
        title, vote = _text(title, "Title", 500), _text(vote, "Vote", 2000)
        digest = hashlib.sha256(content).hexdigest()
        document_id = "booklet-{}-{}".format(language, digest)
        with _WRITE_LOCK:
            if self._directory(document_id).exists():
                self.pdf_path(document_id)
                return self._merge(self._read(document_id), title, vote, source_urls)
            self.root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".import-", dir=self.root) as temporary:
                stage = Path(temporary) / "document"
                stage.mkdir()
                path = stage / "original.pdf"
                path.write_bytes(content)
                count, passages, warnings, ocr = _extract(path, language)
                now = datetime.now(timezone.utc).isoformat()
                urls = list(dict.fromkeys(source_urls))
                document = {"id": document_id, "title": title or "Voting booklet ({})".format(language.upper()),
                            "language": language, "source_url": urls[0] if urls else "", "source_urls": urls,
                            "pdf_url": "/api/booklets/{}/pdf".format(document_id), "page_count": count,
                            "character_count": sum(len(p["text"]) for p in passages), "passages": passages,
                            "votes": [vote] if vote else [], "warnings": warnings, "imported_at": now,
                            "extracted_at": now, "content_sha256": digest, "ocr_pages": ocr}
                _atomic_json(stage / "document.json", document)
                os.replace(stage, self._directory(document_id))
            return self._metadata(document)

    def pdf_path(self, document_id):
        directory = self._directory(document_id)
        path = directory / "original.pdf"
        if path.is_symlink() or path.resolve().parent != directory or not path.is_file():
            raise ValidationError("The original booklet PDF is unavailable.")
        if path.stat().st_size > MAX_PDF_BYTES:
            raise ValidationError("The cached PDF exceeds the booklet size limit.")
        return path

    def get_proposal(self, document_id, vote=""):
        vote = _text(vote, "Vote", 2000)
        document = self._read(document_id)
        self.pdf_path(document_id)
        chosen_vote = vote or (document["votes"][0] if len(document["votes"]) == 1 else document["title"])
        passages = copy.deepcopy(document["passages"])
        for passage in passages:
            passage.update({"title": document["title"], "language": document["language"],
                            "url": document["pdf_url"] + "#page={}".format(passage["page"]),
                            "source_url": document["source_url"],
                            "pdf_url": document["pdf_url"] + "#page={}".format(passage["page"]),
                            "attribution": "Voting booklet; check the quoted speaker and section."
                            + (" OCR transcription; compare the original PDF." if passage.get("extraction") == "ocr" else "")})
        return {"id": document_id, "title": document["title"], "language": document["language"],
                "vote": chosen_vote, "passages": passages, "examples": [], "is_fixture": False,
                "source_url": document["source_url"], "pdf_url": document["pdf_url"],
                "warnings": copy.deepcopy(document["warnings"])}

    def refresh_extraction(self, document_id):
        """Retry text/OCR extraction from cached bytes, without another download."""
        with _WRITE_LOCK:
            document = self._read(document_id)
            path = self.pdf_path(document_id)
            if hashlib.sha256(path.read_bytes()).hexdigest() != document["content_sha256"]:
                raise ValidationError("The cached PDF checksum has changed; import the original file again.")
            count, passages, warnings, ocr = _extract(path, document["language"])
            document.update({"page_count": count, "passages": passages, "warnings": warnings, "ocr_pages": ocr,
                             "character_count": sum(len(p["text"]) for p in passages),
                             "extracted_at": datetime.now(timezone.utc).isoformat()})
            _atomic_json(self._directory(document_id) / "document.json", document)
            return self._metadata(document)
