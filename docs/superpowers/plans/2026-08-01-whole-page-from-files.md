# Whole-Page-From-Files Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the CSV + a `settings.yaml` the single source of truth for the whole strategy-map page — derive the Divisions tab (incl. Systems/Themes) from the Jira stories CSV, add an editable initiatives CSV, and drive header/centre-node/legend from settings.

**Architecture:** A dependency-light `settings_common.py` derives `divisions.csv` from the stories CSV and merges settings into the app's data object. `export_tabs.py` (Playwright) captures the app's current tabs to editable seed files. `regenerate_html.py` grows to import all three tabs via the app's public Upload-CSV contract, then overlay header/hub/legend into `localStorage["insignia_ai_strategy_map_v2"]` and reload before exporting.

**Tech Stack:** Python 3.12, `pyyaml` (already installed, 6.0.3), `playwright`, `pytest`. Builds on the existing `jira_common.py` (reuse `read_csv`/`write_csv`/`split_multi`).

**Reference:** Spec `docs/superpowers/specs/2026-08-01-whole-page-from-files-design.md`.

**VALIDATED FACTS (probed against the real app — rely on these):**
- Storage key: `localStorage["insignia_ai_strategy_map_v2"]`. After a per-tab Upload CSV, the full object is present in localStorage synchronously (~1.8s settle).
- Data object top-level keys: `org, programme, hub, systemsCatalogue, themesCatalogue, departments, initiativeCategories, initiatives, header, fitRating`.
- Divisions are stored as **`departments[]`**, each `{id, name, short, color, tagline, background, people, opportunities, gaps, nextSteps, systems, themes}`. Division-stories are the `opportunities` nested per department.
- Settings live at top-level `header {company,title,intro}`, `hub {id,name,tagline,url}`, `fitRating {title, levels:[{label,color}]}`.
- **Import order stories → divisions → initiatives is non-destructive**: importing Divisions after Division-stories keeps the opportunities AND applies the division colour/systems/themes (validated with sentinels).
- App's public CSV schemas (from its own Export CSV):
  - Divisions: `Division, Systems, Themes, Tagline, Background, Colour`
  - Initiatives: `#, Initiative, Capability, Effort, Value, Quadrant, Divisions impacted`
  - Division stories: the Jira CSV.

---

## File Structure

- Create: `settings_common.py` — YAML load, palette, `derive_divisions`, `merge_settings_into_data`, `build_starter_settings`.
- Create: `export_tabs.py` — Playwright export of the app's tabs to CSV seeds.
- Create: `settings.yaml` — starter settings (generated in Task 2, committed).
- Create: `initiatives.csv` — starter initiatives seed (generated in Task 2, committed).
- Create: `tests/test_settings.py`, extend `tests/test_regenerate.py`.
- Modify: `regenerate_html.py` — derive divisions, import 3 tabs, settings overlay.
- Modify: `README.md`, `.gitignore` (add generated `divisions.csv`).

---

## Task 1: `settings_common.py` — derivation + merge (no browser)

