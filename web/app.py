"""Web demo: upload a print file, see what is wrong, fix it in one click.

Run:  streamlit run web/app.py
"""

from __future__ import annotations

import html
import sys
import tempfile
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from preflight.fixes import fix_artwork
from preflight.matcher import find_products, parse_request
from preflight.preview import numbered, render_preview
from preflight.report import check_after_fix, check_file
from preflight.samples import business_card
from preflight.specs import all_products, get_product

st.set_page_config(page_title="Preflight — check your print file", page_icon="◐", layout="wide")

LABEL = {
    "file": "File", "pages": "Pages", "size": "Size", "bleed": "Bleed", "dpi": "Image sharpness",
    "colour": "Colours", "safezone": "Safe zone", "fonts": "Fonts", "text": "Text & contacts",
}
VERDICT = {
    "pass": ("Print-ready", "ok"),
    "warn": ("Printable — check the warnings", "warn"),
    "fail": ("Needs fixing before print", "bad"),
}

st.markdown(
    """
<style>
#MainMenu, footer, header [data-testid="stToolbar"] {visibility: hidden;}
.block-container {max-width: 1120px; padding-top: 2.2rem; padding-bottom: 4rem;}
h1, h2, h3 {letter-spacing: -0.02em;}
.brand {font-weight: 800; font-size: 1.05rem; letter-spacing: -0.02em;}
.brand span {color: #E8684A;}
.tag {color: #6B7280; font-size: .82rem;}
.hero {font-size: 2.5rem; font-weight: 800; line-height: 1.1; letter-spacing: -0.03em; margin: 1.6rem 0 .4rem;}
.sub {color: #4B5563; font-size: 1.05rem; margin-bottom: 1.6rem;}
.step {font-size: .75rem; font-weight: 700; color: #9CA3AF; letter-spacing: .08em; text-transform: uppercase;}
.chips {display: flex; gap: .4rem; flex-wrap: wrap; margin: .2rem 0 .6rem;}
.chip {background: #F6F5F2; border-radius: 999px; padding: .25rem .7rem; font-size: .8rem; color: #374151;}
.verdict {border-radius: 14px; padding: .9rem 1.1rem; font-weight: 700; display: flex; justify-content: space-between;
          align-items: center; margin: .4rem 0 1rem;}
.verdict small {font-weight: 500; opacity: .75;}
.verdict.ok {background: #ECFDF3; color: #067647;}
.verdict.warn {background: #FFF7E6; color: #B54708;}
.verdict.bad {background: #FEF1EE; color: #B42318;}
.issue {display: flex; gap: .75rem; padding: .7rem 0; border-bottom: 1px solid #F0EFEB;}
.num {flex: 0 0 26px; height: 26px; border-radius: 50%; color: #fff; font-size: .8rem; font-weight: 700;
      display: flex; align-items: center; justify-content: center; margin-top: 2px;}
.num.error {background: #D62828;} .num.warn {background: #E8961E;}
.issue b {font-size: .92rem;} .issue p {margin: .1rem 0 0; color: #4B5563; font-size: .88rem; line-height: 1.4;}
.fixtag {display: inline-block; margin-left: .4rem; font-size: .7rem; font-weight: 700; color: #067647;
         background: #ECFDF3; border-radius: 6px; padding: .05rem .4rem;}
.legend {color: #6B7280; font-size: .78rem; margin-top: .3rem;}
.legend i {display: inline-block; width: 14px; height: 0; vertical-align: middle; margin: 0 .25rem 0 .7rem;}
.changes {background: #F6F5F2; border-radius: 12px; padding: .8rem 1rem; font-size: .88rem; color: #374151;}
.foot {color: #9CA3AF; font-size: .78rem; margin-top: 3rem; border-top: 1px solid #F0EFEB; padding-top: 1rem;}
div.stButton > button {border-radius: 10px; font-weight: 600;}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="brand">preflight<span>.</span></div>'
    '<div class="tag">Unofficial prototype · not affiliated with any print shop</div>'
    '<div class="hero">Check your print file<br>before you order.</div>'
    '<div class="sub">Size, bleed, sharpness, colours, safe zone, fonts, and the text itself: typos, email and '
    "phone. In about a second, with fixes for what is safe to fix.</div>",
    unsafe_allow_html=True,
)

ss = st.session_state
ss.setdefault("path", None)
ss.setdefault("fixed", None)
ss.setdefault("forced_product", None)

products = all_products()
ids = [p.id for p in products]

left, right = st.columns([1, 1], gap="large")
with left:
    st.markdown('<div class="step">1 · What are you printing?</div>', unsafe_allow_html=True)
    request = st.text_input("Request", placeholder="e.g. 250 matte business cards", label_visibility="collapsed")
    guess = find_products(request)[0].product.id if request.strip() else (ss.forced_product or "business-card")
    product_id = st.selectbox("Product", ids, index=ids.index(guess), format_func=lambda i: get_product(i).name)
    p = get_product(product_id)
    parsed = parse_request(request) if request.strip() else {}
    chips = [f"{p.trim_mm[0]:g} × {p.trim_mm[1]:g} mm", f"bleed {p.spec.bleed_mm:g} mm",
             f"safe margin {p.spec.safe_warn_mm:g} mm", f"≥ {p.spec.dpi_min:g} dpi"]
    if parsed.get("quantity"):
        chips.insert(0, f"{parsed['quantity']:,} pcs")
    if parsed.get("finish"):
        chips.insert(1, parsed["finish"])
    st.markdown('<div class="chips">' + "".join(f'<span class="chip">{html.escape(c)}</span>' for c in chips)
                + "</div>", unsafe_allow_html=True)

with right:
    st.markdown('<div class="step">2 · Your file</div>', unsafe_allow_html=True)
    upload = st.file_uploader("File", type=["pdf", "png", "jpg", "jpeg"], label_visibility="collapsed")
    c1, c2 = st.columns(2)
    sample_bad = c1.button("Try a card with mistakes", use_container_width=True)
    sample_good = c2.button("Try a print-ready card", use_container_width=True)

if upload is not None and ss.get("upload_name") != upload.name + str(upload.size):
    tmp = Path(tempfile.mkdtemp()) / upload.name
    tmp.write_bytes(upload.getvalue())
    ss.path, ss.fixed, ss.upload_name, ss.forced_product = str(tmp), None, upload.name + str(upload.size), None
if sample_bad or sample_good:
    name = "business_card_with_mistakes.pdf" if sample_bad else "business_card_print_ready.pdf"
    tmp = Path(tempfile.mkdtemp()) / name
    business_card(tmp, mistakes=sample_bad)
    ss.path, ss.fixed, ss.forced_product = str(tmp), None, "business-card"
    st.rerun()


def issues_html(report) -> str:
    rows = []
    for n, f in numbered(report.findings):
        tag = '<span class="fixtag">auto-fix</span>' if f.fixable else ""
        rows.append(
            f'<div class="issue"><div class="num {f.severity}">{n}</div><div>'
            f"<b>{LABEL.get(f.check, f.check)}</b>{tag}<p>{html.escape(f.message)}</p></div></div>"
        )
    if not rows:
        return '<div class="issue"><div>Nothing to fix. Every check passed.</div></div>'
    return "".join(rows)


def show(report, path, title):
    text, cls = VERDICT[report.verdict]
    n = len(numbered(report.findings))
    st.markdown(
        f'<div class="verdict {cls}"><span>{text}</span><small>{title} · {n} issue{"s" if n != 1 else ""} · '
        f"checked in {report.seconds * 1000:.0f} ms</small></div>",
        unsafe_allow_html=True,
    )
    a, b = st.columns([11, 9], gap="large")
    with a:
        st.image(render_preview(path, get_product(report.product_id), report.findings, width_px=1100),
                 use_container_width=True)
        st.markdown(
            '<div class="legend"><i style="border-top:2px solid #111"></i>cut line'
            '<i style="border-top:2px dashed #D62828"></i>bleed must reach'
            '<i style="border-top:2px dashed #1E9646"></i>safe zone</div>',
            unsafe_allow_html=True,
        )
    with b:
        st.markdown(issues_html(report), unsafe_allow_html=True)


if ss.path:
    pid = ss.forced_product if (ss.forced_product and not request.strip()) else product_id
    report = check_file(ss.path, pid)
    st.write("")
    show(report, ss.path, Path(ss.path).name)

    fixable = [f for f in report.findings if f.fixable and f.severity in ("warn", "error")]
    if fixable and not ss.fixed:
        st.write("")
        if st.button(f"Fix {len(fixable)} issue{'s' if len(fixable) > 1 else ''} automatically", type="primary"):
            out = Path(ss.path).with_name(Path(ss.path).stem + "_print-ready.pdf")
            result = fix_artwork(ss.path, pid, out)
            ss.fixed = (str(out), result.changes)
            st.rerun()

    if ss.fixed:
        out, changes = ss.fixed
        after = check_after_fix(report, out)
        st.markdown("### After automatic fix")
        st.markdown('<div class="changes">' + "<br>".join("✓ " + html.escape(c) for c in changes) + "</div>",
                    unsafe_allow_html=True)
        st.write("")
        show(after, out, "fixed file")
        if after.verdict == "fail":
            st.caption("What is left needs a human decision: a sharper logo, moving text, fixing a typo. "
                       "The tool suggests; you decide.")
        st.download_button("Download print-ready PDF", Path(out).read_bytes(), file_name=Path(out).name,
                           type="primary")

st.markdown(
    '<div class="foot">Open-source prototype by Ammar Sodikov · checks are deterministic code; '
    "numbers come from public print specifications · no orders are placed.</div>",
    unsafe_allow_html=True,
)
