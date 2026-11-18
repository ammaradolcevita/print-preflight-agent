"""Web demo: upload a print file, see what is wrong, fix it in one click.

Run:  streamlit run web/app.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from preflight.fixes import fix_artwork
from preflight.matcher import find_products
from preflight.preview import numbered, render_preview
from preflight.report import check_after_fix, check_file
from preflight.specs import all_products, get_product

st.set_page_config(page_title="Print Preflight Agent", page_icon="🖨️", layout="wide")

BADGE = {"pass": ("✅", "success"), "warn": ("⚠️", "warning"), "fail": ("❌", "error")}
ICON = {"error": "❌", "warn": "⚠️", "info": "ℹ️", "pass": "✅"}

st.title("🖨️ Print Preflight Agent")
st.caption(
    "Checks your print file before you order: size, bleed, sharpness, colours, safe zone, fonts, "
    "and the text itself (typos, email, phone). Unofficial prototype, not affiliated with HelloPrint."
)

products = all_products()
ids = [p.id for p in products]
col_a, col_b = st.columns([2, 3])
with col_a:
    request = st.text_input("What do you want to print?", placeholder="e.g. 250 matte business cards")
    default = find_products(request)[0].product.id if request.strip() else "business-card"
    product_id = st.selectbox(
        "Product", ids, index=ids.index(default), format_func=lambda i: get_product(i).name
    )
    p = get_product(product_id)
    st.markdown(
        f"**Specs:** trim {p.trim_mm[0]:g} × {p.trim_mm[1]:g} mm · bleed {p.spec.bleed_mm:g} mm · "
        f"safe margin {p.spec.safe_warn_mm:g} mm · ≥ {p.spec.dpi_min:g} dpi"
    )
    upload = st.file_uploader("Your file", type=["pdf", "png", "jpg", "jpeg"])
    use_sample = st.button("…or try a sample file with typical mistakes")

if "path" not in st.session_state:
    st.session_state.path = None
if upload is not None:
    tmp = Path(tempfile.mkdtemp()) / upload.name
    tmp.write_bytes(upload.getvalue())
    st.session_state.path = str(tmp)
    st.session_state.fixed = None
elif use_sample:
    from preflight.fixtures import make_pdf

    tmp = Path(tempfile.mkdtemp()) / "sample_business_card.pdf"
    make_pdf(
        tmp, (85, 55), background=(0.15, 0.4, 0.8),
        images=[{"px": (220, 140), "rect_mm": (50, 8, 80, 27), "mode": "RGB"}],
        texts=[
            {"text": "Ammar Sodikov", "at_mm": (6, 20), "size": 11},
            {"text": "graphic desinger", "at_mm": (6, 27)},
            {"text": "ammar@studio", "at_mm": (6, 46)},
            {"text": "+31 6 1234 567", "at_mm": (6, 53), "embed": False},
        ],
    )
    st.session_state.path = str(tmp)
    st.session_state.fixed = None
    product_id = "business-card"


def show_report(report, path, title):
    emoji, kind = BADGE[report.verdict]
    getattr(st, kind)(f"{emoji} **{report.verdict_text}** — checked in {report.seconds:.1f} s")
    left, right = st.columns([3, 2])
    with left:
        st.image(render_preview(path, get_product(report.product_id), report.findings, width_px=1100),
                 caption=f"{title}: black = cut line · red dashed = bleed must reach · green dashed = safe zone")
    with right:
        issues = numbered(report.findings)
        if not issues:
            st.write("No problems found.")
        for n, f in issues:
            fix = " *(auto-fixable)*" if f.fixable else ""
            st.markdown(f"**{n}.** {ICON[f.severity]} **{f.check}** — {f.message}{fix}")
        with st.expander("All checks"):
            for f in report.findings:
                st.markdown(f"{ICON[f.severity]} **{f.check}** — {f.message}")


path = st.session_state.path
with col_b:
    if not path:
        st.info("Upload a PDF, PNG or JPG, or try the sample file.")
if path:
    report = check_file(path, product_id)
    st.divider()
    show_report(report, path, "Your file")
    fixable = [f for f in report.findings if f.fixable and f.severity in ("warn", "error")]
    if fixable and st.button(f"🔧 Fix {len(fixable)} problem(s) automatically", type="primary"):
        out = Path(path).with_name(Path(path).stem + "_print-ready.pdf")
        result = fix_artwork(path, product_id, out)
        st.session_state.fixed = (str(out), result.changes)
    if st.session_state.get("fixed"):
        out, changes = st.session_state.fixed
        after = check_after_fix(report, out)
        st.divider()
        st.subheader("After automatic fix")
        st.markdown("\n".join(f"- {c}" for c in changes))
        show_report(after, out, "Fixed file")
        if after.verdict == "fail":
            st.caption("Some problems need your decision (e.g. a sharper logo or moving text); they are still listed.")
        st.download_button("⬇️ Download print-ready PDF", Path(out).read_bytes(), file_name=Path(out).name)
