# Jira ⇄ CSV ⇄ Standalone-HTML Toolkit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three scripts so the CSV is the single source of truth — push CSV rows to Jira (writing Key+URL back), pull Jira content into the CSV, and regenerate the standalone HTML from the CSV.

**Architecture:** A shared `jira_common.py` module (`.env` loader, CSV I/O, markdown⇄ADF, context-block round-trip carrier, ported Jira client). A `jira_sync.py` CLI with `push`/`pull` subcommands routed by whether the `Jira Key`/`Jira URL` columns are filled. A `regenerate_html.py` that drives the app's own CSV-import + "Save as standalone HTML" via headless Playwright.

**Tech Stack:** Python 3.12, `requests`, `pytest`, `playwright` (Chromium). Optional `truststore` for corporate TLS proxies.

**Reference:** Spec at `docs/superpowers/specs/2026-08-01-jira-csv-html-toolkit-design.md`. Existing working script `upload_to_jira.py` is the source for the Jira client, forward markdown→ADF, and slug helpers — port verbatim where noted.

**Canonical CSV columns (exact order, BOM, every field quoted / `QUOTE_ALL`):**
`#, Division, Opportunity, AI-fit, Key people, Systems, Themes, Summary, Description, Jira Key, Jira URL`

---

## File Structure

- Create: `jira_common.py` — shared module (env, CSV I/O, ADF, context block, labels, Jira client).
- Create: `jira_sync.py` — CLI with `push` / `pull` subcommands.
- Create: `regenerate_html.py` — Playwright HTML regenerator.
- Create: `tests/test_csv_io.py`, `tests/test_adf.py`, `tests/test_context_block.py`, `tests/test_push.py`, `tests/test_pull.py`, `tests/conftest.py`.
- Create: `seed-template.csv`, `.env.example`, `.gitignore`, `README.md`.
- Keep: `upload_to_jira.py` (source of ported code; leave in place until Task 9 confirms parity).
- Keep: `insignia-division-stories-jira-linked.csv`, `Insignia AI Strategy Map - Jira linked.html`.

---

## Task 0: Scaffolding, git, and supporting files

**Files:**
- Create: `.gitignore`, `.env.example`, `seed-template.csv`, `tests/conftest.py`

- [ ] **Step 1: Initialise git so work is tracked**

Run:
```bash
cd "/Users/scotty/dev/scryptid/insignia/0x_Themes/jira-viewer"
git init && git add -A && git commit -m "chore: snapshot existing HTML, CSV, upload script before toolkit work"
```
Expected: a first commit listing the HTML, CSV, `upload_to_jira.py`, and the docs/ specs+plans.

- [ ] **Step 2: Write `.gitignore`**

```gitignore
.env
*.upload-log.csv
*.upload-state.json
__pycache__/
.pytest_cache/
*.pyc
```

- [ ] **Step 3: Write `.env.example`**

```bash
# Copy to .env and fill in. .env is gitignored — never commit real secrets.
# Jira Cloud site, no trailing slash:
JIRA_BASE_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=you@company.com
# API token: https://id.atlassian.com/manage-profile/security/api-tokens
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=ABC
# Issue type created by `push` (must exist in the project):
JIRA_ISSUE_TYPE=Story
```

- [ ] **Step 4: Write `seed-template.csv`** (header only, BOM, all fields quoted)

Run:
```bash
cd "/Users/scotty/dev/scryptid/insignia/0x_Themes/jira-viewer"
printf '\xEF\xBB\xBF"#","Division","Opportunity","AI-fit","Key people","Systems","Themes","Summary","Description","Jira Key","Jira URL"\n' > seed-template.csv
```
Expected: `head -1 seed-template.csv | xxd | head -1` starts with `efbb bf22 2322` (BOM + `"#"`).

- [ ] **Step 5: Write `tests/conftest.py`** (shared fixtures)

```python
import csv
import pytest

COLUMNS = [
    "#", "Division", "Opportunity", "AI-fit", "Key people", "Systems",
    "Themes", "Summary", "Description", "Jira Key", "Jira URL",
]


@pytest.fixture
def sample_row():
    return {
        "#": "1",
        "Division": "Portfolio & FAO",
        "Opportunity": "Unit Pricing Control — the S.U.E. agent",
        "AI-fit": "High",
        "Key people": "Chris Page",
        "Systems": "Unified Data Platform; Copilot; Jira",
        "Themes": "Anomaly detection; Reconciliation & matching",
        "Summary": "Move to predictive, risk-weighted alerting.",
        "Description": "## Problem\n\n**Core problem:** Tolerance-based control.\n\n- Retrospective\n- High volume",
        "Jira Key": "",
        "Jira URL": "",
    }


@pytest.fixture
def write_csv_file(tmp_path):
    def _write(rows, name="data.csv"):
        path = tmp_path / name
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        return path
    return _write
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore .env.example seed-template.csv tests/conftest.py
git commit -m "chore: scaffold toolkit — gitignore, env example, seed template, test fixtures"
```

