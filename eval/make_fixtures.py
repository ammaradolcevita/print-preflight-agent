"""Generate the labelled evaluation set: eval/files/*.pdf|jpg|png + eval/labels.csv.

Each case lists the checks that SHOULD report a problem (warn or error).
Every other check should stay quiet. A few cases are deliberately hard and
expected to be missed today; they are documented in eval/RESULTS.md.

Run: python eval/make_fixtures.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from preflight.fixtures import make_pdf, make_raster, px_for

FILES = ROOT / "files"
BLUE, GREEN, DARK = (0.15, 0.4, 0.8), (0.1, 0.55, 0.35), (0.12, 0.12, 0.16)

CARD_FULL, CARD_TRIM = (91, 61), (85, 55)
A5_FULL, A5_TRIM = (154, 216), (148, 210)


def img(rect, dpi=320, mode="CMYK"):
    w, h = rect[2] - rect[0], rect[3] - rect[1]
    return {"px": (px_for(w, dpi), px_for(h, dpi)), "rect_mm": rect, "mode": mode}


CLEAN_CARD_TEXT = [
    {"text": "Ammar Sodikov", "at_mm": (12, 20), "size": 11},
    {"text": "data and design", "at_mm": (12, 27)},
    {"text": "ammar@studio.nl", "at_mm": (12, 40)},
    {"text": "+31 6 1234 5678", "at_mm": (12, 46)},
]


def card(name, expect, *, page=CARD_FULL, background=BLUE, images=None, texts=None, **kw):
    if texts is None:
        texts = CLEAN_CARD_TEXT
    if images is None:
        images = [img((58, 12, 82, 32))]
    return name, "business-card", expect, lambda p: make_pdf(
        p, page, background=background, images=images, texts=texts, **kw
    )


CASES = [
    # ---------------------------------------------------------------- good files
    card("good_card_full_bleed.pdf", []),
    card("good_card_trimbox.pdf", [], trim_box_mm=(3, 3, 88, 58)),
    card("good_card_portrait.pdf", [], page=(61, 91), images=[img((15, 50, 46, 80))],
         texts=[{"text": "Jane Doe", "at_mm": (12, 20)}]),
    ("good_flyer_a5.pdf", "flyer-a5", [], lambda p: make_pdf(
        p, A5_FULL, background=GREEN, images=[img((20, 30, 134, 120))],
        texts=[{"text": "Summer market", "at_mm": (20, 140), "size": 24},
               {"text": "every saturday in the park", "at_mm": (20, 155), "size": 12}])),
    ("good_poster_a3.pdf", "poster-a3", [], lambda p: make_pdf(
        p, (303, 426), background=DARK, images=[img((40, 40, 263, 300), dpi=310)],
        texts=[{"text": "Open day", "at_mm": (40, 340), "size": 60}])),
    ("good_card_cmyk.jpg", "business-card", [], lambda p: make_raster(p, (px_for(91, 300), px_for(61, 300)), "CMYK")),
    # ---------------------------------------------------------------- tricky but fine
    card("tricky_white_no_bleed.pdf", [], page=CARD_TRIM, background=None, images=[],
         texts=[{"text": "Jane Doe", "at_mm": (12, 20)}, {"text": "jane@doe.com", "at_mm": (12, 30)}]),
    card("tricky_vector_only.pdf", [], images=[]),
    card("tricky_dpi_rounding_299.pdf", [], images=[{"px": (1075, 720), "rect_mm": (0, 0, 91, 61), "mode": "CMYK"}]),
    card("tricky_names_and_dutch.pdf", [], texts=[
        {"text": "Nurmukhammad Sodikov", "at_mm": (12, 18)},
        {"text": "grafisch ontwerp en drukwerk", "at_mm": (12, 25)},
        {"text": "Enschede, Overijssel", "at_mm": (12, 32)},
        {"text": "www.studio.nl", "at_mm": (12, 40)},
        {"text": "06 1234 5678", "at_mm": (12, 46)},
    ]),
    ("tricky_rollup_100dpi.pdf", "rollup-85x200", [], lambda p: make_pdf(
        p, (860, 2010), background=BLUE, images=[img((100, 300, 760, 1100), dpi=110)],
        texts=[{"text": "Visit our booth", "at_mm": (120, 1300), "size": 120}])),
    # ---------------------------------------------------------------- bleed
    card("bleed_none_card.pdf", ["bleed"], page=CARD_TRIM, images=[img((52, 9, 79, 29))],
         texts=[{"text": "Jane Doe", "at_mm": (9, 20)}]),
    ("bleed_none_flyer.pdf", "flyer-a5", ["bleed"], lambda p: make_pdf(
        p, A5_TRIM, background=GREEN, texts=[{"text": "Summer market", "at_mm": (20, 100), "size": 20}])),
    ("bleed_none_postcard.jpg", "postcard-a6", ["bleed"], lambda p: make_raster(
        p, (px_for(148, 300), px_for(105, 300)), "CMYK")),
    card("bleed_1mm.pdf", ["bleed"], page=(87, 57), images=[img((54, 10, 80, 30))],
         texts=[{"text": "Jane Doe", "at_mm": (10, 20)}]),
    card("bleed_2mm.pdf", ["bleed"], page=(89, 59), images=[img((55, 11, 81, 31))],
         texts=[{"text": "Jane Doe", "at_mm": (11, 20)}]),
    # ---------------------------------------------------------------- resolution
    card("dpi_150_photo.pdf", ["dpi"], images=[img((0, 0, 91, 61), dpi=150)]),
    card("dpi_96_logo.pdf", ["dpi"], images=[img((58, 12, 82, 32), dpi=96)]),
    card("dpi_250_soft.pdf", ["dpi"], images=[img((0, 0, 91, 61), dpi=250)]),
    # ---------------------------------------------------------------- colour
    card("rgb_photo.pdf", ["colour"], images=[img((0, 0, 91, 61), mode="RGB")]),
    card("rgb_logo.pdf", ["colour"], images=[img((58, 12, 82, 32), mode="RGB")]),
    ("rgb_png_card.png", "business-card", ["colour"], lambda p: make_raster(
        p, (px_for(91, 300), px_for(61, 300)), "RGB")),
    # ---------------------------------------------------------------- safe zone
    card("safe_text_at_cut.pdf", ["safezone"], texts=[{"text": "Jane Doe", "at_mm": (12, 59)}]),
    card("safe_text_4mm.pdf", ["safezone"], texts=[{"text": "Jane Doe", "at_mm": (7, 30)}]),
    card("safe_text_outside.pdf", ["safezone"], texts=[{"text": "jane@doe.com", "at_mm": (70, 30)}]),
    # ---------------------------------------------------------------- size and pages
    card("size_a4_for_card.pdf", ["size"], page=(210, 297), images=[], texts=[]),
    ("size_square_flyer.pdf", "flyer-a5", ["size"], lambda p: make_pdf(p, (150, 150), background=GREEN)),
    card("size_double_scale.pdf", ["size"], page=(182, 122), images=[], texts=[]),
    card("pages_three.pdf", ["pages"], pages=3),
    ("pages_poster_two.pdf", "poster-a3", ["pages"], lambda p: make_pdf(p, (303, 426), background=DARK, pages=2)),
    # ---------------------------------------------------------------- fonts
    card("font_not_embedded.pdf", ["fonts"], texts=[{"text": "Jane Doe", "at_mm": (12, 20), "embed": False}]),
    ("font_not_embedded_flyer.pdf", "flyer-a5", ["fonts"], lambda p: make_pdf(
        p, A5_FULL, background=GREEN, texts=[{"text": "Summer market", "at_mm": (20, 100), "size": 20,
                                              "embed": False}])),
    # ---------------------------------------------------------------- text
    card("text_typo_designer.pdf", ["text"], texts=[{"text": "graphic desinger", "at_mm": (12, 25)}]),
    card("text_typo_management.pdf", ["text"], texts=[{"text": "project managment", "at_mm": (12, 25)}]),
    card("text_bad_email.pdf", ["text"], texts=[{"text": "jane@doe", "at_mm": (12, 25)}]),
    card("text_bad_phone.pdf", ["text"], texts=[{"text": "+31 6 1234 567", "at_mm": (12, 25)}]),
    card("text_bad_url.pdf", ["text"], texts=[{"text": "www.janedoe", "at_mm": (12, 25)}]),
    # ---------------------------------------------------------------- two problems at once
    card("combo_nobleed_lowdpi.pdf", ["bleed", "dpi"], page=CARD_TRIM, images=[img((0, 0, 85, 55), dpi=120)],
         texts=[]),
    card("combo_rgb_typo.pdf", ["colour", "text"], images=[img((58, 12, 82, 32), mode="RGB")],
         texts=[{"text": "graphic desinger", "at_mm": (12, 25)}]),
    card("combo_font_edge.pdf", ["fonts", "safezone"],
         texts=[{"text": "Jane Doe", "at_mm": (12, 59), "embed": False}]),
    # ---------------------------------------------------------------- known limits (expected misses)
    card("limit_rgb_vector_background.pdf", ["colour"], images=[]),  # RGB vector fill, no picture
    ("limit_typo_inside_image.png", "business-card", ["colour", "text"], None),  # text baked into pixels
]


def _typo_png(path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    from preflight.fixtures import DEFAULT_FONT

    w, h = px_for(91, 300), px_for(61, 300)
    im = Image.new("RGB", (w, h), (40, 110, 200))
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(DEFAULT_FONT, 70) if DEFAULT_FONT else None
    d.text((150, 300), "graphic desinger", fill="white", font=font)
    im.save(path)


def main() -> None:
    FILES.mkdir(parents=True, exist_ok=True)
    for old in FILES.iterdir():
        old.unlink()
    rows = []
    for name, product, expect, build in CASES:
        path = FILES / name
        if build is None:
            _typo_png(path)
        else:
            build(path)
        rows.append({"file": name, "product_id": product, "expected": ";".join(expect)})
    with open(ROOT / "labels.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "product_id", "expected"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} labelled files in {FILES}")


if __name__ == "__main__":
    main()
