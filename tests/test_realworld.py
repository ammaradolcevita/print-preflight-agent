"""Regression tests for the real-world style set (eval/make_realworld.py).

Each case is generated into a temp folder and must get the expected verdict,
so the Stage 0 bugs (crop marks, TrimBox without bleed, rotated pages,
MediaBox offsets, spot colours, phone photos) stay fixed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from preflight.fixes import MAX_PIXELS, fix_artwork, fix_dpi
from preflight.report import check_after_fix, check_file
from preflight.specs import get_product

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "eval" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GEN = _load("make_realworld")
RUN = _load("run_realworld")


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    folder = tmp_path_factory.mktemp("realworld")
    GEN.FILES = folder
    for name, *_rest in GEN.CASES:
        make = _rest[3]
        make(name)
    return folder


@pytest.mark.parametrize("case", GEN.CASES, ids=[c[0] for c in GEN.CASES])
def test_realworld_verdict(files, case):
    name, product_id, expect, flags, _make, note = case
    report = check_file(files / name, product_id)
    ok, why = RUN._judge(report, {"expect": expect, "flags": flags})
    assert ok, f"{name} ({note}): {why}"


def test_never_print_ready_when_cannot_check(files):
    for name, product_id, expect, *_ in GEN.CASES:
        if expect == "cant":
            assert check_file(files / name, product_id).verdict == "fail", name


@pytest.mark.parametrize("name", ["rw_crop_marks_no_boxes_no_bleed.pdf", "rw_trimbox_but_no_bleed_content.pdf"])
def test_fix_adds_real_bleed(files, tmp_path, name):
    before = check_file(files / name, "business-card")
    result = fix_artwork(files / name, "business-card", output=tmp_path / "fixed.pdf")
    after = check_after_fix(before, result.output)
    assert after.verdict == "pass", [f.message for f in after.findings if f.severity != "pass"]


def test_fix_dpi_guard_for_large_products():
    rollup, card = get_product("rollup-85x200"), get_product("business-card")
    dpi = fix_dpi(rollup.trim_mm, rollup.spec.bleed_mm, rollup.spec.dpi_min)
    w_in, h_in = ((v + 2 * rollup.spec.bleed_mm) / 25.4 for v in rollup.trim_mm)
    assert rollup.spec.dpi_min <= dpi < 300
    assert w_in * h_in * dpi * dpi <= MAX_PIXELS
    assert fix_dpi(card.trim_mm, card.spec.bleed_mm, card.spec.dpi_min) == 300
