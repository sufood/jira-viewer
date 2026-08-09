# WSJF Priority Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Strategy Map app's **Priority** tab with WSJF Studio's views on one shared stories store, unify to the navy theme, and surface WSJF scores in the strategy map.

**Architecture:** Both the main app (`Insignia AI Strategy Map - Jira linked.html`) and `WSJF Studio v2.html` are single-file `dc-runtime` bundles (identical framework build `2e38395c4a4a`). The editable source of each is its `<script type="__bundler/template">` block, with the component defined inline as `<script type="text/x-dc" data-dc-script>`. We extract the main app's template to an editable working file, merge WSJF's scoring module + views + Setup into the single main component wired to one shared `stories` array, restyle to navy, add strategy-map integration, then re-apply into the bundle (updating both the live template block **and** the self-embedded `window.__PRISTINE_HTML` copy the app's serializer uses).

**Tech Stack:** `dc-runtime` (class components, `sc-if`/`sc-for`/`sc-camel-on-*` templating), vanilla JS scoring, Python 3 toolkit (`bundle_common.py`, `lock_app.py`, `regenerate_html.py`), pytest, Playwright/headless Chromium for regenerate parity, the Browser MCP tool for view smoke checks.

**Verification model:** The dc-runtime app has no JS unit-test harness. The regression net is Python: a `tests/test_bundle_integrity.py` invariant suite that must pass after every bundle-mutating task, plus per-view **browser smoke checks** (load the file in the Browser tool, confirm the view renders and the console is error-free). All existing `pytest tests/ -q` must stay green throughout.

**Reference source locations** (extracted copies in scratchpad for reading; line numbers cited below are into these extracts):
- WSJF component + views: `WSJF Studio v2.html` template block → `wsjf_template.html`
- Main component + views: main app template block → `main_template.html`

---

## File Structure

| File | Responsibility | New/Modified |
|---|---|---|
| `app/strategy-map.src.html` | Extracted, human-editable template source — the authoring surface going forward | Create (Task 1.2) |
| `apply_source.py` | Write `app/strategy-map.src.html` back into the bundle: replace the `__bundler/template` block **and** rebuild the `__PRISTINE_HTML` (`page-source`) resource; deterministic gzip | Create (Task 1.3) |
| `bundle_resources.py` | Copy a resource (font/js) from one bundle's manifest into another (returns new uuid); remove a resource by uuid | Create (Task 1.4) |
| `bundle_common.py` | Existing manifest decode/edit/re-encode helpers — reused, not changed | Unchanged |
| `tests/test_bundle_integrity.py` | Invariant guard: manifest+template parse; every `src="<uuid>"` in template resolves in manifest; dc-runtime present; `__PRISTINE_HTML` matches template | Create (Task 1.1) |
| `tests/test_apply_source.py` | Round-trip: extract → apply unchanged → integrity holds; edit → apply → change present in both template and `__PRISTINE_HTML` | Create (Task 1.3) |
| `tests/test_bundle_resources.py` | Copy/remove resource correctness | Create (Task 1.4) |
| `Insignia AI Strategy Map - Jira linked.html` | The editable bundle (built artifact) — mutated only via `apply_source.py` | Modified (Tasks 2+) |
| `regenerate_html.py`, `lock_app.py` | Rebuild shipped/locked outputs; verify parity after new views exist | Verify/patch (Task 7) |

**Working sub-sections inside `app/strategy-map.src.html`** (the single `data-dc-script` component is edited in place):
- Scoring module block (ported WSJF constants + pure functions)
- Shared-store block (one `stories` array + normalizer)
- Component state + persistence
- Render/props for: strategy map (existing), Data tab (existing), Priority tab (new WSJF view-switcher), Setup
- `<x-dc>` markup: Priority-tab view markup (ported from WSJF, restyled)

---

## Phase 1 — Build tooling & safety net (Python, TDD)

### Task 1.1: Bundle-integrity invariant test

**Files:**
- Create: `tests/test_bundle_integrity.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bundle_integrity.py
import json, re, base64, gzip, os
import pytest

BUNDLE = "Insignia AI Strategy Map - Jira linked.html"

def _block(html, kind):
    m = re.search(r'<script type="__bundler/%s">(.*?)</script>' % kind, html, re.S)
    assert m, f"missing __bundler/{kind} block"
    return m.group(1).strip()

def _manifest(html):
    return json.loads(_block(html, "manifest"))

def _resource_text(html, uuid):
    v = _manifest(html)[uuid]
    raw = base64.b64decode(v["data"])
    if v.get("compressed"):
        raw = gzip.decompress(raw)
    return raw.decode("utf-8")

def load():
    with open(BUNDLE, encoding="utf-8") as f:
        return f.read()

def test_manifest_and_template_parse():
    html = load()
    man = _manifest(html)
    tmpl = json.loads(_block(html, "template"))
    assert isinstance(man, dict) and man
    assert "<x-dc>" in tmpl

def test_every_template_uuid_resolves():
    html = load()
    man = _manifest(html)
    tmpl = json.loads(_block(html, "template"))
    for uuid in re.findall(r'src="([0-9a-f-]{36})"', tmpl):
        assert uuid in man, f"template references missing resource {uuid}"

def test_dc_runtime_present():
    html = load()
    man = _manifest(html)
    texts = []
    for uuid, v in man.items():
        if "javascript" in (v.get("mime") or ""):
            texts.append(_resource_text(html, uuid))
    assert any("GENERATED from dc-runtime" in t for t in texts)

def test_pristine_html_matches_template():
    html = load()
    tmpl = json.loads(_block(html, "template"))
    # __PRISTINE_HTML lives in a page-source resource; find and compare.
    man = _manifest(html)
    pristine = None
    for uuid, v in man.items():
        if "javascript" not in (v.get("mime") or ""):
            continue
        t = _resource_text(html, uuid)
        m = re.search(r'window\.__PRISTINE_HTML\s*=\s*("(?:[^"\\]|\\.)*")', t)
        if m:
            pristine = json.loads(m.group(1))
            break
    assert pristine is not None, "no __PRISTINE_HTML resource found"
    assert "<x-dc>" in pristine
    # Structural equality: same component script body.
    def dc_body(s):
        mm = re.search(r'data-dc-script="".*?>(.*?)</script>', s, re.S)
        return mm.group(1) if mm else None
    assert dc_body(pristine) == dc_body(tmpl), "__PRISTINE_HTML component drifted from template"
```

- [ ] **Step 2: Run to verify current bundle passes (baseline is green)**

Run: `python -m pytest tests/test_bundle_integrity.py -q`
Expected: PASS (this codifies the current healthy invariants). If `test_pristine_html_matches_template` fails on the untouched bundle, relax `dc_body` to compare normalized whitespace — the invariant is "component bodies equal", adjust the extractor until the pristine bundle passes, then commit that as the baseline.

- [ ] **Step 3: Commit**

```bash
git add tests/test_bundle_integrity.py
git commit -m "test: bundle-integrity invariants for the strategy-map app"
```

### Task 1.2: Extract the editable source

**Files:**
- Create: `app/strategy-map.src.html`
- Create: `extract_source.py` (one-shot extractor; kept for reproducibility)

- [ ] **Step 1: Write `extract_source.py`**

```python
# extract_source.py  — dump the app's editable template source to app/strategy-map.src.html
import json, re, os
BUNDLE = "Insignia AI Strategy Map - Jira linked.html"
OUT = "app/strategy-map.src.html"
def main():
    html = open(BUNDLE, encoding="utf-8").read()
    m = re.search(r'<script type="__bundler/template">(.*?)</script>', html, re.S)
    tmpl = json.loads(m.group(1).strip())
    os.makedirs("app", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(tmpl)
    print("wrote", OUT, len(tmpl), "bytes")
if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `python extract_source.py`
Expected: `wrote app/strategy-map.src.html <N> bytes` (N ≈ 151000). The file contains `<x-dc>` and one `data-dc-script`.

- [ ] **Step 3: Commit**

```bash
git add extract_source.py app/strategy-map.src.html
git commit -m "chore: extract editable strategy-map source from the bundle"
```

### Task 1.3: `apply_source.py` + round-trip test

**Files:**
- Create: `apply_source.py`
- Create: `tests/test_apply_source.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_apply_source.py
import subprocess, shutil, re, json, os
from tests.test_bundle_integrity import _manifest, _block, _resource_text

BUNDLE = "Insignia AI Strategy Map - Jira linked.html"

def _pristine(html):
    man = _manifest(html)
    for uuid, v in man.items():
        if "javascript" in (v.get("mime") or ""):
            t = _resource_text(html, uuid)
            m = re.search(r'window\.__PRISTINE_HTML\s*=\s*("(?:[^"\\]|\\.)*")', t)
            if m:
                return json.loads(m.group(1))
    return None

def test_roundtrip_unchanged(tmp_path):
    work = tmp_path / "b.html"
    shutil.copy(BUNDLE, work)
    src = tmp_path / "s.html"
    subprocess.run(["python", "apply_source.py", "--extract",
                    "--bundle", str(work), "--src", str(src)], check=True)
    subprocess.run(["python", "apply_source.py",
                    "--bundle", str(work), "--src", str(src)], check=True)
    html = work.read_text(encoding="utf-8")
    tmpl = json.loads(_block(html, "template"))
    assert "<x-dc>" in tmpl

def test_edit_lands_in_template_and_pristine(tmp_path):
    work = tmp_path / "b.html"; shutil.copy(BUNDLE, work)
    src = tmp_path / "s.html"
    subprocess.run(["python", "apply_source.py", "--extract",
                    "--bundle", str(work), "--src", str(src)], check=True)
    text = src.read_text(encoding="utf-8")
    marker = "/*__WSJF_MERGE_MARKER__*/"
    src.write_text(text.replace("</x-dc>", marker + "</x-dc>", 1), encoding="utf-8")
    subprocess.run(["python", "apply_source.py",
                    "--bundle", str(work), "--src", str(src)], check=True)
    html = work.read_text(encoding="utf-8")
    assert marker in json.loads(_block(html, "template"))
    assert marker in _pristine(html)   # serializer copy updated too
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_apply_source.py -q`
Expected: FAIL (`apply_source.py` does not exist).

- [ ] **Step 3: Write `apply_source.py`**

```python
# apply_source.py — extract/apply the editable template source into the bundle.
# Apply mode updates BOTH the live __bundler/template block and the
# __PRISTINE_HTML page-source resource so the app's own serializer stays correct.
import argparse, base64, gzip, io, json, re

MANI_RE = re.compile(r'(<script type="__bundler/manifest">)(.*?)(</script>)', re.S)
TMPL_RE = re.compile(r'(<script type="__bundler/template">)(.*?)(</script>)', re.S)

def _manifest(html):
    m = MANI_RE.search(html); return m, json.loads(m.group(2).strip())

def _dec(v):
    raw = base64.b64decode(v["data"])
    return gzip.decompress(raw).decode("utf-8") if v.get("compressed") else raw.decode("utf-8")

def _enc(v, text):
    data = text.encode("utf-8")
    if v.get("compressed"):
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
            g.write(data)
        data = buf.getvalue()
    v = dict(v); v["data"] = base64.b64encode(data).decode(); return v

def extract(html):
    return json.loads(TMPL_RE.search(html).group(2).strip())

def _find_pristine_uuid(html, manifest):
    for uuid, v in manifest.items():
        if "javascript" in (v.get("mime") or "") and "__PRISTINE_HTML" in _dec(v):
            return uuid
    return None

def apply(html, source):
    # 1. Replace the template block (JSON string of the source HTML).
    new_tmpl_json = json.dumps(source)
    m = TMPL_RE.search(html)
    html = html[:m.start(2)] + new_tmpl_json + html[m.end(2):]
    # 2. Rebuild the __PRISTINE_HTML resource to match, preserving its wrapper.
    mman, manifest = _manifest(html)
    uuid = _find_pristine_uuid(html, manifest)
    if uuid:
        v = manifest[uuid]; text = _dec(v)
        esc = json.dumps(source).replace("</", "<\\/")
        text = re.sub(r'window\.__PRISTINE_HTML\s*=\s*"(?:[^"\\]|\\.)*"',
                      "window.__PRISTINE_HTML = " + esc, text, count=1)
        manifest[uuid] = _enc(v, text)
        new_man = json.dumps(manifest, separators=(",", ":"))
        html = html[:mman.start(2)] + new_man + html[mman.end(2):]
    return html

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default="Insignia AI Strategy Map - Jira linked.html")
    ap.add_argument("--src", default="app/strategy-map.src.html")
    ap.add_argument("--extract", action="store_true")
    a = ap.parse_args()
    html = open(a.bundle, encoding="utf-8").read()
    if a.extract:
        open(a.src, "w", encoding="utf-8").write(extract(html))
        print("extracted ->", a.src); return
    source = open(a.src, encoding="utf-8").read()
    open(a.bundle, "w", encoding="utf-8").write(apply(html, source))
    print("applied", a.src, "->", a.bundle)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_apply_source.py tests/test_bundle_integrity.py -q`
Expected: PASS. If `test_pristine_html_matches_template` fails, the `__PRISTINE_HTML` regex wrapper differs — inspect `_dec` of the page-source resource and adjust the `re.sub` pattern until template and pristine bodies match.

- [ ] **Step 5: Commit**

```bash
git add apply_source.py tests/test_apply_source.py
git commit -m "feat: apply_source.py round-trips editable source into the bundle"
```

### Task 1.4: `bundle_resources.py` (copy fonts/js between bundles) + test

**Files:**
- Create: `bundle_resources.py`
- Create: `tests/test_bundle_resources.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bundle_resources.py
import bundle_resources as br
import json, re, base64, gzip

