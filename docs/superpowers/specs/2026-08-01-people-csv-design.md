# people.csv — Design (toolkit extension)

**Date:** 2026-08-01
**Status:** Approved decisions, pending spec review
**Builds on:** `2026-08-01-whole-page-from-files-design.md`

## Purpose

Make the division-level **key people** (with descriptions) file-maintained, in their own
`people.csv`. Today they live only on `departments[].people` inside the app and are the
one part of the page not driven by a file.

## The data

Each division person in the app is `{name, role, relevance}` on `departments[].people`
(`relevance` = the description). There is **no "people" sub-tab**, so — unlike the other
three CSVs — people cannot go through the app's Upload CSV. They are applied via the same
`localStorage["insignia_ai_strategy_map_v2"]` overlay that already handles settings.

## `people.csv` schema

```
Division, Name, Role, Relevance
```

One row per person, grouped by division (row order = display order within the division).
`Relevance` is the description. Committed, hand-editable seed file (like `initiatives.csv`),
seeded by `export_tabs.py`. **Not** generated/git-ignored.

## Semantics — fully authoritative

On regenerate, `people.csv` **defines every division's people**:
- Group rows by `Division` → each department's `people` is set to exactly its rows'
  `{name, role, relevance}` objects.
- A department with **no** rows in `people.csv` gets an **empty** `people` list.
- A `Division` value in `people.csv` that matches no department is reported (unmatched
  notice) and ignored — consistent with the settings/divisions unmatched handling.

Trade-off (accepted): an incomplete `people.csv` removes people from the page. It is the
complete source of truth for division people.

## Components

### `settings_common.py` — add people helpers
- `PEOPLE_COLUMNS = ["Division", "Name", "Role", "Relevance"]`.
- `apply_people(d, people_rows) -> (d, unmatched)` — set `dep["people"]` for every
  department in `d["departments"]` from the grouped rows (empty list when absent); return
  the list of `Division` values with no matching department. Mutates `d` in place.

### `regenerate_html.py` — apply people in the overlay step
- New arg `--people` (default `people.csv`).
- In the existing post-import localStorage overlay: run when settings **or** people are
  present. After the settings merge, if `people.csv` exists, `apply_people(data, rows)`
  and print an unmatched notice per stray division. Then the existing write-back + reload
  + download proceed unchanged. If `people.csv` is missing, log a notice and leave the
  app's existing people untouched (so a people-less run doesn't wipe them).

### `export_tabs.py` — seed `people.csv`
- After the existing Initiatives/Divisions exports, force the app to persist (re-import
  the just-exported `divisions-current.csv`, which is identity and does not touch people),
  read `localStorage[...].departments`, flatten each department's `people` to
  `Division, Name, Role, Relevance` rows, and write `people.csv` (BOM + QUOTE_ALL via
  `jc.write_csv`).

## Testing

- **`apply_people`**: rows for two divisions set exactly those people; a department absent
  from the rows is emptied (authoritative); an unmatched `Division` is returned in
  `unmatched`; blank `Division`/`Name` rows skipped.
- **Browser smoke (extend `test_regenerate.py`)**: a `people.csv` with a sentinel person
  (unique name/relevance) for the test division → after regenerate, the sentinel person's
  name appears in the regenerated page; a division with no rows shows no stale people.

## Assumptions / open (confirm at spec review)

1. **Missing `people.csv` = don't touch people** (preserve current app people). Only a
   present-but-incomplete `people.csv` removes people (the authoritative choice). This
   avoids wiping people just because someone ran regenerate before seeding the file.
2. `export_tabs.py` reads people from `departments[].people` after forcing a save via a
   harmless re-import; validated first thing in the plan.

## Out of scope

- Per-opportunity key people (the stories CSV `Key people` column) — unchanged; those stay
  name-only per story.
- Any Jira linkage for people.