**Files:**
- Create: `settings_common.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_settings.py`:
```python
import settings_common as sc


def _story(div, systems, themes):
    return {"Division": div, "Systems": systems, "Themes": themes}


def test_derive_divisions_roster_first_appearance_order():
    rows = [_story("B", "s1", "t1"), _story("A", "s2", "t2"),
            _story("B", "s3", "t1")]
    divs, unmatched = sc.derive_divisions(rows, {})
    assert [d["Division"] for d in divs] == ["B", "A"]      # first-appearance
    assert unmatched == []


def test_derive_divisions_unions_systems_themes_dedup():
    rows = [_story("A", "Sys1; Sys2", "Th1"),
            _story("A", "Sys2; Sys3", "Th1; Th2")]
    divs, _ = sc.derive_divisions(rows, {})
    d = divs[0]
    assert d["Systems"] == "Sys1; Sys2; Sys3"              # deduped, order kept
    assert d["Themes"] == "Th1; Th2"


def test_derive_divisions_applies_overrides_and_auto_colour():
    rows = [_story("A", "s", "t"), _story("B", "s", "t")]
    settings = {"divisions": {"A": {"colour": "#abcdef",
                                    "tagline": "TA", "background": "BG"}}}
    divs, unmatched = sc.derive_divisions(rows, settings)
    a = next(d for d in divs if d["Division"] == "A")
    b = next(d for d in divs if d["Division"] == "B")
    assert a["Colour"] == "#abcdef" and a["Tagline"] == "TA" and a["Background"] == "BG"
    assert b["Colour"] == sc.PALETTE[1]                    # auto by roster index
    assert b["Tagline"] == "" and b["Background"] == ""
    assert unmatched == []


def test_derive_divisions_warns_unmatched_settings_division():
    rows = [_story("A", "s", "t")]
    divs, unmatched = sc.derive_divisions(rows, {"divisions": {"Ghost": {}}})
    assert [d["Division"] for d in divs] == ["A"]
    assert unmatched == ["Ghost"]


def test_load_settings_missing_returns_empty(tmp_path):
    assert sc.load_settings(tmp_path / "nope.yaml") == {}


def test_load_settings_partial(tmp_path):
    p = tmp_path / "settings.yaml"
    p.write_text('header:\n  company: "X"\n')
    s = sc.load_settings(p)
    assert s == {"header": {"company": "X"}}


def test_merge_settings_overlays_only_present_keys():
    d = {"header": {"company": "old", "title": "keep", "intro": "keepi"},
         "hub": {"id": "hub", "name": "old", "tagline": "old", "url": "old"},
         "fitRating": {"title": "old", "levels": [{"label": "L", "color": "#111"}]}}
    settings = {"header": {"company": "NEW"},
                "hub": {"url": "http://new"},
                "legend": {"title": "Fit", "levels": [{"label": "Hi", "color": "#222"}]}}
    out = sc.merge_settings_into_data(d, settings)
    assert out["header"] == {"company": "NEW", "title": "keep", "intro": "keepi"}
    assert out["hub"]["url"] == "http://new" and out["hub"]["id"] == "hub"
    assert out["fitRating"] == {"title": "Fit", "levels": [{"label": "Hi", "color": "#222"}]}


def test_merge_settings_empty_is_noop():
    d = {"header": {"company": "c"}}
    assert sc.merge_settings_into_data(d, {}) == {"header": {"company": "c"}}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/scotty/dev/scryptid/insignia/0x_Themes/jira-viewer" && python3 -m pytest tests/test_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'settings_common'`.

- [ ] **Step 3: Write the implementation**

