# people.csv Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make division-level key people (name, role, relevance) file-maintained via a dedicated `people.csv`, applied fully-authoritatively during regenerate.

**Architecture:** `people.csv` (`Division, Name, Role, Relevance`) is applied onto `departments[].people` through the existing post-import `localStorage` overlay (there is no people Upload-CSV tab). `settings_common.apply_people` sets every department's people from the file; `export_tabs.py` seeds the file from the app's current people; `regenerate_html.py` applies it alongside the settings merge.

**Tech Stack:** Python 3.12, `playwright`, `pytest`. Reuses `jira_common` (`read_csv`/`write_csv`) and `settings_common`.

**Reference:** Spec `docs/superpowers/specs/2026-08-01-people-csv-design.md`.

**VALIDATED FACTS (probed against the real app):**
- `departments[].people` = `[{name, role, relevance}]`; 13 departments, 95 people total.
- After a per-tab Upload CSV (incl. a harmless re-import of `divisions-current.csv`, which does not touch people), the full object incl. `departments[].people` is in `localStorage["insignia_ai_strategy_map_v2"]`.
- Importing the stories/divisions CSVs does **not** modify `departments[].people`.

---

## File Structure

- Modify: `settings_common.py` — add `PEOPLE_COLUMNS`, `apply_people`.
- Modify: `export_tabs.py` — extract current people → `people.csv`.
- Modify: `regenerate_html.py` — `--people` arg + apply in the overlay step.
- Create (committed seed): `people.csv`.
- Modify: `tests/test_settings.py`, `tests/test_regenerate.py`, `README.md`.

---

## Task 1: `settings_common.apply_people`

**Files:**
- Modify: `settings_common.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_settings.py`:
```python
def _person(div, name, role="r", rel="x"):
    return {"Division": div, "Name": name, "Role": role, "Relevance": rel}


def test_apply_people_sets_people_per_department():
    d = {"departments": [{"name": "A", "people": [{"name": "old"}]},
                         {"name": "B", "people": []}]}
    rows = [_person("A", "Ann", "Lead", "does X"),
            _person("A", "Bob"), _person("B", "Cara")]
    out, unmatched = sc.apply_people(d, rows)
    a = next(x for x in out["departments"] if x["name"] == "A")
    assert a["people"] == [{"name": "Ann", "role": "Lead", "relevance": "does X"},
                           {"name": "Bob", "role": "r", "relevance": "x"}]
    assert unmatched == []


def test_apply_people_is_authoritative_empties_absent_department():
    d = {"departments": [{"name": "A", "people": [{"name": "keep?"}]},
                         {"name": "B", "people": [{"name": "gone"}]}]}
    out, _ = sc.apply_people(d, [_person("A", "Ann")])
    b = next(x for x in out["departments"] if x["name"] == "B")
    assert b["people"] == []                       # not in file -> emptied


def test_apply_people_reports_unmatched_division():
    d = {"departments": [{"name": "A", "people": []}]}
    _, unmatched = sc.apply_people(d, [_person("Ghost", "X")])
    assert unmatched == ["Ghost"]


def test_apply_people_skips_blank_division_or_name():
    d = {"departments": [{"name": "A", "people": [{"name": "old"}]}]}
    rows = [_person("", "NoDiv"), _person("A", ""), _person("A", "RealPerson")]
    out, _ = sc.apply_people(d, rows)
    a = out["departments"][0]
    assert [p["name"] for p in a["people"]] == ["RealPerson"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/scotty/dev/scryptid/insignia/0x_Themes/jira-viewer" && python3 -m pytest tests/test_settings.py -k apply_people -v`
Expected: FAIL — `AttributeError: module 'settings_common' has no attribute 'apply_people'`.

- [ ] **Step 3: Implement**

Append to `settings_common.py`:
```python
PEOPLE_COLUMNS = ["Division", "Name", "Role", "Relevance"]


def apply_people(d, people_rows):
    """Fully authoritative: set every department's `people` from people_rows,
    grouped by Division (row order preserved). A department with no rows gets an
    empty list. Blank Division/Name rows are skipped. Returns (d, unmatched),
    where unmatched lists Division values with no matching department. Mutates d."""
    by_div = {}
    for r in people_rows:
        div = (r.get("Division") or "").strip()
        name = (r.get("Name") or "").strip()
        if not div or not name:
            continue
        by_div.setdefault(div, []).append({
            "name": name,
            "role": (r.get("Role") or "").strip(),
            "relevance": (r.get("Relevance") or "").strip(),
        })
    deps = d.get("departments") or []
    dep_names = {dep.get("name") for dep in deps}
    for dep in deps:
        dep["people"] = by_div.get(dep.get("name"), [])
    unmatched = [k for k in by_div if k not in dep_names]
    return d, unmatched
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_settings.py -v`
Expected: PASS (13 tests: 9 existing + 4 new). Then `python3 -m pytest tests/ -q --ignore=tests/test_regenerate.py` → 32 passed.

