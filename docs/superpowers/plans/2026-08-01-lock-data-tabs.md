# Lock Data Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a locked, view-only app — no upload/edit/add/delete in the Data tabs, Export CSV kept — with data entering only via the backend `regenerate` script (two-stage build).

**Architecture:** `bundle_common.py` decodes/edits/re-encodes the app bundle. `lock_app.py` bakes a self-contained lock guard into the app's embedded `__PRISTINE_HTML` (which downloads rebuild from) → a locked bundle. `regenerate_html.py` goes two-stage: build the exact internal data by importing CSVs into the editable source, then inject it via localStorage into the locked bundle and download.

**Tech Stack:** Python 3.12, `playwright`, `pytest`. Reuses `jira_common`, `settings_common`.

**Reference:** Spec `docs/superpowers/specs/2026-08-01-lock-data-tabs-design.md`.

**VALIDATED FACTS (probed against the real app):**
- Downloads rebuild from `window.__PRISTINE_HTML` (+`support.js`), NOT the outer bundle.
- `__PRISTINE_HTML` is an escaped string in bundle resource `3a33ba6c-5488-4bcb-a34b-1e60440a9449`; injecting before its `<\/head>`, recompressing (gzip mtime=0), and rebuilding the manifest **propagates into the download** (sentinel verified).
- Manifest lives in `<script type="__bundler/manifest">…</script>` as JSON `{uuid:{mime,compressed,data(b64 of gzip)}}`.
- The download path (`getPristineSource`) is timing-flaky — needs a longer settle + a retry.
- Data object `d` at `localStorage["insignia_ai_strategy_map_v2"]`: `departments[]` (with `opportunities`/`people`/`gaps`/`nextSteps`/`systems`/`themes`), `initiatives[]`, `header`, `hub`, `fitRating`, catalogues. Active Data sub-tab is `state.dataTab` ∈ {`init`,`div`,`story`}.
- In read-only, Upload/Reset/Export are already gone (gated on `editable`); residual visible-but-dead controls: `input`/`textarea`, `button[title="Edit details"]`, "+ Add …" buttons, "×" deletes.

---

## File Structure
- Create: `bundle_common.py` — bundle decode/edit/encode.
- Create: `lock_app.py` — build the locked bundle (guard baked into `__PRISTINE_HTML`).
- Modify: `regenerate_html.py` — two-stage build.
- Modify: `.gitignore` (add the generated locked bundle), `README.md`.
- Test: `tests/test_bundle.py`, `tests/test_lock_app.py` (browser), extend `tests/test_regenerate.py`.

---

## Task 1: `bundle_common.py` — decode / edit / encode the bundle

**Files:** Create `bundle_common.py`, `tests/test_bundle.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_bundle.py`:
```python
import pathlib
import bundle_common as bc

SRC = pathlib.Path(__file__).resolve().parent.parent / \
    "Insignia AI Strategy Map - Jira linked.html"
PRISTINE_UUID = "3a33ba6c-5488-4bcb-a34b-1e60440a9449"


def test_find_pristine_resource():
    html = SRC.read_text(encoding="utf-8")
    uuid = bc.find_resource_with(html, "__PRISTINE_HTML")
    assert uuid == PRISTINE_UUID


def test_roundtrip_identity_rebuilds_valid_bundle(tmp_path):
    html = SRC.read_text(encoding="utf-8")
    out = bc.edit_resource(html, PRISTINE_UUID, lambda s: s)   # identity
    # manifest still parses and the resource still decodes to the same text
    assert bc.get_resource_text(out, PRISTINE_UUID) == \
           bc.get_resource_text(html, PRISTINE_UUID)
    assert '__bundler/manifest' in out and len(out) > 900_000


def test_edit_resource_injects_text():
    html = SRC.read_text(encoding="utf-8")
    out = bc.edit_resource(html, PRISTINE_UUID,
                           lambda s: s.replace("<\\/head>",
                                               "<x-marker><\\/x-marker><\\/head>", 1))
    assert "<x-marker>" in bc.get_resource_text(out, PRISTINE_UUID)
```

- [ ] **Step 2: Run to verify FAIL**

Run: `cd "/Users/scotty/dev/scryptid/insignia/0x_Themes/jira-viewer" && python3 -m pytest tests/test_bundle.py -v`
Expected: `ModuleNotFoundError: No module named 'bundle_common'`.

- [ ] **Step 3: Implement `bundle_common.py`**

