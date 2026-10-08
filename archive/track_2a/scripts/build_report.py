#!/usr/bin/env python3
"""Build the four-page presentation report from recorded local observations."""

import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

ROOT = Path(__file__).resolve().parents[1]
NAVY, TEAL, MUTED = colors.HexColor("#17383E"), colors.HexColor("#087B70"), colors.HexColor("#53686C")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    summary = load(ROOT / "output/v2-evaluation/summary.json")
    baseline = load(ROOT / "output/v2-evaluation-baseline/summary.json")
    smoke = load(ROOT / "output/v2-smoke/booklet-result.json")
    verification = load(ROOT / "output/v2-smoke/verification.json")
    documents = [load(path) for path in (ROOT / "data/local/library").glob("*/document.json")]
    documents = [doc for doc in documents if "bk.admin.ch" in doc.get("source_url", "")]
    font, bold = "Helvetica", "Helvetica-Bold"
    regular_path = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
    bold_path = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
    if regular_path.is_file() and bold_path.is_file():
        pdfmetrics.registerFont(TTFont("ReportArial", str(regular_path)))
        pdfmetrics.registerFont(TTFont("ReportArialBold", str(bold_path)))
        pdfmetrics.registerFontFamily("ReportArial", normal="ReportArial", bold="ReportArialBold")
        font, bold = "ReportArial", "ReportArialBold"
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Copy", fontName=font, fontSize=10.3, leading=15, textColor=NAVY, spaceAfter=9))
    styles.add(ParagraphStyle("SmallCopy", parent=styles["Copy"], fontSize=8.6, leading=12, spaceAfter=5))
    styles.add(ParagraphStyle("ReportTitle", fontName=bold, fontSize=29, leading=33, textColor=NAVY, spaceAfter=15))
    styles.add(ParagraphStyle("SectionTitle", fontName=bold, fontSize=19, leading=24, textColor=NAVY, spaceAfter=15))
    styles.add(ParagraphStyle("Sub", fontName=bold, fontSize=11.5, leading=16, textColor=TEAL, spaceBefore=8, spaceAfter=7))
    styles.add(ParagraphStyle("Tag", fontName=bold, fontSize=9, leading=13, textColor=TEAL, spaceAfter=9))
    styles.add(ParagraphStyle("CodeBlock", fontName="Courier", fontSize=8.5, leading=13, textColor=NAVY, spaceAfter=9))

    def p(text, style="Copy"):
        return Paragraph(text, styles[style])

    def table(rows, widths, header=True):
        formatted = [[p(str(cell), "SmallCopy") for cell in row] for row in rows]
        result = Table(formatted, colWidths=widths, hAlign="LEFT", repeatRows=1 if header else 0)
        commands = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LINEBELOW", (0, 0), (-1, -1), .4, colors.HexColor("#DCE6E4"))]
        if header:
            commands += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F2EF"))]
        result.setStyle(TableStyle(commands))
        return result

    width = A4[0] - 40 * mm
    story = [p("HACK APERTUS / TRACK 2A / OST", "Tag"), p("ClaimLens", "ReportTitle"),
             p("Version 0.2 - from a claim to verifiable booklet evidence", "SectionTitle"),
             p("Presentation and engineering report | 8 October 2026", "SmallCopy"), Spacer(1, 8 * mm),
             p("Purpose", "Sub"), p("Check a natural-language claim against a selected Swiss voting booklet. Return the official three-way relationship with exact source quotations and page links. The source and claim may independently be German, French or Italian."),
             table([["0 / Entailment", "1 / Neutral", "2 / Contradiction"],
                    ["The source supports the claim.", "The source does not resolve the claim.", "The source contradicts the claim."]], [width / 3] * 3),
             Spacer(1, 6 * mm), p("What can be demonstrated", "Sub"),
             p("Select a cached official booklet, choose its proposal, and enter a claim. Import another booklet from an official URL or upload a PDF. Live mode calls the local Apertus model; the separately labeled walkthrough uses stored examples."),
             p("Results show the whole-claim verdict, diagnostic highlights, original-language evidence, source-page links and measured token/time usage. A model-health indicator distinguishes a configured endpoint from a responding model."),
             table([["Local source library", "Inference", "Interface"],
                    [str(len(documents)) + " official PDFs; 20 per language", "Apertus v1.5 8B text Q4_K_M", "Browser UI and official JSONL CLI"]], [width / 3] * 3),
             Spacer(1, 6 * mm), p("A reviewable prototype", "Sub"),
             p("Exact quotation checks establish where evidence came from. They do not prove that a model interpretation is correct. The current measurements are development checks, not an official or held-out benchmark."), PageBreak()]

    story += [p("01 / Architecture", "SectionTitle"),
              p("Claim + selected source > context planning > Apertus > quotation validation > result", "Tag"),
              table([["Component", "Responsibility"],
                     ["library.py / booklets.py / ocr.py", "Download or upload once; retain original PDF and source metadata; extract page text; apply bounded local OCR when needed."],
                     ["context.py / llm.py", "Plan context, call the configured Apertus endpoint, and aggregate actual usage from every inference pass."],
                     ["engine.py", "Validate claim spans, source IDs and verbatim quotations. The whole-claim assessment determines NLI."],
                     ["server.py / static/", "Document selection, import, runtime health, results and linked evidence."],
                     ["cli.py", "Read official Task A/B JSONL and write labels, evidence and metrics atomically."]], [61 * mm, width - 61 * mm]),
              Spacer(1, 4 * mm), p("Long documents", "Sub"),
              p("The local model now has a 16,384-token context. Short inputs use one inference call. Longer sources are split into ordered segments that cover all supplied text. Apertus selects relevant source-unit IDs from every segment; Python reconstructs exact excerpts and a final call reasons jointly across them."),
              p("This can retain supporting, opposing and complementary facts across pages. Evidence selection may still miss relevant facts. Overflow, invalid extraction, exhausted time or too many calls fail explicitly instead of silently dropping evidence."),
              p("PDF and OCR provenance", "Sub"),
              p("Original PDFs, SHA256 hashes, language, source URLs and vote titles stay in the local cache. PDF page positions remain 1-based. OCR uses installed Poppler and Tesseract with DE/FR/IT language files; warnings expose unreadable pages and approximate text. OCR is limited to 20 pages and 180 seconds per document."),
              p("Local development and submission", "Sub"),
              p("The Mac uses llama.cpp with Apple Metal and a community text conversion of Apertus v1.5 8B. Official evaluation receives the organizer's runtime endpoint and model IDs. The submission image contains code and extraction dependencies; it contains no gold labels, model weights or credentials."), PageBreak()]

    story += [p("02 / Recorded validation", "SectionTitle"),
              p("Development sample: 27 reference cases", "Sub"),
              p("One example per label for each of the nine language pairs, selected with seed 20261008. Duplicate requests were removed. Gold labels went only to selection/scoring. The same development sample was repeated after tightening the local response schema; it is not held out. Failures count as incorrect outcomes."),
              table([["Accepted / total", "Accuracy incl. failures", "Macro-F1 incl. failures"],
                     ["{} / {}".format(summary["accepted"], summary["cases"]),
                      "{:.1%}".format(summary["accuracy_including_failures"]),
                      "{:.3f}".format(summary["macro_f1_including_failures"])]], [width / 3] * 3),
              Spacer(1, 3 * mm),
              p("Earlier schema: {} accepted, {} failures, {:.1%} accuracy and {:.3f} macro-F1 on the same 27 cases. Both runs are retained for comparison.".format(
                  baseline["accepted"], baseline["failures"], baseline["accuracy_including_failures"],
                  baseline["macro_f1_including_failures"]), "SmallCopy")]
    pair_rows = [["Claim > source", "Accepted", "Correct / cases"]]
    for pair, result in sorted(summary["language_pairs"].items()):
        pair_rows.append([pair.replace("→", " > "), str(result["accepted"]), "{} / {}".format(result["correct"], result["cases"])])
    story += [table(pair_rows, [width * .48, width * .22, width * .30]), Spacer(1, 3 * mm),
              p("Main quality limitation: all nine neutral cases were classified as contradiction. The revised schema removed observed format failures; semantic uncertainty still needs work. This sample does not establish the Task B target of 0.70 macro-F1.", "SmallCopy"),
              p("Mean case duration: {:.1f}s. Recorded input/output tokens: {:,} / {:,}. Metrics available for {} of {} cases.".format(
                  summary["mean_case_ms"] / 1000, summary["recorded_tokens"].get("input_tokens", 0),
                  summary["recorded_tokens"].get("output_tokens", 0), summary["cases_with_token_metrics"], summary["cases"]), "SmallCopy"),
              p("Whole-booklet check", "Sub"),
              p("A German changed-number claim was checked against the complete French 3 March 2024 booklet: {} source pages, {} processing segments, {} model calls. Result: {} ({}). Elapsed {:.1f}s; {:,} input and {:,} output tokens.".format(
                  smoke["processing"]["source_pages"], smoke["processing"]["segments"], smoke["processing"]["model_calls"],
                  smoke["overall"], smoke["classification"], smoke["metrics"]["inference_seconds"], smoke["metrics"]["input_tokens"], smoke["metrics"]["output_tokens"]), "SmallCopy"),
              p("Semantic failure: the model returned entailment for 67 years by 2033 and 100%, while pages 6/21/22 give 66 years and 80%. Its exact page-22 quotation does not justify the verdict. The actual result is preserved unchanged; quotation provenance alone cannot validate reasoning.", "SmallCopy"),
              p("These few examples do not establish accuracy on unseen booklets. Task B quotation provenance is checked; official Task A evidence-overlap scoring has not been run.", "SmallCopy"), PageBreak()]

    story += [p("03 / Reproduce and present", "SectionTitle"),
              p("Run the local application", "Sub"),
              p("make model-serve<br/># In a second terminal:<br/>make dev", "CodeBlock"),
              p("Open http://localhost:8000. Select a booklet and proposal, enter a claim, then choose Live Apertus. A separate offline walkthrough remains available for explaining the interface without inference."),
              p("Prepare sources and inspect quality", "Sub"),
              p("make ocr-setup<br/>make booklets<br/>make test<br/>make evaluate", "CodeBlock"),
              p("The selected evaluation already exists on this Mac. On a fresh checkout, run make evaluate-prepare first. Changed code/model/inputs require a new evaluation directory. Existing downloads and run records are preserved; details are in the README.", "SmallCopy"),
              table([["Verification", "Observed result"],
                     ["Regression suite", "{} passing tests".format(verification["tests_passed"])],
                     ["Frontend", escape(verification["frontend"])],
                     ["Container", escape(verification["docker"])],
                     ["OCR", escape(verification["ocr"])],
                     ["Organizer endpoint", "Not tested: organizer credentials have not been configured."]], [45 * mm, width - 45 * mm]),
              Spacer(1, 3 * mm), p("Remaining work", "Sub"),
              p("First improve neutral-versus-contradiction reasoning. Then evaluate on a separate split grouped by ballot/booklet, measure Task A evidence overlap and inspect extraction failures. Validate the organizer-served Apertus model. Complete team metadata and submission review; this is a prototype report, not a submitted entry."),
              p("Source and model provenance", "Sub"),
              p('Dataset: <link href="https://huggingface.co/datasets/OSTswiss/MNLIoverSwissVotingBooklets">OSTswiss/MNLIoverSwissVotingBooklets</link>, revision fc2b27600310778da6bbf445651ddbca22d86269. 1,488 upstream rows; 1,153 distinct requests.<br/>Model: <link href="https://huggingface.co/Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF">Colby Apertus v1.5 8B text Q4_K_M</link>, revision 248ec68a63e219e3f061e4c946fc8a20d63b9975. Full artifact SHA and conversion lineage: docs/local-model.md.<br/>Booklets: <link href="https://www.bk.admin.ch/de/sammlung-der-abstimmungsbuechlein-seit-1978">Swiss Federal Chancellery archive</link>. Contract: <link href="https://hackapertus.notion.site/solution-api-guide-ef5b4fec112a834da43101ede56300f5">OST solution API guide</link>. Source code Apache-2.0; documentation CC-BY-4.0; imported data retains its source terms.', "SmallCopy")]

    destination = ROOT / "output/pdf/claimlens-v2-report.pdf"
    destination.parent.mkdir(parents=True, exist_ok=True)

    def decorate(canvas, doc):
        canvas.setStrokeColor(TEAL)
        canvas.setLineWidth(2)
        canvas.line(20 * mm, A4[1] - 15 * mm, A4[0] - 20 * mm, A4[1] - 15 * mm)
        canvas.setFont(font, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, 12 * mm, "CLAIMLENS 0.2 / DEVELOPMENT REPORT / 08 OCT 2026")
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, str(doc.page))

    doc = SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=20 * mm,
                            rightMargin=20 * mm, topMargin=23 * mm, bottomMargin=22 * mm,
                            title="ClaimLens v0.2 - Technical and presentation report", author="ClaimLens project")
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    print(destination)


if __name__ == "__main__":
    main()
