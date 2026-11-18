"""Two designed sample business cards for the demo: one with typical mistakes, one print-ready.

Same design, so the difference is only in how the file was prepared:
- with_mistakes: no bleed while the colour band reaches the edge, a small RGB logo,
  typos, a broken email, a phone number too close to the edge and one non-embedded font.
- print_ready: 3 mm bleed, a sharp CMYK logo, clean text inside the safe zone, embedded fonts.
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from .specs import mm_to_pt

PAPER = (0.975, 0.965, 0.945)  # warm off-white
INK = (0.10, 0.11, 0.13)
GREY = (0.42, 0.43, 0.46)
BAND = (0.07, 0.18, 0.24)  # deep blue-green
BAND_RGB = tuple(int(c * 255) for c in BAND)
ACCENT = (0.93, 0.42, 0.29)  # coral


def _cmyk(rgb: tuple[float, float, float]) -> tuple[float, float, float, float]:
    """Same simple RGB->CMYK formula Pillow uses for the logo, so the colours match."""
    return (1 - rgb[0], 1 - rgb[1], 1 - rgb[2], 0.0)


def _logo(px: int, mode: str) -> bytes:
    """Minimal monogram: a coral ring with 'AS' on the band colour."""
    img = Image.new("RGB", (px, px), BAND_RGB)
    d = ImageDraw.Draw(img)
    m = px * 0.08
    d.ellipse((m, m, px - m, px - m), outline=(237, 107, 74), width=max(1, px // 22))
    try:
        font = ImageFont.truetype(io.BytesIO(pymupdf.Font("figbo").buffer), int(px * 0.34))
    except Exception:  # noqa: BLE001 - pymupdf-fonts not installed
        font = ImageFont.load_default()
    d.text((px / 2, px / 2), "AS", fill=(250, 246, 240), font=font, anchor="mm")
    buf = io.BytesIO()
    if mode == "CMYK":
        img.convert("CMYK").save(buf, "JPEG", quality=95)
    else:
        img.save(buf, "PNG")
    return buf.getvalue()


def business_card(path: str | Path, *, mistakes: bool) -> Path:
    path = Path(path)
    bleed = 0.0 if mistakes else 3.0
    w, h = 85 + 2 * bleed, 55 + 2 * bleed
    doc = pymupdf.open()
    page = doc.new_page(width=mm_to_pt(w), height=mm_to_pt(h))
    for name in ("figo", "figbo"):  # FiraGO, from the pymupdf-fonts package (embedded in the PDF)
        page.insert_font(fontname=name, fontbuffer=pymupdf.Font(name).buffer)

    def at(x, y):  # position in trim coordinates (mm) -> page points
        return pymupdf.Point(mm_to_pt(x + bleed), mm_to_pt(y + bleed))

    def rect(x0, y0, x1, y1):
        return pymupdf.Rect(mm_to_pt(x0 + bleed), mm_to_pt(y0 + bleed), mm_to_pt(x1 + bleed), mm_to_pt(y1 + bleed))

    # background and the colour band on the right (it runs into the bleed).
    # The print-ready card uses CMYK fills, matching the CMYK logo exactly.
    paper, band = (PAPER, BAND) if mistakes else (_cmyk(PAPER), _cmyk(BAND))
    page.draw_rect(page.rect, color=None, fill=paper)
    page.draw_rect(rect(63, -bleed, 85 + bleed, 55 + bleed), color=None, fill=band)

    # logo in the band
    logo_px = 90 if mistakes else 300  # 18 mm wide: 127 dpi vs 423 dpi
    page.insert_image(rect(65, 18.5, 83, 36.5), stream=_logo(logo_px, "RGB" if mistakes else "CMYK"))

    bold = "figbo"
    reg = "figo"
    page.insert_text(at(8, 17), "Ammar Sodikov", fontname=bold, fontsize=13, color=INK)
    title = "Data scientst & AI enginer" if mistakes else "Data scientist & AI engineer"
    page.insert_text(at(8, 22.5), title, fontname=reg, fontsize=7.5, color=GREY)
    page.draw_line(at(8, 26.5), at(18, 26.5), color=ACCENT, width=1.2)

    email = "ammar.sodikov@gmail" if mistakes else "ammar.sodikov@gmail.com"
    phone = "+31 6 8607 353" if mistakes else "+31 6 8607 3531"
    page.insert_text(at(8, 38), email, fontname=reg, fontsize=7, color=INK)
    if mistakes:
        # website set in Helvetica (not embedded), phone pushed to the very bottom edge
        page.insert_text(at(8, 43), "www.ammaradolcevita.com", fontname="helv", fontsize=7, color=INK)
        page.insert_text(at(8, 53.6), phone, fontname=reg, fontsize=7, color=INK)
    else:
        page.insert_text(at(8, 43), "www.ammaradolcevita.com", fontname=reg, fontsize=7, color=INK)
        page.insert_text(at(8, 48), phone, fontname=reg, fontsize=7, color=INK)

    if bleed:
        b = mm_to_pt(bleed)
        page.set_trimbox(pymupdf.Rect(b, b, page.rect.width - b, page.rect.height - b))
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path