MAIN = "Insignia AI Strategy Map - Jira linked.html"
WSJF = "WSJF Studio v2.html"

def _man(p):
    h = open(p, encoding="utf-8").read()
    return json.loads(re.search(r'<script type="__bundler/manifest">(.*?)</script>', h, re.S).group(1))

def test_copy_resource_adds_uuid(tmp_path):
    main = open(MAIN, encoding="utf-8").read()
    wsjf = open(WSJF, encoding="utf-8").read()
    # pick one woff2 font uuid from WSJF
    src_uuid = next(u for u, v in _man(WSJF).items() if v.get("mime") == "font/woff2")
    new_html, new_uuid = br.copy_resource(main, wsjf, src_uuid)
    assert new_uuid in _man_str(new_html)
    assert len(_man_from_str(new_html)) == len(_man(MAIN)) + 1

def _man_str(html): return html
def _man_from_str(html):
    return json.loads(re.search(r'<script type="__bundler/manifest">(.*?)</script>', html, re.S).group(1))

def test_remove_resource(tmp_path):
    wsjf = open(WSJF, encoding="utf-8").read()
    victim = next(u for u, v in _man(WSJF).items() if v.get("mime") == "text/csv")
    out = br.remove_resource(wsjf, victim)
    assert victim not in _man_from_str(out)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_bundle_resources.py -q`
Expected: FAIL (`bundle_resources` not found).

- [ ] **Step 3: Write `bundle_resources.py`**

```python
# bundle_resources.py — move resources between app bundles by manifest uuid.
import json, re
MANI_RE = re.compile(r'(<script type="__bundler/manifest">)(.*?)(</script>)', re.S)