```python
#!/usr/bin/env python3
"""Decode / edit / re-encode the single-file app bundle.

The bundle stores resources in a JSON manifest inside
<script type="__bundler/manifest">…</script>, each value
{mime, compressed, data} where data is base64 of gzip when compressed.
"""

import base64
import gzip
import io
import json
import re

_MANIFEST_RE = re.compile(
    r'(<script type="__bundler/manifest">)(.*?)(</script>)', re.S)


def _manifest(html):
    m = _MANIFEST_RE.search(html)
    if not m:
        raise ValueError("no __bundler/manifest block found")
    return m, json.loads(m.group(2))


def get_resource_text(html, uuid):
    _, manifest = _manifest(html)
    v = manifest[uuid]
    raw = base64.b64decode(v["data"])
    if v.get("compressed"):
        raw = gzip.decompress(raw)
    return raw.decode("utf-8")


def find_resource_with(html, needle):
    """UUID of the first text/javascript resource containing `needle`."""
    _, manifest = _manifest(html)
    for uuid, v in manifest.items():
        if "javascript" not in (v.get("mime") or ""):
            continue
        raw = base64.b64decode(v["data"])
        if v.get("compressed"):
            raw = gzip.decompress(raw)
        if needle in raw.decode("utf-8", "replace"):
            return uuid
    return None


def edit_resource(html, uuid, transform):
    """Return new HTML with resource `uuid`'s text replaced by transform(text).
    Recompresses deterministically (gzip mtime=0) and rebuilds the manifest."""
    m, manifest = _manifest(html)
    v = dict(manifest[uuid])
    raw = base64.b64decode(v["data"])
    text = gzip.decompress(raw).decode("utf-8") if v.get("compressed") \
        else raw.decode("utf-8")
    new_text = transform(text)
    data = new_text.encode("utf-8")
    if v.get("compressed"):
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
            g.write(data)
        data = buf.getvalue()
    v["data"] = base64.b64encode(data).decode()
    manifest[uuid] = v
    new_manifest = json.dumps(manifest, separators=(",", ":"))
    return html[:m.start(2)] + new_manifest + html[m.end(2):]
```

- [ ] **Step 4: Run to verify PASS**

Run: `python3 -m pytest tests/test_bundle.py -v` → 3 passed.
Then confirm a rebuilt bundle still renders:
```bash
python3 -c "
import bundle_common as bc, pathlib
html=pathlib.Path('Insignia AI Strategy Map - Jira linked.html').read_text()
out=bc.edit_resource(html,'3a33ba6c-5488-4bcb-a34b-1e60440a9449',lambda s:s)
pathlib.Path('/tmp/rt.html').write_text(out)
print('rebuilt', len(out))
"
```
Then load `/tmp/rt.html` with the existing regenerate harness or a quick Playwright check that the `Data` button appears. (A dedicated browser assertion is in Task 2.)

- [ ] **Step 5: Commit**

```bash
git add bundle_common.py tests/test_bundle.py
git commit -m "feat: bundle_common — decode/edit/encode the app bundle resources"
```

---

## Task 2: `lock_app.py` — bake the lock guard into the pristine source

**Files:** Create `lock_app.py`, `tests/test_lock_app.py`; Modify `.gitignore`

- [ ] **Step 1: Discover Export handling + guard selectors (investigation)**

Open the source app in a browser (or reuse the decompressed JS) to confirm, for the guard:
- the "Export CSV" reachability — decide between (a) **un-gate the existing button** by a targeted edit moving the `<sc-if value="{{ showExport }}">…Export…</sc-if>` block out of the enclosing `<sc-if value="{{ editable }}">`, or (b) **reconstruct export from `d`** in the guard. Prefer (a) if the string move is unambiguous; else (b).
- confirm the residual controls to hide by role/text/title: `label` containing "Upload CSV", button text "↺ Reset", `button[title="Edit details"]`, buttons whose text starts with "+ Add", buttons whose text is "×".

Record the chosen Export path in a comment at the top of `lock_app.py`.

- [ ] **Step 2: Write `lock_app.py`**

