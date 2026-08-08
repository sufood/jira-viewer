# Agile Backlog — Jira ⇄ CSV ⇄ Standalone-HTML Toolkit (v2, corrected)

Scope forks — every epic is tagged so you can build either slice:

- **[App]** — rebuild the interactive *Insignia AI Strategy Map* SPA from scratch (the current one is low-code-builder output: `sc-if`/`sc-for` template directives, UUID-keyed resource bundle, localStorage persistence).
- **[Toolkit]** — treat the app as given; build only the Python automation around it.

Sizing: **S** ≈ ½–1 day · **M** ≈ 1–3 days · **L** ≈ 3–5+ days.

Stories marked ⚠️ were under-specified or missing in v1 and are the load-bearing, easy-to-forget bits.

---

## Epic A — Interactive Strategy Map, viewer [App]

| ID | Story | Size | Key acceptance criteria |
|----|-------|------|-------------------------|
| A1 | As a viewer I want a central strategy node (name, tagline, board link) so the map has a hub. | S | Renders name + tagline; tagline links to a configurable Jira board URL. |
| A2 | As a viewer I want one node per division radiating from the centre, each colour/tagline'd, so I see the structure at a glance. | M | One node per distinct division; per-division colour + tagline; responsive radial layout. |
| A3 | As a viewer I want to open a division page (header, opportunities, systems, themes, key people, gaps, next steps) so I can drill in. | M | All sections render; coloured header/background; back navigation. |
| A4 | As a viewer I want each AI opportunity as a card + detail view (summary, description, AI-fit, systems, themes, people, Jira link) so each idea is self-contained. | M | All fields render; Jira Key/URL shown as link when present; detail view has a round **×** close control (distinct from delete controls). |
| A5 | As a viewer I want a colour-coded AI-fit legend (Very High → Low) so ratings are interpretable. | S | Configurable title + labels + colours; card ratings match legend colours. |
| A6 ⚠️ | As a viewer I want **hover-to-highlight**: hovering a theme/division/category dims non-matching nodes so I can trace relationships. | M | *(Corrected from v1 "filter" — the app highlights on hover, it does not persist a filter.)* Hover dims non-matching nodes (~0.14 alpha); leaving restores. |

---

## Epic B — Editable data tabs (authoring) [App]

| ID | Story | Size | Key acceptance criteria |
|----|-------|------|-------------------------|
| B1 | As an editor I want tabbed data views (Stories, Initiatives, People, Divisions, Settings) so I manage all content in one place. | M | Tab shell; deep-linkable; keyboard accessible. |
| B2 | As an editor I want add / edit / delete per tab so I maintain content without code. | L | Add / edit / delete per tab; required-field validation; delete confirmation. |
| B3 | As an editor I want to edit header (company/title/intro), centre node, legend, and per-division overrides in-app so branding is configurable. | M | Each field editable; changes persist to localStorage. |
| B4 | As an editor I want an Initiatives tab (value/effort/priority/benefits/divisions-impacted). | S | Editable rows; divisions-impacted references existing divisions. |
| B5 | As an editor I want a People tab (division, name, role, relevance). | S | Editable rows keyed by division. |
| B6 ⚠️ | As an editor I want **app-only fields** — per-division `gaps` / `nextSteps` and the systems/themes **catalogues** — editable in-app, since no CSV authors them. | M | These fields have an in-app authoring path; documented as *not* CSV-sourced (see F6/U-note). |

---

## Epic C — Self-contained bundle & persistence [App]

| ID | Story | Size | Key acceptance criteria |
|----|-------|------|-------------------------|
| C1 ⚠️ | As a distributor I want the whole app in one HTML file via a **UUID-keyed resource manifest** (`{mime, compressed, data}`) so it ships as one artifact. | L | Manifest model; find-by-content; edit-by-transform + manifest rebuild. |
| C2 ⚠️ | As a distributor I want embedded data **gzip-compressed and byte-deterministic** (`mtime=0`) so bundles stay small *and* diffable across rebuilds. | M | Re-encoding identical data yields identical bytes. |
| C3 ⚠️ | As the app I want live state persisted to **localStorage** (distinct from the embedded snapshot) so edits survive reloads. | M | Live edits persist; snapshot vs live store clearly separated. |
| C4 | As an editor I want a "Download standalone HTML" action that re-serialises current state into a fresh file. | M | Output opens offline and reflects latest edits. |
| C5 ⚠️ | As a distributor I want a **zero-network guarantee** so the file works fully offline. | S | Automated check: no external requests on load (fonts allowed to fail gracefully). |

