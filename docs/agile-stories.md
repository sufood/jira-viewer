# Agile Stories — Jira ⇄ CSV ⇄ Standalone-HTML Toolkit

Full backlog to build the toolkit from scratch: the interactive **Insignia AI Strategy Map** SPA **and** the Python automation (Jira sync, CSV pipeline, HTML regeneration, view-only lock).

- **Epics:** 8 · **Stories:** 45
- **Tags:** `[App]` = the interactive SPA · `[Toolkit]` = the Python automation
- **Sizing:** S ≈ ½–1 day · M ≈ 1–3 days · L ≈ 3–5+ days

---

## Epic A — Interactive Strategy Map, viewer `[App]`

### A1 · Central strategy node — S
As a viewer, I want a central company/strategy node (name, tagline, board link) so the map has a clear hub.
- Renders name + tagline.
- Tagline links to a configurable Jira board URL.

### A2 · Division nodes radiating from centre — M
As a viewer, I want one node per division arranged around the centre, each with its own colour and tagline, so I can see the structure at a glance.
- One node per distinct division.
- Per-division colour + tagline.
- Responsive radial layout.

### A3 · Division detail page — M
As a viewer, I want to open a division page (header, AI opportunities, systems, themes, key people, gaps, next steps) so I can drill into detail.
- All sections render.
- Coloured header/background.
- Back navigation.

### A4 · AI-opportunity cards + detail view — M
As a viewer, I want each AI opportunity as a card and detail view (summary, description, AI-fit, systems, themes, people, Jira link) so each idea is self-contained.
- All fields render.
- Jira Key/URL shown as a link when present.
- Detail view has a round **×** close control, distinct from delete controls.

### A5 · AI-fit rating legend — S
As a viewer, I want a colour-coded AI-fit legend (Very High → Low) so ratings are interpretable.
- Configurable title + labels + colours.
- Card ratings match legend colours.

### A6 · Hover-to-highlight — M
As a viewer, I want hovering a theme/division/category to dim non-matching nodes so I can trace relationships.
- Hover dims non-matching nodes (~0.14 alpha).
- Leaving the element restores full opacity.

---

## Epic B — Editable data tabs (authoring) `[App]`

### B1 · Data tabs shell — M
As an editor, I want tabbed data views (Stories, Initiatives, People, Divisions, Settings) so I manage all content in one place.
- Tab shell; deep-linkable; keyboard accessible.

### B2 · CRUD per tab — L
As an editor, I want to add / edit / delete rows in each tab so I maintain content without code.
- Add, edit, delete controls per tab.
- Required-field validation.
- Delete confirmation.

### B3 · Settings editor — M
As an editor, I want to edit header (company/title/intro), centre node, legend, and per-division overrides in-app so branding is configurable.
- Each field editable.
- Changes persist to localStorage.

### B4 · Initiatives tab — S
As an editor, I want an Initiatives tab (value / effort / priority / benefits / divisions-impacted).
- Editable rows.
- Divisions-impacted references existing divisions.

### B5 · People tab — S
As an editor, I want a People tab (division, name, role, relevance).
- Editable rows keyed by division.

### B6 · App-only fields — M
As an editor, I want per-division `gaps` / `nextSteps` and the systems/themes catalogues editable in-app, since no CSV authors them.
- In-app authoring path for these fields.
- Documented as not CSV-sourced (preserved by F6).

---

## Epic C — Self-contained bundle & persistence `[App]`

### C1 · UUID-keyed resource bundle — L
As a distributor, I want the whole app in one HTML file via a UUID-keyed resource manifest (`{mime, compressed, data}`) so it ships as one artifact.
- Manifest model.
- Find-by-content; edit-by-transform + manifest rebuild.

### C2 · Compressed, byte-deterministic data — M
As a distributor, I want embedded data gzip-compressed and byte-deterministic (`mtime=0`) so bundles stay small and diffable across rebuilds.
- Re-encoding identical data yields identical bytes.

### C3 · localStorage persistence — M
As the app, I want live state persisted to localStorage (distinct from the embedded snapshot) so edits survive reloads.
- Live edits persist.
- Snapshot vs live store clearly separated.