---

## Task 1: `jira_common.py` — env loader + CSV I/O

**Files:**
- Create: `jira_common.py`
- Test: `tests/test_csv_io.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_csv_io.py`:
```python
import csv
import jira_common as jc


def test_columns_constant_exact_order():
    assert jc.COLUMNS == [
        "#", "Division", "Opportunity", "AI-fit", "Key people", "Systems",
        "Themes", "Summary", "Description", "Jira Key", "Jira URL",
    ]


def test_read_csv_strips_bom(write_csv_file, sample_row):
    path = write_csv_file([sample_row])
    rows = jc.read_csv(path)
    assert list(rows[0].keys())[0] == "#"          # BOM stripped from first key
    assert rows[0]["Division"] == "Portfolio & FAO"


def test_write_csv_roundtrips_bom_and_quoting(write_csv_file, sample_row, tmp_path):
    src = write_csv_file([sample_row])
    rows = jc.read_csv(src)
    out = tmp_path / "out.csv"
    jc.write_csv(out, rows)
    raw = out.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")          # BOM preserved
    text = raw.decode("utf-8-sig")
    assert text.splitlines()[0] == (                # every field quoted
        '"#","Division","Opportunity","AI-fit","Key people","Systems",'
        '"Themes","Summary","Description","Jira Key","Jira URL"'
    )
    assert jc.read_csv(out) == rows                 # data round-trips


def test_load_dotenv_does_not_override_os_env(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("JIRA_PROJECT_KEY=FROMFILE\nJIRA_EMAIL=file@x.com\n")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "FROMOS")
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    jc.load_dotenv(env)
    import os
    assert os.environ["JIRA_PROJECT_KEY"] == "FROMOS"   # OS wins
    assert os.environ["JIRA_EMAIL"] == "file@x.com"     # file fills the gap
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/scotty/dev/scryptid/insignia/0x_Themes/jira-viewer" && python3 -m pytest tests/test_csv_io.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jira_common'`.

- [ ] **Step 3: Write minimal implementation**

Create `jira_common.py`:
```python
#!/usr/bin/env python3
"""Shared helpers for the Jira ⇄ CSV toolkit: env, CSV I/O, ADF, Jira client."""

import csv
import os

COLUMNS = [
    "#", "Division", "Opportunity", "AI-fit", "Key people", "Systems",
    "Themes", "Summary", "Description", "Jira Key", "Jira URL",
]


def load_dotenv(path=".env"):
    """Load KEY=value lines from `path` into os.environ WITHOUT overriding
    variables already set in the real environment."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def read_csv(path):
    """Read a CSV as a list of dict rows; strips the UTF-8 BOM."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames=None):
    """Atomically write rows with BOM + QUOTE_ALL to match the canonical file."""
    fieldnames = fieldnames or COLUMNS
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
    os.replace(tmp, path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_csv_io.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add jira_common.py tests/test_csv_io.py
git commit -m "feat: jira_common env loader and BOM/QUOTE_ALL CSV I/O"
```

---

## Task 2: `jira_common.py` — markdown ⇄ ADF

**Files:**
- Modify: `jira_common.py` (append helpers)
- Test: `tests/test_adf.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_adf.py`:
```python
import jira_common as jc


def test_markdown_to_adf_heading_bullets_bold():
    doc = jc.markdown_to_adf("## Problem\n\n**Core:** x\n\n- a\n- b")
    assert doc["type"] == "doc" and doc["version"] == 1
    types = [n["type"] for n in doc["content"]]
    assert types == ["heading", "paragraph", "bulletList"]
    assert doc["content"][0]["attrs"]["level"] == 3
    # bold run becomes a strong-marked text node
    marks = doc["content"][1]["content"][0].get("marks")
    assert marks == [{"type": "strong"}]


def test_adf_to_markdown_inverts_body():
    md = "## Problem\n\n**Core:** x\n\n- a\n- b"
    doc = jc.markdown_to_adf(md)
    out = jc.adf_to_markdown(doc)
    assert out == md


def test_adf_to_markdown_ignores_context_block():
    # body + rule + context bulletList -> only the body comes back
    doc = jc.markdown_to_adf("Body line")
    doc["content"].append({"type": "rule"})
    doc["content"].append({
        "type": "bulletList",
        "content": [{"type": "listItem",
                     "content": [jc.adf_paragraph("Division: X")]}],
    })
    assert jc.adf_to_markdown(doc) == "Body line"


def test_adf_to_markdown_unknown_node_degrades_to_text():
    doc = {"type": "doc", "version": 1, "content": [
        {"type": "panel", "content": [jc.adf_paragraph("kept")]}]}
    assert "kept" in jc.adf_to_markdown(doc)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_adf.py -v`
