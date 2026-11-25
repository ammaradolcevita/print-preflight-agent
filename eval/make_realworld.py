"""Generate the "real-world style" test set: eval/realworld/files/* + eval/realworld/labels.csv.

The synthetic set (make_fixtures.py) tests one problem at a time on clean files.
This set copies the *structure* real design tools write, which is where a
preflight tool usually breaks: TrimBox/BleedBox, crop marks, rotated pages,
MediaBox not at (0, 0), spot colours, encryption, phone photos, big files.

Real exports (Canva, Illustrator, ...) can be dropped into eval/realworld/real/
and listed in eval/realworld/real_labels.csv; run_realworld.py picks them up too.

expect: pass | warn | fail | cant  (cant = the tool must say it cannot judge the file)
flags:  checks that must report a warn/error (";"-separated), checked only for pass/warn/fail.

Run: python eval/make_realworld.py
"""

from __future__ import annotations

import csv
import io
import random
import sys
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent / "realworld"
sys.path.insert(0, str(ROOT.parent.parent))

from preflight.fixtures import DEFAULT_FONT, image_bytes, px_for
from preflight.specs import mm_to_pt

FILES = ROOT / "files"
BLUE, DARK = (0.15, 0.4, 0.8), (0.12, 0.12, 0.16)
TRIM, BLEED = (85, 55), 3


def _text(page, x_mm, y_mm, s, size=9):
    kw = {"fontsize": size}
    if DEFAULT_FONT:
        kw.update(fontname="embedded", fontfile=DEFAULT_FONT)
    page.insert_text(pymupdf.Point(mm_to_pt(x_mm), mm_to_pt(y_mm)), s, **kw)


def _card_design(page, ox, oy, *, bleed=BLEED, background=BLUE):
    """A clean business card whose trim box starts at (ox, oy) mm on the page."""
    if background is not None:
        r = pymupdf.Rect(*(mm_to_pt(v) for v in (ox - bleed, oy - bleed, ox + TRIM[0] + bleed, oy + TRIM[1] + bleed)))
        page.draw_rect(r, color=None, fill=background)
    img = pymupdf.Rect(*(mm_to_pt(v) for v in (ox + 58, oy + 12, ox + 80, oy + 32)))
    page.insert_image(img, stream=image_bytes((px_for(22, 320), px_for(20, 320)), "CMYK"))
    _text(page, ox + 10, oy + 20, "Sam Jansen", 11)
    _text(page, ox + 10, oy + 27, "graphic design")
    _text(page, ox + 10, oy + 40, "hello@example.com")
    _text(page, ox + 10, oy + 46, "+31 6 0000 0000")


def _crop_marks(page, ox, oy, *, offset=BLEED, length=5):
    """Crop marks in the slug: short black lines on each trim corner, starting outside the bleed."""
    x0, y0, x1, y1 = ox, oy, ox + TRIM[0], oy + TRIM[1]
    for x in (x0, x1):
        for y, d in ((y0, -1), (y1, 1)):
            page.draw_line(*(pymupdf.Point(mm_to_pt(x), mm_to_pt(y + d * (offset + t))) for t in (0, length)),
                           color=(0, 0, 0), width=0.25)
    for y in (y0, y1):
        for x, d in ((x0, -1), (x1, 1)):
            page.draw_line(*(pymupdf.Point(mm_to_pt(x + d * (offset + t)), mm_to_pt(y)) for t in (0, length)),
                           color=(0, 0, 0), width=0.25)


def _boxes(page, ox, oy, bleed=BLEED):
    page.set_bleedbox(pymupdf.Rect(*(mm_to_pt(v) for v in (ox - bleed, oy - bleed, ox + TRIM[0] + bleed,
                                                           oy + TRIM[1] + bleed))))
    page.set_trimbox(pymupdf.Rect(*(mm_to_pt(v) for v in (ox, oy, ox + TRIM[0], oy + TRIM[1]))))


def _new(doc, w_mm, h_mm):
    return doc.new_page(width=mm_to_pt(w_mm), height=mm_to_pt(h_mm))


def _save(doc, name, **kw):
    path = FILES / name
    doc.save(path, **kw)
    doc.close()


# ---------------------------------------------------------------- cases


