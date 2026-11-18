"""Check 9: the text itself - typos and broken contact details.

HelloPrint states on its artwork-check page: "we don't check grammar and spelling".
A typo in an email address on 500 business cards is a costly mistake that
size, bleed and colour checks will never catch.

Rules (deterministic, no LLM needed):
- emails, web addresses and phone numbers must have a valid shape;
- lowercase words of 4+ letters that are in neither the English nor the Dutch
  dictionary are reported as *possible* typos, with a suggestion.
  Capitalised words are skipped: they are usually names (Sodikov, Rotterdam).
We only suggest corrections; we never change the customer's text.
"""

from __future__ import annotations

import re
from functools import lru_cache

from ..models import Finding
from .base import Context

NAME = "text"

EMAIL_OK = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)*\.[A-Za-z]{2,}$")
URL_OK = re.compile(r"^(https?://)?(www\.)?[\w-]+(\.[\w-]+)*\.[A-Za-z]{2,}(/\S*)?$")
PHONE_LIKE = re.compile(r"(?<![\w@])\+?\(?\d[\d\s\-().]{6,}\d")
WORD = re.compile(r"[A-Za-zÀ-ÿ]+(?:'[A-Za-z]+)?")
MAX_TYPOS = 5


@lru_cache(maxsize=1)
def _dictionaries():
    from spellchecker import SpellChecker

    return SpellChecker(language="en"), SpellChecker(language="nl")


def _contact_findings(token: str, pno: int, bbox) -> Finding | None:
    t = token.strip(".,;:()[]<>\"'")
    if "@" in t:
        if not EMAIL_OK.match(t):
            return Finding(
                NAME, "warn", f"\"{t}\" does not look like a valid email address. Please check it.",
                {"value": t, "kind": "email"}, page=pno, bbox_mm=bbox,
            )
    elif t.lower().startswith(("www", "http")):
        if not URL_OK.match(t) or t.lower().startswith("www") and t.count(".") < 2:
            return Finding(
                NAME, "warn", f"\"{t}\" does not look like a complete web address. Please check it.",
                {"value": t, "kind": "url"}, page=pno, bbox_mm=bbox,
            )
    return None


def _phone_findings(text: str, pno: int, bbox) -> list[Finding]:
    out = []
    for m in PHONE_LIKE.finditer(text):
        raw = m.group(0).strip()
        digits = re.sub(r"\D", "", raw)
        problem = None
        if raw.startswith("+31") or raw.startswith("0031"):
            national = digits[2:] if raw.startswith("+") else digits[4:]
            if national.startswith("0"):
                problem = "has a 0 after +31 (write +31 6..., not +31 06...)"
            elif len(national) != 9:
                problem = f"has {len(national)} digits after +31; Dutch numbers have 9"
        elif raw.startswith("06") and len(digits) != 10:
            problem = f"has {len(digits)} digits; Dutch mobile numbers have 10"
        elif raw.startswith("+") and not 8 <= len(digits) <= 15:
            problem = f"has {len(digits)} digits; international numbers have 8 to 15"
        if problem:
            out.append(
                Finding(
                    NAME, "warn", f"Phone number \"{raw}\" {problem}. Please check it.",
                    {"value": raw, "kind": "phone"}, page=pno, bbox_mm=bbox,
                )
            )
    return out


def check(ctx: Context) -> list[Finding]:
    if ctx.artwork.kind == "raster":
        return [Finding(NAME, "info", "Text inside pictures cannot be read yet, so spelling was not checked.")]
    en, nl = _dictionaries()
    contact: list[Finding] = []
    typos: list[Finding] = []
    seen: set[str] = set()
    words_checked = 0
    for page in ctx.artwork.pages:
        pno = page.index + 1
        for span in page.text:
            contact.extend(_phone_findings(span.text, pno, span.bbox_mm))
            for token in span.text.split():
                f = _contact_findings(token, pno, span.bbox_mm)
                if f:
                    contact.append(f)
                if "@" in token or "www" in token.lower() or "://" in token or any(c.isdigit() for c in token):
                    continue
                for w in WORD.findall(token):
                    if len(w) < 4 or not w.islower():
                        continue
                    words_checked += 1
                    if w in seen:
                        continue
                    seen.add(w)
                    if en.unknown([w]) and nl.unknown([w]):
                        suggestion = en.correction(w) or nl.correction(w)
                        hint = f" Did you mean \"{suggestion}\"?" if suggestion and suggestion != w else ""
                        typos.append(
                            Finding(
                                NAME, "warn", f"Possible typo: \"{w}\".{hint}",
                                {"word": w, "suggestion": suggestion, "kind": "spelling"},
                                page=pno, bbox_mm=span.bbox_mm,
                            )
                        )
    out = contact + typos[:MAX_TYPOS]
    if out:
        return out
    return [Finding(NAME, "pass", f"No typos or broken contact details found ({words_checked} words checked).")]