Expected: FAIL — `AttributeError: module 'jira_common' has no attribute 'markdown_to_adf'`.

- [ ] **Step 3: Port forward helpers, then add the inverse**

First, copy verbatim from `upload_to_jira.py` into `jira_common.py`: `_inline` (lines 77–85), `adf_paragraph` (88–89), and `markdown_to_adf_blocks` (92–117). Then append this public wrapper and the inverse:

```python
def markdown_to_adf(md):
    """Full ADF doc from description markdown."""
    return {"type": "doc", "version": 1,
            "content": markdown_to_adf_blocks(md)}


def _adf_inline_to_md(nodes):
    parts = []
    for n in nodes:
        text = n.get("text", "")
        if any(m.get("type") == "strong" for m in n.get("marks", [])):
            text = f"**{text}**"
        parts.append(text)
    return "".join(parts)


def _adf_block_to_md(node):
    t = node.get("type")
    if t == "heading":
        level = node.get("attrs", {}).get("level", 3)
        return f"{'#' * level} {_adf_inline_to_md(node.get('content', []))}"
    if t == "paragraph":
        return _adf_inline_to_md(node.get("content", []))
    if t == "bulletList":
        lines = []
        for item in node.get("content", []):
            for sub in item.get("content", []):
                lines.append(f"- {_adf_inline_to_md(sub.get('content', []))}")
        return "\n".join(lines)
    # Unknown node: recurse into any content, keep the text.
    inner = [_adf_block_to_md(c) for c in node.get("content", [])]
    return "\n".join(x for x in inner if x)


def adf_to_markdown(doc):
    """Inverse of markdown_to_adf. Stops before the trailing context block
    (the last `rule` node and everything after it)."""
    content = doc.get("content", [])
    cut = len(content)
    for i in range(len(content) - 1, -1, -1):
        if content[i].get("type") == "rule":
            cut = i
            break
    blocks = [_adf_block_to_md(n) for n in content[:cut]]
    return "\n\n".join(b for b in blocks if b)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_adf.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add jira_common.py tests/test_adf.py
git commit -m "feat: markdown<->ADF conversion in jira_common"
```

---

## Task 3: `jira_common.py` — context block, labels, slug

**Files:**
- Modify: `jira_common.py`
- Test: `tests/test_context_block.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_context_block.py`:
```python
import jira_common as jc

CONTEXT_KEYS = ["Division", "AI-fit", "Key people", "Systems", "Themes", "Summary"]


def test_context_block_roundtrips_exact_values(sample_row):
    nodes = jc.build_context_block(sample_row)      # [rule, bulletList]
    doc = {"type": "doc", "version": 1, "content": [jc.adf_paragraph("body")] + nodes}
    parsed = jc.parse_context_block(doc)
    for k in CONTEXT_KEYS:
        assert parsed[k] == sample_row[k]           # exact, un-slugified


def test_build_description_body_then_context(sample_row):
    doc = jc.build_description(sample_row)
    assert doc["content"][0]["type"] == "heading"   # body first
    assert doc["content"][-2]["type"] == "rule"     # then rule + context
    assert doc["content"][-1]["type"] == "bulletList"


def test_slug_and_labels(sample_row):
    assert jc.slug("Portfolio & FAO", "div-") == "div-portfolio-fao"
    labels = jc.build_labels(sample_row)
    assert "div-portfolio-fao" in labels
    assert "ai-fit-high" in labels
    assert any(l.startswith("theme-") for l in labels)


def test_parse_context_block_missing_returns_empty():
    doc = {"type": "doc", "version": 1, "content": [jc.adf_paragraph("no context")]}
    assert jc.parse_context_block(doc) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_context_block.py -v`
Expected: FAIL — missing `build_context_block`.

- [ ] **Step 3: Port `slug`/`split_multi`, then add context + labels**

Copy verbatim from `upload_to_jira.py`: `slug` (65–69) and `split_multi` (72–74). Then append:

```python
CONTEXT_KEYS = ["Division", "AI-fit", "Key people", "Systems", "Themes", "Summary"]


def build_context_block(row):
    """Machine-readable, exact-value carrier appended to every description.
    Returns [rule, bulletList]."""
    lines = [f"{k}: {row.get(k, '')}" for k in CONTEXT_KEYS]
    return [
        {"type": "rule"},
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [adf_paragraph(line)]}
            for line in lines]},
    ]


def parse_context_block(doc):
    """Read exact metadata values back from the trailing context bulletList.
    Returns {} when no context block is present."""
    content = doc.get("content", [])
    rule_idx = None
    for i in range(len(content) - 1, -1, -1):
        if content[i].get("type") == "rule":
            rule_idx = i
            break
    if rule_idx is None:
        return {}
    result = {}
    for node in content[rule_idx + 1:]:
        if node.get("type") != "bulletList":
            continue
        for item in node.get("content", []):
            for para in item.get("content", []):
                text = _adf_inline_to_md(para.get("content", []))
                if ": " in text:
                    key, _, value = text.partition(": ")
                    if key in CONTEXT_KEYS:
                        result[key] = value
    return result


def build_description(row):
    """Description markdown body + context block, as one ADF doc."""
    doc = markdown_to_adf(row["Description"])
    doc["content"].extend(build_context_block(row))
    return doc


def build_labels(row):
    labels = [slug(row["Division"], "div-"), slug(row["AI-fit"], "ai-fit-")]
    labels += [slug(t, "theme-") for t in split_multi(row["Themes"])]
    return sorted(set(labels))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_context_block.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add jira_common.py tests/test_context_block.py
git commit -m "feat: context-block round-trip carrier, labels, slug in jira_common"
```

---

## Task 4: `jira_common.py` — port the Jira client

**Files:**
- Modify: `jira_common.py`

- [ ] **Step 1: Port the client and preflight verbatim**

From `upload_to_jira.py`, copy into `jira_common.py`:
- the `truststore` auto-inject block (lines 49–57),
- the `Jira` class in full (lines 182–288): `__init__`, `_request`, `existing_summaries`, `find_account_id`, `whoami`, `can_create_issues`, `check_project`, `list_projects`, `create_issue`, `get_issue`,
- `append_log` (291–301).

Add `import json`, `import re`, `import time`, `import requests` to the imports at the top of `jira_common.py` (alongside `csv`, `os`).

- [ ] **Step 2: Add a reusable preflight function**

Append to `jira_common.py`:
```python
def connect_and_preflight(project_key, issue_type):
    """Build a Jira client from env and run the 4 preflight checks.
    Returns the connected Jira client. Raises SystemExit with an actionable
    message on any failure."""
    import sys
    try:
        jira = Jira(os.environ["JIRA_BASE_URL"], os.environ["JIRA_EMAIL"],
                    os.environ["JIRA_API_TOKEN"])
    except KeyError as e:
        sys.exit(f"Missing environment variable: {e}")

    me = jira.whoami()
    if me is None:
        sys.exit("ERROR: authentication failed (check JIRA_EMAIL / "
                 "JIRA_API_TOKEN; scoped tokens need read+write:jira-work).")
    print(f"Authenticated as: {me.get('displayName')}")

    project = jira.check_project(project_key)
    if project is None:
        visible = ", ".join(p["key"] for p in jira.list_projects()) or "(none)"
        sys.exit(f"ERROR: project {project_key!r} not visible. "
                 f"Projects you can see: {visible}")
    type_names = [t["name"] for t in project.get("issueTypes", [])]
    if type_names and issue_type not in type_names:
        sys.exit(f"ERROR: project has no {issue_type!r} issue type. "
                 f"Available: {', '.join(type_names)}")
    print(f"Target project: {project['key']} — {project['name']} "
          f"(issue type {issue_type})")
    return jira
```

- [ ] **Step 3: Verify the module imports cleanly**

Run: `python3 -c "import jira_common; print('ok', len(jira_common.COLUMNS))"`
Expected: `ok 11`

- [ ] **Step 4: Verify existing tests still pass**

Run: `python3 -m pytest tests/ -v`
Expected: PASS (all tests from Tasks 1–3).

- [ ] **Step 5: Commit**

```bash
git add jira_common.py
git commit -m "feat: port Jira client and preflight into jira_common"
```

---

## Task 5: `jira_sync.py` — push subcommand

