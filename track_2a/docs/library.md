# Voting booklet library

The library stores original PDFs and extracted text for whole-booklet checks. Import a Federal Chancellery PDF link or upload a saved PDF in the web app, select its language, and name the proposal within the booklet. A booklet can cover several votes. Imports prepare sources locally and do not call Apertus.

## Current official collection

The 2026-10-08 import contains every unique booklet URL referenced by the prepared [OST dataset](https://huggingface.co/datasets/OSTswiss/MNLIoverSwissVotingBooklets) at revision `fc2b27600310778da6bbf445651ddbca22d86269`. This is the dataset's collection, not the entire [Federal Chancellery historical archive](https://www.bk.admin.ch/de/sammlung-der-abstimmungsbuechlein-seit-1978).

| Measure | Verified result after extraction refresh |
| --- | --- |
| Official PDFs | 60: 20 German, 20 French, 20 Italian |
| Original PDF pages | 3,408 |
| Original PDF bytes | 75,993,354, about 76MB |
| Extracted text characters | 6,144,888, including whitespace |
| Pages using recovered OCR text | 22, across 10 documents |
| Failed imports / rejected dataset rows | 0 / 0 |

These counts exclude user uploads and temporary verification fixtures. Some pages still contain little readable text; warnings identify them. A blank cover, an image-only page, and a failed text extraction can all produce that warning, so it does not by itself establish missing evidence.

## Import and resume

Run these commands from `track_2a/` after preparing the dataset with `make dataset`:

```sh
make booklets
# Equivalent:
.venv/bin/python scripts/import_booklets.py
```

The importer reads `data/local/ost/dataset`, a `datasets.save_to_disk` snapshot. Only `booklet_url`, `reference_language`, and `vote` are selected. It groups URL/language pairs, collects vote titles, and imports PDFs sequentially. Dataset claims, references, labels, and baseline scores are not copied into the library or import report.

An already imported source URL and language reuse the cached document. Re-running the command resumes missing or failed imports; it does not download successful PDFs again. Each PDF's bytes and language determine its stable identifier, so identical bytes in the same language share one document and accumulate vote titles. Cached URLs are not automatically revalidated against changing remote files.

| Option | Behavior |
| --- | --- |
| `--dataset PATH` | Use a different saved dataset snapshot. |
| `--jsonl PATH` | Read raw OST rows containing the three source fields instead; mutually exclusive with `--dataset`. |
| `--library PATH` | Choose the local library directory. |
| `--manifest PATH` | Choose the import report location. |
| `--limit N` | Process the first N unique URL/language pairs in sorted order. |
| `--refresh` | Re-extract cached PDFs, including local OCR, while retaining their original bytes. Missing documents are imported normally. |

For example:

```sh
.venv/bin/python scripts/import_booklets.py --limit 3
.venv/bin/python scripts/import_booklets.py --jsonl /path/to/ost-rows.jsonl
.venv/bin/python scripts/import_booklets.py --refresh
```

The atomic `import-manifest.json` report is updated after each source. It records source URLs/languages/votes, document identifiers, page and character counts, warnings, and per-item failures. One failed download does not prevent other sources from importing. `complete` means every selected source was processed; check `failed` for individual failures. Interrupted runs are marked `interrupted`, unexpected errors produce `aborted`, and `unprocessed` counts sources without a final item record. The command exits with status 1 if aborted, any source fails, or a row is invalid, and 130 if interrupted. Re-run it to resume. Run one bulk importer at a time against a given library; file publication is atomic, while the write lock coordinates threads within one process.

## Storage and provenance

The default root is `track_2a/data/local/library`. Set `CLAIMLENS_LIBRARY` in the server's environment, or pass `--library` to the importer, to choose another root. The Docker web app mounts the host library at `/library`.

```text
data/local/library/
  import-manifest.json
  booklet-de-<full-pdf-sha256>/
    original.pdf
    document.json
```

`document.json` contains the content SHA256, language, title, source URLs, vote titles, import/extraction timestamps, coverage warnings, and one passage per readable physical PDF page. Pages stay 1-based and retain their original positions when blank pages are omitted from the passage list. The original PDF is unchanged. Its local API route is `/api/booklets/<id>/pdf`, with `#page=N` on evidence links. Source URLs remain available separately; uploaded PDFs have no asserted official source URL.

Document directories are published only after extraction completes. Metadata updates also use temporary files followed by atomic replacement. Reading an absent library returns an empty list without creating directories. The library is ignored by Git and is development data; official CLI cases still read their supplied PDFs from the input data directory.

## Download and extraction boundaries

URL import allows HTTPS on exactly `bk.admin.ch` and `www.bk.admin.ch`, with port 443 or no explicit port. Credentials and custom ports are rejected. Every redirect and the final response URL undergo the same check; query parameters are permitted and fragments are discarded. Other sources can be supplied through an explicit PDF upload.

Both downloads and uploads require a PDF signature and are capped at 25,000,000 bytes. Downloads check the declared size and the bytes received, use a 20-second network timeout, and check a 90-second elapsed deadline between reads. Network failures return short errors without remote response bodies. Document identifiers have a fixed language/SHA256 format; path traversal and symlinked document/PDF paths are rejected.

Extraction rejects encrypted PDFs, more than 200 pages, and more than two million extracted characters. These are library limits; model context and document-processing limits are separate. A readable PDF may still have an imperfect text layer, particularly around tables, typography, or embedded fonts. The original page remains the reference for reviewing a quotation.

PDF parsing and text extraction currently run in-process without a separate time or memory limit. The compressed file limit and checks after extraction do not bound decompression or parsing work; the OCR timeout below starts after this stage. This remains a resource-hardening limitation for unusual or untrusted uploads.

## Local OCR

Install Poppler and Tesseract before importing image-based PDFs on macOS:

```sh
brew install poppler tesseract
make ocr-setup
.venv/bin/python scripts/import_booklets.py --refresh
```

The setup script downloads and verifies only German, French, and Italian language data. OCR itself performs no installation, download, or remote inference. It uses project `.cache/tessdata` automatically when the requested language file exists; an explicitly supplied `TESSDATA_PREFIX` takes precedence. A container can use preinstalled system language data instead.

The pinned source is [tesseract-ocr/tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast/tree/65727574dfcd264acbb0c3e07860e4e9e9b22185), revision `65727574dfcd264acbb0c3e07860e4e9e9b22185`. The setup script records these checksums in its source; the local setup manifest contains the same metadata:

| Language file | Bytes | SHA256 |
| --- | --- | --- |
| `deu.traineddata` | 1,525,436 | `19d219bbb6672c869d20a9636c6816a81eb9a71796cb93ebe0cb1530e2cdb22d` |
| `fra.traineddata` | 1,130,365 | `ced037562e8c80c13122dece28dd477d399af80911a28791a66a63ac1e3445ca` |
| `ita.traineddata` | 2,701,314 | `b8f89e1e785118dac4d51ae042c029a64edb5c3ee42ef73027a6d412748d8827` |

Pages with fewer than 40 non-whitespace text characters are candidates for OCR. Each extraction attempts at most 20 candidate pages within a shared 180-second budget. Individual rendering or recognition processes have at most 30 seconds. Rendering requests 150 DPI with the longest side capped at 2,000 pixels, and recovered text is capped at 2MB. OCR replaces a page's text only when it recovers more text than the existing scant text layer.

This is a scant-text heuristic. A scanned body with a selectable header of 40 or more characters can skip OCR, so an empty `incomplete_pages` list or absence of warnings does not prove that every visible passage was extracted.

Missing tools or language data, empty recognition, page limits, and timeouts become coverage warnings. A completely unreadable document can remain in the web library for inspection; the official CLI rejects a PDF with no readable text. The shared extractor preserves warnings when PDFs are reused from its per-batch cache, and the CLI prints them to stderr without changing the official prediction JSONL schema.

After installing OCR tools, fixing language data, or updating extraction dependencies, use `--refresh`. The refresh checks the cached original PDF's SHA256 before replacing extracted metadata. If the cached bytes changed, it refuses extraction. OCR text is a transcription and may contain errors; an exact quote match against OCR text does not establish an exact match to the visual original. See [Tesseract's language-data documentation](https://tesseract-ocr.github.io/tessdoc/Data-Files.html).

Verification includes source-host/redirect and size rejection, path/symlink protection, deduplication, resumable imports, atomic failure cleanup, preserved page numbers, OCR resource limits, and cached CLI warnings. A separate image-only French PDF was also rendered and inspected: OCR recovered its text on physical page 2 while retaining the blank first-page warning. That temporary fixture was removed and was never stored in the user's booklet library.
