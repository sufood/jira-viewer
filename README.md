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
| `regenerate_html.py` | Playwright HTML regenerator |
| `seed-template.csv` | Empty CSV template |
| `.env.example` | Config template |
