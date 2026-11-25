"""Run check + fix on the real-world style set and report crashes and wrong verdicts.

A file is "correct" when:
- expect pass/warn/fail: the verdict matches and every expected check is flagged;
- expect cant: the tool says honestly that it cannot judge the file (a 'file' error), never a verdict.
Every file that is not print-ready is also run through fix_artwork; a crash there counts as a crash.

Run: python eval/make_realworld.py && python eval/run_realworld.py  (writes eval/realworld/RESULTS_TABLE.md)
"""

from __future__ import annotations

import csv
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "realworld"
sys.path.insert(0, str(ROOT.parent.parent))

from preflight.fixes import fix_artwork
from preflight.report import check_after_fix, check_file


def _rows() -> list[tuple[Path, dict]]:
    out = []
    for folder, labels in ((ROOT / "files", ROOT / "labels.csv"), (ROOT / "real", ROOT / "real" / "labels.csv")):
        if labels.exists():
            with open(labels, encoding="utf-8") as f:
                out += [(folder / r["file"], r) for r in csv.DictReader(f)]
    return out


def _judge(report, row) -> tuple[bool, str]:
    flagged = {f.check for f in report.findings if f.severity in ("warn", "error")}
    cant = any(f.check == "file" and f.severity == "error" for f in report.findings)
    if row["expect"] == "cant":
        return cant, "says it cannot check" if cant else f"gave verdict '{report.verdict}' instead"
    need = set(filter(None, row["flags"].split(";")))
    if cant:
        return False, "said it cannot check"
    if report.verdict != row["expect"]:
        return False, f"verdict '{report.verdict}', expected '{row['expect']}' (flagged: {', '.join(sorted(flagged))})"
    if not need <= flagged:
        return False, f"missed {', '.join(sorted(need - flagged))}"
    extra = flagged - need
    return True, f"extra: {', '.join(sorted(extra))}" if extra else ""


def main() -> None:
    rows = _rows()
    lines = ["# Real-world style set: results", "",
             "| File | Expected | Verdict | OK | Check ms | Fix | Note |", "|---|---|---|:-:|---:|---|---|"]
    ok = crashes = 0
    with tempfile.TemporaryDirectory() as tmp:
        for path, row in rows:
            fix_note = "–"
            try:
                t = time.perf_counter()
                report = check_file(path, row["product_id"])
                ms = (time.perf_counter() - t) * 1000
                good, why = _judge(report, row)
                opened = not any(f.check == "file" and f.severity == "error" for f in report.findings)
                if opened and report.verdict != "pass" and any(f.fixable for f in report.findings):
                    try:
                        res = fix_artwork(path, row["product_id"], output=Path(tmp) / f"{path.stem}_fixed.pdf")
                        if res.skipped:
                            fix_note = "skipped: " + res.skipped[0]
                        else:
                            after = check_after_fix(report, res.output)
                            fix_note = f"{report.verdict} → {after.verdict}"
                    except Exception as exc:  # noqa: BLE001
                        crashes += 1
                        good = False
                        fix_note = f"**CRASH** {type(exc).__name__}: {exc}"
            except Exception as exc:  # noqa: BLE001
                crashes += 1
                good, why, ms, report = False, f"**CRASH** {type(exc).__name__}: {exc}", 0, None
                traceback.print_exc()
            ok += good
            verdict = report.verdict if report else "crash"
            lines.append(f"| `{path.name}` | {row['expect']} | {verdict} | {'✅' if good else '❌'} | {ms:.0f} | "
                         f"{fix_note} | {why or row.get('note', '')} |")
    lines[1] = f"**{ok}/{len(rows)} correct · {crashes} crashes**\n"
    out = "\n".join(lines) + "\n"
    (ROOT / "RESULTS_TABLE.md").write_text(out, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
