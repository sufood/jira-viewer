#!/usr/bin/env python3
"""Build the LOCKED app bundle: bake a self-contained lock guard into the app's
embedded __PRISTINE_HTML (which downloads rebuild from), so every file produced
from it has no upload/edit/add/delete UI in the Data tabs, while keeping Export.

Export CSV implementation choice (investigated against the real pristine
markup): the "Export CSV" button already exists natively and calls the app's
own exportCsv() method, which reads this.data + this.state.dataTab and
produces an exact, tab-aware CSV via the same downloadCsv() helper used
elsewhere. That native implementation is strictly more correct than a DOM
scrape (it reads the real data model, not rendered/virtualised cell text), so
we KEEP it — we just relocate its markup. In the pristine source, the whole
toolbar (Reset / Download page / Upload CSV / Export CSV) is gated behind a
single `<sc-if value="{{ editable }}">`, which is false for read-only
snapshots (window.__DATA_READONLY) — so Export disappears along with the
mutation controls it's bundled with. `_promote_export_button` moves just the
inner `<sc-if value="{{ showExport }}">...exportCsv button...</sc-if>` out
from inside that editable-gate so it always renders and works, in every state
(editable or not), while Reset/Download page/Upload CSV remain gated as-is.
The lock guard then hides Reset/Upload CSV (by text/label), Edit-details
pencils, +Add and delete/x buttons, and flattens data inputs — independent of
the editable/readOnly flags, so the controls are gone even when someone opens
the locked bundle directly (editable defaults to true until a read-only
download round-trip sets window.__DATA_READONLY).

    python lock_app.py [--html SRC] [--out LOCKED]
"""

import argparse
import pathlib
import sys

import bundle_common as bc

PRISTINE_MARKER = "__PRISTINE_HTML"

# Injected into __PRISTINE_HTML's <head>. Runs in every file built from this
# source. Hides mutation controls, flattens data inputs to static, keeps Export.
#
# IMPORTANT — double escaping hazard: this whole guard is text that first
# survives one JS *string-literal* unescape (the browser parsing
# `window.__PRISTINE_HTML = "...this text..."`) before it ever becomes real
# script source. `\"` and `<\/tag>` (single backslash) are correct there —
# they either decode to a literal quote or pass through untouched. But a JS
# string-literal unescape silently DROPS the backslash from any escape it
# doesn't recognise (`\s` -> `s`, `\+` -> `+`), and `\uXXXX` gets consumed
# into the actual Unicode character. A leading `\+` in a regex would decode
# to a bare `+`, an invalid regex (nothing to quantify) that throws a
# SyntaxError and silently kills the whole guard script. So this guard
# deliberately avoids regex escapes entirely — literal Unicode characters
# (pass through both layers untouched) and plain string methods only.
LOCK_GUARD = (
    "<style id=\\\"__lock_style\\\">"
    "[data-lock-hide]{display:none !important;}"
    "[data-mut]{display:none !important;}"
    ".__lock-static{border:none !important;background:transparent !important;"
    "box-shadow:none !important;pointer-events:none !important;"
    "-webkit-appearance:none !important;appearance:none !important;"
    "resize:none !important;cursor:default !important;}"
    "<\\/style>"
    "<script id=\\\"__lock_script\\\">(function(){"
    "function hide(el){el.setAttribute('data-lock-hide','');}"
    "function apply(){"
    "  document.querySelectorAll('label').forEach(function(l){"
    "    var lt=(l.textContent||'');"
    "    if(lt.indexOf('Upload CSV')!==-1||lt.indexOf('CHOOSE CSV')!==-1) hide(l);});"
    "  document.querySelectorAll('button').forEach(function(b){"
    "    var t=(b.textContent||'').trim();"
    # The story-card close button also reads '×'; it is the only round one
    # (inline 'border-radius: 50%'). Keep it — hide only the square '×'
    # data-row delete buttons.
    "    var round=(b.getAttribute('style')||'').indexOf('border-radius: 50%')!==-1;"
    "    if(t==='↺ Reset'||t.indexOf('+ Add')===0||(t==='×'&&!round)"
    "       ||t.indexOf('Download standalone')!==-1"
    "       ||b.getAttribute('title')==='Edit details') hide(b);});"
    # Flatten data-entry inputs to static, but leave the Priority tab's what-if
    # controls live: every range slider (weights / capacity / job-size) and every
    # checkbox (Setup model-weight on/off) is a view-time exploration lever, not a
    # data edit — a view-only recipient must still be able to re-weight and re-sort
    # (and un-grey a category from Setup). They mutate only browser-local what-if
    # state, never the shipped data model, so exempting them keeps the lock's
    # intent (no upload/edit/add/delete of the underlying data) intact.
    "  document.querySelectorAll('input:not([type=file]):not([type=range]):not([type=checkbox]),textarea').forEach("
    "    function(i){i.classList.add('__lock-static');i.setAttribute('readonly','');"
    "    i.tabIndex=-1;});"
    "}"
    "new MutationObserver(apply).observe(document.documentElement,"
    "  {childList:true,subtree:true});"
    "document.addEventListener('DOMContentLoaded',apply);apply();"
    "})();<\\/script>"
)