**Files:**
- Create: `jira_sync.py`
- Test: `tests/test_push.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_push.py`:
```python
import jira_sync


def _make_rows():
    base = {c: "" for c in jira_sync.jc.COLUMNS}
    both_blank = {**base, "#": "1", "Opportunity": "Alpha",
                  "Division": "D", "AI-fit": "High", "Key people": "P",
                  "Systems": "S", "Themes": "T", "Summary": "Sum",
                  "Description": "body"}
    both_filled = {**base, "#": "2", "Opportunity": "Beta",
                   "Jira Key": "ABC-9", "Jira URL": "https://x/browse/ABC-9"}
    inconsistent = {**base, "#": "3", "Opportunity": "Gamma",
                    "Jira Key": "ABC-7", "Jira URL": ""}
    return [both_blank, both_filled, inconsistent]


def test_classify_rows():
    rows = _make_rows()
    eligible, linked, inconsistent = jira_sync.classify_push(rows)
    assert [r["#"] for r in eligible] == ["1"]
    assert [r["#"] for r in linked] == ["2"]
    assert [r["#"] for r in inconsistent] == ["3"]


def test_push_writes_key_and_url_back(monkeypatch, tmp_path):
    rows = _make_rows()

    class FakeResp:
        status_code = 201
        def json(self):
            return {"key": "ABC-1", "id": "1001"}

    class FakeJira:
        base = "https://x.atlassian.net"
        def create_issue(self, payload):
            assert payload["fields"]["summary"] == "Alpha"   # Opportunity = title
            assert payload["fields"]["issuetype"]["name"] == "Story"
            return FakeResp()

    csv_path = tmp_path / "d.csv"
    jira_sync.jc.write_csv(csv_path, rows)
    result = jira_sync.run_push(FakeJira(), csv_path, "PROJ", "Story",
                                assign=False, verify=False, verbose=False)
    assert result["created"] == 1
    assert result["inconsistent"] == 1
    saved = jira_sync.jc.read_csv(csv_path)
    row1 = next(r for r in saved if r["#"] == "1")
    assert row1["Jira Key"] == "ABC-1"
    assert row1["Jira URL"] == "https://x.atlassian.net/browse/ABC-1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_push.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jira_sync'`.

- [ ] **Step 3: Write the push implementation**

Create `jira_sync.py`:
```python
#!/usr/bin/env python3
"""Sync the CSV with Jira. `push` creates issues for blank rows and writes the
Jira Key + URL back; `pull` refreshes content columns from linked issues.

Config (env or .env): JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN,
JIRA_PROJECT_KEY, JIRA_ISSUE_TYPE (default Story).

    python jira_sync.py push --dry-run
    python jira_sync.py push
    python jira_sync.py pull --dry-run
    python jira_sync.py pull
"""

import argparse
import os
import sys
import time

import jira_common as jc

DEFAULT_CSV = "insignia-division-stories-jira-linked.csv"


def classify_push(rows):
    """Split rows into (eligible, linked, inconsistent) by Key/URL state."""
    eligible, linked, inconsistent = [], [], []
    for r in rows:
        has_key = bool(r.get("Jira Key", "").strip())
        has_url = bool(r.get("Jira URL", "").strip())
        if not has_key and not has_url:
            eligible.append(r)
        elif has_key and has_url:
            linked.append(r)
        else:
            inconsistent.append(r)
    return eligible, linked, inconsistent


def run_push(jira, csv_path, project_key, issue_type, assign, verify, verbose):
    rows = jc.read_csv(csv_path)
    eligible, linked, inconsistent = classify_push(rows)
    print(f"{len(rows)} rows: {len(eligible)} to create, {len(linked)} "
          f"already linked, {len(inconsistent)} inconsistent (skipped)")
    for r in inconsistent:
        print(f"  WARNING row {r['#']}: only one of Jira Key/URL set "
              f"(key={r.get('Jira Key')!r} url={r.get('Jira URL')!r}); "
              f"not pushed")

    created, failed = 0, []
    for row in eligible:
        payload = {"fields": {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": row["Opportunity"][:255],
            "description": jc.build_description(row),
            "labels": jc.build_labels(row),
        }}
        if assign:
            first = jc.split_multi(row["Key people"])
            acct = jira.find_account_id(first[0]) if first else None
            if acct:
                payload["fields"]["assignee"] = {"accountId": acct}

        resp = jira.create_issue(payload)
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        if resp.status_code == 201:
            body = resp.json()
            key = body["key"]
            url = f"{jira.base}/browse/{key}"
            row["Jira Key"] = key
            row["Jira URL"] = url
            jc.write_csv(csv_path, rows)     # save after each create
            created += 1
            print(f"  OK  row {row['#']} -> {key}")
            jc.append_log(str(csv_path), {
                "timestamp": ts, "source_id": row["#"], "result": "created",
                "issue_id": body["id"], "issue_key": key, "url": url,
                "verified": "", "error": ""})
        else:
            err = resp.text[:300]
            failed.append((row["#"], resp.status_code, err))
            print(f"  FAIL row {row['#']}: HTTP {resp.status_code} {err[:160]}")
            jc.append_log(str(csv_path), {
                "timestamp": ts, "source_id": row["#"], "result": "failed",
                "issue_id": "", "issue_key": "", "url": "", "verified": "",
                "error": f"HTTP {resp.status_code}: {err}"})

    print(f"\nDone. created={created} failed={len(failed)} "
          f"inconsistent={len(inconsistent)}")
    return {"created": created, "failed": len(failed),
            "inconsistent": len(inconsistent)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_push.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add jira_sync.py tests/test_push.py
git commit -m "feat: jira_sync push — create-guard, create, write Key+URL back"
```

---

## Task 6: `jira_sync.py` — pull subcommand

