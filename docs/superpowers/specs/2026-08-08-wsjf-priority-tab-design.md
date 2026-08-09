# Design: Fold WSJF Studio into the Strategy Map app

**Date:** 2026-08-08
**Status:** Approved (brainstorming) — ready for implementation planning

## Goal

Replace the main app's **Priority** tab with the WSJF Studio views, wired to a
single shared stories store, with one unified navy look and feel, and surface
the WSJF-derived scores in the central strategy map as well.

## Context (what the files actually are)

The main app `Insignia AI Strategy Map - Jira linked.html` is a single-file
`dc-runtime` bundle (framework markers: `<x-dc>`, `sc-if`, `sc-for`,
`sc-camel-on-*`). Its manifest holds:

- **`WORKSHOP_DATA`** (`window.WORKSHOP_DATA`, ~282 KB resource) — hub /
  divisions / initiatives that drive the **strategy map** and the
  Divisions/Initiatives tabs.
- The app component + a self-embedded **`__PRISTINE_HTML`** copy (~217 KB
  resource) used by the app's own in-browser "Download standalone HTML"
  serialiser (the path `regenerate_html.py` drives).
- The **stories CSV** (`insignia-division-stories-jira-linked.csv`, 11 columns)
  feeds the **Data** tab and the current **Priority** tab.

`WSJF Studio v2.html` is the **same `dc-runtime` build** (identical framework
SHA `2e38395c4a4a`). It reads a backlog CSV with the **identical 11 columns**
(`#, Division, Opportunity, AI-fit, Key people, Systems, Themes, Summary,
Description, Jira Key, Jira URL`) and derives Value / Effort / WSJF / rank /
pillar purely from those text fields via `scoreStory()`, `capabilityOf()`,
`confidenceOf()`.

Because the framework and the schema already match, this is a **native merge**,
not an iframe embed.

## Decisions (locked)

| Topic | Decision |
|---|---|
| Stories storage | **One shared array**, canonical. All tabs + map read it. |
| Setup / CSV upload | **Kept.** Upload *writes into the one shared store* (replace/override), not a second store. |
| LLM scoring | Optional API endpoint/key panel kept (as in WSJF Setup). |
| Theme | **Match main app navy** (`#0a1524`, existing gradients + fonts); keep amber `#ffb020` as the priority accent. |
| Score overrides | **Browser-local overlay** (`localStorage`), never mutate the shared store. |
| Views kept | **All:** Exec summary, Table, Value/Effort matrix, Bubble, Heat, Stair, plus Setup. |
| Map ↔ WSJF | **Full:** priority-heat node overlay (toggle), WSJF-ranked stories in division detail, click-through to Priority tab scoped to the division. |
| What-if ↔ map | **Live-linked:** what-if weighting / capacity / financial toggles feed the shared scoring module, so the map reflects them live (one derivation, always consistent). |

## Architecture

### 1. One shared stories store
A single `stories` array parsed once from the stories CSV resource at startup is
the canonical store. Data tab, Priority tab, and strategy map all read it.
WSJF's private `backlogCsv` resource is removed. Setup's "upload CSV" replaces
the contents of this one array (override), satisfying "only one stories data
storage".

### 2. One scoring module
Extract WSJF's pure functions (`scoreStory`, `capabilityOf`, `confidenceOf`,
WSJF/rank derivation, pillar mapping) into a shared module:

```
deriveScores(stories, overrides, modelParams) -> scoredStories
```

Pure function of the shared store → any view calls it. This is the linchpin that
keeps the Priority tab and the strategy map consistent.

- `overrides` — browser-local per-story Value/Size edits (Table view).
- `modelParams` — the **what-if model parameters**: dimension weights,
  sprint capacity, include-financials toggle. Hoisted out of the Exec view's
  local state into shared scoring-model state (persisted in `localStorage`
  alongside overrides).

### 3. Priority tab = all WSJF views, restyled navy
The Priority tab content becomes WSJF Studio's internal view-switcher with all
views kept (Exec, Table, Matrix, Bubble, Heat, Stair, Setup). Each view is
restyled from near-black `#0b0d10`/amber to the main app navy palette. Amber
`#ffb020` retained as the deliberate WSJF-score accent. WSJF's bundled IBM Plex
Mono woff2 fonts carry over for numerics.

**Exec summary** (from `wsjf_template.html` L499–581): two-column grid — left =
4 KPI cards → "Top 10 priorities" ranked list (+ next-15 watchlist below a rule)
+ capability filter chips; right = "What-if weighting" panel + "Investment mix"
(Top-10 effort share by pillar). Ranked rows show rank, name, must-have flag,
confidence bar, ▲▼ delta vs default weighting, WSJF.

**What-if controls** (all inside the Priority tab, in their current views):

- **What-if weighting** — 9 sliders (0–4) + RESET, Exec view. Re-sorts live.
- **Capacity / sprint** — slider (5–40), Stair view. Repacks sprints live.
- **Include financials** — toggle, Setup view. Adds revenue/outcome/
  cost-avoidance categories and renormalises weights.

### 4. Score overrides = browser-local overlay
Table-view manual Value/Size edits stay in `localStorage`, keyed by story id,
passed to `deriveScores` as `overrides`. Shared `stories` stays the clean 11
columns.

### 5. Full strategy-map ↔ WSJF integration
Using the shared scoring module, the map gains:

- **Priority-heat overlay toggle** — division nodes tinted/sized by an aggregate
  WSJF signal (top-10 share or high-WSJF count); toggle returns to the current
  look.
- **WSJF-ranked stories** in the division detail panel, with score + rank badge.
- **Click-through** — selecting a division opens the Priority tab scoped to it.

Because the map reads the same `deriveScores` output, live what-if changes
re-tint the heat overlay and re-order division stories automatically.

### 6. Look & feel unification
One token set (navy backgrounds, shared accent, shared type scale, Plex Mono
only for numerics). Applied across the WSJF views; the existing
Data/Divisions/Initiatives tabs are already navy and need only accent/token
reconciliation.

## Authoring & build approach (constraint)

There is **no external bundler** in this repo or the wider `scryptid` tree, and
no un-bundled source — the editable HTML was committed as a snapshot. Edits are
therefore made **in-place to the app's own bundle resources** via the existing
`bundle_common.py` (`decode → transform → re-encode`), the same path
`lock_app.py` uses.

- The component code lives both live and inside `__PRISTINE_HTML`; both must be
  updated together so the app's re-serialise/regenerate path stays correct.
- A small deterministic Python helper should perform the splice of the WSJF view
  markup + `data-dc-script` into the main template, rather than hand-editing
  gzipped blobs.
- After editing the editable source, shipped outputs are rebuilt with the
  existing toolkit (`lock_app.py` → `regenerate_html.py`); `pytest` must stay
  green.

## Risks

- **In-place bundle editing is delicate** — dual live/`__PRISTINE_HTML` copies;
  splicing into the `data-dc-script` without breaking the dc-runtime parse.
- **Regenerate/lock parity** — `regenerate_html.py` and `lock_app.py` inject
  data into the app; the new Priority views must survive that round-trip.
- **What-if state scope** — model params must be shared state, not Exec-local,
  or the map and Priority tab diverge.

## Out of scope

- Changing the stories CSV schema (overrides stay browser-local).
- Any external bundler / dc-runtime source reconstruction.
- Server or network features beyond the optional LLM scoring already in WSJF.