def _man(html):
    m = MANI_RE.search(html); return m, json.loads(m.group(2).strip())

def _write(html, m, manifest):
    return html[:m.start(2)] + json.dumps(manifest, separators=(",", ":")) + html[m.end(2):]

def copy_resource(dst_html, src_html, src_uuid, new_uuid=None):
    _, src = _man(src_html)
    m, dst = _man(dst_html)
    new_uuid = new_uuid or src_uuid
    dst[new_uuid] = src[src_uuid]
    return _write(dst_html, m, dst), new_uuid

def remove_resource(html, uuid):
    m, man = _man(html)
    man.pop(uuid, None)
    return _write(html, m, man)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_bundle_resources.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bundle_resources.py tests/test_bundle_resources.py
git commit -m "feat: bundle_resources.py copies/removes manifest resources across bundles"
```

### Task 1.5: Baseline browser smoke check (pre-merge)

**Files:** none (verification only)

- [ ] **Step 1: Open the current bundle in the Browser tool**

Navigate the Browser MCP to `file:///Users/scotty/dev/scryptid/insignia/0x_Themes/jira-viewer/Insignia AI Strategy Map - Jira linked.html`.

- [ ] **Step 2: Record the baseline**

Confirm: strategy map renders; tabs **Data / Divisions / Initiatives / Priority** switch; console has no errors. Screenshot the current **Priority** tab. This is the "before" reference for later comparison.

