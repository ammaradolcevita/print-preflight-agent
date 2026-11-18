"""Safe zone, fonts and text checks."""

from __future__ import annotations

from preflight import check_file
from preflight.fixtures import make_pdf

FULL = (91, 61)  # business card with 3 mm bleed; cut line is 3 mm in from the page edge


def findings(report, name):
    return [f for f in report.findings if f.check == name]


def worst(report, name):
    order = ["pass", "info", "warn", "error"]
    return max((f.severity for f in findings(report, name)), key=order.index)


def card(tmp_path, texts, name="card.pdf"):
    return make_pdf(tmp_path / name, FULL, texts=texts)


# ------------------------------------------------------------ safe zone


def test_text_well_inside_passes(tmp_path):
    r = check_file(card(tmp_path, [{"text": "Jane Doe", "at_mm": (15, 30)}]), "business-card")
    assert worst(r, "safezone") == "pass"


def test_text_at_cut_line_is_error(tmp_path):
    # baseline 59 mm on a 61 mm page: text bottom is about 1 mm past the cut line (58 mm)
    r = check_file(card(tmp_path, [{"text": "Jane Doe", "at_mm": (15, 59)}]), "business-card")
    f = findings(r, "safezone")[0]
    assert f.severity == "error" and f.bbox_mm is not None


def test_text_four_mm_from_cut_is_warning(tmp_path):
    # left edge of text at 7 mm on the page = 4 mm from the cut line at 3 mm
    r = check_file(card(tmp_path, [{"text": "Jane Doe", "at_mm": (7, 30)}]), "business-card")
    assert worst(r, "safezone") == "warn"


# ------------------------------------------------------------ fonts


def test_embedded_font_passes(tmp_path):
    r = check_file(card(tmp_path, [{"text": "Jane Doe", "at_mm": (15, 30)}]), "business-card")
    assert worst(r, "fonts") == "pass"


def test_missing_font_is_error(tmp_path):
    r = check_file(card(tmp_path, [{"text": "Jane Doe", "at_mm": (15, 30), "embed": False}]), "business-card")
    f = findings(r, "fonts")[0]
    assert f.severity == "error" and "Helvetica" in f.message


# ------------------------------------------------------------ text


def test_clean_card_text_passes(tmp_path):
    texts = [
        {"text": "Ammar Sodikov", "at_mm": (12, 20)},
        {"text": "graphic designer", "at_mm": (12, 26)},
        {"text": "ammar@studio.nl", "at_mm": (12, 34)},
        {"text": "+31 6 1234 5678", "at_mm": (12, 40)},
        {"text": "www.studio.nl", "at_mm": (12, 46)},
    ]
    r = check_file(card(tmp_path, texts), "business-card")
    assert worst(r, "text") == "pass", r.to_markdown()


def test_typo_is_flagged_with_suggestion(tmp_path):
    r = check_file(card(tmp_path, [{"text": "graphic desinger", "at_mm": (12, 26)}]), "business-card")
    f = findings(r, "text")[0]
    assert f.severity == "warn" and f.detail["word"] == "desinger"
    assert f.detail["suggestion"] == "designer"


def test_names_are_not_typos(tmp_path):
    r = check_file(card(tmp_path, [{"text": "Nurmukhammad Sodikov Enschede", "at_mm": (12, 26)}]), "business-card")
    assert worst(r, "text") == "pass"


def test_dutch_words_are_not_typos(tmp_path):
    r = check_file(card(tmp_path, [{"text": "grafisch ontwerp en drukwerk", "at_mm": (12, 26)}]), "business-card")
    assert worst(r, "text") == "pass"


def test_broken_email_is_flagged(tmp_path):
    r = check_file(card(tmp_path, [{"text": "ammar@studio", "at_mm": (12, 34)}]), "business-card")
    f = findings(r, "text")[0]
    assert f.detail["kind"] == "email"


def test_short_dutch_number_is_flagged(tmp_path):
    r = check_file(card(tmp_path, [{"text": "+31 6 1234 567", "at_mm": (12, 40)}]), "business-card")
    f = findings(r, "text")[0]
    assert f.detail["kind"] == "phone" and "8 digits" in f.message


def test_plus31_with_zero_is_flagged(tmp_path):
    r = check_file(card(tmp_path, [{"text": "+31 06 1234 5678", "at_mm": (12, 40)}]), "business-card")
    assert findings(r, "text")[0].detail["kind"] == "phone"


def test_incomplete_web_address(tmp_path):
    r = check_file(card(tmp_path, [{"text": "www.studio", "at_mm": (12, 46)}]), "business-card")
    assert findings(r, "text")[0].detail["kind"] == "url"
