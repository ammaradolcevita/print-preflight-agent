"""Each check gets at least one good file and one bad file.

Business card: trim 85 x 55 mm, bleed 3 mm -> full page 91 x 61 mm.
"""

from __future__ import annotations

import pytest

from preflight import check_file
from preflight.fixtures import make_pdf, make_raster, px_for

BLUE = (0.15, 0.4, 0.8)
FULL = (91, 61)
TRIM = (85, 55)


def by_check(report, name):
    return [f for f in report.findings if f.check == name]


def sev(report, name):
    """The worst severity reported by one check."""
    order = ["pass", "info", "warn", "error"]
    found = by_check(report, name)
    assert found, f"check {name} returned nothing"
    return max((f.severity for f in found), key=order.index)


# ------------------------------------------------------------ perfect file


@pytest.fixture
def perfect(tmp_path):
    return make_pdf(
        tmp_path / "perfect.pdf",
        FULL,
        background=BLUE,
        images=[{"px": (px_for(40, 320), px_for(30, 320)), "rect_mm": (25, 15, 65, 45), "mode": "CMYK"}],
    )


def test_perfect_file_passes(perfect):
    r = check_file(perfect, "business-card")
    assert r.verdict in ("pass",), r.to_markdown()
    for name in ("size", "bleed", "dpi", "colour"):
        assert sev(r, name) == "pass"


# ------------------------------------------------------------ size


def test_size_trim_only_is_accepted(tmp_path):
    p = make_pdf(tmp_path / "trim.pdf", TRIM)
    assert sev(check_file(p, "business-card"), "size") == "pass"


def test_size_landscape_or_portrait_both_ok(tmp_path):
    p = make_pdf(tmp_path / "portrait.pdf", (61, 91))
    assert sev(check_file(p, "business-card"), "size") == "pass"


def test_size_same_shape_other_scale_is_warning(tmp_path):
    p = make_pdf(tmp_path / "double.pdf", (170, 110))
    f = by_check(check_file(p, "business-card"), "size")[0]
    assert f.severity == "warn" and f.fixable


def test_size_wrong_shape_is_error(tmp_path):
    p = make_pdf(tmp_path / "a4.pdf", (210, 297))
    assert sev(check_file(p, "business-card"), "size") == "error"


def test_size_uses_trimbox(tmp_path):
    p = make_pdf(tmp_path / "trimbox.pdf", FULL, background=BLUE, trim_box_mm=(3, 3, 88, 58))
    r = check_file(p, "business-card")
    assert sev(r, "size") == "pass"
    assert sev(r, "bleed") == "pass"


# ------------------------------------------------------------ bleed


def test_no_bleed_with_colour_at_edge_is_error(tmp_path):
    p = make_pdf(tmp_path / "nobleed.pdf", TRIM, background=BLUE)
    f = by_check(check_file(p, "business-card"), "bleed")[0]
    assert f.severity == "error" and f.fixable
    assert f.detail["measured_mm"] == 0


def test_no_bleed_white_edges_is_only_info(tmp_path):
    p = make_pdf(tmp_path / "white.pdf", TRIM, texts=[{"text": "Jane Doe", "at_mm": (15, 30)}])
    assert sev(check_file(p, "business-card"), "bleed") == "info"


def test_small_bleed_is_warning(tmp_path):
    p = make_pdf(tmp_path / "small.pdf", (87, 57), background=BLUE)  # 1 mm bleed
    f = by_check(check_file(p, "business-card"), "bleed")[0]
    assert f.severity == "warn"
    assert f.detail["measured_mm"] == pytest.approx(1.0, abs=0.05)


# ------------------------------------------------------------ dpi


def test_low_dpi_image_is_error(tmp_path):
    p = make_pdf(tmp_path / "lowdpi.pdf", FULL, images=[{"px": (200, 130), "rect_mm": (0, 0, 91, 61)}])
    f = by_check(check_file(p, "business-card"), "dpi")[0]
    assert f.severity == "error"
    assert f.detail["effective_dpi"] < 100


def test_slightly_low_dpi_is_warning(tmp_path):
    px = (px_for(91, 250), px_for(61, 250))
    p = make_pdf(tmp_path / "softdpi.pdf", FULL, images=[{"px": px, "rect_mm": (0, 0, 91, 61)}])
    assert sev(check_file(p, "business-card"), "dpi") == "warn"


def test_tiny_images_are_ignored(tmp_path):
    p = make_pdf(tmp_path / "icon.pdf", FULL, images=[{"px": (8, 8), "rect_mm": (10, 10, 13, 13)}])
    assert sev(check_file(p, "business-card"), "dpi") == "pass"


# ------------------------------------------------------------ colour


def test_rgb_image_is_warning(tmp_path):
    p = make_pdf(
        tmp_path / "rgb.pdf", FULL, images=[{"px": (1100, 740), "rect_mm": (0, 0, 91, 61), "mode": "RGB"}]
    )
    f = by_check(check_file(p, "business-card"), "colour")[0]
    assert f.severity == "warn" and f.fixable


# ------------------------------------------------------------ pages


def test_too_many_pages_is_error(tmp_path):
    p = make_pdf(tmp_path / "three.pdf", FULL, pages=3)
    assert sev(check_file(p, "business-card"), "pages") == "error"


def test_one_page_double_sided_product_is_info(tmp_path):
    p = make_pdf(tmp_path / "one.pdf", FULL)
    assert sev(check_file(p, "business-card"), "pages") == "info"


# ------------------------------------------------------------ PNG / JPG


def test_png_with_bleed_at_300dpi(tmp_path):
    p = make_raster(tmp_path / "card.png", (px_for(91, 300), px_for(61, 300)), "RGB")
    r = check_file(p, "business-card")
    assert sev(r, "size") == "pass"
    assert sev(r, "bleed") == "pass"
    assert sev(r, "dpi") == "pass"
    assert sev(r, "colour") == "warn"  # PNG is always RGB


def test_small_jpg_without_bleed(tmp_path):
    p = make_raster(tmp_path / "card.jpg", (425, 275), "CMYK")  # 85x55 mm at about 127 dpi
    r = check_file(p, "business-card")
    assert sev(r, "bleed") == "error"
    assert sev(r, "dpi") == "error"
    assert sev(r, "colour") == "pass"
    assert r.verdict == "fail"


# ------------------------------------------------------------ bad files


def test_unsupported_file_type(tmp_path):
    p = tmp_path / "card.docx"
    p.write_bytes(b"not really a docx")
    r = check_file(p, "business-card")
    assert r.verdict == "fail" and r.findings[0].check == "file"


def test_damaged_pdf(tmp_path):
    p = tmp_path / "broken.pdf"
    p.write_bytes(b"%PDF-1.7 this is not a real pdf")
    r = check_file(p, "business-card")
    assert r.verdict == "fail"


def test_unknown_product_is_clear_error(perfect):
    with pytest.raises(KeyError, match="Known products"):
        check_file(perfect, "spaceship")


def test_partial_bleed_is_a_bleed_problem_not_a_size_problem(tmp_path):
    """Regression: found by the evaluation set (eval/RESULTS.md)."""
    p = make_pdf(tmp_path / "bleed1.pdf", (87, 57), background=BLUE)
    r = check_file(p, "business-card")
    assert sev(r, "size") == "pass"
    assert sev(r, "bleed") == "warn"