- [ ] **Step 5: Commit**

```bash
git add settings_common.py tests/test_settings.py
git commit -m "feat: settings_common.apply_people — authoritative division people overlay"
```

---

## Task 2: `export_tabs.py` seeds `people.csv`

**Files:**
- Modify: `export_tabs.py`
- Create (committed): `people.csv`

- [ ] **Step 1: Add people extraction to `export_tabs.py`**

In `export_tabs.py`, after the two `_export_tab(...)` calls and BEFORE `browser.close()`, insert a forced-save + read + flatten:
```python
        # People have no Export-CSV tab. Force a save (re-import the app's own
        # divisions export — identity, doesn't touch people), then read
        # departments[].people out of localStorage.
        page.get_by_role("button", name=re.compile("Divisions ·")).click()
        page.wait_for_timeout(500)
        page.set_input_files(
            'input[type="file"]',
            str(pathlib.Path("divisions-current.csv").resolve()))
        page.wait_for_timeout(1800)
        raw = page.evaluate(
            "() => localStorage.getItem('insignia_ai_strategy_map_v2')")
        browser.close()
```
Change the existing `browser.close()` that followed the exports so it is not duplicated (the line above now performs it). Then, after the `with sync_playwright()` block, add the people-CSV write alongside the settings write:
```python
    import json
    people_rows = []
    for dep in (json.loads(raw).get("departments") if raw else []):
        for p in dep.get("people", []):
            people_rows.append({"Division": dep.get("name", ""),
                                "Name": p.get("name", ""),
                                "Role": p.get("role", ""),
                                "Relevance": p.get("relevance", "")})
    jc.write_csv("people.csv", people_rows, fieldnames=sc.PEOPLE_COLUMNS)
```
Add `import json` to the top imports if not already present. Update the final print to:
```python
    print("Wrote initiatives.csv, divisions-current.csv, settings.yaml, people.csv")
```
(Note: `raw` must be assigned before `browser.close()` inside the `with` block and referenced after — declare it in the outer scope, e.g. initialise `raw = None` before the `with sync_playwright()` block, and assign inside.)

- [ ] **Step 2: Generate `people.csv` and verify**

Run: `python3 export_tabs.py`
Expected: prints the 4-file line.
Verify:
```bash
head -1 people.csv          # -> "Division","Name","Role","Relevance"
python3 -c "import jira_common as jc; r=jc.read_csv('people.csv'); print(len(r),'people;', r[0]['Division'], '-', r[0]['Name'], '-', r[0]['Role'])"
```
Expected: header matches; prints `95 people; Portfolio & FAO - Ryan McCulloch - Senior FAO lead`.

- [ ] **Step 3: Commit**

```bash
git add export_tabs.py people.csv
git commit -m "feat: export_tabs seeds people.csv from the app's current division people"
```

---

## Task 3: apply `people.csv` in regenerate + docs

**Files:**
- Modify: `regenerate_html.py`
- Test: `tests/test_regenerate.py`
- Modify: `README.md`

- [ ] **Step 1: Add `--people` arg + pass-through**

In `regenerate_html.py` `main()`, add:
```python
    ap.add_argument("--people", default="people.csv")
```
and change the `regenerate(...)` call to also pass `people_path=args.people`. Change the signature:
```python
def regenerate(csv_path, html_path, out_path, headed,
               initiatives_path="initiatives.csv",
               settings_path="settings.yaml",
               divisions_out="divisions.csv",
               people_path="people.csv"):
```

- [ ] **Step 2: Apply people in the overlay block**

