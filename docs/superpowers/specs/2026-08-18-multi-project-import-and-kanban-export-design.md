# Multi-project import and kanban columns on export

Date: 2026-08-18

Two related changes to CSV/Jira fidelity. The first lets `import` read more than
one Jira project; the second stops the app's Export CSV from silently dropping
kanban progress.

## Problem

**Import is single-project.** `run_import` builds `project = KEY` from one
`--project` value (`src/jira_sync.py:324`), and preflight checks one key. The
map now needs to span two Jira projects, AITR and AIENG, with more possible
later. Raw `--jql` already accepts `project in (AITR, AIENG)`, but that path
skips the project-visibility preflight, so a mistyped key returns zero issues
without complaint, and it forces `--board` because board discovery is skipped
when no project key is given.

**Export loses kanban progress.** The app reads `Stage` and `Swimlane` on CSV
import (`src/strategy-map.src.html:3704`) but writes neither back out. The
Data → Division stories export emits 13 columns ending at `Jira URL`
(`src/strategy-map.src.html:3026`). Exporting, hand-editing and re-importing
therefore wipes every on-card stepper — and it fails silently, because
`stageMarker` returns `null` for an empty stage (`src/strategy-map.src.html:2312`),
which renders as no marker rather than as an error.

## Change 1 — multi-project import

Both projects sit on the same board (6393), so the column pipeline and `Stage`
values are already shared. No per-project stage mapping is needed.

### CLI

`--project` becomes repeatable and comma-splitting. These are equivalent:

    python src/jira_sync.py import --project AITR,AIENG
    python src/jira_sync.py import --project AITR --project AIENG

Keys are stripped of surrounding whitespace, empty entries dropped, duplicates
removed preserving first-seen order. `--jql` continues to override `--project`
entirely.

### JQL

In `run_import`, `scope` is built from the key list:

- one key → `project = AITR` (unchanged, so existing behaviour and tests hold)
- two or more → `project in (AITR, AIENG)`

The `ORDER BY key ASC` suffix is unchanged. Swimlane composition needs no
change: `scope` is already wrapped in parentheses when lane JQL is AND-ed onto
it (`src/jira_sync.py:351`), yielding
`(project in (AITR, AIENG)) AND (priority = Highest)`.

### Preflight

`connect_and_preflight` accepts a single key or a list. It checks every key,
prints one `Target project:` line per visible project, and collects *all*
invisible keys before exiting, so a two-key typo costs one round trip rather
than two. `push` and `pull` keep passing a single string; the signature stays
backward compatible.

### Board resolution

New precedence: `--board` → `settings.yaml kanban.board` → `find_board(first key)`.

This is required, not incidental: "first board on the project" has no meaning
once there are two projects. It also closes an existing mismatch — the notice at
`src/jira_sync.py:343` tells the user to set `kanban.board` in settings.yaml,
but nothing in the import path ever reads it.

A `load_board(settings_path)` helper sits beside `load_swimlanes`, using the
same soft-import-yaml pattern so `push` and `pull` keep working without PyYAML
installed.

### Environment variable

`JIRA_PROJECT_KEY` stays single-valued, because `push` creates issues into it.
To close the footgun, `push` exits with an actionable message if the value
contains a comma, rather than attempting to create issues in a project literally
named `AITR,AIENG`.

### Makefile

`make import PROJECT="AITR,AIENG"` already passes through correctly — the
existing quoting handles it. Only the help text needs updating.

## Change 2 — Stage and Swimlane on export

In `exportCsv`, the `dataTab === "story"` branch
(`src/strategy-map.src.html:3020`) gains two columns:

- header: append `"Stage"`, `"Swimlane"`
- each row: append `o.stage || ""`, `o.swimlane || ""`

The resulting 15-column header then matches `jc.COLUMNS`
(`src/jira_common.py:23`) exactly, in the same order, making the app export and
the Jira import interchangeable.

The Priority tab's WSJF export and the Divisions export are unchanged. The WSJF
export is a scoring artefact, not a stories round-trip, and the Divisions export
is division-level, where stage has no meaning.

### Implementation note

`src/strategy-map.src.html` is the editable source of the single-file
`dc-runtime` bundle. After editing it, run `python3 src/build_bundle.py`
(`make bundle`) to reassemble the bundle from `src/engine/` plus the source —
there is no `apply` step in the current build. Verify with the **full**
`python3 -m pytest tests/ -q`; the bundle is a generated, gitignored artifact,
so it must be assembled before the suite will run at all.

## Non-goals

- Routing `push` per project. New issues continue to go to one project per run.
- Per-project boards or differing stage pipelines.
- A project list in `settings.yaml` (revisit if the set of projects stabilises).
- Any change to how the map renders steppers.
- Backfilling `Stage`/`Swimlane` into the existing
  `insignia-division-stories-jira-linked.csv`, whose header currently stops at
  `Jira URL`. A fresh `import` regenerates it with both columns.

## Testing

Extending `tests/test_import.py`, which already carries a fake Jira client and
asserts on the JQL the importer builds:

1. Single key still builds `project = AITR ORDER BY key ASC` (regression).
2. Two keys build `project in (AITR, AIENG) ORDER BY key ASC`.
3. Comma form and repeated-flag form produce the same key list.
4. Whitespace stripped, empties dropped, duplicates removed in order.
5. Swimlane search composes as `(project in (AITR, AIENG)) AND (priority = Highest)`.
6. Board falls back to `settings.yaml kanban.board` when `--board` is absent,
   and to `find_board(first key)` when neither is set.
7. Preflight names every invisible key in one message, not just the first.
8. `push` exits with a clear message when `JIRA_PROJECT_KEY` contains a comma.

For change 2, a test asserts the export header literal in
`src/strategy-map.src.html` equals `jc.COLUMNS`, so the two column lists cannot
drift apart again. This test reads the source rather than executing the app; it
is deliberately narrow, and will need updating if the header is ever reformatted
across lines.

## Risks

- Parsing the export header out of the app source is string-matching against
  HTML/JS. Mitigated by keeping the assertion tied to one literal array and
  failing loudly with the matched text on mismatch.
- Widening the import scope pulls in every issue in AIENG. Rows without a
  recognised Division fall to the `--division` default (`N/A`), which keeps
  them on the map rather than dropping them; run `--dry-run` first to see the
  division spread before writing.
