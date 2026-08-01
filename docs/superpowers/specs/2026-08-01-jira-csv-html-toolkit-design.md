# Jira ⇄ CSV ⇄ Standalone-HTML Toolkit — Design

**Date:** 2026-08-01
**Status:** Approved design, pending spec review

## Purpose

Keep the Insignia AI Strategy Map as a single standalone HTML file, and add three
scripts (in the project folder) that let the CSV be the single source of truth:

1. **push** — upload CSV rows to Jira as Stories and write the created Jira Key + URL
   back into the CSV.
2. **pull** — read Jira issues referenced by the CSV and refresh the content columns
   from the ticket contents.
3. **regenerate** — rebuild the standalone HTML from the CSV.

## Core principle

The CSV is the single source of truth. The **`Jira URL` column, blank vs filled, is
the routing signal**:

- `Jira Key` **and** `Jira URL` both blank → a row `push` will create in Jira, then fill in.
- `Jira URL` filled → a row `pull` will refresh from Jira.
- exactly one of the two filled → inconsistent; push refuses the row (see create-guard).

## The canonical CSV

File: `insignia-division-stories-jira-linked.csv` (UTF-8 with BOM, every field quoted,
multi-line markdown inside quoted `Description` cells).

Columns (order preserved exactly):

```
#, Division, Opportunity, AI-fit, Key people, Systems, Themes, Summary, Description, Jira Key, Jira URL
```

| CSV column   | Role                                                                    |
|--------------|-------------------------------------------------------------------------|
| `#`          | Stable row id (source id). Never sent as a Jira field; used for logging. |
| `Opportunity`| **Jira issue title** (summary field).                                   |
| `Description`| Markdown body → ADF on push; ADF → markdown on pull.                     |
| `Summary`    | Short summary; rendered into the ADF context block.                     |
| `Division`, `AI-fit`, `Key people`, `Systems`, `Themes` | Metadata → ADF context block (exact values) **and** slugified Jira labels. |
| `Jira Key`   | Created/linked issue key (e.g. `ABC-123`). Written by push; read by pull.|
| `Jira URL`   | `<base>/browse/<key>`. Routing signal. Written by push; read by pull.   |

## Components

### `jira_common.py` — shared module

- **`.env` loader** — minimal, no third-party dependency. Reads `KEY=value` lines from
  `.env` in the project folder; real OS environment variables override file values.
  Vars: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`,
  `JIRA_ISSUE_TYPE` (default `Story`).
- **`Jira` client** — lifted from the existing `upload_to_jira.py`:
  session auth, `truststore` auto-inject + `--ca-bundle` for TLS-inspecting proxies,
  429 retry with `Retry-After`, and the 4 preflight checks (auth → project visible →
  issue type available → create permission), plus `create_issue`, `get_issue`,
  `find_account_id`.
- **Column constants + CSV I/O** — read with `utf-8-sig`; write atomically
  (`.tmp` then `os.replace`) with `csv.QUOTE_ALL` and BOM preserved, so the file's
  shape round-trips.
- **`markdown_to_adf(md)`** — headings (`##`→h3), bullets, `**bold**`, paragraphs, rule.
  (From existing script.)
- **`adf_to_markdown(adf)`** — the inverse, for pull. Handles heading/bulletList/
  paragraph/strong/rule; unknown node types degrade to their plain text.
- **Context block** — a machine-readable ADF block appended to every description:
  a bullet list of exact-value lines `Division: …`, `AI-fit: …`, `Key people: …`,
  `Systems: …`, `Themes: …`, `Summary: …`. This is the **round-trip carrier**: labels
  are slugified and lose exact text, so pull reconstructs metadata from the context
  block, never from labels. `build_context_block(row)` / `parse_context_block(adf)`.

### `jira_sync.py` — CLI, two subcommands

```
python jira_sync.py push [--csv PATH] [--dry-run] [--assign] [--verify] [-v] [--ca-bundle PEM]
python jira_sync.py pull [--csv PATH] [--dry-run] [-v] [--ca-bundle PEM]
```

**push** — a row is **eligible only when BOTH `Jira Key` and `Jira URL` are blank**
(the create-guard). Row states:
- **both blank** → eligible; create.
- **both filled** → already linked; skip silently (idempotent).
- **exactly one filled** → *inconsistent*; **skip and report as a warning**, never
  create (creating could duplicate an issue that already exists). `--dry-run` and the
  end-of-run summary both list these rows so they can be fixed by hand.

Per eligible row:
1. Build fields — `summary`=Opportunity (≤255), `description`=Description markdown→ADF
   + context block, `labels`=`div-*`, `ai-fit-*`, `theme-*` (slugified).
2. `POST /rest/api/3/issue`. On 201, set the row's `Jira Key` and `Jira URL`, then
   save the CSV immediately (so a crash mid-run never loses a created link).
