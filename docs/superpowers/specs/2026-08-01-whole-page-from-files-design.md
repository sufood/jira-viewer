# Whole-Page-From-Files — Design (toolkit extension)

**Date:** 2026-08-01
**Status:** Approved decisions, pending spec review
**Builds on:** `2026-08-01-jira-csv-html-toolkit-design.md`

## Purpose

Make the editable files the single source of truth for the **entire** strategy-map
page, not just the Division-stories tab. Adds a settings file, an editable initiatives
CSV, and derives the Divisions tab (incl. Systems/Themes) from the Jira stories CSV.

Maps the user's requests onto the app's data model:

| Request | Implementation |
|---|---|
| A1 Export current Initiatives to an editable CSV seed | `export_tabs.py` captures the app's Export CSV output → `initiatives.csv` |
| A2 Create Division data from the Jira CSV | Derive `divisions.csv` from the stories CSV (names + overrides) |
| A3 Systems & Themes populated from the Jira CSV | Each division's Systems/Themes = deduped union across its stories |
| B1 Settings file (company, title, centre-node link, intro, legend title/labels/colours) | `settings.yaml` |

## The app's data model (reverse-engineered — verified)

- **Storage key:** `localStorage["insignia_ai_strategy_map_v2"]`.
- On load: `d = JSON.parse(localStorage[KEY])` (else a baked seed) → `migrate(d)`.
  On any change: `localStorage[KEY] = JSON.stringify(d)`.
- `d` contains: `header {company, title, intro}`, `hub {id, name, tagline, url}`
  (centre node; `url` = the Jira board link), `fitRating {title, levels:[{label,color}]}`
  (the AI-fit legend), `divisions[]`, `initiatives[]`, and the division-stories.
- **Public CSV contract** — the app's Export/Upload CSV per Data sub-tab uses stable
  schemas (confirmed by exporting each tab):
  - Initiatives: `#, Initiative, Capability, Effort, Value, Quadrant, Divisions impacted`
  - Divisions: `Division, Systems, Themes, Tagline, Background, Colour`
  - Division stories: `#, Division, Opportunity, AI-fit, Key people, Systems, Themes, Summary, Description, Jira Key, Jira URL` (the Jira CSV)

We use the **public CSV import** for the three tabular datasets (robust — it's the app's
own contract) and a **minimal localStorage merge** only for settings (header/hub/legend),
which have no CSV path.

## Files

**New**
- `settings.yaml` — the settings file (see schema below).
- `initiatives.csv` — the editable 25-initiative seed (produced by `export_tabs.py`).
- `divisions.csv` — **generated** artifact (git-ignored; produced during regenerate from
  the stories CSV + settings). Not hand-edited.
- `export_tabs.py` — one-shot: drive the app's Export CSV for each tab → `initiatives.csv`
  and a starter `settings.yaml`/`divisions` reference, so nothing is authored from scratch.
- `settings_common.py` — load/validate `settings.yaml`; derive `divisions.csv` from the
  stories CSV; the auto-colour palette.

**Changed**
- `regenerate_html.py` — assemble + import all three tabs + merge settings, then export.
- `README.md`, `.env.example` unaffected; add `pyyaml` to setup.
- `.gitignore` — add `divisions.csv` (generated).

**Unchanged**
- `jira_sync.py` (push/pull) and `jira_common.py` — the Jira ⇄ stories-CSV bridge stays
  exactly as-is. Initiatives are **standalone** (not pushed/pulled to Jira).

## `settings.yaml` schema