Create `settings_common.py`:
```python
#!/usr/bin/env python3
"""Settings + division derivation for the whole-page-from-files regenerate.

- load_settings: read settings.yaml (dependency-light; {} when absent).
- derive_divisions: build the Divisions-CSV rows from the stories CSV, with
  Systems/Themes unioned per division and colour/tagline/background from
  settings (auto-colour otherwise).
- merge_settings_into_data: overlay header/hub/legend onto the app data object.
"""

import os

import yaml

import jira_common as jc   # reuse split_multi (";"-split) — DRY

# Auto-colour palette = the app's own 13 division colours, so new divisions
# look native. Assigned deterministically by roster index (cycles if >13).
PALETTE = ["#3f7c8c", "#c1743a", "#6b6ca3", "#4a8f6d", "#3b6ea5", "#b0567f",
           "#a8484a", "#8a6d3b", "#2f8f8f", "#7a5aa8", "#b98a3c", "#6f8c3e",
           "#bd5f6b"]

# Exact Divisions-CSV header the app's Upload CSV expects.
DIVISION_COLUMNS = ["Division", "Systems", "Themes", "Tagline", "Background",
                    "Colour"]


def load_settings(path="settings.yaml"):
    """Parse settings.yaml into a dict; {} if the file doesn't exist."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _union(seen, cell):
    """Append the ';'-split values of `cell` to list `seen`, dedup, keep order."""
    for v in jc.split_multi(cell):
        if v not in seen:
            seen.append(v)


def derive_divisions(story_rows, settings):
    """Return (division_rows, unmatched_setting_names).

    Roster = distinct `Division` values in first-appearance order. Systems and
    Themes are the deduped union across each division's stories. Colour/Tagline/
    Background come from settings['divisions'][name]; colour auto-assigns from
    PALETTE by roster index when not overridden.
    """
    order, systems, themes = [], {}, {}
    for r in story_rows:
        d = (r.get("Division") or "").strip()
        if not d:
            continue
        if d not in systems:
            order.append(d)
            systems[d], themes[d] = [], []
        _union(systems[d], r.get("Systems", ""))
        _union(themes[d], r.get("Themes", ""))

    overrides = settings.get("divisions") or {}
    rows = []
    for i, d in enumerate(order):
        o = overrides.get(d) or {}
        rows.append({
            "Division": d,
            "Systems": "; ".join(systems[d]),
            "Themes": "; ".join(themes[d]),
            "Tagline": o.get("tagline", ""),
            "Background": o.get("background", ""),
            "Colour": o.get("colour") or PALETTE[i % len(PALETTE)],
        })
    unmatched = [k for k in overrides if k not in systems]
    return rows, unmatched


def merge_settings_into_data(d, settings):
    """Overlay settings onto the app data object `d`, in place. Only keys present
    in settings are touched (never blanks out). settings['legend'] -> d['fitRating']."""
    hdr = settings.get("header")
    if hdr and isinstance(d.get("header"), dict):
        for k in ("company", "title", "intro"):
            if k in hdr:
                d["header"][k] = hdr[k]
    hub = settings.get("hub")
    if hub and isinstance(d.get("hub"), dict):
        for k in ("name", "tagline", "url"):
            if k in hub:
                d["hub"][k] = hub[k]
    leg = settings.get("legend")
    if leg:
        fr = d.setdefault("fitRating", {})
        if "title" in leg:
            fr["title"] = leg["title"]
        if "levels" in leg:
            fr["levels"] = [{"label": l["label"], "color": l["color"]}
                            for l in leg["levels"]]
    return d
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_settings.py -v`
Expected: PASS (8 tests). Then full suite `python3 -m pytest tests/ -q --ignore=tests/test_regenerate.py` → 27 passed.

- [ ] **Step 5: Commit**

```bash
git add settings_common.py tests/test_settings.py
git commit -m "feat: settings_common — derive divisions from stories CSV + settings overlay"
```

---

## Task 2: `export_tabs.py` + starter seed files

**Files:**
- Create: `export_tabs.py`
- Modify: `settings_common.py` (add `build_starter_settings`)
- Create (generated, committed): `initiatives.csv`, `settings.yaml`

- [ ] **Step 1: Add `build_starter_settings` + failing test**

Append to `tests/test_settings.py`:
```python
def test_build_starter_settings_from_division_rows():
    div_rows = [{"Division": "A", "Systems": "s", "Themes": "t",
                 "Tagline": "TA", "Background": "BA", "Colour": "#111"}]
    s = sc.build_starter_settings(div_rows)
    assert s["header"]["company"] == "Insignia Financial"
    assert s["hub"]["url"].startswith("https://ifl.atlassian.net/")
    assert s["legend"]["levels"][0] == {"label": "High", "color": "#e0674c"}
    assert s["divisions"]["A"] == {"colour": "#111", "tagline": "TA",
                                   "background": "BA"}
```
Run: `python3 -m pytest tests/test_settings.py::test_build_starter_settings_from_division_rows -v` → FAIL (no attribute).

- [ ] **Step 2: Implement `build_starter_settings`**

