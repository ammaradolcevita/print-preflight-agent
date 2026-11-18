"""Apply typo corrections the customer accepted, directly in the PDF.

How, in plain words:
1. Find each line of text (a "span") that contains the typo.
2. Remove only that line's text with a PDF redaction: backgrounds, shapes and
   images under it are kept.
3. Write the corrected line at exactly the same spot, size and colour.
   The original font is reused when it has every letter needed; fonts in PDFs are
   often "subsets" with only the letters the designer typed, so when a letter is
   missing we fall back to FiraGO (embedded) and say so.

Only for PDFs with live text. The tool never changes text unless the customer
accepted the correction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

FALLBACK_FONT = "figo"


@dataclass
class Correction:
    page: int  # 1-based
    word: str
    replacement: str


@dataclass
class TextFixResult:
    output: str
    changes: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _rgb(color_int: int) -> tuple[float, float, float]:
    return ((color_int >> 16 & 255) / 255, (color_int >> 8 & 255) / 255, (color_int & 255) / 255)


def _font_for(doc, page, span, text: str) -> tuple[str, pymupdf.Font, bool]:
    """(fontname to use on the page, Font object, True if it is the original font)."""
    for xref, ext, _type, basefont, *_ in page.get_fonts(full=True):
        if basefont.split("+")[-1] != span["font"].split("+")[-1] or ext == "n/a":
            continue
        try:
            _, _, _, buffer = doc.extract_font(xref)
            font = pymupdf.Font(fontbuffer=buffer)
            if all(font.has_glyph(ord(c)) for c in text if not c.isspace()):
                fontname = f"orig{xref}"
                page.insert_font(fontname=fontname, fontbuffer=buffer)
                return fontname, font, True
        except Exception:  # noqa: BLE001 - unusable font: fall back below
            pass
        break
    font = pymupdf.Font(FALLBACK_FONT)
    page.insert_font(fontname=FALLBACK_FONT, fontbuffer=font.buffer)
    return FALLBACK_FONT, font, False


def apply_corrections(path: str | Path, corrections: list[Correction], output: str | Path | None = None) -> TextFixResult:
    path = Path(path)
    output = Path(output) if output else path.with_name(f"{path.stem}_corrected.pdf")
    result = TextFixResult(output=str(output))
    if path.suffix.lower() != ".pdf":
        result.skipped.append("Text can only be corrected in PDF files.")
        return result

    doc = pymupdf.open(path)
    for pno in sorted({c.page for c in corrections}):
        page = doc[pno - 1]
        todo = [c for c in corrections if c.page == pno]
        # collect the spans to rewrite first, then redact, then write (redaction changes the page)
        rewrites = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    new_text = span["text"]
                    applied = []
                    for c in todo:
                        pattern = rf"\b{re.escape(c.word)}\b"
                        if re.search(pattern, new_text):
                            new_text = re.sub(pattern, c.replacement, new_text)
                            applied.append(c)
                    if applied:
                        rewrites.append((span, new_text, applied))
        if not rewrites:
            continue
        for span, _, _ in rewrites:
            page.add_redact_annot(pymupdf.Rect(span["bbox"]), fill=False)
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )
        for span, new_text, applied in rewrites:
            fontname, font, original = _font_for(doc, page, span, new_text)
            page.insert_text(
                pymupdf.Point(span["origin"]), new_text, fontname=fontname,
                fontsize=span["size"], color=_rgb(span["color"]),
            )
            for c in applied:
                same_family = "fira" in span["font"].lower()
                note = "" if original or same_family else " (set in FiraGO: the original font did not include every letter)"
                result.changes.append(f'Page {pno}: "{c.word}" → "{c.replacement}"{note}.')
    doc.save(output, garbage=3, deflate=True)
    doc.close()
    return result
