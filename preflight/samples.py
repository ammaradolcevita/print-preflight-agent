"""Designed sample business cards for the demo (85 x 55 mm, warm off-white, EB Garamond, "A/S" monogram).

Same design, so the difference is only in how the file was prepared:
- mistakes=True: no bleed while the paper colour reaches the edge, a small RGB logo,
  typos, an incomplete email, a line too close to the edge and one non-embedded font.
- mistakes=False: 3 mm bleed, CMYK colours, vector monogram, clean text inside the safe zone,
  embedded (subset) fonts.
- mistakes=False, bleed=False: the clean card exported without bleed. Only the bleed is wrong,
  so the automatic fix turns it into a print-ready file.

Contacts are the owner's real ones, published here with his permission (25 Nov 2026).
Font: EB Garamond, SIL Open Font License (preflight/fonts/OFL-EBGaramond.txt).
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from .specs import mm_to_pt

FONT_FILE = Path(__file__).resolve().parent / "fonts" / "EBGaramond.ttf"

PAPER = (0.957, 0.937, 0.906)  # warm off-white: printed, so it needs bleed
INK = (0.17, 0.16, 0.15)  # warm charcoal
GREY = (0.47, 0.45, 0.42)
RULE = (0.72, 0.69, 0.65)

NAME = "Ammar Sodikov"
TITLE = "Data scientist & AI engineer"
TITLE_TYPOS = "Data scientst & AI enginer"
PHONE = "+31 6 8607 3531"
EMAIL = "ammar.sodikov@gmail.com"
LINKEDIN = "linkedin.com/in/ammarsodikov"


def _cmyk(rgb: tuple[float, float, float]) -> tuple[float, float, float, float]:
    """Simple RGB -> CMYK with a black component, so the print-ready card is CMYK throughout."""
    k = 1 - max(rgb)
    if k >= 1:
        return (0.0, 0.0, 0.0, 1.0)
    return tuple(round((1 - c - k) / (1 - k), 4) for c in rgb) + (round(k, 4),)


def _monogram_png(px_w: int, px_h: int) -> bytes:
    """The A/S monogram as a small RGB picture (only used for the card with mistakes)."""
    paper = tuple(int(c * 255) for c in PAPER)
    ink = tuple(int(c * 255) for c in INK)
    img = Image.new("RGB", (px_w, px_h), paper)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(FONT_FILE), int(px_h * 0.62))
    d.text((px_w * 0.26, px_h * 0.36), "A", fill=ink, font=font, anchor="mm")
    d.text((px_w * 0.74, px_h * 0.66), "S", fill=ink, font=font, anchor="mm")
    d.line((px_w * 0.60, px_h * 0.06, px_w * 0.40, px_h * 0.94), fill=tuple(int(c * 255) for c in RULE), width=1)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def business_card(path: str | Path, *, mistakes: bool, bleed: bool | None = None) -> Path:
    path = Path(path)
    b = 0.0 if mistakes or bleed is False else 3.0
    w, h = 85 + 2 * b, 55 + 2 * b
    colour = (lambda c: c) if mistakes else _cmyk  # the clean card is CMYK throughout

    doc = pymupdf.open()
    page = doc.new_page(width=mm_to_pt(w), height=mm_to_pt(h))
    page.insert_font(fontname="garamond", fontfile=str(FONT_FILE))

    def at(x, y):  # trim coordinates (mm) -> page points
        return pymupdf.Point(mm_to_pt(x + b), mm_to_pt(y + b))

    def text(x, y, s, size, col=INK, font="garamond"):
        page.insert_text(at(x, y), s, fontname=font, fontsize=size, color=colour(col))

    page.draw_rect(page.rect, color=None, fill=colour(PAPER))  # paper colour runs into the bleed

    # monogram, top right
    if mistakes:
        box = pymupdf.Rect(at(61, 8), at(79, 30))
        page.insert_image(box, stream=_monogram_png(70, 86))  # 18 x 22 mm at ~100 dpi, RGB
    else:
        text(61.2, 19.5, "A", 24)
        text(70.0, 28.5, "S", 24)
        page.draw_line(at(71.0, 9.5), at(67.0, 29.5), color=colour(RULE), width=0.5)

    # name, title, short rule
    text(9, 29.5, NAME, 16)
    text(9, 34.3, TITLE_TYPOS if mistakes else TITLE, 8, GREY)
    page.draw_line(at(9.2, 37.6), at(16.5, 37.6), color=colour(RULE), width=0.6)

    # contacts: phone, email, LinkedIn (baselines keep every line 5 mm inside the cut)
    if mistakes:
        text(9, 41.8, PHONE, 7, font="helv")  # Helvetica, not embedded
        text(9, 45.2, EMAIL.removesuffix(".com"), 7)  # incomplete email
        text(9, 53.6, LINKEDIN, 7)  # pushed to the very bottom edge
    else:
        text(9, 41.8, PHONE, 7)
        text(9, 45.2, EMAIL, 7)
        text(9, 48.6, LINKEDIN, 7)

    if b:
        page.set_trimbox(pymupdf.Rect(*(mm_to_pt(v) for v in (b, b, b + 85, b + 55))))
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.subset_fonts()  # embed only the glyphs used, like real design tools do
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path


DEMO_SET = {
    "sample_print_ready.pdf": {"mistakes": False},
    "sample_missing_bleed.pdf": {"mistakes": False, "bleed": False},
    "sample_with_mistakes.pdf": {"mistakes": True},
}


def write_demo_set(folder: str | Path) -> list[Path]:
    """The three demo files: print-ready, only bleed missing (fixable), many mistakes."""
    return [business_card(Path(folder) / name, **kw) for name, kw in DEMO_SET.items()]


if __name__ == "__main__":  # python -m preflight.samples samples/
    import sys

    for p in write_demo_set(sys.argv[1] if len(sys.argv) > 1 else "samples"):
        print(p)
