"""Every message a customer can see in the Studio panel has a Dutch version.

Runs both evaluation sets (synthetic and real-world style) plus the demo samples,
collects every warn/error message and every fix text, and checks each one has a pattern.
A new message in a check without a Dutch pattern makes this test fail.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from mcp_server.i18n import is_translated, translate
from preflight.fixes import fix_artwork
from preflight.report import check_file
from preflight.samples import write_demo_set

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"i18n_{name}", ROOT / "eval" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def all_files(tmp_path_factory):
    folder = tmp_path_factory.mktemp("i18n")
    files: list[tuple[Path, str]] = []
    synthetic = _load("make_fixtures")
    for name, product, _expect, build in synthetic.CASES:
        path = folder / name
        synthetic._typo_png(path) if build is None else build(path)
        files.append((path, product))
    realworld = _load("make_realworld")
    realworld.FILES = folder
    for name, product, _exp, _flags, make, _note in realworld.CASES:
        make(name)
        files.append((folder / name, product))
    files += [(p, "flyer-a5" if "flyer" in p.name else "business-card") for p in write_demo_set(folder / "samples")]
    return files


def test_every_issue_and_fix_text_has_dutch(all_files, tmp_path):
    missing = set()
    for path, product in all_files:
        report = check_file(path, product)
        for f in report.findings:
            if f.severity in ("warn", "error") and not is_translated(f.message):
                missing.add(f.message)
        opened = not any(f.check == "file" and f.severity == "error" for f in report.findings)
        if opened and report.verdict != "pass" and product in ("business-card", "flyer-a5", "flyer-a6"):
            res = fix_artwork(path, product, output=tmp_path / f"{path.stem}.pdf")
            missing |= {t for t in res.changes + res.skipped if not is_translated(t)}
    assert not missing, "No Dutch version for:\n" + "\n".join(sorted(missing))


def test_translation_keeps_numbers_and_quotes():
    en = '"hello@example" does not look like a valid email address. Please check it.'
    assert translate(en, "nl") == '"hello@example" lijkt geen geldig e-mailadres. Controleer het even.'
    sides = ("Your file has room for bleed, but the design stops at the cut line (left, bottom). After cutting, "
             "a thin white line may show. Extend the background 3 mm past the cut line.")
    assert "(links, onder)" in translate(sides, "nl")
    assert translate(en, "en") == en
    assert translate("A brand new message.", "nl") == "A brand new message."  # never dropped


def test_typo_change_texts_have_dutch(tmp_path):
    from preflight.samples import business_card
    from preflight.textfix import Correction, apply_corrections

    card = business_card(tmp_path / "card.pdf", mistakes=True)
    res = apply_corrections(card, [Correction(1, "scientst", "scientist")], output=tmp_path / "fixed.pdf")
    assert res.changes and all(is_translated(c) for c in res.changes)
    assert is_translated('Page 1: "x" → "y" (set in FiraGO: the original font did not include every letter).')