**Files:**
- Modify: `jira_sync.py` (append `run_pull`)
- Test: `tests/test_pull.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_pull.py`:
```python
import jira_sync
import jira_common as jc


def test_pull_updates_columns_from_issue(tmp_path):
    src = {c: "" for c in jc.COLUMNS}
    src.update({"#": "1", "Opportunity": "OLD", "Description": "old",
                "Division": "OLD", "AI-fit": "OLD", "Key people": "OLD",
                "Systems": "OLD", "Themes": "OLD", "Summary": "OLD",
                "Jira Key": "ABC-1", "Jira URL": "https://x/browse/ABC-1"})
    csv_path = tmp_path / "d.csv"
    jc.write_csv(csv_path, [src])

    # An issue whose description carries a fresh context block.
    fresh = {"Division": "NEWDIV", "AI-fit": "Medium", "Key people": "NewPerson",
             "Systems": "NewSys", "Themes": "NewTheme", "Summary": "NewSum"}
    doc = jc.markdown_to_adf("## New body\n\n- point")
    doc["content"].extend(jc.build_context_block(fresh))

    class FakeJira:
        def get_issue(self, key):
            assert key == "ABC-1"
            return {"fields": {"summary": "NEW TITLE", "description": doc}}

    result = jira_sync.run_pull(FakeJira(), csv_path, dry_run=False, verbose=False)
    assert result["updated"] == 1
    row = jc.read_csv(csv_path)[0]
    assert row["Opportunity"] == "NEW TITLE"
    assert row["Division"] == "NEWDIV"
    assert row["Summary"] == "NewSum"
    assert "New body" in row["Description"]
    assert row["Jira Key"] == "ABC-1"          # link columns untouched


def test_pull_skips_rows_without_url(tmp_path):
    src = {c: "" for c in jc.COLUMNS}
    src.update({"#": "1", "Opportunity": "keep"})
    csv_path = tmp_path / "d.csv"
    jc.write_csv(csv_path, [src])

    class FakeJira:
        def get_issue(self, key):
            raise AssertionError("should not be called")

    result = jira_sync.run_pull(FakeJira(), csv_path, dry_run=False, verbose=False)
    assert result["updated"] == 0
    assert jc.read_csv(csv_path)[0]["Opportunity"] == "keep"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_pull.py -v`
Expected: FAIL — `AttributeError: module 'jira_sync' has no attribute 'run_pull'`.

- [ ] **Step 3: Append `run_pull` to `jira_sync.py`**

```python
def _issue_key(row):
    key = row.get("Jira Key", "").strip()
    if key:
        return key
    url = row.get("Jira URL", "").strip()
    return url.rstrip("/").split("/")[-1] if url else ""


def run_pull(jira, csv_path, dry_run, verbose):
    rows = jc.read_csv(csv_path)
    updated, failed = 0, []
    for row in rows:
        if not row.get("Jira URL", "").strip():
            continue                              # nothing linked to pull
        key = _issue_key(row)
        issue = jira.get_issue(key)
        if not issue:
            failed.append(key)
            print(f"  FAIL row {row['#']}: could not fetch {key}")
            continue

        fields = issue["fields"]
        doc = fields.get("description") or {"type": "doc", "version": 1,
                                            "content": []}
        ctx = jc.parse_context_block(doc)
        new_vals = {
            "Opportunity": fields.get("summary", row["Opportunity"]),
            "Description": jc.adf_to_markdown(doc),
        }
        for k in jc.CONTEXT_KEYS:
            if k in ctx:
                new_vals[k] = ctx[k]

        changes = {k: v for k, v in new_vals.items() if row.get(k, "") != v}
        if changes:
            updated += 1
            if verbose or dry_run:
                for k, v in changes.items():
                    print(f"  row {row['#']} {k}: {row.get(k,'')!r} -> {v!r}")
            if not dry_run:
                row.update(new_vals)

    if not dry_run:
        jc.write_csv(csv_path, rows)
    print(f"\nDone. updated={updated} failed={len(failed)}"
          f"{' (dry-run, no write)' if dry_run else ''}")
    return {"updated": updated, "failed": len(failed)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_pull.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add jira_sync.py tests/test_pull.py
git commit -m "feat: jira_sync pull — refresh content columns from linked issues"
```

---

## Task 7: `jira_sync.py` — CLI wiring

**Files:**
- Modify: `jira_sync.py` (append `main`)

- [ ] **Step 1: Add argparse subcommands and `main`**