Append to `settings_common.py`:
```python
# Current app defaults (from the bundle's migrate() seed) — the starting point
# a user edits. Values chosen to match what the app ships with today.
_DEFAULT_INTRO = ("Thirteen enterprise workshops · 25 Sprint 1 initiatives. "
                  "Switch lenses above. In this view, click any division to fan "
                  "out its cards — problem areas, AI-fit, the people engaged, "
                  "gaps and next steps.")


def build_starter_settings(division_rows):
    """Assemble a fully-populated settings dict from the app's current defaults
    plus per-division overrides taken from an exported Divisions CSV."""
    return {
        "header": {
            "company": "Insignia Financial",
            "title": "AI Strategy Value Realisation",
            "intro": _DEFAULT_INTRO,
        },
        "hub": {
            "name": "AI Strategy",
            "tagline": "Enterprise-wide AI strategy programme — March 2026",
            "url": "https://ifl.atlassian.net/jira/software/c/projects/AIENG/boards/4552",
        },
        "legend": {
            "title": "AI-fit rating",
            "levels": [
                {"label": "High", "color": "#e0674c"},
                {"label": "Medium-High", "color": "#e3a24b"},
                {"label": "Medium", "color": "#5aa9a0"},
                {"label": "Medium-Low", "color": "#7d8ca3"},
            ],
        },
        "divisions": {
            r["Division"]: {"colour": r.get("Colour", ""),
                            "tagline": r.get("Tagline", ""),
                            "background": r.get("Background", "")}
            for r in division_rows
        },
    }
```
Run the test again → PASS.

- [ ] **Step 3: Write `export_tabs.py`**

Create `export_tabs.py`:
```python
#!/usr/bin/env python3
"""Export the app's current tabs to editable seed files, using its own Export CSV.

    python export_tabs.py                       # writes initiatives.csv, divisions-current.csv, settings.yaml
    python export_tabs.py --html X --headed

Produces the starter files you then hand-edit. `divisions-current.csv` is a
reference dump of the app's current Divisions tab (the live regenerate derives
its own divisions.csv from the stories CSV — this is just for seeding settings).
"""

import argparse
import pathlib
import re
import sys

import yaml
from playwright.sync_api import sync_playwright

import jira_common as jc
import settings_common as sc

DEFAULT_HTML = "Insignia AI Strategy Map - Jira linked.html"
SUBTABS = {"Initiatives": "Initiatives ·", "Divisions": "Divisions ·"}


def _export_tab(page, subtab_label, out_path):
    page.get_by_role("button", name=re.compile(re.escape(subtab_label))).click()
    page.wait_for_timeout(600)
    with page.expect_download(timeout=30_000) as dl:
        page.get_by_role("button", name=re.compile("Export CSV")).click()
    dl.value.save_as(str(out_path))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", default=DEFAULT_HTML)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    html = pathlib.Path(args.html).resolve()
    if not html.exists():
        sys.exit(f"Missing HTML: {html}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        page = browser.new_page(accept_downloads=True)
        page.goto(html.as_uri())
        page.get_by_role("button", name=re.compile(r"^Data$")).wait_for(timeout=30_000)
        page.wait_for_timeout(1500)
        for _ in range(10):
            page.get_by_role("button", name=re.compile(r"^Data$")).click()
            try:
                page.get_by_role("button",
                                 name=re.compile("Divisions ·")).wait_for(
                                     state="visible", timeout=6000)
                break
            except Exception:
                continue
        _export_tab(page, "Initiatives ·", "initiatives.csv")
        _export_tab(page, "Divisions ·", "divisions-current.csv")
        browser.close()

    div_rows = jc.read_csv("divisions-current.csv")
    with open("settings.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(sc.build_starter_settings(div_rows), f,
                       sort_keys=False, allow_unicode=True, width=100)
    print("Wrote initiatives.csv, divisions-current.csv, settings.yaml")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Generate the seed files and verify**

Run: `python3 export_tabs.py`
Expected: prints "Wrote initiatives.csv, divisions-current.csv, settings.yaml".
Verify:
```bash
head -1 initiatives.csv          # -> "#","Initiative","Capability","Effort","Value","Quadrant","Divisions impacted"
python3 -c "import settings_common as sc; s=sc.load_settings('settings.yaml'); print(s['header']['company'], len(s['divisions']), 'divisions')"
```
Expected: header line matches; prints `Insignia Financial 13 divisions`.

- [ ] **Step 5: Commit**

```bash
git add export_tabs.py settings_common.py tests/test_settings.py initiatives.csv settings.yaml divisions-current.csv
git commit -m "feat: export_tabs.py + starter initiatives.csv/settings.yaml seeds"
```

---

## Task 3: extend `regenerate_html.py` — whole page from files

**Files:**
- Modify: `regenerate_html.py`
- Modify: `.gitignore` (add `divisions.csv`)
- Test: extend `tests/test_regenerate.py`

- [ ] **Step 1: Add `divisions.csv` to `.gitignore`**

Append line `divisions.csv` to `.gitignore` (it's a generated build artifact).

- [ ] **Step 2: Rewrite the regenerate flow**

Replace the body of `regenerate(...)` in `regenerate_html.py` and its signature/args. New full file body for the interaction (keep the module docstring header, `DEFAULT_*`, selector constants, and `PWTimeout` import; add `import json`, `import settings_common as sc`, `import jira_common as jc`):

Signature:
```python
def regenerate(csv_path, html_path, out_path, headed,
               initiatives_path="initiatives.csv",
               settings_path="settings.yaml",
               divisions_out="divisions.csv"):