```python
#!/usr/bin/env python3
"""Build the LOCKED app bundle: bake a self-contained lock guard into the app's
embedded __PRISTINE_HTML (which downloads rebuild from), so every file produced
from it has no upload/edit/add/delete UI in the Data tabs, while keeping Export.

    python lock_app.py [--html SRC] [--out LOCKED]
"""

import argparse
import pathlib
import sys

import bundle_common as bc

PRISTINE_MARKER = "__PRISTINE_HTML"

# Injected into __PRISTINE_HTML's <head>. Runs in every file built from this
# source. Hides mutation controls, flattens data inputs to static, keeps Export.
LOCK_GUARD = (
    "<style id=\\\"__lock_style\\\">"
    "[data-lock-hide]{display:none !important;}"
    ".__lock-static{border:none !important;background:transparent !important;"
    "box-shadow:none !important;pointer-events:none !important;"
    "-webkit-appearance:none !important;appearance:none !important;"
    "resize:none !important;cursor:default !important;}"
    "<\\/style>"
    "<script id=\\\"__lock_script\\\">(function(){"
    "function hide(el){el.setAttribute('data-lock-hide','');}"
    "function apply(){"
    "  document.querySelectorAll('label').forEach(function(l){"
    "    if(/Upload CSV/i.test(l.textContent)) hide(l);});"
    "  document.querySelectorAll('button').forEach(function(b){"
    "    var t=(b.textContent||'').trim();"
    "    if(/^\\u21ba?\\s*Reset$/.test(t)||/^\\+\\s*Add/.test(t)||t==='\\u00d7'"
    "       ||b.getAttribute('title')==='Edit details') hide(b);});"
    "  document.querySelectorAll('input:not([type=file]),textarea').forEach("
    "    function(i){i.classList.add('__lock-static');i.setAttribute('readonly','');"
    "    i.tabIndex=-1;});"
    "}"
    "new MutationObserver(apply).observe(document.documentElement,"
    "  {childList:true,subtree:true});"
    "document.addEventListener('DOMContentLoaded',apply);apply();"
    "})();<\\/script>"
)


def _inject_guard(pristine):
    """Insert the lock guard just before the pristine source's first </head>."""
    needle = "<\\/head>"
    idx = pristine.find(needle)
    if idx < 0:
        raise ValueError("no </head> found in __PRISTINE_HTML")
    if "__lock_script" in pristine:
        return pristine                       # idempotent
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
```
If Step 1 chose Export path (a) (un-gate), add that string move as a second transform in `build_locked` (compose with `_inject_guard`); if (b), extend the guard `<script>` to append an Export button that reads `localStorage["insignia_ai_strategy_map_v2"]` and serialises `state.dataTab`'s dataset. Whichever path, the Task 3 test asserts an Export control exists.

- [ ] **Step 3: Add the locked bundle to `.gitignore`**

Append `Insignia AI Strategy Map - locked.html` to `.gitignore` (generated artifact).

- [ ] **Step 4: Write the browser validation test `tests/test_lock_app.py`**

```python
import pathlib
import re
import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / \
    "Insignia AI Strategy Map - Jira linked.html"


def _chromium():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as pw:
            pw.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not SRC.exists() or not _chromium(),
                                reason="source HTML or Chromium unavailable")


def test_locked_bundle_has_no_mutation_controls(tmp_path):
    import lock_app
    from playwright.sync_api import sync_playwright
    locked = tmp_path / "locked.html"
    locked.write_text(lock_app.build_locked(SRC.read_text(encoding="utf-8")),
                      encoding="utf-8")
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(locked.resolve().as_uri())
        pg.get_by_role("button", name=re.compile(r"^Data$")).wait_for(timeout=30000)
        pg.wait_for_timeout(1500)
        for _ in range(8):
            pg.get_by_role("button", name=re.compile(r"^Data$")).click()
            try:
                pg.get_by_role("button", name=re.compile("Divisions ·")).wait_for(
                    state="visible", timeout=5000); break
            except Exception:
                continue
        pg.wait_for_timeout(800)
        counts = pg.evaluate("""() => {
          const vis = el => el.offsetParent !== null &&
            !el.hasAttribute('data-lock-hide');
          const btn = t => [...document.querySelectorAll('button')]
            .filter(b => t(b) && vis(b)).length;
          return {
            upload: [...document.querySelectorAll('label')]
              .filter(l => /Upload CSV/i.test(l.textContent) && vis(l)).length,
            pencils: btn(b => b.getAttribute('title') === 'Edit details'),
            adds: btn(b => /^\\+\\s*Add/.test((b.textContent||'').trim())),
            dels: btn(b => (b.textContent||'').trim() === '\\u00d7'),
            liveInputs: [...document.querySelectorAll('input:not([type=file]),textarea')]
              .filter(i => vis(i) && !i.classList.contains('__lock-static')).length,
            exportPresent: [...document.querySelectorAll('button,a')]
              .some(e => /Export CSV/i.test(e.textContent||'')),
            renders: !!document.querySelector('input,td,div'),
          };
        }""")
        b.close()
    assert counts["upload"] == 0
    assert counts["pencils"] == 0 and counts["adds"] == 0 and counts["dels"] == 0
    assert counts["liveInputs"] == 0        # all data inputs flattened to static
    assert counts["exportPresent"] is True
    assert counts["renders"] is True
```

