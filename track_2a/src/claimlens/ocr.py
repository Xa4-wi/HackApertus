"""Optional, bounded local OCR; never installs tools or sends documents away."""

import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


LANGUAGES = {"de": "deu", "fr": "fra", "it": "ita"}
MAX_TEXT_BYTES = 2_000_000
LOCAL_TESSDATA = Path(__file__).resolve().parents[3] / ".cache/tessdata"


def ocr_pages(pdf_path, page_numbers, language, *, max_pages=20, timeout_seconds=180):
    """Return OCR text keyed by original 1-based PDF page, plus safe warnings.

    Poppler and Tesseract must already be installed with the source language.
    An unspecified language (``auto``) uses all three challenge languages in
    one recognition pass; it does not guess a language from the PDF filename.
    Rendering is limited to 2,000 pixels on the longest side. Each command has
    a 30-second timeout within a shared deadline of at most 180 seconds.
    """
    warnings = []
    extracted = {}
    if language != "auto" and language not in LANGUAGES:
        return {}, ["OCR supports German, French, and Italian source documents."]
    required_languages = tuple(LANGUAGES.values()) if language == "auto" else (LANGUAGES[language],)
    recognition_languages = "+".join(required_languages)
    try:
        limit = min(20, max(0, int(max_pages)))
        seconds = float(timeout_seconds)
        if not math.isfinite(seconds) or seconds <= 0 or limit == 0:
            return {}, ["OCR was skipped because its page or time budget is exhausted."]
        deadline = time.monotonic() + min(180, seconds)
        source = Path(pdf_path).resolve()
        if not source.is_file():
            return {}, ["OCR could not open the PDF document."]
    except (TypeError, ValueError, OSError):
        return {}, ["OCR could not open the PDF document or use its configured limits."]
    selected = []
    for number in page_numbers:
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            if "OCR skipped invalid PDF page numbers." not in warnings:
                warnings.append("OCR skipped invalid PDF page numbers.")
            continue
        if number in selected:
            continue
        if len(selected) == limit:
            warnings.append("OCR page limit reached; some scanned pages were not processed.")
            break
        selected.append(number)
    if not selected:
        return {}, warnings
    renderer, recognizer = shutil.which("pdftoppm"), shutil.which("tesseract")
    if not renderer or not recognizer:
        return {}, warnings + ["Scanned pages need local pdftoppm and tesseract; OCR tools are unavailable."]
    # Respect an explicitly configured Tesseract installation. Otherwise use
    # the project's checksum-pinned language data when available.
    tessdata = []
    if "TESSDATA_PREFIX" not in os.environ and all(
            (LOCAL_TESSDATA / (code + ".traineddata")).is_file() for code in required_languages):
        tessdata = ["--tessdata-dir", str(LOCAL_TESSDATA)]

    def run(command, output=subprocess.DEVNULL):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command[0], 0)
        subprocess.run(command, stdin=subprocess.DEVNULL, stdout=output,
                       stderr=subprocess.DEVNULL, check=True, timeout=min(30, remaining))

    try:
        with tempfile.TemporaryDirectory(prefix="claimlens-ocr-") as directory:
            folder = Path(directory)
            languages = folder / "languages.txt"
            try:
                with languages.open("wb") as output:
                    run([recognizer] + tessdata + ["--list-langs"], output)
                with languages.open("rb") as output:
                    available = output.read(65536).decode("utf-8", errors="replace").splitlines()
                missing = sorted(set(required_languages) - {line.strip() for line in available})
                if missing:
                    return {}, warnings + ["OCR language data for this document is unavailable: {}.".format(
                        ", ".join(missing))]
            except (OSError, subprocess.SubprocessError):
                return {}, warnings + ["OCR could not check installed language data."]
            consumed = 0
            for number in selected:
                if time.monotonic() >= deadline:
                    warnings.append("OCR time limit reached; some scanned pages were not processed.")
                    break
                prefix = folder / ("page-{}".format(number))
                stage = "render"
                try:
                    run([renderer, "-f", str(number), "-l", str(number),
                         "-singlefile", "-r", "150", "-scale-to", "2000", "-png",
                         str(source), str(prefix)])
                    stage = "read text from"
                    run([recognizer, str(prefix.with_suffix(".png")), str(prefix)] + tessdata +
                        ["-l", recognition_languages, "txt"])
                    remaining = MAX_TEXT_BYTES - consumed
                    with prefix.with_suffix(".txt").open("rb") as output:
                        raw = output.read(remaining + 1)
                    truncated = len(raw) > remaining
                    raw = raw[:remaining]
                    consumed += len(raw)
                    result = raw.decode("utf-8", errors="replace").strip()
                    if result:
                        extracted[number] = result
                    else:
                        warnings.append("OCR found no readable text on PDF page {}.".format(number))
                    if truncated or consumed >= MAX_TEXT_BYTES:
                        warnings.append("OCR reached its 2 MB text limit; additional text was omitted.")
                        break
                except subprocess.TimeoutExpired:
                    warnings.append("OCR timed out on PDF page {}.".format(number))
                except (OSError, subprocess.SubprocessError):
                    warnings.append("OCR could not {} PDF page {}.".format(stage, number))
                finally:
                    for suffix in (".png", ".txt"):
                        prefix.with_suffix(suffix).unlink(missing_ok=True)
    except OSError:
        warnings.append("OCR could not use its temporary working files.")
    if extracted:
        warnings.append("OCR text is approximate; verify quotations against the original PDF pages.")
    return extracted, warnings