```

Add — after loading the page and the Data-tab retry block (unchanged), before the download — this import+merge sequence:
```python
        # Derive divisions.csv from the stories CSV + settings (A2/A3).
        settings = sc.load_settings(settings_path)
        div_rows, unmatched = sc.derive_divisions(jc.read_csv(csv_path), settings)
        for name in unmatched:
            print(f"  notice: settings division {name!r} has no stories; ignored")
        jc.write_csv(divisions_out, div_rows, fieldnames=sc.DIVISION_COLUMNS)

        # Import the three tabs via the app's own Upload CSV. Order matters:
        # stories → divisions (division metadata authoritative) → initiatives.
        imports = [("Division stories ·", csv_path),
                   ("Divisions ·", divisions_out),
                   ("Initiatives ·", initiatives_path)]
        for subtab, path in imports:
            if not pathlib.Path(path).exists():
                print(f"  notice: {path} missing; skipping {subtab.strip(' ·')} import")
                continue
            page.get_by_role("button", name=re.compile(re.escape(subtab))).click()
            page.wait_for_timeout(600)
            page.set_input_files(FILE_INPUT, str(pathlib.Path(path).resolve()))
            page.wait_for_timeout(1800)

        # Overlay settings (header/hub/legend) into the app's data object, which
        # has no CSV import path, then reload so the app boots the merged state.
        if settings:
            raw = page.evaluate("() => localStorage.getItem('insignia_ai_strategy_map_v2')")
            if raw:
                data = sc.merge_settings_into_data(json.loads(raw), settings)
                page.evaluate(
                    "(v) => localStorage.setItem('insignia_ai_strategy_map_v2', v)",
                    json.dumps(data, ensure_ascii=False))
                page.reload()
                page.get_by_role("button", name=DATA_TAB).wait_for(timeout=30_000)
                page.wait_for_timeout(1000)
            else:
                print("  notice: no app data in localStorage after import; "
                      "settings overlay skipped")
```
Keep the existing download-to-`.part` + size-guard + promote block after this. Update `main()` to add and pass the new args:
```python
    ap.add_argument("--initiatives", default="initiatives.csv")
    ap.add_argument("--settings", default="settings.yaml")
    ap.add_argument("--divisions-out", default="divisions.csv")
    ...
    regenerate(args.csv, args.html, args.out, args.headed,
               initiatives_path=args.initiatives, settings_path=args.settings,
               divisions_out=args.divisions_out)
