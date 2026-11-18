"""Run all checks on a file and build one report."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .checks import CHECKS, Context
from .loader import LoadError, load
from .models import Finding
from .specs import get_product

VERDICT_TEXT = {
    "pass": "Print-ready",
    "warn": "Printable, but check the warnings",
    "fail": "Needs fixing before print",
}


@dataclass
class Report:
    file: str
    product_id: str
    product_name: str
    verdict: str  # "pass" | "warn" | "fail"
    findings: list[Finding] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def verdict_text(self) -> str:
        return VERDICT_TEXT[self.verdict]

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "verdict": self.verdict,
            "verdict_text": self.verdict_text,
            "seconds": round(self.seconds, 2),
            "findings": [f.to_dict() for f in self.findings],
        }

    def to_markdown(self) -> str:
        icon = {"pass": "✅", "info": "ℹ️", "warn": "⚠️", "error": "❌"}
        badge = {"pass": "✅", "warn": "⚠️", "fail": "❌"}[self.verdict]
        lines = [
            f"## {badge} {self.verdict_text}",
            f"*{Path(self.file).name}* checked as **{self.product_name}** in {self.seconds:.1f} s",
            "",
        ]
        order = {"error": 0, "warn": 1, "info": 2, "pass": 3}
        for f in sorted(self.findings, key=lambda f: order[f.severity]):
            where = f" (page {f.page})" if f.page else ""
            fix = " — *can be fixed automatically*" if f.fixable and f.severity in ("warn", "error") else ""
            lines.append(f"- {icon[f.severity]} **{f.check}**{where}: {f.message}{fix}")
        return "\n".join(lines)


def verdict_of(findings: list[Finding]) -> str:
    severities = {f.severity for f in findings}
    if "error" in severities:
        return "fail"
    if "warn" in severities:
        return "warn"
    return "pass"


def check_file(path: str | Path, product_id: str) -> Report:
    start = time.perf_counter()
    product = get_product(product_id)
    try:
        artwork = load(path, product)
    except LoadError as exc:
        findings = [Finding("file", "error", str(exc))]
    else:
        ctx = Context(artwork=artwork, product=product)
        findings = [Finding("file", "pass", f"File opened ({artwork.kind.upper()}).")]
        for check in CHECKS:
            findings.extend(check.check(ctx))
    return Report(
        file=str(path),
        product_id=product.id,
        product_name=product.name,
        verdict=verdict_of(findings),
        findings=findings,
        seconds=time.perf_counter() - start,
    )


# Checks whose problems survive an automatic fix. Re-checking the fixed file
# cannot see them any more (the page is now one 300-dpi image), so we carry
# them over from the original report instead of pretending they are gone.
NOT_FIXED_BY_AUTOFIX = ("dpi", "safezone", "text")


def check_after_fix(original: Report, fixed_path: str | Path) -> Report:
    fixed = check_file(fixed_path, original.product_id)
    kept = [f for f in fixed.findings if f.check not in NOT_FIXED_BY_AUTOFIX]
    carried = [_move_to_fixed_page(f, original, fixed_path) for f in original.findings
               if f.check in NOT_FIXED_BY_AUTOFIX]
    findings = kept + carried
    return Report(
        file=str(fixed_path),
        product_id=original.product_id,
        product_name=original.product_name,
        verdict=verdict_of(findings),
        findings=findings,
        seconds=fixed.seconds,
    )


def _move_to_fixed_page(f: Finding, original: Report, fixed_path: str | Path) -> Finding:
    """Shift a marker box from the original page to the same spot on the fixed page."""
    if f.bbox_mm is None or f.page is None:
        return f
    from dataclasses import replace

    from .checks.base import trim_rect_on_page

    product = get_product(original.product_id)
    try:
        before = load(original.file, product).pages[f.page - 1]
        after = load(fixed_path, product).pages[f.page - 1]
    except (LoadError, IndexError):
        return f
    a, b = trim_rect_on_page(before, product), trim_rect_on_page(after, product)
    if not a or not b:
        return f
    (ax0, ay0, _, _), sa = a
    (bx0, by0, _, _), sb = b
    k = sb / sa
    x0, y0, x1, y1 = f.bbox_mm
    moved = (bx0 + (x0 - ax0) * k, by0 + (y0 - ay0) * k, bx0 + (x1 - ax0) * k, by0 + (y1 - ay0) * k)
    return replace(f, bbox_mm=moved)