### C4 · Download standalone HTML — M
As an editor, I want a "Download standalone HTML" action that re-serialises current state into a fresh file.
- Output opens offline and reflects the latest edits.

### C5 · Zero-network guarantee — S
As a distributor, I want the file to work fully offline so it can be emailed and opened anywhere.
- Automated check: no external requests on load (fonts may fail gracefully).

---

## Epic D — CSV as source of truth `[Toolkit]`

### D1 · Three-CSV import — M
As an editor, I want to import three CSVs (Division stories, Initiatives, People) via their sub-tabs so bulk content lives in diffable files.
- 11-column stories contract.
- UTF-8 **+BOM**; `QUOTE_ALL`.
- Per-file validation with clear errors.

### D2 · CSV export — S
As an editor, I want CSV export back to the same contract, retained even in locked builds.
- Export round-trips the import contract.

### D3 · Seed template — S
As an editor, I want an empty 11-column seed template to start a fresh batch.
- Header-only file usable for push or pull seeding.

### D4 · Atomic writes — S
As a tool author, I want atomic CSV writes (temp + rename) so a crash mid-batch never corrupts the file.
- Write is atomic; partial writes impossible.

### D5 · Encoding fidelity — M
As a tool author, I want special-character fidelity (BOM, embedded quotes/commas, unicode) through CSV ↔ Jira ↔ bundle.
- Golden fixtures with tricky strings survive a full round-trip.

---

## Epic E — Bidirectional Jira sync `[Toolkit]`

### E1 · Staged preflight — M
As an operator, I want a staged preflight — auth (`whoami`) → project exists → create permission — with `list_projects` fallback on a bad key.
- Each stage fails with a distinct, actionable message.

### E2 · `push` — create issues for blank rows — L
As an operator, I want `push` to turn blank rows (both Key **and** URL empty) into issues (title = Opportunity, body = Description + context block + labels), writing Key/URL back and saving after each create.
- `--dry-run` previews payloads.
- Half-linked rows reported and skipped (never duplicated).
- Already-linked rows skipped.
- Re-runnable / idempotent.

### E3 · markdown ⇄ ADF engine — L
As a tool author, I want a markdown⇄ADF engine (`##` headings, `-` bullets, `**bold**`, paragraphs) in both directions, since Jira takes ADF not markdown.
- Push renders ADF; pull renders markdown.
- Round-trip test passes.

### E4 · Context block round-trip — M
As a tool author, I want a context block appended on push and structurally parsed + stripped on pull (pull stops before the trailing block).
- Division / AI-fit / people / systems / themes / summary survive push→pull identically.
- Block never leaks into Description.

### E5 · Label slugification — S
As a tool author, I want label slugification (`div-*` / `ai-fit-*` / `theme-*`, no spaces).
- Spaces/punctuation normalised; deduped + sorted.

### E6 · Assignee resolution — S
As an operator, I want `--assign` to set the first Key person as assignee only when unambiguous (account lookup; skip silently otherwise).
- Resolves accountId.
- Ambiguous/absent → no assignee, noted.

### E7 · Verify after create — S
As an operator, I want `--verify` to re-fetch each created issue and confirm fields.
- Mismatch reported per row.

### E8 · `pull` — refresh from linked issues — M
As an operator, I want `pull` to refresh linked rows (title, body, context fields) with a per-cell diff in `--dry-run`; rows without a URL untouched.
- Diff shown before apply.
- No write on dry-run.

### E9 · Audit log — S
As an operator, I want a per-run audit log appended to `<csv>.upload-log.csv`.
- One record per create; gitignored.

### E10 · Corporate TLS proxy — S
As an operator behind a TLS-inspecting proxy, I want `truststore` auto-detect + `--ca-bundle`.
- Works through Zscaler/Netskope; falls back cleanly.

---

## Epic F — HTML regeneration pipeline `[Toolkit]`

### F1 · Headless regenerate — L
As a build operator, I want a Playwright regenerator that drives the app's own CSV import + download in headless Chromium so output reuses the real serializer.
- `--headed` mode.
- `--csv` / `--html` / `--out` overrides.