def canva_print_bleed(name):
    """Canva 'PDF Print' + 'Crop marks and bleed' off, bleed on: page = trim + bleed, TrimBox set."""
    doc = pymupdf.open()
    pg = _new(doc, 91, 61)
    _card_design(pg, 3, 3)
    _boxes(pg, 3, 3)
    _save(doc, name)


def canva_print_no_bleed(name):
    """Canva export without bleed: page = trim, background colour runs to the edge."""
    doc = pymupdf.open()
    pg = _new(doc, *TRIM)
    _card_design(pg, 0, 0, bleed=0)
    _save(doc, name)


def crop_marks_trimbox(name):
    """Bleed + crop marks with TrimBox/BleedBox (InDesign / Canva 'crop marks and bleed')."""
    doc = pymupdf.open()
    slug = 10
    pg = _new(doc, TRIM[0] + 2 * (BLEED + slug), TRIM[1] + 2 * (BLEED + slug))
    o = BLEED + slug
    _card_design(pg, o, o)
    _crop_marks(pg, o, o)
    _boxes(pg, o, o)
    _save(doc, name)


def crop_marks_no_boxes(name, *, bleed=BLEED):
    """Crop marks drawn, but no TrimBox (Word/Affinity/older exporters). Bleed may be missing."""
    doc = pymupdf.open()
    slug = 10
    pg = _new(doc, TRIM[0] + 2 * (BLEED + slug), TRIM[1] + 2 * (BLEED + slug))
    o = BLEED + slug
    _card_design(pg, o, o, bleed=bleed)
    _crop_marks(pg, o, o)
    _save(doc, name)


def trimbox_no_bleed_content(name):
    """Boxes say 3 mm bleed, but the background stops at the trim line (designer forgot to extend it)."""
    doc = pymupdf.open()
    pg = _new(doc, 91, 61)
    _card_design(pg, 3, 3, bleed=0)
    _boxes(pg, 3, 3)
    _save(doc, name)


def illustrator_offset_mediabox(name):
    """Illustrator: MediaBox not starting at (0, 0), TrimBox + BleedBox in the same shifted space."""
    doc = pymupdf.open()
    pg = _new(doc, 91, 61)
    _card_design(pg, 3, 3)
    w, h = pg.rect.width, pg.rect.height
    off = mm_to_pt(20)
    # shift the drawing by `off` and move every box with it (PDF coordinates, origin bottom-left)
    head = doc.get_new_xref()
    doc.update_object(head, "<< >>")
    doc.update_stream(head, f"q 1 0 0 1 {off:.2f} {off:.2f} cm".encode())
    tail = doc.get_new_xref()
    doc.update_object(tail, "<< >>")
    doc.update_stream(tail, b"Q")
    body = " ".join(f"{x} 0 R" for x in pg.get_contents())
    doc.xref_set_key(pg.xref, "Contents", f"[{head} 0 R {body} {tail} 0 R]")
    b = mm_to_pt(BLEED)

    def box(x0, y0, x1, y1):
        return f"[{x0 + off:.2f} {y0 + off:.2f} {x1 + off:.2f} {y1 + off:.2f}]"

    doc.xref_set_key(pg.xref, "MediaBox", box(0, 0, w, h))
    doc.xref_set_key(pg.xref, "CropBox", box(0, 0, w, h))
    doc.xref_set_key(pg.xref, "BleedBox", box(0, 0, w, h))
    doc.xref_set_key(pg.xref, "TrimBox", box(b, b, w - b, h - b))
    _save(doc, name)


def rotated_page(name):
    """Page stored portrait with /Rotate 90 (some RIP/exporters do this), TrimBox in unrotated space."""
    doc = pymupdf.open()
    pg = _new(doc, 91, 61)
    _card_design(pg, 3, 3)
    _boxes(pg, 3, 3)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    # re-create as a portrait page with the landscape design shown via /Rotate
    src = pymupdf.open("pdf", buf.getvalue())
    out = pymupdf.open()
    pg = out.new_page(width=mm_to_pt(61), height=mm_to_pt(91))
    pg.show_pdf_page(pg.rect, src, 0, rotate=-90)
    pg.set_trimbox(pymupdf.Rect(*(mm_to_pt(v) for v in (3, 3, 58, 88))))
    pg.set_rotation(90)
    _save(out, name)


def word_a4(name):
    """Word / Google Docs export: an A4 page with the card drawn in the top-left corner."""
    doc = pymupdf.open()
    pg = _new(doc, 210, 297)
    _card_design(pg, 25, 25, bleed=0)
    _save(doc, name)