```python
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_push = sub.add_parser("push", help="create Jira issues for blank rows")
    p_pull = sub.add_parser("pull", help="refresh columns from linked issues")
    for p in (p_push, p_pull):
        p.add_argument("--csv", default=DEFAULT_CSV)
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("-v", "--verbose", action="store_true")
        p.add_argument("--ca-bundle", metavar="PATH")
    p_push.add_argument("--assign", action="store_true",
                        help="set first Key person as assignee when unambiguous")
    p_push.add_argument("--verify", action="store_true",
                        help="GET each created issue back to confirm it exists")
    args = parser.parse_args()

    jc.load_dotenv(".env")
    if args.ca_bundle:
        os.environ["REQUESTS_CA_BUNDLE"] = args.ca_bundle

    project_key = os.environ.get("JIRA_PROJECT_KEY", "PROJ")
    issue_type = os.environ.get("JIRA_ISSUE_TYPE", "Story")

    if args.dry_run and args.cmd == "push":
        rows = jc.read_csv(args.csv)
        eligible, linked, inconsistent = classify_push(rows)
        print(f"DRY-RUN push: {len(eligible)} would be created, "
              f"{len(linked)} linked, {len(inconsistent)} inconsistent")
        for r in eligible:
            payload = {"summary": r["Opportunity"][:255],
                       "labels": jc.build_labels(r)}
            print(f"  row {r['#']}: {payload['summary']}  "
                  f"labels={payload['labels']}")
        for r in inconsistent:
            print(f"  WARNING row {r['#']}: inconsistent Key/URL; not pushed")
        return 0

    if not os.environ.get("JIRA_PROJECT_KEY"):
        sys.exit('JIRA_PROJECT_KEY not set (env or .env).')

    jira = jc.connect_and_preflight(project_key, issue_type)
    if args.cmd == "push":
        res = run_push(jira, args.csv, project_key, issue_type,
                       assign=args.assign, verify=args.verify,
                       verbose=args.verbose)
        return 1 if res["failed"] else 0
    res = run_pull(jira, args.csv, dry_run=args.dry_run, verbose=args.verbose)
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke-test the CLI wiring offline**

Run: `python3 jira_sync.py push --dry-run --csv seed-template.csv`
Expected: `DRY-RUN push: 0 would be created, 0 linked, 0 inconsistent` (no network, no crash).

Run: `python3 jira_sync.py --help` and `python3 jira_sync.py push --help`
Expected: subcommands and flags listed, exit 0.

- [ ] **Step 3: Run the full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: PASS (all tests).

- [ ] **Step 4: Commit**

```bash
git add jira_sync.py
git commit -m "feat: jira_sync CLI — push/pull subcommands, dry-run, preflight"
```

---

## Task 8: `regenerate_html.py` — Playwright regeneration

**Files:**
- Create: `regenerate_html.py`

- [ ] **Step 1: Ensure Playwright's Chromium is installed**

Run: `python3 -m playwright install chromium`
Expected: Chromium downloads (or "is already installed").

- [ ] **Step 2: Discover the app's import + save controls**

Open the app in the in-app browser to read the real DOM (do NOT guess selectors):
```
Use mcp__Claude_Browser__preview_start with url = file:///Users/scotty/dev/scryptid/insignia/0x_Themes/jira-viewer/Insignia AI Strategy Map - Jira linked.html
Then mcp__Claude_Browser__read_page (filter: interactive) to list controls.
Navigate to the Division-stories Data tab; find the CSV import <input type=file>
and the "Save as standalone HTML" / "Download" button; record their accessible
names / refs.
```
Write the discovered selectors into the constants block in Step 3 (replace the
`# DISCOVERED:` comments). If the import is a hidden `<input type=file>`, Playwright's
`set_input_files` targets it directly even when visually hidden.

- [ ] **Step 3: Write the regenerator**