# --- Export-button promotion --------------------------------------------
# Anchor tokens used to locate the toolbar in the escaped __PRISTINE_HTML
# text without hand-retyping its (long, style-heavy) markup.
_EDITABLE_OPEN = '<sc-if value=\\"{{ editable }}\\"'
_TOOLBAR_DIV_OPEN = '<div style=\\"display: flex; gap: 8px; align-items: center;\\">'
_EXPORT_OPEN = '<sc-if value=\\"{{ showExport }}\\"'
_SC_IF_CLOSE = '<\\/sc-if>'
_DIV_CLOSE = '<\\/div>'


def _promote_export_button(pristine):
    """Move the '{{ showExport }}' sc-if block out from inside the toolbar's
    '{{ editable }}' gate, so Export CSV always renders (and keeps using the
    native, data-model-accurate exportCsv() handler) regardless of the
    editable/read-only state. Reset/Download page/Upload CSV stay gated.
    Safe no-op (returns input unchanged) if the expected structure isn't
    found, e.g. already transformed or the app markup changed upstream.
    """
    reset_idx = pristine.find("resetData")
    if reset_idx < 0:
        return pristine
    editable_open_idx = pristine.rfind(_EDITABLE_OPEN, 0, reset_idx)
    if editable_open_idx < 0:
        return pristine
    div_open_idx = pristine.find(_TOOLBAR_DIV_OPEN, editable_open_idx)
    if div_open_idx < 0:
        return pristine
    div_open_end = pristine.find(">", div_open_idx) + 1
    if div_open_end <= 0:
        return pristine
    wrapper_div_open = pristine[div_open_idx:div_open_end]

    export_open_idx = pristine.find(_EXPORT_OPEN, div_open_idx)
    if export_open_idx < 0:
        return pristine  # already promoted, or not found — leave as-is
    export_close_idx = pristine.find(_SC_IF_CLOSE, export_open_idx)
    if export_close_idx < 0:
        return pristine
    export_close_end = export_close_idx + len(_SC_IF_CLOSE)
    export_block = pristine[export_open_idx:export_close_end]

    toolbar_div_close_idx = pristine.find(_DIV_CLOSE, export_close_end)
    if toolbar_div_close_idx < 0:
        return pristine
    editable_close_idx = pristine.find(_SC_IF_CLOSE, toolbar_div_close_idx)
    if editable_close_idx < 0:
        return pristine
    editable_close_end = editable_close_idx + len(_SC_IF_CLOSE)

    return (
        pristine[:export_open_idx]
        + pristine[export_close_end:editable_close_end]
        + "\\n        " + wrapper_div_open + export_block + _DIV_CLOSE
        + pristine[editable_close_end:]
    )


def _inject_guard(pristine):
    """Insert the lock guard just before the pristine source's first </head>."""
    needle = "<\\/head>"
    idx = pristine.find(needle)
    if idx < 0:
        raise ValueError("no </head> found in __PRISTINE_HTML")
    if "__lock_script" in pristine:
        return pristine                       # idempotent
    pristine = _promote_export_button(pristine)
    return pristine[:idx] + LOCK_GUARD + pristine[idx:]


def build_locked(src_html):
    uuid = bc.find_resource_with(src_html, PRISTINE_MARKER)
    if not uuid:
        raise ValueError("could not locate the __PRISTINE_HTML resource")
    return bc.edit_resource(src_html, uuid, _inject_guard)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", default="Insignia AI Strategy Map - Jira linked.html")
    ap.add_argument("--out", default="Insignia AI Strategy Map - locked.html")
    args = ap.parse_args()
    src = pathlib.Path(args.html)
    if not src.exists():
        sys.exit(f"Missing source HTML: {src}")
    out = build_locked(src.read_text(encoding="utf-8"))
    pathlib.Path(args.out).write_text(out, encoding="utf-8")
    print(f"Wrote {args.out} ({len(out):,} bytes)")


if __name__ == "__main__":
    main()