def two_sided(name):
    doc = pymupdf.open()
    for back in (False, True):
        pg = _new(doc, 91, 61)
        if back:
            pg.draw_rect(pg.rect, color=None, fill=DARK)
            _text(pg, 30, 33, "example studio", 12)
        else:
            _card_design(pg, 3, 3)
        _boxes(pg, 3, 3)
    _save(doc, name)


def vector_only(name):
    doc = pymupdf.open()
    pg = _new(doc, 91, 61)
    pg.draw_rect(pg.rect, color=None, fill=DARK)
    pg.draw_circle(pymupdf.Point(mm_to_pt(70), mm_to_pt(25)), mm_to_pt(9), color=None, fill=(0.9, 0.7, 0.1))
    _text(pg, 12, 25, "Sam Jansen", 11)
    _text(pg, 12, 45, "hello@example.com")
    _boxes(pg, 3, 3)
    _save(doc, name)


def spot_colour(name):
    """Background in a spot colour (Separation colour space), as brand cards often have."""
    doc = pymupdf.open()
    pg = _new(doc, 91, 61)
    fn = doc.get_new_xref()
    doc.update_object(fn, "<< /FunctionType 2 /Domain [0 1] /C0 [0 0 0 0] /C1 [0.9 0.1 0 0] /N 1 >>")
    cs = doc.get_new_xref()
    doc.update_object(cs, f"[/Separation /PANTONE#20Demo#20Blue /DeviceCMYK {fn} 0 R]")
    _text(pg, 12, 25, "Sam Jansen", 11)  # creates the page's resources and content stream
    _text(pg, 12, 45, "hello@example.com")
    kind, ref = doc.xref_get_key(pg.xref, "Resources")
    res_xref = int(ref.split()[0]) if kind == "xref" else pg.xref
    doc.xref_set_key(res_xref, "ColorSpace", f"<< /CS0 {cs} 0 R >>")
    w, h = pg.rect.width, pg.rect.height
    bg = doc.get_new_xref()
    doc.update_object(bg, "<< >>")
    doc.update_stream(bg, f"q /CS0 cs 1 scn 0 0 {w:.2f} {h:.2f} re f Q".encode())
    rest = " ".join(f"{x} 0 R" for x in pg.get_contents())
    doc.xref_set_key(pg.xref, "Contents", f"[{bg} 0 R {rest}]")
    _boxes(pg, 3, 3)
    _save(doc, name)