Replace this exact block (currently lines ~112–128):
```python
        # Overlay settings (header/hub/legend) into the app's data object, which
        # has no CSV import path, then reload so the app boots the merged state.
        if settings:
            raw = page.evaluate(
                "() => localStorage.getItem('insignia_ai_strategy_map_v2')")
            if raw:
                data = sc.merge_settings_into_data(json.loads(raw), settings)
                page.evaluate(
                    "(v) => localStorage.setItem("
                    "'insignia_ai_strategy_map_v2', v)",
                    json.dumps(data, ensure_ascii=False))
                page.reload()
                page.get_by_role("button", name=DATA_TAB).wait_for(timeout=30_000)
                page.wait_for_timeout(1000)
            else:
                print("  notice: no app data in localStorage after import; "
                      "settings overlay skipped")
```
with:
```python
        # Overlay settings (header/hub/legend) and people onto the app's data
        # object — neither has a CSV import path — then reload so the app boots
        # the merged state. A missing people.csv leaves existing people intact.
        people_rows = (jc.read_csv(people_path)
                       if pathlib.Path(people_path).exists() else None)
        if people_rows is None:
            print(f"  notice: {people_path} missing; division people left as-is")
        if settings or people_rows:
            raw = page.evaluate(
                "() => localStorage.getItem('insignia_ai_strategy_map_v2')")
            if raw:
                data = json.loads(raw)
                if settings:
                    sc.merge_settings_into_data(data, settings)
                if people_rows:
                    _, unmatched = sc.apply_people(data, people_rows)
                    for name in unmatched:
                        print(f"  notice: people.csv division {name!r} "
                              f"matches no division; ignored")
                page.evaluate(
                    "(v) => localStorage.setItem("
                    "'insignia_ai_strategy_map_v2', v)",
                    json.dumps(data, ensure_ascii=False))
                page.reload()
                page.get_by_role("button", name=DATA_TAB).wait_for(timeout=30_000)
                page.wait_for_timeout(1000)
            else:
                print("  notice: no app data in localStorage after import; "
                      "settings/people overlay skipped")
```

- [ ] **Step 3: Extend the browser smoke test**

In `tests/test_regenerate.py::test_regenerate_reflects_csv`, after the `init_p` write and before the `regenerate(...)` call, add a people.csv with a sentinel person for the test division (the stories row uses `Division: "D"`):
```python
    people_p = tmp_path / "people.csv"
    person = "ZZPERSON_regen"
    jc.write_csv(people_p, [{"Division": "D", "Name": person,
                             "Role": "Tester", "Relevance": "sentinel"}],
                 fieldnames=["Division", "Name", "Role", "Relevance"])
```
Change the `regenerate(...)` call to also pass `people_path=str(people_p)`. Then in the verification browser block, after the existing `company` assertion, add:
```python
        assert person in body, "people.csv person not in regenerated HTML"
```
(`body` is the `document.body.textContent` already captured; `person` is in scope.)

- [ ] **Step 4: Run the smoke test + full suite + end-to-end**

Run: `python3 -m pytest tests/test_regenerate.py -v` → PASS (~20s).
Run: `python3 regenerate_html.py --out /tmp/regen-people.html` → `Regenerated … (… bytes)`.
Run: `python3 -m pytest tests/ -q` → all green.

- [ ] **Step 5: Update README**

In the whole-page-regeneration section's file list, add a bullet:
```markdown
- **`people.csv`** (`Division, Name, Role, Relevance`) — the division key people and their descriptions. Fully authoritative when present: each division's people are set from the file (a division with no rows shows none); a missing file leaves existing people untouched.
```
And add `people.csv` to the `## Files` table:
```markdown
| `people.csv` | Division key people (name, role, relevance) |
```

- [ ] **Step 6: Commit**

```bash
git add regenerate_html.py tests/test_regenerate.py README.md
git commit -m "feat: regenerate applies people.csv onto division people; docs"
```

- [ ] **Step 7: Final review**

Dispatch an independent reviewer over this extension: `apply_people` authoritative semantics + unmatched handling, the missing-vs-present people.csv behaviour, export_tabs people extraction, README accuracy, and any data-loss footgun (e.g. an empty people.csv wiping everyone — confirm that's the intended authoritative behaviour and that a *missing* file does not). Fix Critical/Important findings; re-run suite.

---

## Self-Review Notes

- **Spec coverage:** schema `Division,Name,Role,Relevance` (Task 1 `PEOPLE_COLUMNS`), authoritative apply + unmatched (Task 1 `apply_people`), export seed (Task 2), regenerate overlay + `--people` + missing-file preservation (Task 3), tests (Tasks 1 & 3), README (Task 3). All mapped.
- **Placeholder scan:** none — concrete code/commands throughout.
- **Name consistency:** `sc.PEOPLE_COLUMNS`, `sc.apply_people`, `--people`/`people_path`, storage key `insignia_ai_strategy_map_v2`, person object keys `name`/`role`/`relevance` — consistent across tasks.
- **Validated:** people live at `departments[].people`; extraction after a forced save works (95 people); imports don't disturb people.
