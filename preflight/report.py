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