def password_pdf(name):
    doc = pymupdf.open()
    _card_design(_new(doc, 91, 61), 3, 3)
    _save(doc, name, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")


def owner_password_only(name):
    """Opens without a password, but printing/editing permissions are restricted (common from Word)."""
    doc = pymupdf.open()
    pg = _new(doc, 91, 61)
    _card_design(pg, 3, 3)
    _boxes(pg, 3, 3)
    _save(doc, name, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner",
          permissions=pymupdf.PDF_PERM_ACCESSIBILITY)


def png_export(name):
    """Canva 'PNG' download: RGB, trim size at 300 dpi, no bleed."""
    img = Image.new("RGB", (px_for(85, 300), px_for(55, 300)), (40, 100, 200))
    img.save(FILES / name, dpi=(300, 300))


def phone_photo(name):
    """A phone photo of a printed card on a table: 4:3, camera EXIF."""
    img = Image.new("RGB", (4032, 3024), (150, 130, 110))
    img.paste((245, 245, 245), (900, 800, 3100, 2200))
    exif = Image.Exif()
    exif[271] = "Apple"  # Make
    exif[272] = "iPhone 15"  # Model
    exif.get_ifd(0x8769)[33434] = 1 / 120  # ExposureTime: only a camera writes this
    img.save(FILES / name, "JPEG", quality=85, exif=exif)


def square_card(name):
    doc = pymupdf.open()
    pg = _new(doc, 61, 61)
    pg.draw_rect(pg.rect, color=None, fill=BLUE)
    _text(pg, 12, 30, "Sam Jansen", 11)
    _save(doc, name)


def card_90x50(name):
    """A 90 x 50 mm card (UK/US-ish size) with bleed, uploaded for the 85 x 55 product."""
    doc = pymupdf.open()
    pg = _new(doc, 96, 56)
    pg.draw_rect(pg.rect, color=None, fill=BLUE)
    _text(pg, 12, 25, "Sam Jansen", 11)
    _save(doc, name)


def large_file(name):
    """~25 MB: a full-bleed photo saved without compression."""
    random.seed(7)
    w, h = px_for(91, 600), px_for(61, 600)
    noise = Image.frombytes("RGB", (w, h), random.randbytes(w * h * 3))
    buf = io.BytesIO()
    noise.save(buf, "PNG", compress_level=0)
    doc = pymupdf.open()
    pg = _new(doc, 91, 61)
    pg.insert_image(pg.rect, stream=buf.getvalue())
    _text(pg, 12, 25, "Sam Jansen", 11)
    _boxes(pg, 3, 3)
    _save(doc, name, deflate=False)


def not_a_pdf(name):
    """A Word file renamed to .pdf (wrong magic bytes)."""
    (FILES / name).write_bytes(b"PK\x03\x04" + b"\x00" * 200)


CASES = [
    # file, product, expect, flags, generator, note
    ("rw_canva_print_bleed.pdf", "business-card", "pass", "", canva_print_bleed, "Canva PDF Print with bleed"),
    ("rw_canva_print_no_bleed.pdf", "business-card", "fail", "bleed", canva_print_no_bleed,
     "Canva PDF Print without bleed, colour to the edge"),
    ("rw_crop_marks_trimbox.pdf", "business-card", "pass", "", crop_marks_trimbox, "bleed + crop marks + TrimBox"),
    ("rw_crop_marks_no_boxes.pdf", "business-card", "pass", "", crop_marks_no_boxes,
     "bleed + crop marks, no TrimBox"),
    ("rw_crop_marks_no_boxes_no_bleed.pdf", "business-card", "fail", "bleed",
     lambda n: crop_marks_no_boxes(n, bleed=0), "crop marks, no TrimBox, design stops at the cut line"),
    ("rw_trimbox_but_no_bleed_content.pdf", "business-card", "fail", "bleed", trimbox_no_bleed_content,
     "TrimBox says bleed, but the background stops at the cut line"),
    ("rw_illustrator_offset_mediabox.pdf", "business-card", "pass", "", illustrator_offset_mediabox,
     "MediaBox not at 0,0; TrimBox + BleedBox"),
    ("rw_rotated_page.pdf", "business-card", "pass", "", rotated_page, "/Rotate 90 with TrimBox"),
    ("rw_word_a4.pdf", "business-card", "fail", "size", word_a4, "card drawn on an A4 page"),
    ("rw_two_sided.pdf", "business-card", "pass", "", two_sided, "front + back"),
    ("rw_vector_only.pdf", "business-card", "pass", "", vector_only, "no pictures at all"),
    ("rw_spot_colour.pdf", "business-card", "warn", "colour", spot_colour,
     "spot colour background: must not be silently 'print-ready'"),
    ("rw_password.pdf", "business-card", "cant", "", password_pdf, "needs a password to open"),
    ("rw_owner_password_only.pdf", "business-card", "pass", "", owner_password_only,
     "opens, but permissions restricted"),
    ("rw_png_export.png", "business-card", "fail", "bleed;colour", png_export, "Canva PNG, RGB, no bleed"),
    ("rw_phone_photo.jpg", "business-card", "cant", "", phone_photo, "photo of a printed card"),
    ("rw_square_card.pdf", "business-card", "fail", "size", square_card, "square card for 85x55"),
    ("rw_card_90x50.pdf", "business-card", "fail", "size", card_90x50, "90x50 card for 85x55"),
    ("rw_large_photo.pdf", "business-card", "warn", "colour", large_file, "10 MB uncompressed RGB photo"),
    ("rw_not_a_pdf.pdf", "business-card", "cant", "", not_a_pdf, "Word file renamed to .pdf"),
]


def main() -> None:
    FILES.mkdir(parents=True, exist_ok=True)
    for name, _pid, _exp, _flags, make, _note in CASES:
        make(name)
    with open(ROOT / "labels.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "product_id", "expect", "flags", "note"])
        for name, pid, exp, flags, _make, note in CASES:
            w.writerow([name, pid, exp, flags, note])
    print(f"{len(CASES)} files in {FILES}")


if __name__ == "__main__":
    main()