```yaml
header:
  company: "Insignia Financial"
  title: "AI Strategy Value Realisation"
  intro: "Thirteen enterprise workshops · 25 Sprint 1 initiatives. Switch lenses above…"
hub:                                   # the centre node
  name: "AI Strategy"
  tagline: "Enterprise-wide AI strategy programme — March 2026"
  url: "https://ifl.atlassian.net/jira/software/c/projects/AIENG/boards/4552"
legend:                                # AI-fit rating legend
  title: "AI-fit rating"
  levels:
    - {label: "High",        color: "#e0674c"}
    - {label: "Medium-High", color: "#e3a24b"}
    - {label: "Medium",      color: "#5aa9a0"}
    - {label: "Medium-Low",  color: "#7d8ca3"}
divisions:                             # per-division overrides (A2); keys are division names
  "Portfolio & FAO":
    colour: "#3f7c8c"
    tagline: "Financial Accounting Operations under the FAR regime"
    background: "Financial Accounting Operations, governed by the FAR…"
```

All sections optional — anything omitted keeps the app's current value (settings *overlay*,
never blank out). `legend.levels` fully replaces the legend when present.

## Derivation rules

**Division roster = distinct `Division` values in the stories CSV** (first-appearance
order). Nothing else defines the roster; a `settings.yaml → divisions` entry with no
matching story is ignored with a warning.

For each division, build a `divisions.csv` row:
- `Division` — the name.
- `Systems` — `"; "`-joined dedup union of the `Systems` cells across that division's
  stories (each cell is itself `"; "`-split), preserving first-seen order (A3).
- `Themes` — same, from the `Themes` cells (A3).
- `Tagline`, `Background` — from `settings.yaml → divisions[name]`, else empty.
- `Colour` — from `settings.yaml → divisions[name].colour`, else an **auto-assigned**
  palette colour (deterministic by roster order, cycling a fixed accessible palette).

`divisions.csv` is regenerated every run; it is a build artifact, not a source file.

## `regenerate_html.py` — new sequence

1. Launch headless Chromium, open the source HTML, wait for the app to render.
2. Data tab → for each sub-tab, select it and **Upload CSV**:
   - Division stories ← the Jira CSV
   - Divisions ← the derived `divisions.csv`
   - Initiatives ← `initiatives.csv`
3. **Settings merge:** read `localStorage["insignia_ai_strategy_map_v2"]` (now the full
   post-import object), overlay `header` / `hub` / `fitRating` from `settings.yaml`,
   write it back, and `page.reload()` so the app boots the merged state.
4. Click **Download standalone HTML**; capture to `--out` via the temp-then-promote
   guard already in place.

Flags: `--csv`, `--initiatives`, `--settings`, `--divisions-out`, `--html`, `--out`,
`--headed`. Missing `settings.yaml`/`initiatives.csv` → skip that overlay/import with a
logged notice (so a stories-only regenerate still works).

## Dependencies

Add `pyyaml`. Setup becomes `pip install requests playwright pyyaml`.

## Testing

- **`settings_common`**: `divisions.csv` derivation from a fixture stories CSV — roster =
  distinct divisions in first-appearance order; Systems/Themes union dedup correct;
  settings overrides applied; auto-colour deterministic and settings-colour wins;
  unmatched settings division warned.
- **YAML load**: partial `settings.yaml` (only `header`) loads; omitted sections absent.
- **Regenerate (browser smoke)**: extend the existing sentinel test — a stories row, a
  divisions override colour, and a header company sentinel all appear in the regenerated
  HTML (proving CSV import + settings merge both land). Skipped when Chromium absent.

## Assumptions / open (confirm at spec review)

1. **Upload-CSV-per-tab persists to localStorage** synchronously enough that step 3 can
   read the merged object after the imports. To be validated first thing in the plan;
   fallback is a no-op edit to force a save before reading.
2. **Importing `divisions.csv` updates the division nodes** (names/colour/tagline/systems/
   themes) — it's the app's own export schema, so round-trip is expected; validated early.
3. **Auto-colour palette** is a fixed curated set (seeded from the app's existing division
   colours); exact values chosen in the plan.

## Out of scope (YAGNI)

- Pushing/pulling initiatives to Jira (they're standalone).
- Full localStorage reconstruction of the private data object (we use the public CSV
  contract + a minimal settings overlay instead).
- Editing the Priority view independently (it derives from initiatives).
