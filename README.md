# Jira ⇄ CSV ⇄ Standalone-HTML Toolkit

The CSV `insignia-division-stories-jira-linked.csv` is the single source of truth.
Whether a row's `Jira Key` / `Jira URL` columns are filled decides what each script does.

**Columns:** `#, Division, Opportunity, AI-fit, Key people, Systems, Themes, Summary, Description, Jira Key, Jira URL`
(UTF-8 with BOM, every field quoted; `Opportunity` is the Jira issue title.)

## Setup

```bash
pip install requests playwright
python -m playwright install chromium      # for regenerate_html.py only
cp .env.example .env                        # then fill in JIRA_* values
```

`.env` (gitignored) holds your Jira Cloud credentials:

```
JIRA_BASE_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=...        # https://id.atlassian.com/manage-profile/security/api-tokens
JIRA_PROJECT_KEY=ABC
JIRA_ISSUE_TYPE=Story
```

## push — create Jira issues for blank rows

A row is eligible only when **both** `Jira Key` and `Jira URL` are blank. Eligible rows
become Jira issues (title = `Opportunity`, body = `Description` + a metadata context
block, plus `div-*` / `ai-fit-*` / `theme-*` labels); the created key + URL are written
back into the CSV, saved after each create. Rows already linked are skipped. A row with
only **one** of Key/URL filled is inconsistent — reported and skipped, never duplicated.

```bash
python jira_sync.py push --dry-run          # preview payloads, no API calls
python jira_sync.py push                     # create + write Key/URL back
python jira_sync.py push --assign --verify   # set assignee (when unambiguous), verify each create
```

Other flags: `-v/--verbose`, `--csv PATH`, `--ca-bundle PATH` (corporate TLS proxy).
A per-run audit log is appended to `<csv>.upload-log.csv` (gitignored).

## pull — refresh columns from linked issues

The inverse. For each row with a `Jira URL`, the issue is fetched and the content columns
are refreshed from it: `Opportunity` from the title, `Description` from the issue body,
and Division / AI-fit / Key people / Systems / Themes / Summary from the description's
context block. Rows without a URL are untouched.

```bash
python jira_sync.py pull --dry-run           # show per-cell diff, no write
python jira_sync.py pull                      # apply
```

## regenerate — rebuild the standalone HTML from the CSV

Drives the app's own CSV import + "Download standalone HTML" in headless Chromium
(the data is compressed inside the bundle, so this reuses the app's real serializer).
The output is the app's read-only share snapshot and reflects the current CSV.

```bash
python regenerate_html.py                    # -> "Insignia AI Strategy Map - regenerated.html"
python regenerate_html.py --headed           # watch it run
python regenerate_html.py --csv X --html Y --out Z
```

`regenerate_html.py` rebuilds the **entire** page from files, not just the stories tab:

- **`settings.yaml`** drives the header (company, title, intro), the centre node
  (name, tagline, and its Jira board `url`), the AI-fit legend (title + labels/colours),
  and per-division colour/tagline/background overrides. Every section is optional — it's
  an overlay, so anything you omit keeps the app's current value.
- **Divisions** are derived automatically from the stories CSV: one per distinct
  `Division`, with Systems/Themes = the deduped union across that division's stories, and
  colour/tagline/background from `settings.yaml` (an auto-assigned palette colour for any
  division you haven't overridden). Written to `divisions.csv` (generated, git-ignored).
- **`initiatives.csv`** is a standalone editable file.
- **`people.csv`** (`Division, Name, Role, Relevance`) — division key people and their descriptions. Fully authoritative when present: each division's people are set from the file (a division with no rows shows none); a missing file leaves existing people untouched.

Seed the editable files from the app's current content, then regenerate:

```bash
python export_tabs.py        # writes initiatives.csv, settings.yaml, people.csv
python regenerate_html.py    # stories CSV + initiatives.csv + settings.yaml + people.csv -> standalone HTML
```

Setup for this path also needs YAML: `pip install requests playwright pyyaml`.

## seed-template.csv

The 11-column header row, empty. Start a fresh batch by pasting full content with blank
Jira columns (then `push`), or paste Jira URLs into existing rows (then `pull`).

## Tests

```bash
python -m pytest tests/ -q
```

## Files

| File | Role |
|------|------|
| `jira_common.py` | Shared: `.env` loader, CSV I/O (BOM + QUOTE_ALL), markdown⇄ADF, context-block round-trip, labels, Jira client + preflight |
| `jira_sync.py` | CLI: `push` / `pull` |
| `regenerate_html.py` | Playwright regenerator: whole page from stories CSV + `initiatives.csv` + `settings.yaml` + `people.csv` |
| `settings_common.py` | Settings load, division derivation (Systems/Themes union + auto-colour), settings + people overlay |
| `export_tabs.py` | Seed `initiatives.csv` + `settings.yaml` + `people.csv` from the app's current content |
| `settings.yaml` | Header / centre-node / legend / per-division overrides |
| `initiatives.csv` | Standalone editable initiatives |
| `people.csv` | Division key people (name, role, relevance) |
| `seed-template.csv` | Empty stories-CSV template |
| `.env.example` | Config template |