---

## Epic D — CSV as source of truth [Toolkit]

| ID | Story | Size | Key acceptance criteria |
|----|-------|------|-------------------------|
| D1 ⚠️ | As an editor I want to import **three** CSVs (Division stories, Initiatives, People) via their sub-tabs so bulk content lives in diffable files. | M | 11-column stories contract; UTF-8 **+BOM**; `QUOTE_ALL`; per-file validation + clear errors. |
| D2 | As an editor I want CSV export back to the same contract (retained even in locked builds). | S | Export round-trips the import contract. |
| D3 | As an editor I want an empty 11-column seed template to start a fresh batch. | S | Header-only file; usable for push or pull seeding. |
| D4 ⚠️ | As a tool author I want atomic CSV writes (temp + rename) so a crash mid-batch never corrupts the file. | S | Write is atomic; partial writes impossible. |
| D5 ⚠️ | As a tool author I want special-character fidelity (BOM, embedded quotes/commas, unicode) through CSV↔Jira↔bundle. | M | Golden fixtures with tricky strings survive a full round-trip. |

---

## Epic E — Bidirectional Jira sync [Toolkit]

| ID | Story | Size | Key acceptance criteria |
|----|-------|------|-------------------------|
| E1 ⚠️ | As an operator I want a **staged preflight**: auth (`whoami`) → project exists → create permission, with `list_projects` fallback on a bad key. | M | Each stage fails with a distinct, actionable message. |
| E2 | As an operator I want `push` to turn blank rows (both Key **and** URL empty) into issues (title=Opportunity, body=Description+context block+labels), writing Key/URL back and **saving after each create**. | L | `--dry-run` previews payloads; half-linked rows reported & skipped (never duplicated); already-linked skipped; re-runnable/idempotent. |
| E3 ⚠️ | As a tool author I want a **markdown⇄ADF** engine (`##` headings, `-` bullets, `**bold**`, paragraphs) both directions, since Jira takes ADF not markdown. | L | Push renders ADF; pull renders markdown; round-trip test passes. |
| E4 ⚠️ | As a tool author I want a **context block** appended on push and **structurally parsed + stripped** on pull (pull stops before the trailing block). | M | Division/AI-fit/people/systems/themes/summary survive push→pull identically; block never leaks into Description. |
| E5 ⚠️ | As a tool author I want **label slugification** (`div-*`/`ai-fit-*`/`theme-*`, no spaces). | S | Spaces/punctuation normalised; deduped + sorted. |
| E6 ⚠️ | As an operator I want `--assign` to set the first Key person **only when unambiguous** (account lookup; skip silently otherwise). | S | Resolves accountId; ambiguous/absent → no assignee, noted. |
| E7 ⚠️ | As an operator I want `--verify` to re-fetch each created issue and confirm fields. | S | Mismatch reported per row. |
| E8 | As an operator I want `pull` to refresh linked rows (title, body, context fields) with a per-cell diff in `--dry-run`; rows without URL untouched. | M | Diff shown before apply; no write on dry-run. |
| E9 | As an operator I want a per-run audit log appended to `<csv>.upload-log.csv`. | S | One record per create; gitignored. |
| E10 | As an operator behind a TLS-inspecting proxy I want `truststore` auto-detect + `--ca-bundle`. | S | Works through Zscaler/Netskope; falls back cleanly. |

---

## Epic F — HTML regeneration pipeline [Toolkit]