- [ ] **Step 3: Commit a note**

```bash
git commit --allow-empty -m "chore: baseline smoke check recorded before WSJF merge"
```

---

## Phase 2 — WSJF fonts + scoring module into the source

### Task 2.1: Bring WSJF's IBM Plex Mono fonts into the bundle

**Files:**
- Modify: `Insignia AI Strategy Map - Jira linked.html` (via a one-shot script)
- Create: `import_wsjf_fonts.py`

- [ ] **Step 1: Write `import_wsjf_fonts.py`**

```python
# import_wsjf_fonts.py — copy WSJF's woff2 fonts into the main bundle,
# recording {original-css-name -> new uuid} is unnecessary; the source CSS
# will reference the fonts by uuid via the loader like other resources.
import json, re, bundle_resources as br
MAIN = "Insignia AI Strategy Map - Jira linked.html"
WSJF = "WSJF Studio v2.html"

def man(html):
    return json.loads(re.search(r'<script type="__bundler/manifest">(.*?)</script>', html, re.S).group(1))

def main():
    main_html = open(MAIN, encoding="utf-8").read()
    wsjf_html = open(WSJF, encoding="utf-8").read()
    mapping = {}
    for uuid, v in man(wsjf_html).items():
        if v.get("mime") == "font/woff2":
            main_html, new_uuid = br.copy_resource(main_html, wsjf_html, uuid)
            mapping[uuid] = new_uuid
    open(MAIN, "w", encoding="utf-8").write(main_html)
    open("app/_wsjf_font_map.json", "w").write(json.dumps(mapping, indent=2))
    print("copied", len(mapping), "fonts")
if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it, then re-run integrity**

Run: `python import_wsjf_fonts.py && python -m pytest tests/test_bundle_integrity.py -q`
Expected: `copied 19 fonts` (WSJF has 19 woff2 resources), integrity PASS.

- [ ] **Step 3: Commit**

```bash
git add import_wsjf_fonts.py app/_wsjf_font_map.json "Insignia AI Strategy Map - Jira linked.html"
git commit -m "feat: import WSJF IBM Plex Mono fonts into the strategy-map bundle"
```

### Task 2.2: Port WSJF's `@font-face` + scoring module into the source

**Files:**
- Modify: `app/strategy-map.src.html` (component `data-dc-script`, `<style>`)

- [ ] **Step 1: Extract the current source fresh**

Run: `python apply_source.py --extract`
Expected: `extracted -> app/strategy-map.src.html`.

- [ ] **Step 2: Add the `@font-face` rules**

Copy the `@font-face` blocks for IBM Plex Mono from `wsjf_template.html` (the `<style>` in its `<head>`, search `@font-face`) into the `<style>` of `app/strategy-map.src.html`, rewriting each `src:url(<wsjf-uuid>)` to the mapped uuid from `app/_wsjf_font_map.json`.

- [ ] **Step 3: Port the scoring module verbatim**

Into the component's `data-dc-script`, above the component class, paste **verbatim** from `wsjf_template.html` these top-level declarations and functions (they are pure, framework-free, and depend only on their arguments):
`CATS`, `SIZES`, `HEAT`, `HEAT_FG`, `PILLARS`, `DIV_PILLAR`, `CAPS`, `MUSTDO_RE` (source L812–L872) and functions `capabilityOf`, `confidenceOf`, `parseCSV`, `pick`, `shortName`, `evidenceBody`, `hasNum`, `scoreStory` and its continuation through `return { scores, why, pillar }` (source L875–L1041).

Wrap them in an IIFE that exposes one entry point so the rest of the component calls a single surface:

```js
// --- WSJF scoring module (ported verbatim from WSJF Studio v2; pure) ---
const WSJF = (() => {
  /* PASTE CATS..DIV_PILLAR..CAPS..MUSTDO_RE here */
  /* PASTE capabilityOf, confidenceOf, parseCSV, pick, shortName,
     evidenceBody, hasNum, scoreStory here */
  function buildCorpus(stories) {
    const themeFreq = {};
    stories.forEach(s => (s.themes || []).forEach(t => { themeFreq[t] = (themeFreq[t] || 0) + 1; }));
    return { themeFreq };
  }
  return { CATS, SIZES, HEAT, HEAT_FG, PILLARS, DIV_PILLAR, CAPS,
           capabilityOf, confidenceOf, scoreStory, buildCorpus, shortName, evidenceBody };
})();
```

> Note: `buildCorpus` reproduces the `themeFreq` structure `capabilityOf` expects (`corpus.themeFreq`). Confirm against WSJF's own corpus builder — search `themeFreq` in `wsjf_template.html` and match its shape exactly; if WSJF computes additional corpus fields used by `scoreStory`, include them.

- [ ] **Step 4: Apply + integrity + smoke**

Run: `python apply_source.py && python -m pytest tests/test_bundle_integrity.py -q`
Expected: integrity PASS. Then open the bundle in the Browser tool; confirm the app still loads and the console is error-free (the scoring module is defined but not yet called).

- [ ] **Step 5: Commit**

```bash
git add app/strategy-map.src.html "Insignia AI Strategy Map - Jira linked.html"
git commit -m "feat: port WSJF fonts + pure scoring module into the strategy-map source"
```

---

## Phase 3 — One shared stories store + derivation

### Task 3.1: Identify and unify the stories source

**Files:**
- Modify: `app/strategy-map.src.html`

- [ ] **Step 1: Locate the current stories representation**

In `app/strategy-map.src.html`, read the component `state` (source L781) and the CSV import path (`importCsv`, `csvToRecords`, search both). The strategy map's per-division `opportunities` come from `window.WORKSHOP_DATA`; the Data tab / CSV import build the flat story list. Write down (as a comment in the source) the single array that will be canonical — the flattened list of story records with keys `#, Division, Opportunity, AI-fit, Key people, Systems, Themes, Summary, Description, Jira Key, Jira URL`.