3. Idempotency comes from the CSV itself — the side-car `.upload-state.json` is dropped.
4. Keeps `--dry-run`, `--verify` (GET-back check), `--assign` (first Key person →
   assignee when unambiguous), append-only `<csv>.upload-log.csv`, scoped-token
   diagnostic.

**pull** (per row where `Jira Key`/`Jira URL` is filled):
1. `GET /rest/api/3/issue/<key>` (fields: summary, description, labels).
2. Refresh columns: `Opportunity`←title; `Description`←ADF→markdown (body above the
   context rule); `Division/AI-fit/Key people/Systems/Themes/Summary`←parsed context
   block.
3. `--dry-run` prints a per-cell before/after diff; without it, writes the CSV back.
4. Rows with a blank `Jira URL` are skipped (nothing to pull).

### `regenerate_html.py` — Playwright browser automation

Rebuilds the standalone HTML by driving the app's own machinery (the data is
gzip+base64-compressed inside the bundle and lives in localStorage at runtime; there is
no clean text-injection point, so we reuse the app's real serializer).

```
python regenerate_html.py [--csv PATH] [--html PATH] [--out PATH] [--headed]
```

1. Launch headless Chromium, open the source standalone HTML (`file://`).
2. Drive the app's **CSV import** control (Division-stories tab) to load `--csv`.
3. Trigger the app's **"Save as standalone HTML"** and capture the download to `--out`.
4. Verify the output is a non-empty HTML bundle before reporting success.

Selectors for import/save are discovered against the real app during implementation
(open in a browser, read the DOM). If a selector is missing the script fails loudly
with what it looked for.

### Supporting files

- **`seed-template.csv`** — the 11-column header row, empty. Paste Jira URLs for a
  pull, or full content with blank Jira columns for a push.
- **`.env.example`** — documents the five vars. **`.gitignore`** — ignores `.env`,
  `*.upload-log.csv`, `__pycache__/`.
- **`README.md`** — the three flows, install (`pip install requests playwright` +
  `playwright install chromium`), and env setup.

## Data flow

```
                 push (Jira URL blank)
   CSV row  ─────────────────────────────▶  Jira Story   (writes Key+URL back to CSV)
   CSV row  ◀─────────────────────────────  Jira Story
                 pull (Jira URL filled)

   CSV  ──▶  regenerate_html.py ──▶  headless app import + Save-as-HTML  ──▶  standalone .html
```

## Error handling

- **Auth / project / permission** — the existing 4-stage preflight aborts with an
  actionable message (incl. scoped-token hint) before any writes.
- **Partial push** — CSV saved after each successful create; a crash leaves already-
  created rows correctly linked and the rest still blank (safe to re-run).
- **Create-guard** — a row with exactly one of `Jira Key`/`Jira URL` filled is treated
  as inconsistent and never pushed; it is reported so it can be reconciled by hand,
  preventing accidental duplicate issues.
- **TLS-inspecting proxy** — `truststore` auto-inject, `--ca-bundle`, and an SSLError
  handler explaining the three fixes. (From existing script.)
- **Rate limiting** — 429 retry with `Retry-After`, up to 5 attempts.
- **pull ADF surprises** — unknown ADF node types degrade to plain text rather than
  crashing; `--dry-run` lets you inspect the diff before writing.
- **regenerate** — missing selector or empty output → non-zero exit with the specific
  failure; never overwrites `--out` with a truncated file.

## Testing

- **`markdown_to_adf` / `adf_to_markdown`** — round-trip unit tests on representative
  Description cells (headings, bullets, bold, blank lines).
- **Context block** — `parse_context_block(build_context_block(row)) == row` metadata.
- **CSV I/O** — read→write a copy of the real CSV with no field changes yields byte-
  equivalent quoting/BOM/column order.
- **push/pull** — `--dry-run` against a 2-row fixture, asserting payloads and diffs
  without hitting the network (Jira client mocked).
- **regenerate** — smoke test: run against the real HTML + a 2-row CSV, assert the
  output opens and contains the new data.

## Assumptions / open notes (confirm at spec review)

1. **Regenerated HTML is the app's read-only snapshot.** The app's "Save as standalone
   HTML" bakes `__DATA_READONLY`, so the regenerated file is a read-only share snapshot,
   not an editable app. If an editable regenerated file is needed, that's a different
   export path.
2. **Scope of regenerate.** The canonical CSV maps to the **Division-stories** data.
   Regenerate updates that data; the app's other baked-in tabs (Initiatives, Divisions)
   keep their current defaults unless separately re-imported.
3. **One Jira issue type** (`Story`) for all rows; no epic/child hierarchy.

## Out of scope (YAGNI)

- Updating existing Jira issues' fields *from* the CSV (push only creates; pull only
  reads). No two-way field-level merge/conflict resolution.
- Attachments, comments, transitions, sprint/board assignment.
- Editing the other two data tabs via CSV.