- [ ] **Step 5: Run + iterate**

Run: `python3 -m pytest tests/test_lock_app.py -v`
Expected: PASS. If a control slips through, fix the guard's selectors (Step 2) — do NOT relax the assertions. Re-run until green.

- [ ] **Step 6: Commit**

```bash
git add lock_app.py tests/test_lock_app.py .gitignore
git commit -m "feat: lock_app — bake a lock guard into the pristine source (locked bundle)"
```

---

## Task 3: `regenerate_html.py` — two-stage build

**Files:** Modify `regenerate_html.py`, extend `tests/test_regenerate.py`

- [ ] **Step 1: Refactor into stage 1 (build data) + stage 2 (ship)**

Change `regenerate(...)` to:
1. **Stage 1** — keep the current flow (open editable `--html`, import the 3 CSVs, overlay settings + people) but instead of downloading there, read the assembled object:
   `data_json = page.evaluate("() => localStorage.getItem('insignia_ai_strategy_map_v2')")`
   then `browser.close()` for stage 1.
2. **Ensure the locked bundle exists** — new arg `--locked-html` (default `Insignia AI Strategy Map - locked.html`); if missing, build it inline: `locked_html = lock_app.build_locked(pathlib.Path(html_path).read_text())` and write it to `--locked-html` (log that it was built).
3. **Stage 2** — open the locked bundle, `page.evaluate("(v)=>localStorage.setItem('insignia_ai_strategy_map_v2', v)", data_json)`, `page.reload()`, wait for the `Data` tab, then click **Download standalone HTML** with a **settle (2500ms) + retry (up to 4×)** to absorb the known download-timing flakiness; save via the existing temp-then-promote guard.

Import `lock_app` at the top. Keep all existing args and the CSV/settings/people logic (they run in stage 1).

- [ ] **Step 2: Extend the browser smoke test**

In `tests/test_regenerate.py::test_regenerate_reflects_csv`, after the existing sentinel assertions, add checks that the output has **no** mutation controls and **has** Export (reuse the evaluate from Task 2's test). Keep the existing sentinel checks (they prove data still lands through the two-stage path).

- [ ] **Step 3: Run**

Run: `python3 -m pytest tests/test_regenerate.py -v` → PASS (~30s).
Run: `python3 regenerate_html.py --out /tmp/regen-locked.html` → `Regenerated …`; open it and confirm data present + no mutation controls + Export present.
Run: `python3 -m pytest tests/ -q` → all green.

- [ ] **Step 4: Commit**

```bash
git add regenerate_html.py tests/test_regenerate.py
git commit -m "feat: regenerate two-stage — build data in editable copy, ship via locked bundle"
```

---

## Task 4: README + final review

**Files:** Modify `README.md`

- [ ] **Step 1: Document the locked output**

Add to the regeneration section: the shipped file is a locked, view-only page (no upload/edit/add/delete; Export CSV kept); data changes only via `regenerate`; the editable source file is an internal build tool, never distributed; the locked bundle is generated (git-ignored). Add `lock_app.py` and `bundle_common.py` to the Files table.

- [ ] **Step 2: Full suite + commit**

Run: `python3 -m pytest tests/ -q` → all green.
```bash
git add README.md && git commit -m "docs: document the locked view-only output"
```

- [ ] **Step 3: Final review**

Dispatch an independent reviewer over the extension: `bundle_common` round-trip safety, the guard (does it hide ALL mutation controls incl. after re-render; does it wrongly break non-data inputs; is Export genuinely present and correct), the two-stage flow (does stage-1 data reach the locked output; download retry robustness; temp-promote guard intact), README accuracy, and any way a viewer could still mutate data. Fix Critical/Important; re-run suite.

---

## Self-Review Notes
- **Spec coverage:** bundle decode/edit (Task 1), locked bundle via pristine surgery + guard (Task 2), Export kept (Task 2 investigation + test gate), two-stage regenerate (Task 3), README + review (Task 4). All mapped.
- **Placeholder scan:** the only investigation-then-implement step is Export path (a vs b) in Task 2 — bounded, with a test gate asserting Export presence; everything else is concrete code.
- **Name consistency:** `bc.find_resource_with`/`edit_resource`/`get_resource_text`, `lock_app.build_locked`, pristine uuid `3a33ba6c-…`, storage key `insignia_ai_strategy_map_v2`, guard ids `__lock_script`/`__lock_style` — consistent.
- **Validated:** pristine-surgery propagation, round-trip rebuild, localStorage injection, download timing flakiness — all probed before writing.
