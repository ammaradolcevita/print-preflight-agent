"""Interactive preview: hover a numbered marker on the page and the matching issue lights up
(and the other way round). Pure HTML/CSS/JS, rendered with streamlit.components.v1.html."""

from __future__ import annotations

import base64
import html
import io

from preflight.preview import layout, numbered

LABEL = {
    "file": "File", "pages": "Pages", "size": "Size", "bleed": "Bleed", "dpi": "Image sharpness",
    "colour": "Colours", "safezone": "Safe zone", "fonts": "Fonts", "text": "Text & contacts",
}

CSS = """
* {box-sizing: border-box;}
body {margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, "Helvetica Neue", Arial, sans-serif;
      color: #111827; -webkit-font-smoothing: antialiased;}
.wrap {display: flex; gap: 28px; align-items: flex-start;}
.left {flex: 13 1 0; min-width: 0; position: sticky; top: 0;}
.right {flex: 8 1 0; min-width: 0; max-height: calc(100vh - 6px); overflow-y: auto; padding-right: 4px;}
.page {position: relative; border-radius: 16px; overflow: hidden; background: #EEEEF1;
       box-shadow: 0 1px 2px rgba(16,24,40,.06), 0 8px 24px rgba(16,24,40,.08);}
.page img {display: block; width: 100%; height: auto;}
.box {position: absolute; border: 2px solid; border-radius: 3px; transition: all .15s ease; cursor: pointer;}
.box.error {border-color: #D62828;} .box.warn {border-color: #E8961E;}
.box.active {box-shadow: 0 0 0 4px rgba(17,24,39,.15); background: rgba(255,255,255,.18);}
.mk {position: absolute; width: 28px; height: 28px; font-size: 13px; transform: translate(-50%, -50%); border-radius: 50%; color: #fff; font-weight: 700;
     display: flex; align-items: center; justify-content: center; border: 2px solid #fff; cursor: pointer;
     box-shadow: 0 2px 6px rgba(0,0,0,.25); transition: transform .15s ease; z-index: 2; user-select: none;}
.mk.error {background: #D62828;} .mk.warn {background: #E8961E;}
.mk.active {transform: translate(-50%, -50%) scale(1.25); z-index: 5;}
.dim .mk:not(.active), .dim .box:not(.active) {opacity: .35;}
.tip {position: absolute; z-index: 10; max-width: 300px; background: #111827; color: #F9FAFB; font-size: 13px;
      line-height: 1.4; padding: 10px 12px; border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,.25);
      pointer-events: none; opacity: 0; transform: translateY(4px); transition: opacity .12s, transform .12s;}
.tip.show {opacity: 1; transform: translateY(0);}
.tip b {display: block; margin-bottom: 2px; font-size: 13px;}
.legend {color: #6B7280; font-size: 12px; margin-top: 10px;}
.legend i {display: inline-block; width: 16px; height: 0; vertical-align: middle; margin: 0 5px 0 12px;}
.legend i:first-child {margin-left: 2px;}
.hint {color: #9CA3AF; font-size: 12px; margin-top: 4px;}
.issue {display: flex; gap: 12px; padding: 12px 14px; margin-bottom: 8px; border-radius: 12px; cursor: pointer;
        border: 1px solid #F0EFEB; border-left: 4px solid transparent; background: #fff; transition: all .15s ease;}
.issue:hover, .issue.active {background: #FAFAF8; box-shadow: 0 4px 14px rgba(16,24,40,.08);}
.issue.active.error {border-left-color: #D62828; background: #FEF6F5;}
.issue.active.warn {border-left-color: #E8961E; background: #FFFAF0;}
.num {flex: 0 0 26px; height: 26px; border-radius: 50%; color: #fff; font-size: 13px; font-weight: 700;
      display: flex; align-items: center; justify-content: center; margin-top: 1px;}
.num.error {background: #D62828;} .num.warn {background: #E8961E;}
.issue b {font-size: 14px;} .issue p {margin: 3px 0 0; color: #4B5563; font-size: 13.5px; line-height: 1.45;}
.fix {display: inline-block; margin-left: 6px; font-size: 11px; font-weight: 700; color: #067647;
      background: #ECFDF3; border-radius: 6px; padding: 1px 6px; vertical-align: 1px;}
.ok {padding: 18px; border-radius: 12px; background: #ECFDF3; color: #067647; font-weight: 600;}
@media (max-width: 760px) {.wrap {flex-direction: column;} .left {position: static;}}
"""