```

- [ ] **Step 3: Extend the browser smoke test**

Replace `tests/test_regenerate.py::test_regenerate_reflects_csv` body's assembly to also exercise settings + a division, and assert both a story sentinel and a header-company sentinel appear. Add after the existing sentinel setup (keep skip guard):
```python
    # settings.yaml with a sentinel company + one initiatives row
    import yaml
    settings_p = tmp_path / "settings.yaml"
    company = "ZZCOMPANY_regen"
    yaml.safe_dump({"header": {"company": company}}, open(settings_p, "w"))
    init_p = tmp_path / "initiatives.csv"
    jc.write_csv(init_p, [], fieldnames=["#", "Initiative", "Capability",
        "Effort", "Value", "Quadrant", "Divisions impacted"])

    out = tmp_path / "out.html"
    regenerate_html.regenerate(str(src_csv), str(HTML), str(out), headed=False,
                               initiatives_path=str(init_p),
                               settings_path=str(settings_p),
                               divisions_out=str(tmp_path / "divisions.csv"))
    assert out.exists() and out.stat().st_size > 100_000
```
Then, in the verification browser block, also assert the company sentinel is present in the regenerated page text:
```python
        body = pg.evaluate("() => document.body.innerText")
        assert company in body, "settings header.company not in regenerated HTML"
```

- [ ] **Step 4: Run the smoke test**

Run: `python3 -m pytest tests/test_regenerate.py -v`
Expected: PASS (may take ~15s; launches Chromium, imports 3 tabs, merges settings, reloads, downloads, re-opens and checks both sentinels).

- [ ] **Step 5: Run the tool end-to-end + full suite**

Run:
```bash
python3 regenerate_html.py --out "/tmp/regen-whole.html"
python3 -m pytest tests/ -q
```
Expected: `Regenerated /tmp/regen-whole.html (… bytes)`; suite all green.

- [ ] **Step 6: Commit**

```bash
git add regenerate_html.py tests/test_regenerate.py .gitignore
git commit -m "feat: regenerate whole page from files — derive divisions, import 3 tabs, overlay settings"
```

---

## Task 4: README + final review

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Add a section after the existing `regenerate` section:
````markdown
## Whole-page regeneration (settings + all tabs)

`regenerate_html.py` rebuilds the entire page from files:
- **`settings.yaml`** — company, title, intro, centre-node name/tagline/**Jira board url**, and the AI-fit legend (title + labels/colours), plus per-division colour/tagline/background overrides. All sections optional (overlay only).
- **Divisions** are derived from the stories CSV automatically: one per distinct `Division`, with Systems/Themes unioned from its stories; colour/tagline/background from `settings.yaml` (auto-colour otherwise). Written to `divisions.csv` (generated, git-ignored).
- **`initiatives.csv`** — standalone editable file.

```bash
python export_tabs.py        # seed initiatives.csv + settings.yaml from the current app
python regenerate_html.py    # rebuild the standalone HTML from stories CSV + initiatives.csv + settings.yaml
```

Setup now also needs YAML: `pip install requests playwright pyyaml`.
````

- [ ] **Step 2: Full suite + commit**

Run: `python3 -m pytest tests/ -q` → all green.
```bash
git add README.md
git commit -m "docs: document whole-page regeneration (settings.yaml, derived divisions, initiatives)"
```

- [ ] **Step 3: Final review dispatch**

Dispatch one independent reviewer over the whole extension (commits since the spec) checking: derive_divisions correctness (roster/union/overrides/auto-colour), merge_settings overlay-not-blank semantics, regenerate import order + settings merge, README accuracy, and any data-loss path. Fix Critical/Important findings, re-run suite.

---

## Self-Review Notes

- **Spec coverage:** A1 export initiatives (Task 2 `export_tabs.py`), A2 divisions from CSV (Task 1 `derive_divisions`), A3 systems/themes union (Task 1), B1 settings.yaml (Task 1 load + Task 2 starter + Task 3 merge), whole-page regenerate (Task 3), pyyaml/setup + README (Task 4). All mapped.
- **Placeholder scan:** none — every step has concrete code/commands.
- **Name consistency:** `sc.PALETTE`, `sc.DIVISION_COLUMNS`, `sc.load_settings`, `sc.derive_divisions`, `sc.merge_settings_into_data`, `sc.build_starter_settings`; storage key `insignia_ai_strategy_map_v2`; import order stories→divisions→initiatives — consistent across tasks.
- **Validated assumptions:** localStorage persistence, import non-destructiveness, and schema key names were probed against the real app before writing this plan.
