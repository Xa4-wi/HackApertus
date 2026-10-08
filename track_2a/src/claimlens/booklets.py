"""Page-preserving PDF extraction and official CLI request validation."""

from pathlib import Path
import time

from .models import ValidationError
from .ocr import ocr_pages

LANGUAGES = {"de", "fr", "it"}


def require_text(value, field, maximum=300000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValidationError("{} must contain 1–{} characters.".format(field, maximum))
    return value


def language(value, field):
    if not isinstance(value, str) or value not in LANGUAGES:
        raise ValidationError("{} must be de, fr, or it.".format(field))
    return value


def extract_pdf(path, source_language, *, metadata=None, allow_empty=False, deadline=None):
    """Preserve physical PDF pages, using bounded local OCR for scant text.

    The optional metadata dictionary receives coverage warnings. The returned
    list remains compatible with the original CLI extraction API.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValidationError("PDF input needs pypdf. Install requirements.txt or use the Docker image.") from None
    if not path.is_file() or path.stat().st_size > 25_000_000:
        raise ValidationError("Booklet must be an existing PDF no larger than 25 MB.")
    try:
        def check_deadline():
            if deadline is not None and time.monotonic() >= deadline:
                raise ValidationError("PDF preparation exceeded the case time budget. No partial source was accepted.")

        check_deadline()
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValidationError("Encrypted PDFs are not supported.")
        page_count = len(reader.pages)
        if not 1 <= page_count <= 200:
            raise ValidationError("Prototype booklet limit: 200 PDF pages.")
        passages, total = [], 0
        for number, page in enumerate(reader.pages, start=1):
            check_deadline()
            text = page.extract_text() or ""
            total += len(text)
            if total > 2_000_000:
                raise ValidationError("The extracted booklet exceeds the two-million-character limit.")
            if text.strip():
                passages.append({"id": "page-{}".format(number), "text": text,
                                 "page": number, "title": path.name, "url": "",
                                 "attribution": "Voting booklet; check speaker and section in the quoted text",
                                 "language": source_language, "extraction": "pdf_text"})
        by_page = {passage["page"]: passage for passage in passages}
        scant = [number for number in range(1, page_count + 1)
                 if len("".join(by_page.get(number, {}).get("text", "").split())) < 40]
        warnings, used_ocr = [], []
        if scant:
            check_deadline()
            ocr_options = ({"timeout_seconds": max(0, deadline - time.monotonic())}
                           if deadline is not None else {})
            recognized, warnings = ocr_pages(path, scant, source_language, **ocr_options)
            check_deadline()
            for number, text in recognized.items():
                if number in scant and len(text.strip()) > len(by_page.get(number, {}).get("text", "").strip()):
                    by_page[number] = {"id": "page-{}".format(number), "page": number, "text": text,
                                       "title": path.name, "url": "", "language": source_language,
                                       "attribution": "OCR transcription; compare the original PDF and quoted speaker.",
                                       "extraction": "ocr"}
                    used_ocr.append(number)
        incomplete = [number for number in scant
                      if len("".join(by_page.get(number, {}).get("text", "").split())) < 40]
        if incomplete:
            warnings.append("Little or no readable text on PDF pages: {}. These pages may contain images, scans, or little text.".format(
                ", ".join(str(n) for n in incomplete)))
        passages = [by_page[number] for number in sorted(by_page) if by_page[number]["text"].strip()]
        characters = sum(len(passage["text"]) for passage in passages)
        if characters > 2_000_000:
            raise ValidationError("The extracted booklet exceeds the two-million-character limit.")
        if not passages:
            warnings.append("No readable text was extracted. Check local OCR tools and the original PDF.")
        if metadata is not None:
            metadata.update({"page_count": page_count, "character_count": characters,
                             "warnings": list(dict.fromkeys(warnings)), "ocr_pages": sorted(used_ocr),
                             "incomplete_pages": incomplete})
        if not passages and not allow_empty:
            raise ValidationError("No readable text found. Local OCR is unavailable or could not recover text from this PDF.")
        check_deadline()
        return passages
    except ValidationError:
        raise
    except Exception:
        raise ValidationError("Could not extract the booklet PDF. Check its format and text layer.") from None


def prepare_case(case, data_root, pdf_cache=None, *, deadline=None):
    """Translate the presentation and annotated API inputs to the engine.

    Language metadata is optional in the presentation. Absence means the
    model reads the original multilingual text without a guessed language;
    supplied metadata still has to use an official language code. Reference
    tasks need no vote context because their supplied text is the only source.
    """
    if not isinstance(case, dict):
        raise ValidationError("Each input line must be a JSON object.")
    require_text(case.get("id"), "id", 256)
    claim = case.get("claim")
    if not isinstance(claim, dict):
        raise ValidationError("claim must be an object containing text and optional language.")
    claim_text = require_text(claim.get("text"), "claim.text", 2000)
    claim_language = language(claim["language"], "claim.language") if "language" in claim else "auto"
    if ("booklet" in case) == ("reference" in case):
        raise ValidationError("Supply exactly one of booklet or reference.")
    kind = "booklet" if "booklet" in case else "reference"
    source = case[kind]
    if not isinstance(source, dict):
        raise ValidationError("{} must be an object.".format(kind))
    source_language = language(source["language"], kind + ".language") if "language" in source else "auto"
    vote = require_text(case.get("vote"), "vote", 2000) if kind == "booklet" or "vote" in case else ""
    source_metadata = {}
    if kind == "reference":
        passages = [{"id": "reference-1", "text": require_text(source.get("text"), "reference.text"),
                     "page": None, "title": vote or "Supplied reference", "url": "",
                     "attribution": "Supplied reference; retain the source's attribution",
                     "language": source_language}]
    else:
        supplied_path = require_text(source.get("path"), "booklet.path", 4096)
        if "\x00" in supplied_path:
            raise ValidationError("booklet.path must not contain null bytes.")
        try:
            root = Path(data_root).resolve()
            path = (root / supplied_path).resolve()
        except (OSError, ValueError, RuntimeError):
            raise ValidationError("Could not resolve booklet.path inside the input data directory.") from None
        try:
            path.relative_to(root)
        except ValueError:
            raise ValidationError("Booklet paths must stay inside the input data directory.") from None
        cache = pdf_cache if pdf_cache is not None else {}
        key = (str(path), source_language)
        if key not in cache:
            extracted_metadata = {}
            options = {"deadline": deadline} if deadline is not None else {}
            extracted = extract_pdf(path, source_language, metadata=extracted_metadata, **options)
            cache[key] = {"passages": extracted, "metadata": extracted_metadata}
        cached = cache[key]
        if isinstance(cached, dict):
            passages, source_metadata = cached["passages"], cached["metadata"]
        else:
            passages = cached
    return ({"id": case["id"], "title": vote, "language": source_language,
             "vote": vote, "passages": passages, "source_kind": kind, "examples": [], "is_fixture": False,
             **source_metadata}, claim_text, claim_language)