JS = """
const root = document.querySelector('.wrap'), page = document.querySelector('.page'), tip = document.querySelector('.tip');
let pinned = null;
function show(n, from) {
  root.querySelectorAll('[data-n]').forEach(e => e.classList.toggle('active', e.dataset.n === n));
  page.classList.toggle('dim', n !== null);
  const mk = page.querySelector('.mk[data-n="' + n + '"]');
  if (n === null || !mk) { tip.classList.remove('show'); return; }
  const it = root.querySelector('.issue[data-n="' + n + '"]');
  tip.innerHTML = '<b>' + it.dataset.title + '</b>' + it.dataset.msg;
  const pr = page.getBoundingClientRect(), mr = mk.getBoundingClientRect();
  let x = mr.left - pr.left + mr.width / 2 + 14, y = mr.top - pr.top + mr.height / 2 + 14;
  tip.style.left = '0px'; tip.style.top = '0px'; tip.classList.add('show');
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  if (x + tw > pr.width - 8) x = Math.max(8, mr.left - pr.left - tw - 10);
  if (y + th > pr.height - 8) y = Math.max(8, mr.top - pr.top - th - 10);
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
  if (from === 'list') it.scrollIntoView({block: 'nearest'});
}
root.querySelectorAll('[data-n]').forEach(e => {
  e.addEventListener('mouseenter', () => { if (!pinned) show(e.dataset.n, e.classList.contains('issue') ? 'list' : 'page'); });
  e.addEventListener('mouseleave', () => { if (!pinned) show(null); });
  e.addEventListener('click', () => { pinned = pinned === e.dataset.n ? null : e.dataset.n; show(pinned); });
});
"""


def interactive_html(report, path, product) -> tuple[str, int]:
    """HTML for the preview + issue list, and a height estimate for the iframe."""
    canvas, markers, r = layout(path, product, report.findings)
    w, h = canvas.size
    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=90, optimize=True)
    src = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

    def pct(v, total):
        return f"{v / total * 100:.3f}%"

    overlay = []
    for m in sorted(markers, key=lambda m: m.finding.severity == "error"):
        if m.box:
            x0, y0, x1, y1 = m.box
            overlay.append(
                f'<div class="box {m.finding.severity}" data-n="{m.n}" style="left:{pct(x0, w)};top:{pct(y0, h)};'
                f'width:{pct(x1 - x0, w)};height:{pct(y1 - y0, h)}"></div>'
            )
    for m in markers:
        cx, cy = m.centre
        overlay.append(
            f'<div class="mk {m.finding.severity}" data-n="{m.n}" style="left:{pct(cx, w)};top:{pct(cy, h)}">'
            f'{m.n}</div>'
        )

    items = []
    for n, f in numbered(report.findings):
        title = LABEL.get(f.check, f.check)
        msg = html.escape(f.message)
        fix = '<span class="fix">auto-fix</span>' if f.fixable else ""
        items.append(
            f'<div class="issue {f.severity}" data-n="{n}" data-title="{html.escape(title)}" data-msg="{msg}">'
            f'<div class="num {f.severity}">{n}</div><div><b>{title}</b>{fix}<p>{msg}</p></div></div>'
        )
    if not items:
        items.append('<div class="ok">✓ Nothing to fix. Every check passed.</div>')

    legend = (
        '<div class="legend"><i style="border-top:2px solid #111"></i>cut line'
        '<i style="border-top:2px dashed #D62828"></i>bleed must reach'
        '<i style="border-top:2px dashed #1E9646"></i>safe zone</div>'
    )
    hint = '<div class="hint">Hover a number or an issue to see where it is. Click to pin.</div>' if markers else ""
    body = (
        f'<div class="wrap"><div class="left"><div class="page"><img src="{src}">{"".join(overlay)}'
        f'<div class="tip"></div></div>{legend}{hint}</div><div class="right">{"".join(items)}</div></div>'
    )
    doc = f"<!doctype html><html><head><style>{CSS}</style></head><body>{body}<script>{JS}</script></body></html>"

    # iframe height: the page image (left column is about 60% of a ~1100px wide layout) vs the list,
    # which scrolls on its own when it is longer than the image
    img_h = 650 * h / w + 70
    list_h = sum(60 + 20 * (len(f.message) // 48 + 1) for _, f in numbered(report.findings)) or 80
    return doc, int(max(img_h, min(list_h, 760)) + 10)
