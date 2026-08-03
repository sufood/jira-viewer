# Lock Data Tabs (read-only app) — Design

**Date:** 2026-08-01
**Status:** Approved decisions, pending spec review
**Builds on:** the whole-page + people.csv work.

## Purpose

Remove the ability to **upload, edit, add, or delete** any data from the app's Data tabs.
Data enters the page **only** via the backend `regenerate` script. Keep an **Export CSV**
download for viewers.

## Decisions (locked with the user)

1. **Lock the app entirely** — the shipped artifact has no mutation UI at all.
2. **Two-stage build** — the script builds the app's internal data by feeding the CSVs
   through a headless *editable* build-copy (lossless — preserves `gaps`/`nextSteps`/
   catalogues not present in any CSV), then injects that data via localStorage into the
   **locked** app and downloads. The importer is an invisible internal step.
3. **Bundle surgery** — the lock is baked into the app's own source, not post-processed.
4. **Export CSV stays** available in the locked/read-only output.

## Validated findings (probed against the real app)

- **Downloads rebuild from `window.__PRISTINE_HTML`** (an in-memory source snapshot) +
  `support.js` — NOT the outer bundler blocks. So the lock must live in `__PRISTINE_HTML`.
- `__PRISTINE_HTML` is an escaped string inside bundle resource `3a33ba6c-…`. Injecting
  into it → recompressing that resource → rebuilding the manifest **propagates into the
  downloaded output** (verified: a sentinel `<style>` injected before `</head>` appeared
  in the download).
- The app is **entirely JS-rendered** (no JS → blank page), so a baked-in JS/CSS lock is
  as strong as physically removing controls.
- The download path (`getPristineSource`) is **timing-sensitive** — a too-early click
  intermittently fails with a data-load error; a longer settle (and a retry) fixes it.
  Same flakiness class already handled in `regenerate`.
- Data injection via `localStorage["insignia_ai_strategy_map_v2"]` works; the object has
  `departments[]` (with `opportunities`/`people`/`gaps`/`nextSteps`/`systems`/`themes`),
  `initiatives[]`, `header`, `hub`, `fitRating`, `systemsCatalogue`, `themesCatalogue`,
  `initiativeCategories`, `org`, `programme`.
- In today's read-only download, Upload/Export/Reset are already gone (gated on
  `editable`); what remains is 34 inputs, 25 "Edit details" pencils, 2 "Add" buttons,
  4 "×" deletes — all non-functional (`onEdit` no-ops) but visible.

## Components

### `bundle_common.py` — bundle read/edit/write
Pure helpers (no browser): parse the `__bundler/manifest`, find the resource containing
a marker string, decompress it (gzip+base64), apply a text transform, recompress
(gzip mtime=0), and rebuild the full HTML with only that resource's `data` replaced.
Round-trippable and unit-testable.

### `lock_app.py` — produce the locked bundle
Reads the source HTML, edits `__PRISTINE_HTML` (via `bundle_common`) to bake a **lock
guard** into its `<head>`, and writes `Insignia AI Strategy Map - locked.html`.

The lock guard (self-contained `<style>` + `<script>`, keyed to run always):
- **Hides/neutralises** every Data-tab mutation control: the "↑ Upload CSV" label, "↺
  Reset", every `button[title="Edit details"]` pencil, every "+ Add …" button, every "×"
  delete; and renders data `input`/`textarea` as static (no border/background, `readonly`,
  `pointer-events:none`).
- **Keeps Export**: ensures an "Export CSV" affordance remains available. Implementation:
  the guard re-adds/keeps a working Export button that serialises the active Data sub-tab
  from `localStorage` (the guard owns the 3 CSV schemas), so it works even though the
  app's own toolbar is hidden in read-only.
- Uses a `MutationObserver` so it re-applies after the app re-renders (tab switches).

Selectors are matched by role/text/title (robust to styling), discovered against the
real DOM during implementation.

### `regenerate_html.py` — two-stage
- **Stage 1 (build data):** open the *editable source* bundle headless, import the three
  tabs via Upload CSV + overlay settings/people (exactly as today), read the full `d`
  from `localStorage`.
- **Stage 2 (ship):** open the *locked* bundle headless, `localStorage.setItem` the `d`,
  reload, and click **Download standalone HTML** with a settle+retry (per the timing
  finding). Output = the locked app with data injected via localStorage — the only
  distributable artifact.
- New args: `--locked-html` (default `Insignia AI Strategy Map - locked.html`). The
  existing `--html` is the editable build-copy. If the locked bundle is missing,
  `regenerate` builds it on the fly via `lock_app` (or errors with the exact command).
- The temp-then-promote output guard and all existing CSV/settings/people logic are kept.

### Retained: the editable source bundle
`Insignia AI Strategy Map - Jira linked.html` stays as the **internal build tool** (drives
Stage 1 headless). It is never distributed; the locked output is the only shareable file.
(This is inherent to the two-stage choice.)

## Data flow

```
CSVs + settings.yaml + people.csv
        │  Stage 1: editable build-copy (Upload CSV import + overlays)
        ▼
   full internal `d`  ──inject localStorage──►  LOCKED bundle ──Download──► locked output
                                                (lock guard baked in __PRISTINE_HTML)
```

## Error handling / risks

- **Download timing flakiness** — settle before click + retry the download N times; on
  persistent failure, screenshot + non-zero exit (never emit a truncated file — the temp
  promote guard already covers this).
- **Surgery fragility** — `bundle_common` round-trip is unit-tested; `lock_app` output is
  validated by loading it and asserting (a) the app renders, (b) no mutation controls
  present, (c) Export present, (d) data renders. A bad edit fails these gates, not users.
- **Guard vs re-render races** — `MutationObserver` re-applies; the guard is idempotent.

## Testing

- **`bundle_common`**: decode→transform(identity)→encode reproduces a loadable bundle;
  a marker injected into the pristine resource is present after rebuild.
- **`lock_app` (browser)**: build the locked bundle, open it, Data tab shows **zero**
  Upload/Reset/pencil/Add/× controls and non-interactive inputs, **Export present**, and
  the baked default data still renders.
- **`regenerate` two-stage (browser)**: from a sentinel stories row + settings company +
  people person, the output (a) contains all three sentinels, (b) has no mutation
  controls, (c) has Export. Skipped when Chromium absent.

## Assumptions / open (confirm at spec review)

1. Locked bundle is a **generated build artifact** (git-ignored), rebuilt by `lock_app`
   from the source when missing — not a hand-maintained committed file. (Keeps it in sync
   if the source app is ever updated.)
2. Export in the locked output is provided by the **guard's own** serialiser (owns the CSV
   schemas), since the app's toolbar Export is gated away in read-only.
3. The editable source bundle is retained as an internal build dependency (not shipped).

## Out of scope

- Changing `push`/`pull` (Jira ↔ stories CSV) — unaffected.
- Re-architecting the internal data model by hand (two-stage avoids it).
