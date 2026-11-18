"""Run every check on the labelled set and measure precision and recall per check.

A check "flags" a file when it reports a warn or error.
- TP: flagged and expected      - FP: flagged but not expected (false alarm)
- FN: expected but not flagged  (miss)
precision = TP / (TP + FP)   "when it complains, is it right?"
recall    = TP / (TP + FN)   "of the real problems, how many does it catch?"

Run: python eval/run_eval.py   (writes eval/RESULTS.md)
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from preflight.report import check_file

CHECKS = ["pages", "size", "bleed", "dpi", "colour", "safezone", "fonts", "text"]


def main() -> None:
    with open(ROOT / "labels.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    stats = {c: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for c in CHECKS}
    misses, false_alarms, times = [], [], []
    verdict_ok = 0

    for row in rows:
        expected = set(filter(None, row["expected"].split(";")))
        start = time.perf_counter()
        report = check_file(ROOT / "files" / row["file"], row["product_id"])
        times.append(time.perf_counter() - start)
        flagged = {f.check for f in report.findings if f.severity in ("warn", "error")}
        for c in CHECKS:
            e, p = c in expected, c in flagged
            key = "tp" if e and p else "fp" if p else "fn" if e else "tn"
            stats[c][key] += 1
            if key == "fn":
                misses.append((row["file"], c))
            if key == "fp":
                msg = next(f.message for f in report.findings if f.check == c and f.severity in ("warn", "error"))
                false_alarms.append((row["file"], c, msg))
        # a clean file should not fail, a file with problems should not pass
        if (not expected and report.verdict != "fail") or (expected and report.verdict != "pass"):
            verdict_ok += 1

    def pct(a, b):
        return f"{a / b:.2f}" if b else "–"

    lines = [
        "# Evaluation results",
        "",
        f"{len(rows)} labelled files · average {sum(times) / len(times) * 1000:.0f} ms per file · "
        f"correct overall verdict on {verdict_ok}/{len(rows)} files",
        "",
        "| Check | TP | FP | FN | TN | Precision | Recall |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    tot = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for c in CHECKS:
        s = stats[c]
        for k in tot:
            tot[k] += s[k]
        lines.append(f"| {c} | {s['tp']} | {s['fp']} | {s['fn']} | {s['tn']} | "
                     f"{pct(s['tp'], s['tp'] + s['fp'])} | {pct(s['tp'], s['tp'] + s['fn'])} |")
    lines.append(f"| **all** | {tot['tp']} | {tot['fp']} | {tot['fn']} | {tot['tn']} | "
                 f"**{pct(tot['tp'], tot['tp'] + tot['fp'])}** | **{pct(tot['tp'], tot['tp'] + tot['fn'])}** |")
    lines += ["", "## Misses (expected problem not reported)", ""]
    lines += [f"- `{f}` — {c}" for f, c in misses] or ["None."]
    lines += ["", "## False alarms (problem reported on a fine file)", ""]
    lines += [f"- `{f}` — {c}: {m}" for f, c, m in false_alarms] or ["None."]
    out = "\n".join(lines) + "\n"
    (ROOT / "RESULTS_TABLE.md").write_text(out, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