### F2 · Hydration robustness — M
As a build operator, I want the automation to be hydration-robust: wait on tab mount (not `networkidle`), retry clicks until handlers attach.
- No flakiness from clicks fired pre-hydration.
- Fonts-never-idle handled.

### F3 · Whole-page rebuild from files — M
As a build operator, I want the whole page rebuilt from `settings.yaml` + derived `divisions.csv` + `initiatives.csv` + `people.csv`, not just the stories tab.
- All four inputs applied.

### F4 · Division derivation — M
As a build operator, I want divisions derived from the stories CSV (Systems/Themes = deduped union per division; auto-palette colour).
- Deterministic derivation.
- Overrides win.

### F5 · Settings overlay — S
As a build operator, I want `settings.yaml` to be an overlay — omitted sections keep current app values.
- Partial settings don't clobber unset fields.

### F6 · Two-stage data preservation — M
As a build operator, I want a two-stage build (import into editable source → inject data into locked bundle → download) so app-only data (gaps/nextSteps, catalogues) rides along.
- Non-CSV data preserved end-to-end.

### F7 · Seed editable files — S
As a build operator, I want `export_tabs.py` to seed `initiatives.csv` + `settings.yaml` + `people.csv` from current app content.
- Seeds match live state.

### F8 · Automation-stability contract — M
As a build operator, I want stable automation hooks (data-testids / stable labels) so renaming a tab doesn't silently break regenerate.
- Pipeline targets stable hooks, not display text.

---

## Epic G — View-only lock `[Toolkit]`

### G1 · Bake lock guard — M
As a distributor, I want `lock_app.py` to bake a self-contained lock guard into the source so downloads have no upload/edit/add/delete UI.
- Reset / Upload / Edit-pencils / +Add / delete-× hidden.
- Data inputs flattened to static.

### G2 · Promote Export CSV — M
As a distributor, I want Export CSV surgically promoted out of the `{{ editable }}` gate so it survives the lock while siblings stay gated.
- Only the `{{ showExport }}` block is hoisted.
- Reset / Download / Upload remain gated.

### G3 · Harden guard against double-escaping — S
As a tool author, I want the guard hardened against the double-escaping hazard (guard is JS injected as text; one bad escape kills it silently). Spike + regression test.
- Guard survives round-trip through the bundle encoder.
- Test asserts it executes.

### G4 · Ship locked, never stale — S
As a distributor, I want regenerate to rebuild the locked bundle if missing and always ship the locked output.
- Locked build auto-created.
- Editable source never shipped.

---

## Epic H — Quality & operability `[Toolkit]`

### H1 · Test suite — M
As a maintainer, I want pytest coverage for CSV I/O, markdown⇄ADF, context-block round-trip, push/pull classification, lock, bundle encode/decode.
- Core paths covered; CI-runnable.

### H2 · Shared helpers — S
As a maintainer, I want shared helpers centralised in `jira_common.py` (env, CSV, ADF, labels, Jira client).
- No duplication across CLIs.

### H3 · Docs / README — S
As a maintainer, I want README setup + push/pull/regenerate/lock workflows + a file-role table.
- A new dev can run each path unaided.

### H4 · Secret hygiene — S
As a maintainer, I want `.env`, tokens, and audit logs never baked into shipped HTML; generated artifacts gitignored.
- Grep of shipped file finds no secrets.
- `.gitignore` covers generated files.

### H5 · Push→pull golden test — S
As a maintainer, I want a push→pull golden test: push then pull yields a byte-identical CSV.
- Round-trip is lossless end-to-end.

---

## Suggested sequencing

1. **Foundation** — D (CSV contract), H2 (shared helpers).
2. **Highest-value automation** — E (push/pull with ADF + context block), then H1/H5 tests.
3. **App** — A (viewer) → C (bundle/persistence) → B (authoring).
4. **Distribution** — F (regenerate) → G (lock).
5. **Hardening** — remaining H stories, non-functionals (C5, D5, F8).

**MVP:** A1–A5 + C1–C4 + D1–D2 (a shareable, offline, interactive map from CSV); E adds Jira sync; F+G add automated, locked distribution.
