#!/usr/bin/env python3
"""Render the current technical_report.md, preserving the historical V2 report.

ReportLab builds an embedded-font PDF; pypdf enforces the six-page submission
limit and records provenance. Rendering and visual inspection remain required
after final content changes (see the PDF skill and report verification manifest).
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from xml.sax.saxutils import escape

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
NAVY = colors.HexColor("#17383e")
TEAL = colors.HexColor("#087b70")
MUTED = colors.HexColor("#53686c")
PALE = colors.HexColor("#edf5f2")
LINE = colors.HexColor("#dbe5e1")


def normalize(text):
    return text.translate(str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u00a0": " "}))


def fonts():
    roots = [Path("/System/Library/Fonts/Supplemental"), Path("/usr/share/fonts/truetype/dejavu")]
    options = [(roots[0] / "Arial.ttf", roots[0] / "Arial Bold.ttf"),
               (roots[1] / "DejaVuSans.ttf", roots[1] / "DejaVuSans-Bold.ttf")]
    for normal, bold in options:
        if normal.is_file() and bold.is_file():
            pdfmetrics.registerFont(TTFont("ClaimLensBody", str(normal)))
            pdfmetrics.registerFont(TTFont("ClaimLensBold", str(bold)))
            pdfmetrics.registerFontFamily("ClaimLensBody", normal="ClaimLensBody", bold="ClaimLensBold")
            return "ClaimLensBody", "ClaimLensBold"
    raise RuntimeError("Install Arial or DejaVu Sans to render this multilingual report with embedded fonts.")


def markup(text):
    """Small deterministic inline Markdown subset; text is XML-escaped first."""
    output, position = [], 0
    pattern = re.compile(r"`([^`]+)`|\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)]+)\)")
    for match in pattern.finditer(normalize(text)):
        normalized = normalize(text)
        output.append(escape(normalized[position:match.start()]))
        code, bold, label, url = match.groups()
        if code is not None:
            output.append('<font name="Courier" size="8.5">' + escape(code) + "</font>")
        elif bold is not None:
            output.append("<b>" + escape(bold) + "</b>")
        elif url.startswith(("https://", "http://")):
            output.append('<link href="{}" color="#087b70">{}</link>'.format(escape(url, {'"': '&quot;'}), escape(label)))
        else:
            output.append(escape(label) + ' <font size="8.5" color="#53686c">(' + escape(url) + ")</font>")
        position = match.end()
    output.append(escape(normalize(text)[position:]))
    return "".join(output)


def styles(normal, bold):
    body = ParagraphStyle("Body", fontName=normal, fontSize=9.6, leading=13.3,
                          textColor=NAVY, spaceAfter=6.4, allowWidows=0, allowOrphans=0)
    return {"body": body,
            "title": ParagraphStyle("ReportTitle", parent=body, fontName=bold, fontSize=24, leading=28, spaceAfter=11, keepWithNext=True),
            "heading": ParagraphStyle("Heading", parent=body, fontName=bold, fontSize=14, leading=18, textColor=TEAL, spaceBefore=10, spaceAfter=8, keepWithNext=True),
            "subheading": ParagraphStyle("Subheading", parent=body, fontName=bold, fontSize=10.5, leading=14, spaceBefore=7, spaceAfter=6, keepWithNext=True),
            "bullet": ParagraphStyle("Bullet", parent=body, leftIndent=9, firstLineIndent=0, bulletIndent=0, spaceAfter=4),
            "cell": ParagraphStyle("Cell", parent=body, fontSize=9, leading=12.3, spaceAfter=0),
            "header_cell": ParagraphStyle("HeaderCell", parent=body, fontName=bold, fontSize=9, leading=12.3, spaceAfter=0)}


def markdown_story(source, style, width):
    lines, story, index = source.splitlines(), [], 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", cell.replace(" ", "")) for cell in cells):
                    rows.append(cells)
                index += 1
            columns = len(rows[0])
            if any(len(row) != columns for row in rows):
                raise ValueError("Malformed Markdown table in technical report.")
            if columns == 2:
                widths = [width * 0.30, width * 0.70]
            elif columns == 3:
                widths = [width * 0.25, width * 0.10, width * 0.65]
            else:
                widths = [width / columns] * columns
            values = [[Paragraph(markup(cell), style["header_cell" if row_index == 0 else "cell"])
                       for cell in row] for row_index, row in enumerate(rows)]
            table = Table(values, colWidths=widths, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("BACKGROUND", (0, 0), (-1, 0), PALE),
                ("LINEBELOW", (0, 0), (-1, -1), 0.45, LINE)]))
            story.extend([table, Spacer(1, 8)])
            continue
        if line.startswith("### "):
            story.append(Paragraph(markup(line[4:]), style["subheading"]))
        elif line.startswith("## "):
            story.append(Paragraph(markup(line[3:]), style["heading"]))
        elif line.startswith("# "):
            story.append(Paragraph(markup(line[2:]), style["title"]))
        elif line.startswith("- "):
            story.append(Paragraph(markup(line[2:]), style["bullet"], bulletText="-"))
        else:
            paragraph = [line]
            while index + 1 < len(lines) and lines[index + 1].strip() and not lines[index + 1].lstrip().startswith(("#", "|", "- ")):
                index += 1
                paragraph.append(lines[index].strip())
            story.append(Paragraph(markup(" ".join(paragraph)), style["body"]))
        index += 1
    return story


def build(source_path, output):
    source_bytes = source_path.read_bytes()
    source = source_bytes.decode("utf-8")
    normal, bold = fonts()
    style = styles(normal, bold)
    margin = 18 * mm
    width = A4[0] - 2 * margin
    output.parent.mkdir(parents=True, exist_ok=True)
    draft = output.with_name(output.stem + ".building.pdf")
    version = re.search(r"ClaimLens\s+(v[\d.]+)", source)
    version = version.group(1) if version else "current"
    source_digest = hashlib.sha256(source_bytes).hexdigest()

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(TEAL)
        canvas.setLineWidth(1.8)
        canvas.line(margin, A4[1] - 13 * mm, A4[0] - margin, A4[1] - 13 * mm)
        canvas.setFont(normal, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(margin, 11.5 * mm, "CLAIMLENS {} | HACK APERTUS TRACK 2A | TECHNICAL REPORT".format(version))
        canvas.drawRightString(A4[0] - margin, 11.5 * mm, str(doc.page))
        canvas.restoreState()

    document = SimpleDocTemplate(str(draft), pagesize=A4, leftMargin=margin, rightMargin=margin,
        topMargin=19 * mm, bottomMargin=20 * mm, title="ClaimLens {} - Technical report".format(version),
        author="ClaimLens project", subject="Hack Apertus Track 2A OST - source SHA256 " + source_digest)
    document.build(markdown_story(source, style, width), onFirstPage=decorate, onLaterPages=decorate)
    reader = PdfReader(draft)
    if not 1 <= len(reader.pages) <= 6:
        raise ValueError("Report has {} pages; submission limit is six. Inspect {} and revise layout/content.".format(len(reader.pages), draft))
    if source_path.read_bytes() != source_bytes:
        raise ValueError("technical_report.md changed during rendering; rerun from the updated source.")
    draft.replace(output)
    manifest = {"source": str(source_path), "source_sha256": source_digest,
                "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "pdf": str(output), "pdf_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "pages": len(reader.pages), "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "visual_review_required": True,
                "note": "Render every page with pdftoppm and inspect PNGs after the latest content change before delivery."}
    output.with_suffix(".build.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("{} ({} pages; source {})".format(output, len(reader.pages), source_digest[:12]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "technical_report.md")
    parser.add_argument("--output", type=Path, default=ROOT / "output/pdf/claimlens-v4-report.pdf")
    args = parser.parse_args()
    build(args.source.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
