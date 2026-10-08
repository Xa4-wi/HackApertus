"""Page-preserving PDF extraction and official CLI request validation."""

from pathlib import Path

from .models import ValidationError

LANGUAGES = {"de", "fr", "it"}


def require_text(value, field, maximum=300000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValidationError("{} must contain 1–{} characters.".format(field, maximum))
    return value


def language(value, field):
    if not isinstance(value, str) or value not in LANGUAGES:
        raise ValidationError("{} must be de, fr, or it.".format(field))
    return value


def extract_pdf(path, source_language):
    """Keep one passage per PDF page; never invent a printed page number."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValidationError("PDF input needs pypdf. Install requirements.txt or use the Docker image.") from None
    if not path.is_file() or path.stat().st_size > 25_000_000:
        raise ValidationError("Booklet must be an existing PDF no larger than 25 MB.")
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValidationError("Encrypted PDFs are not supported.")
        if len(reader.pages) > 200:
            raise ValidationError("Prototype booklet limit: 200 PDF pages.")
        passages = []
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                passages.append({"id": "page-{}".format(number), "text": text,
                                 "page": number, "title": path.name, "url": "",
                                 "attribution": "Voting booklet; check speaker and section in the quoted text",
                                 "language": source_language})
        if not passages:
            raise ValidationError("No selectable text found. Scanned booklets require OCR, which this prototype does not provide.")
        return passages
    except ValidationError:
        raise
    except Exception:
        raise ValidationError("Could not extract the booklet PDF. Check its format and text layer.") from None


def prepare_case(case, data_root, pdf_cache=None):
    """Translate either official task input into the shared engine contract."""
    if not isinstance(case, dict):
        raise ValidationError("Each input line must be a JSON object.")
    require_text(case.get("id"), "id", 256)
    vote = require_text(case.get("vote"), "vote", 2000)
    claim = case.get("claim")
    if not isinstance(claim, dict):
        raise ValidationError("claim must be an object containing text and language.")
    claim_text = require_text(claim.get("text"), "claim.text", 2000)
    claim_language = language(claim.get("language"), "claim.language")
    if ("booklet" in case) == ("reference" in case):
        raise ValidationError("Supply exactly one of booklet or reference.")
    kind = "booklet" if "booklet" in case else "reference"
    source = case[kind]
    if not isinstance(source, dict):
        raise ValidationError("{} must be an object.".format(kind))
    source_language = language(source.get("language"), kind + ".language")
    if kind == "reference":
        passages = [{"id": "reference-1", "text": require_text(source.get("text"), "reference.text"),
                     "page": None, "title": vote, "url": "",
                     "attribution": "Supplied reference; retain the source's attribution",
                     "language": source_language}]
    else:
        supplied_path = require_text(source.get("path"), "booklet.path", 4096)
        root = Path(data_root).resolve()
        path = (root / supplied_path).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            raise ValidationError("Booklet paths must stay inside the input data directory.") from None
        cache = pdf_cache if pdf_cache is not None else {}
        key = (str(path), source_language)
        if key not in cache:
            cache[key] = extract_pdf(path, source_language)
        passages = cache[key]
    return ({"id": case["id"], "title": vote, "language": source_language,
             "passages": passages, "examples": [], "is_fixture": False}, claim_text, claim_language)