| ID | Story | Size | Key acceptance criteria |
|----|-------|------|-------------------------|
| F1 ⚠️ | As a build operator I want a Playwright regenerator that drives the app's **own** CSV-import + download in headless Chromium, so output reuses the real serializer. | L | `--headed`; `--csv/--html/--out` overrides. |
| F2 ⚠️ | As a build operator I want the automation to be **hydration-robust**: wait on tab mount (not `networkidle`), retry clicks until handlers attach. | M | No flakiness from clicks fired pre-hydration; fonts-never-idle handled. |
| F3 | As a build operator I want the whole page rebuilt from `settings.yaml` + derived `divisions.csv` + `initiatives.csv` + `people.csv`, not just the stories tab. | M | All four inputs applied. |
| F4 | As a build operator I want divisions derived from the stories CSV (Systems/Themes = deduped union per division; auto-palette colour). | M | Deterministic derivation; overrides win. |
| F5 | As a build operator I want `settings.yaml` to be an **overlay** — omitted sections keep current app values. | S | Partial settings don't clobber unset fields. |
| F6 ⚠️ | As a build operator I want a **two-stage** build (import into editable source → inject data into locked bundle → download) so app-only data (gaps/nextSteps, catalogues) rides along. | M | Non-CSV data preserved end-to-end. |
| F7 | As a build operator I want `export_tabs.py` to seed `initiatives.csv` + `settings.yaml` + `people.csv` from current app content. | S | Seeds match live state. |
| F8 ⚠️ | As a build operator I want a **stable automation contract** (data-testids / stable labels) so renaming a tab doesn't silently break regenerate. | M | Pipeline targets stable hooks, not display text. |

---

## Epic G — View-only lock [Toolkit]

| ID | Story | Size | Key acceptance criteria |
|----|-------|------|-------------------------|
| G1 | As a distributor I want `lock_app.py` to bake a self-contained lock guard into the source so downloads have no upload/edit/add/delete UI. | M | Reset/Upload/Edit-pencils/+Add/delete-× hidden; inputs flattened to static. |
| G2 ⚠️ | As a distributor I want **Export CSV surgically promoted** out of the `{{ editable }}` gate so it survives the lock while siblings stay gated. | M | Only the `{{ showExport }}` block is hoisted; Reset/Download/Upload remain gated. |
| G3 ⚠️ | As a tool author I want the guard hardened against the **double-escaping hazard** (guard is JS injected as text; one bad escape kills it silently). *(Spike + regression test.)* | S | Guard survives round-trip through the bundle encoder; test asserts it executes. |
| G4 | As a distributor I want regenerate to **rebuild the locked bundle if missing** and always ship the locked output (never a stale artifact). | S | Locked build auto-created; editable source never shipped. |

---

## Epic H — Quality & operability [Toolkit]

| ID | Story | Size | Key acceptance criteria |
|----|-------|------|-------------------------|
| H1 | As a maintainer I want pytest coverage for CSV I/O, markdown⇄ADF, context-block round-trip, push/pull classification, lock, bundle encode/decode. | M | Core paths covered; CI-runnable. |
| H2 | As a maintainer I want shared helpers centralised in `jira_common.py` (env, CSV, ADF, labels, Jira client). | S | No duplication across CLIs. |
| H3 | As a maintainer I want README setup + push/pull/regenerate/lock workflows + file-role table. | S | A new dev can run each path unaided. |
| H4 ⚠️ | As a maintainer I want **secret hygiene**: `.env`, tokens, and audit logs never baked into shipped HTML; generated artifacts gitignored. | S | Grep of shipped file finds no secrets; `.gitignore` covers generated files. |
| H5 ⚠️ | As a maintainer I want a **push→pull golden test**: push then pull yields a byte-identical CSV. | S | Round-trip is lossless end-to-end. |

---

## MVP slice (either fork)

- **[App] fork:** A1–A5 + C1–C4 + D1–D2 → a shareable, offline, interactive map from CSV. Then B, then E/F/G.
- **[Toolkit] fork:** D + E (push/pull with ADF + context block) first — the highest-value automation — then F (regenerate) and G (lock).

## Open scoping question

Which fork is in scope — rebuild the **App** too, or **Toolkit** only? The App epics (A–C) are a substantial SPA effort; the Toolkit epics (D–H) assume the current low-code app is a given.

## Correction log vs v1

- **A6** rewritten: hover-highlight, not persistent filtering (verified against source).
- Split out as first-class stories: markdown⇄ADF (E3), context-block strip-on-pull (E4), staged preflight (E1), assignee ambiguity (E6), verify (E7), label slugs (E5), atomic writes (D4), deterministic recompression (C2), resource-manifest model (C1), localStorage persistence (C3), Export-promotion (G2), double-escape spike (G3), hydration robustness (F2), automation-stability contract (F8), three-CSV import (D1), app-only fields (B6).
- Added non-functionals: offline guarantee (C5), encoding fidelity (D5), secret hygiene (H4), round-trip golden test (H5).