- [ ] **Step 2: Add a normalizer to the shared store**

Add a method that maps a raw story record to the shape `WSJF.scoreStory` expects (verify field names against WSJF's `readFile`/row builder — search `themes:` and `systems:` and `body:` in `wsjf_template.html` around L1131–L1169):

```js
normalizeStory(rec, i) {
  const themes = (rec["Themes"] || "").split(/;|,/).map(s => s.trim()).filter(Boolean);
  const systems = (rec["Systems"] || "").split(/;|,/).map(s => s.trim()).filter(Boolean);
  const desc = rec["Description"] || "";
  const body = WSJF.evidenceBody(desc);
  return {
    id: rec["Jira Key"] || String(rec["#"] || i),
    division: rec["Division"] || "",
    title: rec["Opportunity"] || "",
    summary: rec["Summary"] || "",
    themes, systems, body,
    rawLen: desc.length,
    thin: desc.length < 200,
    url: rec["Jira URL"] || "",
  };
}
```

> Cross-check every field WSJF's `scoreStory`/`capabilityOf`/`confidenceOf` reads (`s.body, s.summary, s.themes, s.systems, s.thin, s.rawLen`) is populated here. Adjust split delimiters to match WSJF's own parsing exactly.

- [ ] **Step 3: Wire the store**

Ensure `this.state.stories` (raw 11-column records) is the one array populated at init (from WORKSHOP_DATA opportunities and/or CSV import). Remove any WSJF-specific `rows`/`backlogCsv` fetch — the WSJF views will read `this.state.stories` via the derivation in Task 3.2. Delete the WSJF `componentDidMount` fetch of `backlogCsv` (source: WSJF L1084–L1097 pattern) if it was pasted; the main app already has the data.

- [ ] **Step 4: Remove the now-unused WSJF backlog CSV resource**

The WSJF `backlogCsv` resource is not in the main bundle (it was WSJF's own). Confirm no `src`/fetch in the source references a CSV uuid. Run integrity + smoke.

Run: `python apply_source.py && python -m pytest tests/test_bundle_integrity.py -q`
Expected: PASS; app loads; console clean.

- [ ] **Step 5: Commit**

```bash
git add app/strategy-map.src.html "Insignia AI Strategy Map - Jira linked.html"
git commit -m "feat: single shared stories store feeding the scoring module"
```

### Task 3.2: `deriveScores` + model params + persistence

**Files:**
- Modify: `app/strategy-map.src.html`

- [ ] **Step 1: Add model-param state + persistence keys**

Add to component state, mirroring WSJF (source L1069–L1084): `overrides` (`wsjf.overrides.v1`), `sizes` (`wsjf.sizes.v1`), `capacity` (`wsjf.capacity.v1`, default 18), `weights` (`wsjf.weights.v1`, null → defaults), `must` (`wsjf.mustdo.v1`), `off` (financial toggles). Port the WSJF `save(k,v)` helper (L1172) and the setters `resetAll` (L1184), `resetWeights` (L1192), `W()` (L1204), `activeCats()` (L1205), plus the override/size/must setters (L1176–L1201) verbatim.

- [ ] **Step 2: Add the single derivation entry point**

Port WSJF's `derived()` (source L1204–L1230) as `deriveScores()`, reading `this.state.stories` (normalized via `normalizeStory`) instead of `this.state.rows`:

```js
deriveScores() {
  const norm = this.state.stories.map((r, i) => this.normalizeStory(r, i));
  const corpus = WSJF.buildCorpus(norm);
  const W = this.W();
  const act = this.activeCats();
  const totalW = act.reduce((a, c) => a + W[c.k], 0);
  const list = norm.map(s => {
    const sc = WSJF.scoreStory(s, corpus);
    const ov = this.state.overrides[s.id] || {};
    const scores = Object.assign({}, sc.scores, ov);
    const value = act.reduce((a, c) => a + (scores[c.k] || 0) * W[c.k], 0) / (totalW || 1);
    const sizeIdx = this.state.sizes[s.id] != null ? this.state.sizes[s.id] : this.autoSize(s, sc);
    const pts = WSJF.SIZES[sizeIdx].pts;
    const wsjf = +(value / pts).toFixed(2);
    const must = this.state.must[s.id] != null ? this.state.must[s.id] : this.mustAuto(s);
    return { s, scores, why: sc.why, pillar: sc.pillar, value, sizeIdx, pts, wsjf, must,
             conf: WSJF.confidenceOf(s),
             edited: Object.keys(ov).length > 0 || this.state.sizes[s.id] != null };
  });
  list.sort((a, b) => (b.must - a.must) || (b.wsjf - a.wsjf));
  list.forEach((r, i) => r.rank = i + 1);
  return { list, W, act, totalW };
}
```

> `autoSize` and `mustAuto` correspond to WSJF's `r.autoSize`/`r.mustAuto` computed in its row builder (search `autoSize` and `mustAuto` in `wsjf_template.html`). Port those two derivations verbatim as methods. Match WSJF's `value` and `wsjf` formulas exactly — copy the arithmetic from WSJF's `derived()`, do not invent it.

- [ ] **Step 2b: Verify the numbers against WSJF**

Because there is no JS unit harness, verify by parity: open both the untouched `WSJF Studio v2.html` and the current bundle in the Browser tool, and confirm the Top-10 WSJF ranks/scores match for the shared corpus once the Priority tab exists (this check is completed in Task 4.3; note the expected values now).

- [ ] **Step 3: Apply + integrity + smoke**

Run: `python apply_source.py && python -m pytest tests/test_bundle_integrity.py -q`
Expected: PASS; console clean.

- [ ] **Step 4: Commit**

```bash
git add app/strategy-map.src.html "Insignia AI Strategy Map - Jira linked.html"
git commit -m "feat: deriveScores + what-if model params on the shared store"
```

---

## Phase 4 — Priority tab = WSJF views (restyled navy)

### Task 4.1: View switcher + mode wiring

**Files:**
- Modify: `app/strategy-map.src.html`

- [ ] **Step 1: Add a `priorityView` sub-state**

Add `priorityView: "exec"` to state. The main app's `mode === "priority"` (from `modePriority`, source L1344 `setMode`) selects the Priority tab; within it, `priorityView` selects exec/table/matrix/bubble/heat/stair/setup. Add a setter `setPriorityView(k){ this.setState({ priorityView: k }) }`.

- [ ] **Step 2: Replace the Priority markup region**

In the `<x-dc>` markup, find the current Priority-mode render region (search the block guarded by the priority mode near the Data/Divisions/Initiatives conditionals, e.g. `showData`/mode conditionals around source L338–L603). Replace the current Priority content with a container holding: a view-switcher tab bar (buttons calling `setPriorityView`) + the seven WSJF view blocks copied from `wsjf_template.html` (the `sc-if` blocks at L369 matrix, L408 bubble, L440 heat, L465 stair, L499 exec, L583 table, L642 setup). Keep each block's structure; change its `isMatrix`/`isExec`/… guards to read from `priorityView` in the render props.

- [ ] **Step 3: Provide the render props for every view**

Port WSJF's render/props methods that build `kpis`, `execRows`, `sliders`, `mixRows`, `capChips`, table rows, matrix/bubble/heat/stair geometry (WSJF source L1230–L1625) as component methods, all sourced from `deriveScores()`. Expose the same prop names the copied markup binds (`isExec`, `execRows`, `kpis`, `sliders`, `onResetWeights`, `capacity`, `onCapacity`, `onResetAll`, etc.). Copy each method body verbatim, substituting `this.derived()` → `this.deriveScores()` and `this.state.rows` → normalized stories.

- [ ] **Step 4: Apply + integrity + smoke each view**

Run: `python apply_source.py && python -m pytest tests/test_bundle_integrity.py -q`
Then in the Browser tool: open the bundle, go to Priority, click through all seven views. Expected: each renders without console errors. Fix binding mismatches (undefined props) until clean.

- [ ] **Step 5: Commit**

```bash
git add app/strategy-map.src.html "Insignia AI Strategy Map - Jira linked.html"
git commit -m "feat: Priority tab hosts all WSJF views on the shared store"
```

### Task 4.2: Setup view writes into the shared store

**Files:**
- Modify: `app/strategy-map.src.html`

- [ ] **Step 1: Point Setup's file input at the shared store**

The Setup view's `onFile` (WSJF L1131) currently builds WSJF `rows`. Re-target it: parse the uploaded CSV with the existing `parseCSV`/`csvToRecords`, then **replace** `this.state.stories` (the one store) and re-render. This preserves "one store" — upload is an override, not a second source.

```js
onFile = e => {
  const f = e.target.files && e.target.files[0]; if (!f) return;
  const reader = new FileReader();
  reader.onload = () => {
    const recs = WSJF.parseCSV(String(reader.result)); // 11-col records
    this.setState({ stories: recs, storySource: f.name });
  };
  reader.readAsText(f);
};
```

- [ ] **Step 2: Keep the optional LLM panel**

Leave the API endpoint/key inputs (WSJF Setup L659–L667) and their handlers intact; they remain session-storage only. No change to the shared store contract.

- [ ] **Step 3: Apply + integrity + smoke**

Run: `python apply_source.py && python -m pytest tests/test_bundle_integrity.py -q`
Then upload `insignia-division-stories-jira-linked.csv` via the Setup view in the Browser tool; confirm the Exec Top-10 repopulates from the uploaded file and the Data tab reflects the same rows (proves single store).

- [ ] **Step 4: Commit**

```bash
git add app/strategy-map.src.html "Insignia AI Strategy Map - Jira linked.html"
git commit -m "feat: Setup upload overrides the single shared stories store"
```

### Task 4.3: WSJF parity check

**Files:** none (verification)

- [ ] **Step 1: Compare Top-10 against standalone WSJF**

Open `WSJF Studio v2.html` and the bundle side by side in the Browser tool (both using the same `insignia-division-stories-jira-linked.csv`). Compare the Exec Top-10 names, ranks, and WSJF scores.
Expected: identical ordering and scores (the scoring module is verbatim). Any mismatch means a `normalizeStory` field or a ported formula diverged — fix, re-apply, re-check.

- [ ] **Step 2: Commit the parity note**

```bash
git commit --allow-empty -m "test: WSJF Top-10 parity between standalone and merged Priority tab"
```

---

## Phase 5 — Strategy-map ↔ WSJF integration (live-linked)

### Task 5.1: WSJF-ranked stories in division detail

**Files:**
- Modify: `app/strategy-map.src.html`

- [ ] **Step 1: Rank the selected division's opportunities**

Where the division detail/opportunity cards are built (source `selectDivision`/`layoutCards` around L1351–L1505), sort that division's stories by their `wsjf`/`rank` from `deriveScores()` and add a score + rank badge to each card's props.

- [ ] **Step 2: Apply + smoke**

Run: `python apply_source.py && python -m pytest tests/test_bundle_integrity.py -q`
Then select a division on the map; confirm its cards show WSJF order + badges; console clean.

- [ ] **Step 3: Commit**

```bash
git add app/strategy-map.src.html "Insignia AI Strategy Map - Jira linked.html"
git commit -m "feat: division detail lists stories in WSJF order with score badges"
```

### Task 5.2: Priority-heat node overlay (toggle)

**Files:**
- Modify: `app/strategy-map.src.html`

- [ ] **Step 1: Add the toggle + aggregate signal**

Add `heatOverlay: false` to state and a toggle control in the map header. When on, tint each division node by an aggregate WSJF signal — its share of the global Top-10 (count of that division's stories in `deriveScores().list.slice(0,10)`), mapped through `WSJF.HEAT`. When off, nodes keep their current colours.

- [ ] **Step 2: Recolor nodes from derivation**

In the node draw path (`drawDivisions`, source L1088/L1146), when `heatOverlay`, override the node fill with the heat colour for that division's signal. Because the fill reads `deriveScores()`, live what-if weight changes re-tint automatically.

- [ ] **Step 3: Apply + smoke**

Run: `python apply_source.py && python -m pytest tests/test_bundle_integrity.py -q`
Then toggle heat on; drag a what-if weight in Priority→Exec; return to the map and confirm the tint changed (live-linked). Console clean.

- [ ] **Step 4: Commit**

```bash
git add app/strategy-map.src.html "Insignia AI Strategy Map - Jira linked.html"
git commit -m "feat: priority-heat map overlay, live-linked to what-if weights"
```

### Task 5.3: Click-through from map to Priority

**Files:**
- Modify: `app/strategy-map.src.html`

- [ ] **Step 1: Add a "View in Priority" affordance**

In the division detail panel, add a control that calls `setMode("priority")` then filters the Priority views to that division: add `priorityDivision` to state, set it here, and have the view methods filter `deriveScores().list` to `priorityDivision` when set (with a "clear filter" chip in the Priority header).

- [ ] **Step 2: Apply + smoke**

Run: `python apply_source.py && python -m pytest tests/test_bundle_integrity.py -q`
Then select a division → click "View in Priority" → confirm Priority opens filtered to it; clear the filter restores all. Console clean.

- [ ] **Step 3: Commit**

```bash
git add app/strategy-map.src.html "Insignia AI Strategy Map - Jira linked.html"
git commit -m "feat: click-through from map division to a scoped Priority tab"
```

---

## Phase 6 — Theme unification (navy)

### Task 6.1: Token pass across WSJF views

**Files:**
- Modify: `app/strategy-map.src.html`

- [ ] **Step 1: Map WSJF colours → navy tokens**

In the copied WSJF view markup, replace WSJF's palette with the main app's: backgrounds `#0b0d10`/`#101319`/`#161a21` → the app's navy surfaces (`#0a1524` base; panel `rgba(9,18,30,0.72)`; borders `rgba(255,255,255,0.12)` per source L308 legend styles). Keep amber `#ffb020` as the WSJF-score accent and `WSJF.HEAT` for the heatmap. Keep IBM Plex Mono for numerics only.

- [ ] **Step 2: Apply + full visual pass**

Run: `python apply_source.py && python -m pytest tests/test_bundle_integrity.py -q`
Then in the Browser tool, screenshot each Priority view and the map; confirm one coherent navy look and readable contrast. Iterate on tokens until consistent.

- [ ] **Step 3: Commit**

```bash
git add app/strategy-map.src.html "Insignia AI Strategy Map - Jira linked.html"
git commit -m "style: unify WSJF views to the navy theme"
```

---

## Phase 7 — Regenerate/lock parity + full test run

### Task 7.1: Locked-bundle parity

**Files:**
- Verify: `lock_app.py`; Modify only if the lock guard misses new controls.

- [ ] **Step 1: Rebuild the locked bundle**

Run: `python lock_app.py`
Expected: locked bundle builds. Open it in the Browser tool: Priority views render read-only; confirm the lock hides editing affordances (score edits, API key, Setup upload) per the app's view-only contract. If any new WSJF editing control leaks through the lock, extend `lock_app.py`'s guard to cover it, then rebuild.

- [ ] **Step 2: Commit any lock changes**

```bash
git add lock_app.py
git commit -m "fix: extend view-only lock to cover WSJF editing controls"
```

### Task 7.2: Regenerate parity (headless round-trip)

**Files:**
- Verify: `regenerate_html.py`

- [ ] **Step 1: Regenerate from the CSV**

Run: `python regenerate_html.py`
Expected: produces `Insignia AI Strategy Map - regenerated.html` with the Priority/WSJF views intact and the stories driven by `insignia-division-stories-jira-linked.csv`. The serializer reads `__PRISTINE_HTML`, which `apply_source.py` kept in sync — confirm the regenerated file's Priority tab matches the editable one. If the views are missing, `__PRISTINE_HTML` drifted; re-run `apply_source.py` and regenerate.

- [ ] **Step 2: Open regenerated output + smoke**

Open the regenerated file in the Browser tool; click through all views + map heat; console clean.

- [ ] **Step 3: Commit**

```bash
git add "Insignia AI Strategy Map - regenerated.html" "Insignia AI Strategy Map - locked.html"
git commit -m "chore: regenerate shipped/locked outputs with WSJF Priority tab"
```

### Task 7.3: Full suite + finish

**Files:** none

- [ ] **Step 1: Run the whole Python suite**

Run: `python -m pytest tests/ -q`
Expected: all PASS (integrity, apply_source, bundle_resources, plus the pre-existing toolkit tests).

- [ ] **Step 2: Final review**

Invoke `superpowers:requesting-code-review` on the branch diff. Address findings.

- [ ] **Step 3: Finish the branch**

Invoke `superpowers:finishing-a-development-branch` to choose merge/PR.

---

## Self-review notes

- **Spec coverage:** shared store (Ph3), kept Setup+upload writing into the one store (4.2), LLM option kept (4.2), navy theme (Ph6), browser-local overrides (3.2), all views (4.1), full map integration — heat+ranked+jump (5.1–5.3), what-if live-linked (5.2), in-place bundle authoring via `apply_source.py`+`__PRISTINE_HTML` sync (Ph1), regenerate/lock parity (Ph7). All spec items map to tasks.
- **Verification substitute for TDD:** JS has no unit harness; the `tests/test_bundle_integrity.py` invariant + browser smoke + WSJF parity (4.3) + regenerate parity (7.2) are the guards, run after every mutating task.
- **Known risk to watch:** ported WSJF render methods (Task 4.1 Step 3) are the largest verbatim transfer; if a prop name in the copied markup isn't produced by a ported method, the view silently blanks — the per-view smoke check in 4.1 Step 4 is the catch.
- **Assumption to confirm early (Task 3.1):** the exact current stories source in the main component (WORKSHOP_DATA opportunities vs. CSV import) — resolve before Phase 4.