Create `regenerate_html.py`:
```python
#!/usr/bin/env python3
"""Regenerate the standalone HTML from the CSV by driving the app's own
CSV-import + "Save as standalone HTML" in headless Chromium.

    python regenerate_html.py                     # defaults below
    python regenerate_html.py --headed            # watch it run
    python regenerate_html.py --csv X --html Y --out Z

Requires: pip install playwright && python -m playwright install chromium
"""

import argparse
import pathlib
import sys

from playwright.sync_api import sync_playwright

DEFAULT_CSV = "insignia-division-stories-jira-linked.csv"
DEFAULT_HTML = "Insignia AI Strategy Map - Jira linked.html"
DEFAULT_OUT = "Insignia AI Strategy Map - regenerated.html"

# DISCOVERED in Task 8 Step 2 — replace with the real selectors:
DATA_TAB = "Data"                    # e.g. role=tab name="Data"
IMPORT_FILE_INPUT = 'input[type="file"]'
SAVE_BUTTON = "Save as standalone HTML"


def regenerate(csv_path, html_path, out_path, headed):
    csv_path = pathlib.Path(csv_path).resolve()
    html_path = pathlib.Path(html_path).resolve()
    out_path = pathlib.Path(out_path).resolve()
    if not csv_path.exists() or not html_path.exists():
        sys.exit(f"Missing input: {csv_path if not csv_path.exists() else html_path}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        page = browser.new_page(accept_downloads=True)
        page.goto(html_path.as_uri())
        page.wait_for_load_state("networkidle")

        # Open the Division-stories Data tab (selector from Step 2).
        page.get_by_role("tab", name=DATA_TAB).click()

        # Load the CSV through the app's import control.
        page.set_input_files(IMPORT_FILE_INPUT, str(csv_path))
        page.wait_for_timeout(1000)   # let the app parse + re-render

        # Trigger the app's own "Save as standalone HTML" and capture download.
        with page.expect_download() as dl_info:
            page.get_by_role("button", name=SAVE_BUTTON).click()
        dl_info.value.save_as(str(out_path))
        browser.close()

    size = out_path.stat().st_size if out_path.exists() else 0
    if size < 100_000:
        sys.exit(f"ERROR: output {out_path} is only {size} bytes — "
                 "regeneration likely failed (check selectors).")
    print(f"Regenerated {out_path} ({size:,} bytes)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--html", default=DEFAULT_HTML)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    regenerate(args.csv, args.html, args.out, args.headed)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run it against the real files (smoke test)**

Run: `python3 regenerate_html.py --headed`
Expected: a browser opens, the CSV loads, a download is captured, and the script
prints `Regenerated ... (N bytes)` with N > 100000. Open the output and confirm the
new data shows.

If a selector is wrong, the script exits with the size guard or a Playwright timeout
naming the control it couldn't find — fix the constant from Step 2 and re-run.

- [ ] **Step 5: Commit**

```bash
git add regenerate_html.py
git commit -m "feat: regenerate_html.py — Playwright import + save-as-standalone"
```

---

## Task 9: README, parity check, retire old script

**Files:**
- Create: `README.md`
- Remove: `upload_to_jira.py` (only after parity confirmed)

- [ ] **Step 1: Write `README.md`**

````markdown
# Jira ⇄ CSV ⇄ Standalone-HTML Toolkit

The CSV `insignia-division-stories-jira-linked.csv` is the single source of truth.
Whether a row's `Jira Key` / `Jira URL` columns are filled decides what each script does.

## Setup
```bash
pip install requests playwright
python -m playwright install chromium      # for regenerate_html.py only
cp .env.example .env                        # then fill in JIRA_* values
```

## push — create Jira issues for blank rows
Rows with **both** `Jira Key` and `Jira URL` blank become Jira Stories
(title = `Opportunity`); the created key + URL are written back into the CSV.
Rows already linked are skipped; a row with only one of the two filled is reported
and skipped (never duplicated).
```bash
python jira_sync.py push --dry-run          # preview, no API calls
python jira_sync.py push                     # create + write back
python jira_sync.py push --assign --verify   # set assignee, verify creation
```

## pull — refresh columns from linked issues
Rows with a `Jira URL` are refreshed from Jira: `Opportunity` from the title,
`Description` from the issue body, and Division/AI-fit/Key people/Systems/Themes/
Summary from the description's context block.
```bash
python jira_sync.py pull --dry-run           # show per-cell diff
python jira_sync.py pull                      # apply
```

## regenerate — rebuild the standalone HTML from the CSV
Drives the app's own CSV import + "Save as standalone HTML" in headless Chromium.
The output is the app's read-only share snapshot.
```bash
python regenerate_html.py
```
````

- [ ] **Step 2: Confirm parity, then retire `upload_to_jira.py`**

Compare a `push --dry-run` payload against the old script's mapping to confirm the
new toolkit covers it (title, description, labels). Once confirmed:
```bash
git rm upload_to_jira.py
```

- [ ] **Step 3: Full test suite + final commit**

Run: `python3 -m pytest tests/ -v`
Expected: PASS (all).
```bash
git add README.md
git commit -m "docs: toolkit README; retire upload_to_jira.py (superseded by jira_sync)"
```

---

## Self-Review Notes

- **Spec coverage:** push (Task 5), create-guard both-blank (Task 5 `classify_push`),
  write-back (Task 5), pull (Task 6), context-block round-trip (Task 3), markdown⇄ADF
  (Task 2), CSV BOM/QUOTE_ALL fidelity (Task 1), Jira client + preflight (Task 4),
  regenerate via Playwright (Task 8), seed-template/.env/.gitignore (Task 0),
  README (Task 9). All spec sections mapped.
- **Read-only regenerate assumption** and **Division-stories-only scope** were approved
  by the user; documented in README (Task 9).
- **Type/name consistency:** `jc.COLUMNS`, `jc.CONTEXT_KEYS`, `build_description`,
  `build_context_block`/`parse_context_block`, `markdown_to_adf`/`adf_to_markdown`,
  `classify_push`/`run_push`/`run_pull`, `connect_and_preflight` used consistently
  across tasks.
